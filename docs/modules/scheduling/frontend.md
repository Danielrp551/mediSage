# Módulo `scheduling` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-06-06
> **Audiencia**: developer implementando `frontend/src/.../scheduling/`.
> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), y como moldes de referencia el frontend de [`../crm/frontend.md`](../crm/frontend.md) (catálogos + matriz + history/timeline) y [`../staff/frontend.md`](../staff/frontend.md) (la **grilla semanal** `DoctorAvailabilityTab`, el patrón `/me` reusable, fetch-token) y [`../clinic/frontend.md`](../clinic/frontend.md) (entidad con sub-recursos + TZ del branch + horas `time` que NO pasan por `new Date()`).

> **Contrato autoritativo**: este doc respeta la spec compartida de scheduling (consolidada en [`README.md`](./README.md)) — nombres de entidades, campos, endpoints, permisos, códigos de error y **fases** son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, manda la spec.

> **Modelo confirmado** (ADR-006 + ADR-007): **no hay tabla de slots** — la unidad persistida es `Appointment`; la disponibilidad se **calcula on-the-fly** (`compute_available_slots`) combinando `staff.DoctorAvailability` (bloques concretos por fecha), `clinic.OfficeOperatingHours`/`OfficeClosure`/`Branch.timezone`, `catalog.Product.duration_min`/`min_hours_to_cancel` y las citas activas del doctor. **Matriz de transiciones configurable** (espeja crm/ADR-008) modela las aristas permitidas del grafo de estados de cita; los side-effects (attend→promote, cancel→min_hours, reschedule→nueva cita) viven en el SERVICE. **Doctor `active=false` está EXCLUIDO de nuevas reservas** (decisión #3: en scheduling `active` SÍ es gate de agendar, diverge de staff). Las 3 columnas forward de crm hacia scheduling (`related_appointment_id`) ya existen del lado crm; aquí `Appointment` referencia `person_id`/`doctor_id`/`office_id`/`branch_id`/`product_id` con FKs reales.

> **Convenciones heredadas de catalog/clinic/staff/crm shipped** (el lector debe tenerlas presentes desde ya):
> 1. **Verbos HTTP**: los updates completos usan **`PUT`** (no `PATCH`). Los shortcuts de lifecycle son `POST` sub-recursos (`/confirm`, `/cancel`, …).
> 2. **Dropdowns**: los endpoints de "lista plana de activos" se llaman **`/active`** y devuelven **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`; no se lee `.data`).
> 3. **Detalle de cita = drawer/página con tabs** (control de estado + timeline + reschedule/cancel) — patrón "entidad con sub-recursos" de Office/Doctor/Person. La **lista** de citas y la **grilla** abren ese detalle.
> 4. **Lección hotfix `cd10c78` de staff** (crítica: `Appointment` tiene muchos denormalizados): `defaultSort`, columnas `isSortable` y `searchFields` **SOLO** sobre columnas reales de `ALLOWED_FIELDS`. Ordenar/filtrar server-side por una columna denormalizada (`person_name`, `doctor_name`, `office_name`, `status_name`) devuelve **400 → error boundary del RSC**. El `defaultSort` del client y el `sorting` del prefetch RSC **DEBEN coincidir** (si difieren, el primer paint pide una página y el client otra → flash + refetch). Filtrar por estado/doctor/sede/fecha/producto = **deep-link traducido a `FilterCondition` sobre columnas reales** (`status_id`, `doctor_id`, `office_id`/`branch_id`, `scheduled_for`, `product_id` — todas columnas reales del `appointment`), NO order-by de denormalizados.
> 5. **TZ** (lección recurrente de staff/crm): **cualquier `new Date()`/now que afecte el render** (resaltar "hoy" en la grilla, el default de fecha del wizard/grilla, agrupar el timeline por día) = **client-only** (`useState<T | null>(null)` + `useEffect`). El SSR corre en UTC y desfasa el día en TZ negativas (Lima `-05:00`). `scheduled_for`/`cancelled_at`/`*_at` son `timestamptz` ISO 8601 con offset → `lib/utils/date.ts`. Las fechas-puro (`from_date`/`to_date`/columna del día) viajan `"YYYY-MM-DD"` y se parsean como **local** (`new Date(\`${d}T00:00:00\`)`), nunca como UTC.

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── scheduling.types.ts                 ← AppointmentStatus*, AppointmentStatusTransition*,
│                                              Appointment*, AppointmentStatusHistory*,
│                                              AppointmentChangeLog*, AvailabilitySlot/Request/Response,
│                                              CalendarResponse, enums (AppointmentSource)
│                                              (reusa UserAuditInfo de audit.types; DoctorOption/BranchOption/
│                                               PersonOption/ProductOption de staff/clinic/crm/catalog)
├── lib/
│   ├── schemas/
│   │   ├── appointment-status.schema.ts     ← statusCreate/Update (superRefine is_initial único hint;
│   │   │                                       sin invariante cross-fila) + transitionTargetsSchema
│   │   ├── appointment.schema.ts            ← bookingWizardSchema (4 pasos), appointmentUpdate (no-estado),
│   │   │                                       transitionSchema, cancelSchema, rescheduleSchema, availabilityRequestSchema
│   │   └── (reusa transitionTargetsSchema)
│   └── constants/
│       ├── endpoints.ts                     ← EXTEND con bloque SCHEDULING (APPOINTMENT_STATUSES,
│       │                                       AVAILABILITY, APPOINTMENTS con nested transitions/shortcuts,
│       │                                       ME_SCHEDULING)
│       ├── navigation.ts                    ← EXTEND con grupo 'SCHEDULING' (MENU-SCHEDULING)
│       ├── calendar.ts                      ← REUSA el de staff (GRID_*; timeToMinutes/minutesToTime;
│       │                                       WEEKDAY_SHORT) — extender con helpers de scheduling si falta
│       └── scheduling.ts                    ← NUEVO: APPOINTMENT_SOURCE_META (label ES por origen),
│                                              statusColor helper (badge desde el catálogo), CHECK_SLOT_REASON_LABELS
├── actions/
│   ├── appointment-status.actions.ts        ← CRUD + active + getTransitions/setTransitions
│   ├── availability.actions.ts              ← computeAvailability + checkSlot (lecturas; sin revalidateTag)
│   └── appointment.actions.ts               ← list/get/create(book)/update + calendar + transition + shortcuts
│                                              (confirm/check-in/start/attend/no-show/cancel/reschedule)
│                                              + history/changelog + listMyAppointments/getMyCalendar
└── app/(main)/scheduling/
    ├── estados/
    │   ├── page.tsx                         ← catálogo AppointmentStatus + editor de matriz
    │   └── _components/
    │       ├── AppointmentStatusesClient.tsx
    │       ├── AppointmentStatusDrawer.tsx
    │       └── StatusMatrixEditor.tsx       ← multiselect "transiciones permitidas hacia…" (reusa el de crm)
    ├── citas/
    │   ├── page.tsx                         ← LISTA de citas (filtros chip + deep-link)
    │   └── _components/
    │       ├── AppointmentsClient.tsx       ← tabla + botón "Nueva cita"
    │       ├── BookingWizardDrawer.tsx      ← wizard 4 pasos (Paciente→Producto+Doctor→Slot→Confirmar)
    │       │   ├── WizardStepPerson.tsx
    │       │   ├── WizardStepServiceDoctor.tsx
    │       │   ├── WizardStepSlot.tsx       ← llama computeAvailability + render de slots
    │       │   └── WizardStepConfirm.tsx
    │       └── AppointmentDetailDrawer.tsx  ← detalle: StatusControl + Timeline + reschedule/cancel
    │           ├── AppointmentStatusControl.tsx  ← shortcuts gated por matriz
    │           ├── AppointmentTimeline.tsx       ← status_history + change_log entrelazados
    │           ├── RescheduleDialog.tsx          ← re-corre el wizard de slot, EXCLUYE la cita vieja
    │           └── CancelDialog.tsx              ← reason + manejo de CANCEL_TOO_LATE/override
    ├── calendario/
    │   ├── page.tsx                         ← GRILLA semanal (citas + slots libres overlay)
    │   └── _components/
    │       ├── CalendarClient.tsx           ← toolbar (doctor/sede/semana) + monta <ScheduleGrid>
    │       └── ScheduleGrid.tsx             ← grilla bespoke: bloques de cita + overlay de slots libres
    └── mi-agenda/
        ├── page.tsx                         ← "Mi agenda" del doctor (MY_APPOINTMENTS_READ)
        └── _components/MyAgendaClient.tsx   ← reusa <ScheduleGrid> en modo self read (+ tabla "mis citas")
```

> **`calendario`/`mi-agenda` reusan `<ScheduleGrid>`, no duplican** (mismo criterio que `MyAvailabilityClient` monta `<AvailabilityGrid>` en staff): `ScheduleGrid` es genérica respecto al "de quién es la agenda" y al modo (admin vs self read-only); sólo cambian las actions que llama (`getCalendar` vs `getMyCalendar`) y el gating. Ver [ScheduleGrid](#schedulegridtsx--la-grilla-semanal).

> **`BookingWizardDrawer` se reusa desde lista Y grilla**: el botón "Nueva cita" de `AppointmentsClient` lo abre vacío; un click en un **slot libre** del calendario lo abre **prefilled** (doctor/office/product/scheduled_for ya elegidos, salta directo al paso Confirmar). Mismo componente, distinto estado inicial. Ver [WizardStepSlot](#bookingwizarddrawertsx--el-wizard-de-reserva).

> **Por qué no hay `scheduling/layout.tsx`**: igual que catalog/clinic/staff/crm — `estados`, `citas`, `calendario`, `mi-agenda` son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El detalle de la cita es un **drawer** (no una sub-ruta), montado desde la lista/grilla.

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas.

> **Sobre `loading.tsx`**: catalog/clinic/staff/crm shipped **no** incluyeron `loading.tsx` (el `DataTable` ya renderiza su skeleton vía `isLoading`; la grilla tiene su propio skeleton). `scheduling` sigue ese criterio. No se crean `loading.tsx`.

## Tipos TS — `types/scheduling.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic)). Importable desde server actions y client components. **Reusa** `UserAuditInfo` de `audit.types.ts`; **reusa** `DoctorOption` (staff), `BranchOption`/`OfficeOption` (clinic), `PersonOption` (crm), `ProductOption` (catalog) para los dropdowns del wizard — no se redefinen.

```ts
import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de scheduling/enums.py; valores EXACTOS) ─────────

// Origen de la cita (código guardado en appointment.source). El bot escribe "bot";
// el panel del asesor "advisor"; el admin "admin"; import/api para back-office.
export type AppointmentSource = "bot" | "advisor" | "admin" | "import" | "api";

export const APPOINTMENT_SOURCES: readonly AppointmentSource[] = [
  "bot",
  "advisor",
  "admin",
  "import",
  "api",
] as const;

// Razón de no-disponibilidad devuelta por POST /availability/check-slot
// (código en inglés; el front lo traduce con CHECK_SLOT_REASON_LABELS).
export type CheckSlotReason =
  | "NO_AVAILABILITY_BLOCK"
  | "OFFICE_CLOSED"
  | "SLOT_TAKEN"
  | "OFFICE_SLOT_TAKEN"
  | "DOCTOR_INACTIVE"
  | "DOCTOR_NOT_APT_FOR_VERTICAL"
  | "OFFICE_NOT_APT_FOR_VERTICAL"
  | "DOCTOR_NOT_IN_BRANCH"
  | "OFFICE_NOT_IN_BRANCH";

// ── AppointmentStatus (catálogo configurable) ───────────
// Espeja crm.LeadStatus pero con flags propios de citas (sin is_won).

export interface AppointmentStatusItem {
  id: string;
  code: string; // MAYÚSCULAS, ej. "SCHEDULED" (espeja crm.LeadStatus; sin pattern restrictivo)
  name: string;
  description: string | null;
  color: string | null; // hex para badges
  is_initial: boolean; // EXACTAMENTE uno true por catálogo (SCHEDULED)
  is_final: boolean; // terminal (ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED)
  is_active_attention: boolean; // 0..N "en atención ahora" (IN_PROGRESS)
  display_order: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Para dropdowns y el StatusControl (lista cruda en /active).
export interface AppointmentStatusOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_initial: boolean;
  is_final: boolean;
  is_active_attention: boolean;
}

// Subset para badges en listados/detalle/timeline/grilla (color + name).
export interface AppointmentStatusSummary {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
  is_active_attention: boolean;
}

export interface AppointmentStatusCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_active_attention?: boolean;
  display_order?: number;
}

export interface AppointmentStatusUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_active_attention?: boolean;
  display_order?: number;
  active?: boolean;
}

// ── AppointmentStatusTransition (matriz, ADR-008) ───────
// La fila cruda de la matriz; el front normalmente consume la forma resuelta
// TransitionTargets. SIN soft-delete (deshabilitar arista = active=false / DELETE).

export interface AppointmentStatusTransitionItem {
  id: string;
  from_status_id: string;
  to_status_id: string;
  active: boolean;
  created_on: string;
  updated_on: string;
}

// Respuesta de GET /appointment-statuses/{id}/transitions: los estados a los que
// el estado {id} PUEDE ir (aristas de salida ya resueltas a Options).
export interface TransitionTargets {
  from_id: string;
  to: AppointmentStatusOption[];
}

// Body de PUT /appointment-statuses/{id}/transitions — REEMPLAZA aristas de salida.
export interface TransitionTargetsReplacePayload {
  to_ids: string[];
}

// ── Availability (cálculo on-the-fly; NO persiste) ──────

// Body de POST /availability/compute.
export interface AvailabilityRequest {
  doctor_id: string;
  product_id: string;
  branch_id?: string | null; // opcional: acota a una sede
  office_id?: string | null; // opcional: acota a un consultorio
  from_date: string; // "YYYY-MM-DD"
  to_date: string; // "YYYY-MM-DD"
}

// Un slot libre computado. starts_at/ends_at son timestamptz UTC (ISO 8601 con
// offset); el render los formatea client-only en la TZ del navegador/branch.
export interface AvailabilitySlot {
  starts_at: string; // ISO 8601 UTC
  ends_at: string; // ISO 8601 UTC (= starts_at + duration_min)
  doctor_id: string;
  doctor_name: string; // denormalizado para mostrar sin join
  office_id: string;
  office_name: string;
  branch_id: string;
  branch_name: string;
}

export interface AvailabilityResponse {
  slots: AvailabilitySlot[];
  duration_min: number; // duración del producto (o fallback doctor.slot_duration_min)
  doctor_slot_duration_min: number; // grano del doctor (para alinear la grilla)
}

// Body de POST /availability/check-slot (revalida UN slot puntual antes de book).
export interface CheckSlotRequest {
  doctor_id: string;
  office_id: string;
  product_id: string;
  scheduled_for: string; // ISO 8601 UTC del inicio
}

export interface CheckSlotResponse {
  available: boolean;
  reason?: CheckSlotReason | null; // presente sólo si available=false
}

// ── Appointment (unidad persistida del calendario) ──────

// Fila de listado. El backend DENORMALIZA (batch maps, sin N+1) person/doctor/
// office/branch/product/status. NINGUNO de los *_name está en ALLOWED_FIELDS →
// NO son server-sortable/filterable (lección cd10c78). El filtro del listado va
// sobre las columnas REALES (status_id/doctor_id/office_id/branch_id/scheduled_for/
// product_id), NO sobre los *_name.
export interface AppointmentItem {
  id: string;
  person_id: string;
  person_name: string; // denormalizado (full_name de la persona)
  doctor_id: string;
  doctor_name: string; // denormalizado
  office_id: string;
  office_name: string; // denormalizado
  branch_id: string;
  branch_name: string; // denormalizado (DENORM de office.branch_id)
  product_id: string;
  product_name: string; // denormalizado
  scheduled_for: string; // timestamptz UTC (inicio)
  duration_min: number; // copiado de product al agendar
  status: AppointmentStatusSummary; // estado actual (badge color)
  source: AppointmentSource;
  previous_appointment_id: string | null; // cadena de reagendamiento
  confirmed_at: string | null;
  attended_at: string | null;
  cancelled_at: string | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle: identidad completa + history + changelog embebidos (un solo GET puebla
// el drawer de detalle — ver GET /appointments/{id} en backend.md).
export interface AppointmentDetail {
  id: string;
  person_id: string;
  person_name: string;
  doctor_id: string;
  doctor_name: string;
  office_id: string;
  office_name: string;
  branch_id: string;
  branch_name: string;
  product_id: string;
  product_name: string;
  scheduled_for: string;
  duration_min: number;
  status: AppointmentStatusSummary;
  source: AppointmentSource;
  previous_appointment_id: string | null;
  notes: string | null;
  cancellation_reason: string | null;
  cancelled_at: string | null;
  cancelled_by: string | null;
  cancelled_by_user: UserAuditInfo | null;
  confirmed_at: string | null;
  attended_at: string | null;
  // Sub-recursos embebidos (no inflan listados; sólo el detalle los trae).
  status_history: AppointmentStatusHistoryItem[];
  change_log: AppointmentChangeLogItem[];
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Body de POST /appointments (create/book) — lo arma el wizard al confirmar.
export interface AppointmentCreatePayload {
  person_id: string;
  doctor_id: string;
  office_id: string;
  branch_id: string;
  product_id: string;
  scheduled_for: string; // ISO 8601 UTC del slot elegido
  source?: AppointmentSource; // "advisor"/"admin" desde la UI (default por rol)
  notes?: string | null;
  // duration_min lo COPIA el backend de product.duration_min (fallback doctor.slot_duration_min);
  // el front NO lo manda — la spec dice "copiado al agendar".
}

// Body de PUT /appointments/{id} — SOLO columnas no-estado (van al change_log).
// scheduled_for NO se edita aquí (usa /reschedule); status_id NO se edita aquí
// (usa /transition o shortcuts). El backend rechaza esos campos.
export interface AppointmentUpdatePayload {
  doctor_id?: string;
  office_id?: string;
  branch_id?: string;
  product_id?: string;
  notes?: string | null;
  reason?: string | null; // se escribe en change_log.reason
}

// ── AppointmentStatusHistory (timeline de estado) ───────
// SIN soft-delete (audit trail honesto). from_status_id null al crear.

export interface AppointmentStatusHistoryItem {
  id: string;
  appointment_id: string;
  from_status: AppointmentStatusSummary | null; // null al crear (NULL→initial)
  to_status: AppointmentStatusSummary;
  changed_at: string; // timestamptz ISO 8601
  changed_by: string | null; // null = bot/sistema
  changed_by_user: UserAuditInfo | null; // resuelto batch; null si SYSTEM/hard-deleted
  reason: string | null;
}

// ── AppointmentChangeLog (cambios in-place de columnas no-estado) ─
// SIN soft-delete. previous_value/new_value serializados (UUID/ISO8601/string).

export interface AppointmentChangeLogItem {
  id: string;
  appointment_id: string;
  field_name: string; // "doctor_id"/"office_id"/"notes"/…
  previous_value: string | null;
  new_value: string | null;
  changed_at: string;
  changed_by: string | null;
  changed_by_user: UserAuditInfo | null;
  reason: string | null;
}

// ── Calendar (citas + slots libres en rango, para la grilla) ────
// Respuesta de GET /appointments/calendar (y /me/calendar). Combina las citas
// del rango con los slots libres ya computados, en una sola payload.
export interface CalendarResponse {
  appointments: AppointmentItem[];
  free_slots: AvailabilitySlot[]; // overlay clickeable (vacío si no se pidió doctor/producto)
  from_date: string; // "YYYY-MM-DD" (eco del request)
  to_date: string;
}

// ── Lifecycle payloads (transición + shortcuts) ─────────

export interface AppointmentTransitionPayload {
  to_status_id: string;
  reason?: string | null;
}

export interface AppointmentCancelPayload {
  cancellation_reason: string; // obligatorio
  // override = lo decide el backend por permiso APPOINTMENTS_CANCEL_OVERRIDE; el
  // front NO manda un flag — si el actor tiene el permiso, el backend salta el gate.
}

// Reagendar: revalida invariantes 1-8 sobre la NUEVA cita, excluye la vieja del
// conflicto, marca la vieja RESCHEDULED y crea la nueva en la misma transacción.
export interface AppointmentReschedulePayload {
  doctor_id: string;
  office_id: string;
  branch_id: string;
  product_id: string;
  scheduled_for: string; // ISO 8601 UTC del NUEVO slot
  reason?: string | null;
  notes?: string | null;
}

// Fila de /me/appointments/list (citas del doctor logueado). Mismo perfil que
// AppointmentItem recortado a lo que el doctor necesita.
export interface MyAppointmentItem {
  id: string;
  person_name: string;
  office_name: string;
  product_name: string;
  scheduled_for: string;
  duration_min: number;
  status: AppointmentStatusSummary;
}
```

> **Nota sobre las clases de tiempo** (igual que clinic/staff/crm):
> - `AvailabilityRequest.from_date`/`to_date`, `CalendarResponse.from_date`/`to_date` → fechas-puro `"YYYY-MM-DD"` (date sin TZ). Se componen del rango de la semana visible y se parsean como **local** (`new Date(\`${d}T00:00:00\`)`), nunca como UTC.
> - `scheduled_for`, `starts_at`/`ends_at`, `confirmed_at`/`attended_at`/`cancelled_at`/`changed_at`/`created_on`/`updated_on` → `timestamptz` ISO 8601 con offset → `lib/utils/date.ts` (`formatDate` / relativa) o, en la grilla, posicionados por minutos-desde-medianoche **en la TZ del branch** (ver [ScheduleGrid](#schedulegridtsx--la-grilla-semanal)).
> - El catálogo `AppointmentStatus` **no** tiene campos de hora — sólo `display_order` y flags.

> **Por qué `AppointmentItem` denormaliza tanto** (`person_name`, `doctor_name`, `office_name`, `branch_name`, `product_name`, `status`): el listado/grilla no quiere 6 joins por fila. El backend los resuelve con batch maps (sin N+1). **Implicancia crítica**: ninguno de los `*_name` está en `ALLOWED_FIELDS` → **no** son server-sortable ni server-filterable (lección `cd10c78`). El filtro va sobre las columnas **reales** (`status_id`/`doctor_id`/`office_id`/`branch_id`/`scheduled_for`/`product_id`). El `defaultSort` del listado usa `scheduled_for` (columna real) y **debe coincidir** con el prefetch RSC.

## Zod schemas

> **Regla del template** ([frontend/CLAUDE.md](../../../frontend/CLAUDE.md)): los Zod viven en `src/lib/schemas/` y los importan **tanto el form (cliente) como el Server Action (server)** → drift imposible. Los mensajes visibles van en **español**; los `path`/nombres de campo en inglés.

### `lib/schemas/appointment-status.schema.ts`

Catálogo + matriz. Espeja crm `lead-status.schema.ts` **sin `is_won`** y **con** `is_active_attention`. No hay invariante `is_won⟹is_final` (no existe `is_won` aquí). La regla "exactamente un `is_initial` por catálogo" (`MULTIPLE_INITIAL_STATUS`, 400) **no** se valida en Zod (cruza con los demás registros) → error de servidor; la UI lo mitiga avisando al marcar `is_initial` que desmarcará el actual.

```ts
import { z } from "zod";

// code = MAYÚSCULAS (ej. SCHEDULED, NO_SHOW) — espeja crm.LeadStatus (sin pattern restrictivo
// en backend; el front fuerza el casing por consistencia). Inmutable post-create (el update no lo incluye).
const CODE_SLUG_REGEX = /^[A-Z][A-Z0-9_]*$/;
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{6})$/;

const appointmentStatusBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  color: z
    .string()
    .regex(HEX_COLOR_REGEX, "Color hex como #RRGGBB")
    .nullable()
    .optional()
    .or(z.literal("")),
  is_initial: z.boolean().optional().default(false),
  is_final: z.boolean().optional().default(false),
  is_active_attention: z.boolean().optional().default(false),
  display_order: z
    .number({ invalid_type_error: "Número entero" })
    .int("Entero")
    .min(0)
    .default(0),
});

export const appointmentStatusCreateSchema = appointmentStatusBase.extend({
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(40, "Máximo 40 caracteres")
    .regex(CODE_SLUG_REGEX, "Minúsculas, números y guiones bajos (ej. scheduled)"),
});

export const appointmentStatusUpdateSchema = appointmentStatusBase
  .partial()
  .extend({ active: z.boolean().optional() });

// Body de PUT /appointment-statuses/{id}/transitions (reemplaza aristas de salida).
export const transitionTargetsSchema = z.object({
  to_ids: z.array(z.string()),
});

export type AppointmentStatusCreateInput = z.infer<typeof appointmentStatusCreateSchema>;
export type AppointmentStatusUpdateInput = z.infer<typeof appointmentStatusUpdateSchema>;
export type TransitionTargetsInput = z.infer<typeof transitionTargetsSchema>;
```

> **`is_active_attention` no tiene invariante de unicidad en Zod** (la spec dice "0..N"): pueden existir varios estados marcados "en atención"; el seed deja uno (`IN_PROGRESS`), pero el catálogo lo permite múltiple → no hay refine. El `code` lleva el `pattern` slug en el Pydantic **y** en Zod (lección F2 de bots: todo `code`/slug expuesto debe llevar el `pattern` en ambos lados; el QA E2E debe incluir el caso inválido).

### `lib/schemas/appointment.schema.ts`

El **wizard de reserva** (4 pasos), el update no-estado, la transición genérica, cancel y reschedule, y el request de disponibilidad. El wizard valida paso a paso; el schema final (`bookingWizardSchema`) valida el body completo antes de `createAppointment`.

```ts
import { z } from "zod";

// ── Availability request (wizard paso Slot) ─────────────
export const availabilityRequestSchema = z
  .object({
    doctor_id: z.string().min(1, "Elige un doctor"),
    product_id: z.string().min(1, "Elige un servicio/producto"),
    branch_id: z.string().nullable().optional(),
    office_id: z.string().nullable().optional(),
    from_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD"),
    to_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD"),
  })
  .superRefine((data, ctx) => {
    // from_date <= to_date (comparación lexicográfica válida para YYYY-MM-DD).
    if (data.to_date < data.from_date) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["to_date"],
        message: "La fecha final no puede ser anterior a la inicial.",
      });
    }
  });

// ── Booking wizard (4 pasos → body de POST /appointments) ─
// Cada paso valida su slice; el confirm valida el body completo. duration_min NO
// va en el body (lo copia el backend de product.duration_min). source lo pone el
// action según el rol (advisor/admin); el form no lo pide.
export const bookingWizardSchema = z.object({
  // Paso 1 — Paciente.
  person_id: z.string().min(1, "Elige al paciente"),
  // Paso 2 — Producto + Doctor (+ sede/consultorio para acotar el cómputo).
  product_id: z.string().min(1, "Elige el servicio/producto"),
  doctor_id: z.string().min(1, "Elige el doctor"),
  branch_id: z.string().min(1, "Elige la sede"),
  office_id: z.string().min(1, "Elige el consultorio"),
  // Paso 3 — Slot (ISO 8601 con offset; lo setea WizardStepSlot al elegir un slot).
  scheduled_for: z.string().datetime({ offset: true }),
  // Paso 4 — Confirmar.
  notes: z.string().max(5000, "Máximo 5000 caracteres").nullable().optional(),
});

// ── Editar columnas NO-estado (→ change_log) ────────────
export const appointmentUpdateSchema = z
  .object({
    doctor_id: z.string().min(1).optional(),
    office_id: z.string().min(1).optional(),
    branch_id: z.string().min(1).optional(),
    product_id: z.string().min(1).optional(),
    notes: z.string().max(5000).nullable().optional(),
    reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
  })
  // scheduled_for / status_id NO se editan aquí (usa /reschedule y /transition).
  .strict();

// ── Transición genérica (valida matriz en backend) ──────
export const appointmentTransitionSchema = z.object({
  to_status_id: z.string().min(1, "Elige un estado destino"),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

// ── Cancelar ────────────────────────────────────────────
// cancellation_reason obligatorio. El override (saltar min_hours_to_cancel) lo
// decide el backend por permiso APPOINTMENTS_CANCEL_OVERRIDE — no hay flag en Zod.
export const appointmentCancelSchema = z.object({
  cancellation_reason: z.string().min(1, "Indica el motivo de la cancelación").max(255),
});

// ── Reagendar ───────────────────────────────────────────
export const appointmentRescheduleSchema = z.object({
  doctor_id: z.string().min(1, "Elige el doctor"),
  office_id: z.string().min(1, "Elige el consultorio"),
  branch_id: z.string().min(1, "Elige la sede"),
  product_id: z.string().min(1, "Elige el servicio/producto"),
  scheduled_for: z.string().datetime({ offset: true }),
  reason: z.string().max(255).nullable().optional(),
  notes: z.string().max(5000).nullable().optional(),
});

export type AvailabilityRequestInput = z.infer<typeof availabilityRequestSchema>;
export type BookingWizardInput = z.infer<typeof bookingWizardSchema>;
export type AppointmentUpdateInput = z.infer<typeof appointmentUpdateSchema>;
export type AppointmentTransitionInput = z.infer<typeof appointmentTransitionSchema>;
export type AppointmentCancelInput = z.infer<typeof appointmentCancelSchema>;
export type AppointmentRescheduleInput = z.infer<typeof appointmentRescheduleSchema>;
```

> **`scheduled_for` viaja como ISO 8601 con offset** (`z.string().datetime({ offset: true })`): el slot elegido viene de `AvailabilitySlot.starts_at` (ya UTC) → se pasa tal cual. **No** se re-construye con `new Date(...)` en el wizard (el slot YA es un instante absoluto del backend); sólo se serializa el `starts_at` recibido. El **default de fecha** del wizard/grilla (qué semana/día mostrar al abrir) SÍ es `new Date()` → **client-only** (ver [Decisiones TZ](#decisiones-del-frontend-recap)).

> **Lo que Zod NO puede validar** (queda como error de servidor en español, `MessageBar`): los **9 invariantes del create/reschedule** (`OFFICE_NOT_IN_BRANCH`, `OFFICE_NOT_APT_FOR_VERTICAL`, `DOCTOR_NOT_IN_BRANCH`, `DOCTOR_NOT_APT_FOR_VERTICAL`, `SLOT_TAKEN`, `OFFICE_SLOT_TAKEN`, `NO_AVAILABILITY_BLOCK`, `OFFICE_CLOSED`, `CANCEL_TOO_LATE`), más `DOCTOR_INACTIVE` y `APPOINTMENT_TRANSITION_NOT_ALLOWED`. La UI los **mitiga** ofreciendo sólo slots que `compute_available_slots` ya validó (paso Slot) y sólo transiciones que la matriz permite (StatusControl), pero el backend es la fuente de verdad (concurrencia: dos asesores eligen el mismo slot → el 2º recibe `SLOT_TAKEN`).

## Constantes de presentación — `lib/constants/scheduling.ts`

Metadata de origen y helpers de presentación de citas. **Nuevo** (scheduling necesita su propia tabla; el color de los estados viene del catálogo en BD, no de aquí).

```ts
import type { AppointmentSource, CheckSlotReason } from "@/types/scheduling.types";

// Origen de la cita: label ES para badges/columna. El ícono es opcional.
export const APPOINTMENT_SOURCE_META: Record<AppointmentSource, { label: string }> = {
  bot: { label: "Bot" },
  advisor: { label: "Asesor" },
  admin: { label: "Administración" },
  import: { label: "Importación" },
  api: { label: "API" },
};

// Razones de check-slot (POST /availability/check-slot devuelve el code en inglés;
// el front lo muestra en español cuando un slot puntual ya no está libre).
export const CHECK_SLOT_REASON_LABELS: Record<CheckSlotReason, string> = {
  NO_AVAILABILITY_BLOCK: "El doctor no tiene un bloque de disponibilidad en ese horario.",
  OFFICE_CLOSED: "El consultorio está cerrado en ese horario.",
  SLOT_TAKEN: "El doctor ya tiene una cita en ese horario.",
  OFFICE_SLOT_TAKEN: "El consultorio ya está ocupado en ese horario.",
  DOCTOR_INACTIVE: "El doctor está inactivo y no admite nuevas reservas.",
  DOCTOR_NOT_APT_FOR_VERTICAL: "El doctor no atiende esta especialidad.",
  OFFICE_NOT_APT_FOR_VERTICAL: "El consultorio no está habilitado para esta especialidad.",
  DOCTOR_NOT_IN_BRANCH: "El doctor no atiende en esta sede.",
  OFFICE_NOT_IN_BRANCH: "El consultorio no pertenece a esta sede.",
};
```

> **El color de los badges de estado viene del catálogo** (`AppointmentStatus.color`, hex configurable en BD), **no** de `brandPalette` (que no tiene `accent` — lección operativa transversal). Para colores que no sean del estado (p.ej. el overlay de slots libres en la grilla) usar **tokens Fluent semánticos** (`tokens.colorPaletteGreenBackground2`, etc.). El `StatusBadge` (reusado del patrón crm) aplica `status.color` con contraste best-effort.

> **`calendar.ts` se REUSA del módulo staff** (ya creado en F0 de staff): `GRID_START_HOUR`/`GRID_END_HOUR`/`GRID_STEP_MIN`, `WEEKDAY_SHORT`, `timeToMinutes`/`minutesToTime`. La grilla de scheduling usa los mismos parámetros. Si scheduling necesita un grano distinto (p.ej. alinear a `doctor_slot_duration_min` devuelto por `compute`), parametrizar el alto de fila en el componente, **no** duplicar el archivo.

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque SCHEDULING completo (todas las URLs de la spec §5). `/active` antes de `/{id}` en el backend; verbos `PUT` para updates; shortcuts de lifecycle como `POST` sub-recursos. **`from-bot`/`cancel-from-bot` NO se exponen en el front** (los consume el motor de bots server-side; el front nunca los llama) — se omiten del `ENDPOINTS` del frontend a propósito.

```ts
const SCHEDULING = "/api/v1/scheduling"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, VERTICALS, SERVICES, PRODUCTS,
  //   BRANCHES, OFFICES, DOCTORS, ME (staff), CRM (existentes) …

  // ── Scheduling module ─────────────────────────────────────
  APPOINTMENT_STATUSES: {
    LIST: `${SCHEDULING}/appointment-statuses/list`,
    CREATE: `${SCHEDULING}/appointment-statuses`,
    GET: (id: string) => `${SCHEDULING}/appointment-statuses/${id}`,
    UPDATE: (id: string) => `${SCHEDULING}/appointment-statuses/${id}`, // ← PUT
    DELETE: (id: string) => `${SCHEDULING}/appointment-statuses/${id}`, // 409 si en uso
    ACTIVE: `${SCHEDULING}/appointment-statuses/active`, // raw AppointmentStatusOption list
    TRANSITIONS: (id: string) => `${SCHEDULING}/appointment-statuses/${id}/transitions`, // GET / PUT
  },
  AVAILABILITY: {
    COMPUTE: `${SCHEDULING}/availability/compute`, // POST AvailabilityRequest → AvailabilityResponse
    CHECK_SLOT: `${SCHEDULING}/availability/check-slot`, // POST CheckSlotRequest → CheckSlotResponse
  },
  APPOINTMENTS: {
    LIST: `${SCHEDULING}/appointments/list`,
    CREATE: `${SCHEDULING}/appointments`, // POST (book)
    GET: (id: string) => `${SCHEDULING}/appointments/${id}`, // detalle + history + changelog
    UPDATE: (id: string) => `${SCHEDULING}/appointments/${id}`, // ← PUT (columnas no-estado)
    CALENDAR: `${SCHEDULING}/appointments/calendar`, // ?doctor_id=&branch_id=&product_id=&from=&to=
    // Lifecycle (todos POST sub-recursos).
    TRANSITION: (id: string) => `${SCHEDULING}/appointments/${id}/transition`, // genérico (valida matriz)
    CONFIRM: (id: string) => `${SCHEDULING}/appointments/${id}/confirm`,
    CHECK_IN: (id: string) => `${SCHEDULING}/appointments/${id}/check-in`,
    START: (id: string) => `${SCHEDULING}/appointments/${id}/start`,
    ATTEND: (id: string) => `${SCHEDULING}/appointments/${id}/attend`, // attend→promote (CRM)
    NO_SHOW: (id: string) => `${SCHEDULING}/appointments/${id}/no-show`,
    CANCEL: (id: string) => `${SCHEDULING}/appointments/${id}/cancel`, // min_hours_to_cancel + override
    RESCHEDULE: (id: string) => `${SCHEDULING}/appointments/${id}/reschedule`, // cierra vieja, crea nueva
  },
  ME_SCHEDULING: {
    APPOINTMENTS_LIST: `${SCHEDULING}/me/appointments/list`, // POST + QueryRequest (MY_APPOINTMENTS_READ)
    CALENDAR: `${SCHEDULING}/me/calendar`, // ?from=&to= (MY_APPOINTMENTS_READ)
  },
} as const;
```

> **Query params**: `APPOINTMENTS.CALENDAR` acepta `?doctor_id=&branch_id=&product_id=&from=&to=` (fechas `YYYY-MM-DD`); el `doctor_id`+`product_id` habilitan el overlay de slots libres (sin producto el calendario sólo pinta citas). `ME_SCHEDULING.CALENDAR` acepta `?from=&to=` (el doctor lo resuelve el token). El deep-link del listado de citas (`?doctor_id=`/`?status_id=`/`?office_id=`/`?date=`/`?product_id=`) se traduce a `FilterCondition` en el page RSC, **no** a query param del endpoint `/list`.

> **`/active` devuelve lista CRUDA** (`response_model=list[...]`, sin envelope) — no se lee `.data`. El resto (`/list`, `GET /{id}`, `POST`, `PUT`, `/calendar`, shortcuts, `compute`, `check-slot`) usa los envelopes del template y se lee con `.data` — **excepto** `compute`/`check-slot`, que el backend devuelve enveloped `SingleResponse[AvailabilityResponse]`/`SingleResponse[CheckSlotResponse]` (confirmar con [`backend.md`](./backend.md#availability) si son crudos o enveloped; este doc asume **enveloped** → `.data`).

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `scheduling` entre `crm` y `admin`:

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … */ },
  { key: "catalog", /* … */ },
  { key: "clinic", /* … */ },
  { key: "staff", /* … */ },
  { key: "crm", /* … */ },

  // ── NEW ───────────────────────────────────────────
  {
    key: "scheduling",
    label: "Agenda",
    icon: "CalendarLtrRegular",
    permissions: ["MENU-SCHEDULING"], // gate del grupo (el ASESOR/DOCTOR lo tienen)
    children: [
      {
        key: "appointments",
        label: "Citas",
        icon: "CalendarClockRegular",
        url: "/scheduling/citas",
        permissions: ["APPOINTMENTS_READ"],
      },
      {
        key: "calendar",
        label: "Calendario",
        icon: "CalendarWeekStartRegular",
        url: "/scheduling/calendario",
        permissions: ["APPOINTMENTS_READ"],
      },
      {
        key: "appointment-statuses",
        label: "Estados de cita",
        icon: "TagRegular",
        url: "/scheduling/estados",
        permissions: ["APPOINTMENT_STATUSES_READ"],
      },
      {
        key: "my-appointments",
        label: "Mi agenda",
        icon: "PersonClockRegular",
        url: "/scheduling/mi-agenda",
        permissions: ["MY_APPOINTMENTS_READ"],
      },
    ],
  },

  { key: "admin", /* … */ },
];
```

> **Gating del grupo vs items**: la spec pide el grupo **gated `MENU-SCHEDULING`** (lo tienen ADMIN/ASESOR/DOCTOR). Cada item lleva su permiso fino (`APPOINTMENTS_READ`, `APPOINTMENTS_READ`, `APPOINTMENT_STATUSES_READ`, `MY_APPOINTMENTS_READ`) y el page RSC valida con `requirePermission(...)`. El **DOCTOR** ve Citas (scoped a sí mismo vía service), Calendario, Mi agenda; **no** ve Estados de cita (es `APPOINTMENT_STATUSES_READ`, que tiene ASESOR+ADMIN). **No** redefinir los permisos aquí — los 13 ya son canónicos en `_seed-and-roles.md` (los introduce backend F0).

> **Íconos** (verificar que existan en `@fluentui/react-icons` v9; fallback si no): grupo Agenda `CalendarLtrRegular` (ya usado por staff "Mi agenda"), Citas `CalendarClockRegular`, Calendario `CalendarWeekStartRegular`, Estados `TagRegular`, Mi agenda `PersonClockRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que catalog/clinic/staff/crm). Alternativas: `CalendarWeekStartRegular` → `CalendarLtrRegular`; `PersonClockRegular` → `CalendarLtrRegular`/`ClockRegular`. **No** introducir librerías de íconos nuevas.

## Server Actions

Mismo molde que clinic/catalog/staff/crm: validar con Zod en el action → llamar backend client → `revalidateTag(TAG, "max")`. Reusa el `MutationResult<T>` exportado por `user.actions.ts`. **Next 16 exige el 2º argumento de `revalidateTag`** (`"max"`); omitirlo es error de tipos/runtime.

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `scheduling:appointments` | listas y detalle de citas, `/calendar`, `/me/appointments`, `/me/calendar` | crear (book), editar, transición/shortcut, cancel, reschedule (afectan denormalizados + ocupación de la grilla) |
| `scheduling:appointment:{id}` | detalle (status_history + change_log) de UNA cita | transición/shortcut/update/cancel de esa cita |
| `scheduling:statuses` | catálogo AppointmentStatus + `/active` + matriz | CRUD catálogo, editar transiciones |

> **Por qué tag por-cita** (`scheduling:appointment:{id}`): el detalle (timeline) de una cita es independiente del de otra; taggear por id evita invalidar el cache de todas. **Cross-tag**: una transición/cancel/reschedule invalida **tanto** `scheduling:appointment:{id}` (su timeline) **como** `scheduling:appointments` (su badge/columna en la lista y su bloque en la grilla). El reschedule además crea una **nueva** cita → sólo el tag global `scheduling:appointments` la trae (la nueva no tiene su tag por-id cacheado aún). El `attend`→promote toca **crm** (`crm:lead:{personId}`/`crm:customer:{personId}`/`crm:activity:{personId}`/`crm:persons`): el action de `attend` revalida también esos tags (cross-módulo aditivo) — ver nota abajo.

> **`availability.actions.ts` NO revalida tags**: `compute`/`check-slot` son **lecturas puras on-the-fly** (no persisten, ADR-006). No llevan `tags` en el fetch (o `cache: "no-store"`): la disponibilidad cambia con cada cita nueva y el caching está **diferido** (MVP sin Redis). El wizard las llama directo cuando el usuario avanza al paso Slot. Tras **crear/cancelar/reschedule** una cita, la disponibilidad mostrada en un wizard abierto puede quedar stale → el wizard re-computa al re-entrar al paso Slot, y el backend reconfirma con `SLOT_TAKEN` (defensa).

### `actions/appointment-status.actions.ts`

Catálogo + matriz. Molde directo de crm `lead-status.actions.ts` (sin `is_won`, con `is_active_attention`).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  appointmentStatusCreateSchema,
  appointmentStatusUpdateSchema,
  transitionTargetsSchema,
} from "@/lib/schemas/appointment-status.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  AppointmentStatusItem,
  AppointmentStatusOption,
  TransitionTargets,
} from "@/types/scheduling.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const TAG = "scheduling:statuses";

export async function listAppointmentStatuses(
  query: QueryRequest,
): Promise<ApiPaginated<AppointmentStatusItem>> {
  return backendClient.post<ApiPaginated<AppointmentStatusItem>>(
    ENDPOINTS.APPOINTMENT_STATUSES.LIST,
    query,
    { tags: [TAG] },
  );
}

export async function listActiveAppointmentStatuses(): Promise<AppointmentStatusOption[]> {
  // Lista CRUDA. La consumen el StatusControl y los dropdowns de filtro/grilla.
  return backendClient.get<AppointmentStatusOption[]>(ENDPOINTS.APPOINTMENT_STATUSES.ACTIVE, {
    tags: [TAG],
  });
}

export async function createAppointmentStatus(
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentStatusItem>>> {
  const parsed = appointmentStatusCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<AppointmentStatusItem>>(
      ENDPOINTS.APPOINTMENT_STATUSES.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 MULTIPLE_INITIAL_STATUS en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateAppointmentStatus(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentStatusItem>>> {
  const parsed = appointmentStatusUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<AppointmentStatusItem>>(
      ENDPOINTS.APPOINTMENT_STATUSES.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteAppointmentStatus(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.APPOINTMENT_STATUSES.DELETE(id));
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 APPOINTMENT_STATUS_IN_USE si hay citas/history referenciándolo.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Matriz de transiciones ──────────────────────────────

export async function getStatusTransitions(id: string): Promise<TransitionTargets> {
  const res = await backendClient.get<ApiSingle<TransitionTargets>>(
    ENDPOINTS.APPOINTMENT_STATUSES.TRANSITIONS(id),
    { tags: [TAG] },
  );
  return res.data;
}

export async function setStatusTransitions(
  id: string,
  input: unknown, // { to_ids: [...] } — reemplaza aristas de salida
): Promise<MutationResult<ApiSingle<TransitionTargets>>> {
  const parsed = transitionTargetsSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<TransitionTargets>>(
      ENDPOINTS.APPOINTMENT_STATUSES.TRANSITIONS(id), // ← PUT (reemplaza)
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/availability.actions.ts`

Lecturas puras (sin `revalidateTag`). Las consume el wizard (paso Slot) y la grilla (overlay de slots libres, si se prefiere computar aparte del `/calendar`).

```ts
"use server";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  availabilityRequestSchema,
} from "@/lib/schemas/appointment.schema";
import { backendClient } from "@/services/backend.client";
import { type ApiSingle } from "@/types/api.types";
import type {
  AvailabilityResponse,
  CheckSlotRequest,
  CheckSlotResponse,
} from "@/types/scheduling.types";

export async function computeAvailability(
  input: unknown,
): Promise<AvailabilityResponse> {
  // Valida el request (doctor/producto/rango). Lanza si inválido → el caller
  // (WizardStepSlot) muestra los fieldErrors. Lectura on-the-fly: cache: "no-store".
  const parsed = availabilityRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<AvailabilityResponse>>(
    ENDPOINTS.AVAILABILITY.COMPUTE,
    parsed,
    { cache: "no-store" },
  );
  return res.data; // { slots, duration_min, doctor_slot_duration_min }
}

export async function checkSlot(input: CheckSlotRequest): Promise<CheckSlotResponse> {
  const res = await backendClient.post<ApiSingle<CheckSlotResponse>>(
    ENDPOINTS.AVAILABILITY.CHECK_SLOT,
    input,
    { cache: "no-store" },
  );
  return res.data; // { available, reason? }
}
```

> **`computeAvailability` valida con `.parse` (no `.safeParse`)** porque el caller es un client component que ya pre-valida el form; un request inválido es un bug, no input de usuario. Si se prefiere el patrón `MutationResult`, envolver con `safeParse` y devolver `fieldErrors` (alternativa válida). La spec marca `compute`/`check-slot` como **gated** por permiso `APPOINTMENTS_READ`/`APPOINTMENTS_CREATE` (no por un `AVAILABILITY_READ` propio — la spec §6 NO lista `AVAILABILITY_READ`; el viejo `scheduling.md` plano sí, **deprecado**) — confirmar el gate en [`backend.md`](./backend.md#permisos) y reflejarlo en el botón "Buscar disponibilidad" del wizard (visible con `APPOINTMENTS_CREATE`).

### `actions/appointment.actions.ts`

El más grande: CRUD + calendar + transición + 7 shortcuts + `/me`. Cross-tag por-cita + global. El `attend` revalida además los tags de crm (attend→promote).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  appointmentCancelSchema,
  appointmentRescheduleSchema,
  appointmentTransitionSchema,
  appointmentUpdateSchema,
  bookingWizardSchema,
} from "@/lib/schemas/appointment.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  AppointmentDetail,
  AppointmentItem,
  CalendarResponse,
  MyAppointmentItem,
} from "@/types/scheduling.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const APPTS_TAG = "scheduling:appointments";
const apptTag = (id: string) => `scheduling:appointment:${id}`;

// ── Listado / detalle ───────────────────────────────────

export async function listAppointments(
  query: QueryRequest,
): Promise<ApiPaginated<AppointmentItem>> {
  return backendClient.post<ApiPaginated<AppointmentItem>>(ENDPOINTS.APPOINTMENTS.LIST, query, {
    tags: [APPTS_TAG],
  });
}

export async function getAppointment(id: string): Promise<ApiSingle<AppointmentDetail>> {
  // Incluye status_history + change_log embebidos para el drawer de detalle.
  return backendClient.get<ApiSingle<AppointmentDetail>>(ENDPOINTS.APPOINTMENTS.GET(id), {
    tags: [apptTag(id), APPTS_TAG],
  });
}

// ── Calendar (citas + slots libres en rango) ────────────

export async function getCalendar(params: {
  from: string; // "YYYY-MM-DD"
  to: string;
  doctorId?: string;
  branchId?: string;
  productId?: string;
}): Promise<CalendarResponse> {
  const qs = new URLSearchParams({ from: params.from, to: params.to });
  if (params.doctorId) qs.set("doctor_id", params.doctorId);
  if (params.branchId) qs.set("branch_id", params.branchId);
  if (params.productId) qs.set("product_id", params.productId);
  const res = await backendClient.get<ApiSingle<CalendarResponse>>(
    `${ENDPOINTS.APPOINTMENTS.CALENDAR}?${qs.toString()}`,
    { tags: [APPTS_TAG] },
  );
  return res.data;
}

// ── Book (create) ───────────────────────────────────────

export async function createAppointment(
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = bookingWizardSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    // source lo decide el action por rol (advisor/admin); aquí "advisor" por defecto
    // del panel; el admin lo puede sobreescribir. duration_min lo copia el backend.
    const body = { ...parsed.data, source: "advisor" as const };
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.CREATE,
      body,
    );
    revalidateTag(APPTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 SLOT_TAKEN/OFFICE_SLOT_TAKEN/NO_AVAILABILITY_BLOCK/OFFICE_CLOSED/
    // DOCTOR_INACTIVE/OFFICE_NOT_IN_BRANCH/… en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Editar columnas no-estado (→ change_log) ────────────

export async function updateAppointment(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(apptTag(id), "max");
    revalidateTag(APPTS_TAG, "max"); // denormalizados (doctor/office) en lista/grilla
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Transición genérica (valida matriz) ─────────────────

export async function transitionAppointment(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentTransitionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.TRANSITION(id),
      parsed.data,
    );
    revalidateTag(apptTag(id), "max");
    revalidateTag(APPTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 APPOINTMENT_TRANSITION_NOT_ALLOWED en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Shortcuts (mapean a su to-state vía la matriz; reason opcional) ─
// Helper interno para no repetir el try/catch/revalidate de los 5 sin side-effect
// especial (confirm/check-in/start/no-show). attend y cancel/reschedule van aparte.

async function lifecycleShortcut(
  url: string,
  id: string,
  body: Record<string, unknown> = {},
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(url, body);
    revalidateTag(apptTag(id), "max");
    revalidateTag(APPTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export const confirmAppointment = (id: string, reason?: string) =>
  lifecycleShortcut(ENDPOINTS.APPOINTMENTS.CONFIRM(id), id, { reason });
export const checkInAppointment = (id: string, reason?: string) =>
  lifecycleShortcut(ENDPOINTS.APPOINTMENTS.CHECK_IN(id), id, { reason });
export const startAppointment = (id: string, reason?: string) =>
  lifecycleShortcut(ENDPOINTS.APPOINTMENTS.START(id), id, { reason });
export const noShowAppointment = (id: string, reason?: string) =>
  lifecycleShortcut(ENDPOINTS.APPOINTMENTS.NO_SHOW(id), id, { reason });

// attend: side-effect attend→promote (CRM). Revalida también los tags de crm de
// esa persona (cross-módulo aditivo) para que el badge cliente/timeline reflejen
// el promote sin refresh manual.
export async function attendAppointment(
  id: string,
  personId: string,
  reason?: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.ATTEND(id),
      { reason },
    );
    revalidateTag(apptTag(id), "max");
    revalidateTag(APPTS_TAG, "max");
    // Cross-módulo: attend promueve a cliente (o emite APPOINTMENT_ATTENDED).
    revalidateTag(`crm:customer:${personId}`, "max");
    revalidateTag(`crm:lead:${personId}`, "max");
    revalidateTag(`crm:activity:${personId}`, "max");
    revalidateTag("crm:persons", "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Cancel (min_hours_to_cancel + override por permiso) ──

export async function cancelAppointment(
  id: string,
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentCancelSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.CANCEL(id),
      parsed.data,
    );
    revalidateTag(apptTag(id), "max");
    revalidateTag(APPTS_TAG, "max");
    revalidateTag(`crm:activity:${personId}`, "max"); // emite LeadActivity(APPOINTMENT_CANCELLED)
    return { ok: true, data };
  } catch (e) {
    // 400 CANCEL_TOO_LATE (sin permiso override) / APPOINTMENT_TRANSITION_NOT_ALLOWED.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Reschedule (cierra la vieja RESCHEDULED, crea la nueva) ─

export async function rescheduleAppointment(
  id: string,
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentRescheduleSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    // Devuelve la NUEVA cita (con previous_appointment_id = id). No sujeta a min_hours.
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.RESCHEDULE(id),
      parsed.data,
    );
    revalidateTag(apptTag(id), "max"); // la vieja pasa a RESCHEDULED
    revalidateTag(APPTS_TAG, "max"); // la nueva aparece en lista/grilla
    revalidateTag(`crm:activity:${personId}`, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 SLOT_TAKEN/NO_AVAILABILITY_BLOCK/… sobre la NUEVA cita.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── /me (doctor self-service) ───────────────────────────

export async function listMyAppointments(
  query: QueryRequest,
): Promise<ApiPaginated<MyAppointmentItem>> {
  return backendClient.post<ApiPaginated<MyAppointmentItem>>(
    ENDPOINTS.ME_SCHEDULING.APPOINTMENTS_LIST,
    query,
    { tags: [APPTS_TAG] },
  );
}

export async function getMyCalendar(params: {
  from: string;
  to: string;
}): Promise<CalendarResponse> {
  const qs = new URLSearchParams({ from: params.from, to: params.to });
  const res = await backendClient.get<ApiSingle<CalendarResponse>>(
    `${ENDPOINTS.ME_SCHEDULING.CALENDAR}?${qs.toString()}`,
    { tags: [APPTS_TAG] },
  );
  return res.data;
}
```

> **Por qué `attend`/`cancel`/`reschedule` reciben `personId`**: necesitan invalidar los tags de **crm** de esa persona (attend→promote escribe customer/lead/activity; cancel/reschedule emiten `LeadActivity`). El `personId` lo tiene el caller (está en `AppointmentDetail.person_id`). Es una **invalidación cross-módulo aditiva** — la documenta también [`crm/frontend.md`](../crm/frontend.md#todos-deliberados-postergados-al-mvp1) como TODO ("cuando scheduling emita actividades en el timeline, revalidar `crm:activity:{personId}`"). Aquí se cumple.

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/scheduling/citas/page.tsx` (LISTA)

Análoga a `crm/personas/page.tsx`. El create vive en un **wizard drawer**; ver/editar abre el **detalle drawer**. **Deep-link**: `?doctor_id=`/`?status_id=`/`?office_id=`/`?branch_id=`/`?product_id=`/`?date=` traducidos a `FilterCondition` sobre columnas **reales** (no denormalizados). El `defaultSort` del prefetch usa `scheduled_for` (columna real) y **debe coincidir** con el `defaultSort` del client.

```tsx
import { listActiveAppointmentStatuses } from "@/actions/appointment-status.actions";
import { listAppointments } from "@/actions/appointment.actions";
import { listActiveDoctors } from "@/actions/doctor.actions"; // staff (dropdown de filtro)
import { listActiveBranches } from "@/actions/branch.actions"; // clinic
import { listActiveProducts } from "@/actions/product.actions"; // catalog
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { AppointmentsClient } from "./_components/AppointmentsClient";

export const metadata = { title: "Citas" };

interface PageProps {
  searchParams: Promise<{
    doctor_id?: string;
    status_id?: string;
    office_id?: string;
    branch_id?: string;
    product_id?: string;
    date?: string; // "YYYY-MM-DD" → rango [date 00:00, date+1 00:00) en backend
  }>;
}

export default async function AppointmentsPage({ searchParams }: PageProps) {
  await requirePermission("APPOINTMENTS_READ");
  const sp = await searchParams;

  // Deep-link → FilterCondition sobre columnas REALES del appointment.
  const conditions: FilterCondition[] = [];
  if (sp.doctor_id) conditions.push({ field: "doctor_id", operator: "eq", value: sp.doctor_id });
  if (sp.status_id) conditions.push({ field: "status_id", operator: "eq", value: sp.status_id });
  if (sp.office_id) conditions.push({ field: "office_id", operator: "eq", value: sp.office_id });
  if (sp.branch_id) conditions.push({ field: "branch_id", operator: "eq", value: sp.branch_id });
  if (sp.product_id) conditions.push({ field: "product_id", operator: "eq", value: sp.product_id });
  if (sp.date) {
    // scheduled_for entre [date 00:00, date 23:59:59] — el backend interpreta el
    // rango; se manda el día como dos condiciones gte/lt sobre la columna real.
    conditions.push({ field: "scheduled_for", operator: "gte", value: `${sp.date}T00:00:00` });
    conditions.push({ field: "scheduled_for", operator: "lt", value: `${sp.date}T23:59:59` });
  }
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  const [initialData, statuses, doctors, branches, products] = await Promise.all([
    listAppointments({
      pagination: { skip: 0, limit: 10 },
      // defaultSort = scheduled_for (columna REAL). DEBE coincidir con el client.
      sorting: { sort_by: "scheduled_for", sort_order: "desc" },
      filters,
    }),
    listActiveAppointmentStatuses(),
    listActiveDoctors(),
    listActiveBranches(),
    listActiveProducts(),
  ]);

  return (
    <AppointmentsClient
      initialData={initialData}
      statuses={statuses}
      doctors={doctors}
      branches={branches}
      products={products}
    />
  );
}
```

> **Por qué los filtros van sobre columnas reales y NO sobre los `*_name`**: `status_id`/`doctor_id`/`office_id`/`branch_id`/`product_id`/`scheduled_for` son columnas **reales** del `appointment` (todas en `ALLOWED_FIELDS`) → server-filterable sin riesgo (lección `cd10c78`). Los `*_name` denormalizados son **sólo para render** (badge/columna). Ordenar por `person_name`/`doctor_name`/`status_name` (texto denormalizado) **NO** está permitido → 400. La tabla **no** marca esas columnas como `isSortable`; sólo `scheduled_for`/`created_on` (reales).

### `app/(main)/scheduling/calendario/page.tsx` (GRILLA)

```tsx
import { listActiveAppointmentStatuses } from "@/actions/appointment-status.actions";
import { listActiveDoctors } from "@/actions/doctor.actions";
import { listActiveBranches } from "@/actions/branch.actions";
import { listActiveProducts } from "@/actions/product.actions";
import { requirePermission } from "@/lib/auth/session";

import { CalendarClient } from "./_components/CalendarClient";

export const metadata = { title: "Calendario" };

export default async function CalendarPage() {
  await requirePermission("APPOINTMENTS_READ");
  // Sólo catálogos para la toolbar; las citas/slots los carga el client por semana
  // (la semana inicial = "esta semana" se resuelve CLIENT-ONLY para no desfasar el día).
  const [statuses, doctors, branches, products] = await Promise.all([
    listActiveAppointmentStatuses(),
    listActiveDoctors(),
    listActiveBranches(),
    listActiveProducts(),
  ]);
  return (
    <CalendarClient statuses={statuses} doctors={doctors} branches={branches} products={products} />
  );
}
```

> **El calendario NO prefetcha citas en el RSC**: la semana inicial depende de `new Date()` (qué semana es "esta") → resolverla en el server (UTC) desfasaría el lunes en TZ negativas. Igual que `DoctorAvailabilityTab`, la grilla resuelve `weekStart` **client-only** y dispara `getCalendar(from, to)` en `useEffect` con fetch-token. El RSC sólo prefetcha los catálogos de la toolbar (no dependen de la fecha).

### `app/(main)/scheduling/estados/page.tsx`

```tsx
import { listAppointmentStatuses } from "@/actions/appointment-status.actions";
import { requirePermission } from "@/lib/auth/session";

import { AppointmentStatusesClient } from "./_components/AppointmentStatusesClient";

export const metadata = { title: "Estados de cita" };

export default async function AppointmentStatusesPage() {
  await requirePermission("APPOINTMENT_STATUSES_READ");
  const initialData = await listAppointmentStatuses({
    pagination: { skip: 0, limit: 50 }, // catálogo chico (8 seed); una página basta
    sorting: { sort_by: "display_order", sort_order: "asc" }, // columna real
    filters: null,
  });
  return <AppointmentStatusesClient initialData={initialData} />;
}
```

> **`defaultPageSize: 50`** en el client de estados (el prefetch pide `limit: 50`): si el `useTableQuery` queda con el default `pageSize=10`, el footer desync + flash (lección recurrente de crm). Pasar `defaultPageSize: 50` al `useTableQuery` del `AppointmentStatusesClient`.

### `app/(main)/scheduling/mi-agenda/page.tsx`

```tsx
import { requirePermission } from "@/lib/auth/session";

import { MyAgendaClient } from "./_components/MyAgendaClient";

export const metadata = { title: "Mi agenda" };

export default async function MyAgendaPage() {
  await requirePermission("MY_APPOINTMENTS_READ");
  // El doctor se resuelve del token en el backend; el calendario/lista cargan en
  // cliente por semana (client-only weekStart). Maneja el 403 NOT_A_DOCTOR dentro
  // del client (estado vacío "Tu cuenta no tiene un perfil de doctor"), no notFound.
  return <MyAgendaClient />;
}
```

> **`mi-agenda` no prefetcha** (igual que el calendario): la semana inicial es client-only. Si el actor no es doctor, el `getMyCalendar` lanza 403 `NOT_A_DOCTOR` → el client muestra un estado vacío de negocio (no `notFound()`), espejando `staff/me/agenda` (`MyAvailabilityClient`).

## Client components — esqueletos

> **No reproduzco los archivos completos** — siguen el patrón exacto de `crm/.../*` (catálogo + matriz + StatusBadge/TransitionControl + timeline) + `staff/.../DoctorAvailabilityTab` (la grilla bespoke + fetch-token + reuse self/admin). Documento las diferencias específicas a scheduling. El **`BookingWizardDrawer`** (wizard multi-paso con `/availability/compute`) y la **`ScheduleGrid`** (grilla con citas + overlay de slots) son las piezas sustancialmente nuevas y se detallan aparte. La UI detallada (mockups, copy) vive en [`ui.md`](./ui.md).

### `AppointmentsClient.tsx`

Sigue el patrón de `PersonsClient.tsx`/`DoctorsClient.tsx` (lista con filtros chip + botón de creación + RowActions). Diferencias:

- Recibe `statuses: AppointmentStatusOption[]`, `doctors: DoctorOption[]`, `branches: BranchOption[]`, `products: ProductOption[]` (dropdowns de filtro).
- `useTableQuery`: `queryKey: "scheduling:appointments"`, `fetcher: listAppointments`, `searchFields: ["person_name", "doctor_name", "product_name"]` (**client-side**: son denormalizados), `defaultSort: { field: "scheduled_for", order: "desc" }` (**columna real**, coincide con el prefetch RSC), `initialData`.
- State `doctorFilter`/`statusFilter`/`officeFilter`/`branchFilter`/`productFilter`/`dateFilter` sincronizados con URL (`nuqs`); Dropdowns en la toolbar + `Input type="date"` para el día + chips "Filtrado por: …" con ✕ (mismo flujo que el filtro de sede en `DoctorsClient`).
- Columns: `actions`, `scheduled_for` (fecha+hora, `formatDate`, **client-only** render), `person_name` (Paciente), `doctor_name` (Doctor), `product_name` (Servicio), `office_name` (Consultorio, con `branch_name` debajo), `status` (badge color vía `StatusBadge`), `source` (`APPOINTMENT_SOURCE_META[source].label`), `duration_min` ("{n} min"). **Ninguna columna denormalizada es `isSortable`** (lección `cd10c78`); sólo `scheduled_for`/`created_on` (reales).
- **RowActions** → abren el **detalle drawer** (no navegan a una ruta):
  ```ts
  { key: "view", label: "Ver", icon: <EyeRegular />, onSelect: (a) => setDetailId(a.id) },
  { key: "reschedule", label: "Reagendar", icon: <CalendarSyncRegular />, permissions: ["APPOINTMENTS_RESCHEDULE"], onSelect: (a) => { setDetailId(a.id); setDetailTab("reschedule"); } },
  { key: "cancel", label: "Cancelar", icon: <DismissCircleRegular />, permissions: ["APPOINTMENTS_CANCEL"], danger: true, onSelect: (a) => { setDetailId(a.id); setDetailTab("cancel"); } },
  ```
- Botón **"Nueva cita"** gated `APPOINTMENTS_CREATE` → abre `BookingWizardDrawer` vacío.
- El **detalle** se monta como `AppointmentDetailDrawer` controlado por `detailId` (carga `getAppointment(detailId)` en cliente al abrir).

### `BookingWizardDrawer.tsx` — el wizard de reserva

> **Honestidad**: el wizard de 4 pasos dentro de un `Drawer` Fluent es **bespoke** (Fluent 9 no trae un Stepper de página; se usan `TabList`/indicadores propios + estado de paso). Construir **incrementalmente**: (1) los 4 pasos lineales con validación por paso + `computeAvailability` en el paso Slot → (2) el atajo "prefilled desde la grilla" (saltar a Confirmar) + revalidación `check-slot` antes de confirmar. La capa de datos es la misma.

Props: `{ open: boolean; onClose: () => void; prefill?: Partial<BookingWizardInput> & { slot?: AvailabilitySlot }; doctors: DoctorOption[]; branches: BranchOption[]; products: ProductOption[]; onBooked?: (appt: AppointmentDetail) => void }`.

**Shape del estado**:

```ts
type WizardStep = "person" | "service" | "slot" | "confirm";
const [step, setStep] = useState<WizardStep>(prefill?.slot ? "confirm" : "person");

// Form acumulativo (react-hook-form con bookingWizardSchema, validación por paso
// via trigger(["campo"]) antes de avanzar).
const form = useForm<BookingWizardInput>({
  resolver: zodResolver(bookingWizardSchema),
  defaultValues: { person_id: "", product_id: "", doctor_id: "", branch_id: "", office_id: "", scheduled_for: "", notes: "", ...prefill },
});

// Resultado de computeAvailability (paso Slot).
const [slots, setSlots] = useState<AvailabilitySlot[]>([]);
const [computeMeta, setComputeMeta] = useState<{ duration_min: number; doctor_slot_duration_min: number } | null>(null);
const [computing, setComputing] = useState(false);
const [computeError, setComputeError] = useState<string | null>(null);
const reqIdRef = useRef(0); // fetch-token: cambiar doctor/producto/fecha rápido no pisa la lista vieja

// Default de la fecha del paso Slot = HOY → CLIENT-ONLY (no SSR; el drawer es cliente).
const [fromDate, setFromDate] = useState<string | null>(null);
useEffect(() => { setFromDate(toIsoDateLocal(new Date())); }, []); // "YYYY-MM-DD" local
```

**Pasos**:

- **`WizardStepPerson`**: `Dropdown`/búsqueda de paciente (`PersonOption[]` de crm via `listActivePersons()` o `searchPersons(q)` — se carga en cliente; el wizard no recibe la lista completa por prop si es grande). Selecciona `person_id`. (No crea persona aquí; si el paciente no existe, link a `/crm/personas` — MVP.)
- **`WizardStepServiceDoctor`**: `Dropdown product_id` (`products` prop), `Dropdown doctor_id` (`doctors` prop, filtrable por vertical del producto — opcional), `Dropdown branch_id` (`branches`, acota el cómputo), `Dropdown office_id` (offices de esa sede via `listActiveOffices(branchId)` de clinic, en cliente). El **producto define la duración** (de `catalog`, no de Service — reconciliación de la spec). Al completar, habilita avanzar a Slot.
- **`WizardStepSlot`**: dispara `computeAvailability` con `{ doctor_id, product_id, branch_id, office_id, from_date: fromDate, to_date }` (rango = la semana/los próximos N días desde `fromDate`). Render: **lista/grilla de slots** agrupados por día (agrupación **client-only** por la TZ del navegador/branch). Cada slot muestra `formatTime(starts_at)`–`formatTime(ends_at)` + `office_name`. Click en un slot → `form.setValue("scheduled_for", slot.starts_at)` + setear `office_id`/`branch_id`/`doctor_id` del slot (por si el cómputo cruzó varios offices) → avanza a Confirmar.
  - **Estados**: `computing` → skeleton; `slots.length === 0` → "No hay horarios disponibles para ese doctor/servicio en el rango. Prueba otra fecha o sede."; error → `MessageBar`.
  - **fetch-token**: cambiar fecha/doctor/producto rápido → la respuesta vieja se descarta (`reqId !== reqIdRef.current`).
- **`WizardStepConfirm`**: resumen (paciente, servicio, doctor, consultorio/sede, fecha+hora **client-only**, duración) + `Textarea notes`. Botón "Confirmar reserva" → (opcional, etapa 2) `checkSlot(...)` para revalidar justo antes; luego `createAppointment(form.getValues())`. En éxito → `onBooked?.(detail)` + cerrar + (si se montó desde la lista) la tabla se re-pinta por el tag invalidado. Errores de invariante (`SLOT_TAKEN`, etc.) en `MessageBar` **sin cerrar** (el usuario vuelve al paso Slot a re-elegir).

> **Prefilled desde la grilla**: cuando se abre con `prefill.slot` (click en un slot libre del calendario), el wizard arranca en `confirm` con `person_id` vacío → en realidad necesita el paciente, así que si falta `person_id`, arranca en `person` pero con `product_id/doctor_id/office_id/branch_id/scheduled_for` ya seteados del slot (sólo pide el paciente y confirma). Documentar este matiz: el slot fija el "cuándo/quién atiende/dónde"; el wizard sólo completa el "a quién".

### `AppointmentDetailDrawer.tsx`

Drawer de detalle (no página). Carga `getAppointment(id)` en cliente al abrir (`useState` + `useEffect` con fetch-token). Molde de los tabs de `PersonDetailShell` pero en un drawer. Secciones:

- **Cabecera**: `person_name`, badge de estado (`StatusBadge` con `status.color`), `doctor_name` · `office_name`/`branch_name`, `scheduled_for` (fecha+hora **client-only**) + `duration_min`, `source` (`APPOINTMENT_SOURCE_META`), origen de reagendamiento si `previous_appointment_id` ("Reagendada de una cita anterior" + link).
- **`AppointmentStatusControl`** (gated por la matriz + permisos): ver abajo.
- **Editar columnas no-estado** (gated `APPOINTMENTS_UPDATE`): form inline `doctor_id`/`office_id`/`branch_id`/`product_id`/`notes` + `reason` → `updateAppointment(id, values)`. Cambiar doctor/office puede violar invariantes → error en `MessageBar`.
- **`AppointmentTimeline`** (status_history + change_log entrelazados): ver abajo.
- **`RescheduleDialog`** / **`CancelDialog`**: ver abajo.

### `AppointmentStatusControl.tsx`

Componente que ofrece **shortcuts** gated por la matriz (espeja el `TransitionControl` de crm pero con los shortcuts nombrados de la spec). Dado el estado actual (`appointment.status`), carga `getStatusTransitions(status.id)` → conoce los destinos permitidos. Renderiza botones de acción mapeados a su shortcut **sólo si el destino está permitido** por la matriz:

- "Confirmar" (→CONFIRMED) gated `APPOINTMENTS_TRANSITION`, visible si `confirmed` ∈ destinos.
- "Registrar recepción" (check-in →CHECKED_IN), "Iniciar atención" (start →IN_PROGRESS), "Marcar atendida" (attend →ATTENDED, gated `APPOINTMENTS_TRANSITION`; **dispara attend→promote**), "No asistió" (no-show →NO_SHOW) — cada uno visible sólo si su to-state está en `getStatusTransitions`.
- "Cancelar" (→CANCELLED) gated `APPOINTMENTS_CANCEL` → abre `CancelDialog`.
- "Reagendar" (→RESCHEDULED) gated `APPOINTMENTS_RESCHEDULE` → abre `RescheduleDialog`.
- Si el estado actual es **terminal** (`is_final`) → no hay destinos → controles deshabilitados con hint "Cita en estado final, sin acciones."
- También un **"Cambiar estado…"** genérico (`transitionAppointment`) con un `Dropdown` de los destinos restantes (para estados configurados por la clínica que no tengan shortcut), gated `APPOINTMENTS_TRANSITION`.

> **Por qué shortcuts + genérico**: la spec define 7 shortcuts (`/confirm`,`/check-in`,`/start`,`/attend`,`/no-show`,`/cancel`,`/reschedule`) que mapean a su to-state, **más** el `/transition` genérico que valida la matriz. La UI ofrece los shortcuts como botones nombrados (UX clara) **y** el genérico para aristas configuradas a mano. Ambos consultan la **misma** matriz (`getStatusTransitions`) para no ofrecer una acción que el backend rechazaría con `APPOINTMENT_TRANSITION_NOT_ALLOWED`. Tras cualquier acción, re-`load()` del detalle (el tag `scheduling:appointment:{id}` se revalidó) y `router.refresh()` si el drawer se montó sobre una página con denormalizados (lista/grilla) para re-pintar el badge.

### `RescheduleDialog.tsx`

Reagendar = elegir un **nuevo** slot (re-corre el sub-flujo del wizard de Slot) que **EXCLUYE la cita vieja** del chequeo de conflicto. Reusa `WizardStepServiceDoctor` + `WizardStepSlot` (o un compute directo) con los valores actuales de la cita como defaults. Al confirmar → `rescheduleAppointment(id, personId, { doctor_id, office_id, branch_id, product_id, scheduled_for, reason, notes })`. El backend marca la vieja `RESCHEDULED` y crea la nueva con `previous_appointment_id` en la misma transacción; devuelve la **nueva** cita → el drawer puede saltar a la nueva o cerrar y dejar que la lista/grilla se re-pinten. **No** está sujeto a `min_hours_to_cancel` (no es cancelación). Errores (`SLOT_TAKEN`, etc.) sobre la **nueva** cita → `MessageBar`.

### `CancelDialog.tsx`

`Textarea cancellation_reason` (obligatorio) + botón "Cancelar cita" → `cancelAppointment(id, personId, { cancellation_reason })`. Si el backend devuelve `CANCEL_TOO_LATE` (400) — la cita está dentro de la ventana `min_hours_to_cancel` y el actor **no** tiene `APPOINTMENTS_CANCEL_OVERRIDE` — mostrar el mensaje en `MessageBar` ("No se puede cancelar: faltan menos de {n} horas. Requiere permiso de cancelación forzada."). Si el actor **sí** tiene `APPOINTMENTS_CANCEL_OVERRIDE` (`usePermissions`), mostrar un aviso "Estás cancelando fuera de la ventana permitida" pero permitir el submit (el backend salta el gate por el permiso). El front **no** manda un flag de override — lo decide el backend por permiso.

### `AppointmentTimeline.tsx`

Timeline read-only que **entrelaza** `status_history` (cambios de estado: from→to badges, `changed_at`, actor, `reason`) y `change_log` (cambios de columnas no-estado: `field_name`, `previous_value`→`new_value`, actor, `reason`). Ambos vienen embebidos en `AppointmentDetail`. Molde del history de crm (`LeadTab` history), pero fusionando dos fuentes:

- Merge: combinar ambas listas en una sola ordenada por `changed_at` **desc** (más reciente arriba). Cada entrada tipada: `kind: "status" | "field"`.
- Render por entrada: ícono (cambio de estado vs edición de campo), actor (`changed_by_user.full_name ?? "Sistema"`), `changed_at` relativo (**client-only**), y el cuerpo: para `status` los badges from→to (con color del catálogo); para `field` "{field_name}: {previous_value} → {new_value}" (traducir `field_name` a label ES con un map pequeño: `doctor_id`→"Doctor", `office_id`→"Consultorio", `notes`→"Notas", …; los valores serializados UUID se muestran resueltos si vienen denormalizados, o crudos si no).
- **Agrupación por día** "Hoy"/"Ayer"/fecha = **client-only** (`new Date()`; SSR en UTC desfasaría el día en Lima `-05:00`) — igual que el `ActivityTimeline` de crm.
- Estado vacío: "Sin historial." (siempre hay al menos el `NULL→SCHEDULED` inicial).

> **Por qué un map para `field_name`** (no el valor crudo): el `change_log` guarda `field_name` como columna técnica (`doctor_id`); la UI lo muestra en español. Los `previous_value`/`new_value` de un FK son UUIDs serializados — si el backend no los resuelve a nombres, mostrarlos como "(referencia)" o el UUID corto; resolver a nombre es un refinamiento (TODO).

### `ScheduleGrid.tsx` — la grilla semanal

> **Honestidad**: la grilla semanal de citas es **custom/bespoke** dentro de Fluent UI 9 (no se introduce librería de calendario; tokens Fluent, primitivas propias). Comparte el armazón con el `<AvailabilityGrid>` de staff (columnas Lun..Dom, filas por hora, posicionamiento por minutos-desde-medianoche, fetch-token, navegación de semana, `weekStart` **client-only**), pero **pinta dos capas**: (1) **citas** como bloques sólidos coloreados por estado; (2) **slots libres** como overlay clickeable (sólo si la toolbar tiene doctor+producto). Construir **incrementalmente**: (1) pintar citas (read) + navegación de semana → (2) overlay de slots libres + click→wizard prefilled.

Props (genérica respecto a self/admin): `{ load: (from: string, to: string) => Promise<CalendarResponse>; statuses: AppointmentStatusOption[]; canBook: boolean; onSlotClick?: (slot: AvailabilitySlot) => void; onAppointmentClick?: (appt: AppointmentItem) => void; branchTimezone?: string }`.

**Shape del estado** (molde directo de `DoctorAvailabilityTab`):

```ts
// Lunes de la semana visible — CLIENT-ONLY (null hasta el primer effect; el SSR en
// UTC desfasaría el lunes en TZ negativas). Navegación ‹ › / "Hoy".
const [weekStart, setWeekStart] = useState<Date | null>(null);
useEffect(() => { setWeekStart(startOfWeek(new Date())); }, []);

// Citas + slots de la semana visible.
const [appointments, setAppointments] = useState<AppointmentItem[]>([]);
const [freeSlots, setFreeSlots] = useState<AvailabilitySlot[]>([]);
const [loading, setLoading] = useState(true);
const [listError, setListError] = useState<string | null>(null);

// Token monotónico para descartar respuestas fuera de orden al navegar semanas.
const reqIdRef = useRef(0);
```

**Carga de la ventana** (mismo patrón fetch-token que `DoctorAvailabilityTab`/`OfficeClosuresTab`):

```ts
const loadWeek = useCallback(() => {
  if (!weekStart) return; // espera al primer effect client-only
  const reqId = ++reqIdRef.current;
  setLoading(true);
  setListError(null);
  const from = toIsoDate(weekStart); // "YYYY-MM-DD" del lunes
  const to = toIsoDate(addDays(weekStart, 6)); // domingo
  void load(from, to)
    .then((res) => {
      if (reqId !== reqIdRef.current) return; // respuesta superada → descartar
      setAppointments(res.appointments);
      setFreeSlots(res.free_slots);
      setLoading(false);
    })
    .catch(() => {
      if (reqId !== reqIdRef.current) return;
      setAppointments([]);
      setFreeSlots([]);
      setListError("No se pudo cargar el calendario. Intenta de nuevo.");
      setLoading(false);
    });
}, [weekStart, load]);

useEffect(() => { loadWeek(); }, [loadWeek]);
```

**Layout + TZ del branch** (el punto delicado):

- Columnas = Lun..Dom de `weekStart`, encabezado "Lun 12" (componer con `WEEKDAY_SHORT[i]` + día del mes de `addDays(weekStart, i)`; **no** usar `Date.getDay()` que es 0=domingo). Filas = `GRID_START_HOUR..GRID_END_HOUR` con paso `GRID_STEP_MIN` (de `calendar.ts` de staff).
- **Posicionar una cita**: `scheduled_for` es `timestamptz` UTC. Para ubicarla en la columna del día y el `top/height` correctos hay que expresarla en la **TZ del branch** (no la del navegador, no UTC): convertir `scheduled_for` a la hora local del branch con `Intl.DateTimeFormat(undefined, { timeZone: branchTimezone, ... })` (o `formatInTimeZone` si el template trae una util), derivar `day` (columna) y `minutes-since-midnight` (top) **en esa TZ**. La altura = `duration_min` escalado. **Esto es client-only** (depende de formateo de fecha) — la grilla entera es `"use client"`. Documentar como la decisión TZ central: *la grilla pinta en la TZ del branch, derivada por `Intl` con `timeZone`, nunca por `getHours()` del navegador.*
- **Color del bloque** = `status.color` del catálogo (badge/relleno); etiqueta dentro: `formatTimeInTZ(scheduled_for)` + `person_name` + `product_name`. Bloques en estados finales (CANCELLED/RESCHEDULED) se pueden atenuar o filtrar por un toggle de la toolbar.
- **Overlay de slots libres** (`freeSlots`, sólo si la toolbar tiene doctor+producto): franjas verdes tenues (token `colorPaletteGreenBackground2`) posicionadas igual (TZ del branch). Click → `onSlotClick?.(slot)` → abre `BookingWizardDrawer` prefilled. Read-only si `!canBook`.
- **Resaltar "hoy"**: la columna del día actual se resalta — el "hoy" se computa **client-only** (`isSameDay(addDays(weekStart,i), new Date())` con parseo local), nunca en SSR.

**Toolbar** (en `CalendarClient`, no en la grilla genérica): `Dropdown doctor_id` (obligatorio para ver slots), `Dropdown product_id` (habilita slots), `Dropdown branch_id` (acota), navegación ‹ semana › + "Hoy" + (opcional) salto a fecha (`Input type="date"` → `setWeekStart(startOfWeek(parseLocal(value)))`). Sin doctor/producto, la grilla **sólo pinta citas** (sin overlay de slots).

**Estados** (en español): loading → skeleton de la grilla; vacío → "No hay citas esta semana." (+ "Elige doctor y servicio para ver horarios disponibles." si falta el filtro de slots); error → `MessageBar`.

> <a name="reuse-self-vs-admin"></a>**Reuse self vs admin**: `CalendarClient` monta `<ScheduleGrid load={(from,to)=>getCalendar({from,to,doctorId,branchId,productId})} canBook={hasPermission("APPOINTMENTS_CREATE")} onSlotClick={openWizardPrefilled} onAppointmentClick={openDetail} />`. `MyAgendaClient` monta `<ScheduleGrid load={(from,to)=>getMyCalendar({from,to})} canBook={false} onAppointmentClick={openDetailReadonly} branchTimezone={...} />` (el doctor ve su agenda; sin overlay de reserva — el doctor no agenda; `MY_APPOINTMENTS_READ`). Misma UI, distinta capa de datos.

### `MyAgendaClient.tsx`

Vista del doctor logueado. Monta `<ScheduleGrid>` en modo self read (`load = getMyCalendar`, `canBook = false`) **más** una tabla "Mis próximas citas" (`listMyAppointments` con `useTableQuery`, `defaultSort` sobre columna real del query `/me` — confirmar con [`backend.md`](./backend.md#me) cuál es `scheduled_for`). Maneja el 403 `NOT_A_DOCTOR`: si `getMyCalendar`/`listMyAppointments` lanzan 403, mostrar estado vacío "Tu cuenta no tiene un perfil de doctor asociado." (no `notFound()`). El doctor con `APPOINTMENTS_TRANSITION` puede abrir el detalle de **su** cita y usar los shortcuts de su agenda (check-in/start/attend/no-show) — el scoping anti-IDOR lo aplica el service (`doctor_id == current.doctor.id`).

### `AppointmentStatusesClient.tsx`

Molde de crm `LeadStatusesClient` (catálogo + matriz). Diferencias:

- `useTableQuery`: `queryKey: "scheduling:statuses"`, `fetcher: listAppointmentStatuses`, `defaultSort: { field: "display_order", order: "asc" }` (**columna real**, coincide con el prefetch), `defaultPageSize: 50`, `searchFields: ["code", "name"]`.
- Columns: `actions`, `display_order`, `code`, `name`, `color` (swatch `style={{ backgroundColor: color }}`), `is_initial`/`is_final`/`is_active_attention` (badges "Inicial"/"Final"/"En atención"), `active`. **Sin `is_won`** (no aplica a citas).
- **RowActions**: Editar (gated `APPOINTMENT_STATUSES_WRITE`) → `AppointmentStatusDrawer`; Eliminar (gated `APPOINTMENT_STATUSES_WRITE`, danger). Error `APPOINTMENT_STATUS_IN_USE` (409) en `ConfirmDialog`/`MessageBar` ("No se puede eliminar: hay citas o historial usando este estado.").
- Botón "Nuevo estado" gated `APPOINTMENT_STATUSES_WRITE`.
- **Editor de matriz**: botón "Transiciones" por fila → abre `StatusMatrixEditor` (reusa el de crm con `getStatusTransitions`/`setStatusTransitions`).

### `AppointmentStatusDrawer.tsx`

Drawer create/edit. `useForm` con `appointmentStatusCreateSchema`/`appointmentStatusUpdateSchema`. Campos: `code` (solo create, disabled en edit), `name`, `description`, `color` (Input hex + swatch preview), `display_order`, y los **switches** `is_initial`/`is_final`/`is_active_attention`. Al marcar `is_initial` mostrar hint "Esto desmarcará el estado inicial actual." (`MULTIPLE_INITIAL_STATUS` 400 → `MessageBar`). **Sin `is_won`/sin refine** (diverge de crm). El `code` valida el `pattern` slug minúsculas en Zod (espeja el Pydantic).

### `StatusMatrixEditor.tsx`

Reusa el componente de crm. Recibe `statusId`, `allStatuses: AppointmentStatusOption[]`, carga `getStatusTransitions(statusId)` → preselecciona los `to.id` → multiselect (`SearchableOptionList`) con todos los estados **menos el propio** → guardar `setStatusTransitions(statusId, { to_ids })`. Estado terminal (`is_final`) → multiselect vacío/deshabilitado con hint "Estado final: sin transiciones de salida." MVP = multiselect por estado; la grilla visual from×to es diferible.

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| `PUT` para updates (no `PATCH`); shortcuts = `POST` sub-recursos | Alineación a catalog/clinic/staff/crm shipped. `/confirm`,`/check-in`,`/start`,`/attend`,`/no-show`,`/cancel`,`/reschedule`,`/transition` son `POST`. |
| `/active` para dropdowns (lista cruda) | Misma convención shipped; no se lee `.data`. |
| `revalidateTag(TAG, "max")` (2º arg) | Next 16 exige el 2º argumento; omitirlo es error. |
| Citas: wizard-de-creación + detalle = **drawer** (no página) | El detalle (estado + timeline + reschedule/cancel) cabe en un drawer; la lista y la grilla lo abren. (Diverge de Person/Office, que usan página de detalle, porque la cita tiene menos sub-recursos y se opera in-context.) |
| **Wizard de reserva de 4 pasos** con `computeAvailability` en el paso Slot | La reserva necesita validar disponibilidad on-the-fly (ADR-006); el wizard guía Paciente→Producto+Doctor→Slot→Confirmar. Bespoke en Fluent. |
| El wizard se reusa **prefilled** desde la grilla (click en slot libre) | Mismo componente; el slot fija cuándo/quién/dónde, el wizard sólo completa el paciente. |
| **`defaultSort`/`isSortable`/`searchFields` SOLO sobre columnas reales** | Lección `cd10c78`: ordenar/filtrar por `*_name` denormalizado da 400. `defaultSort = scheduled_for` (real); el client y el prefetch deben coincidir. Filtros del listado = `FilterCondition` sobre `status_id`/`doctor_id`/`office_id`/`branch_id`/`scheduled_for`/`product_id` (reales). |
| Búsqueda por paciente/doctor/servicio = **client-side** | Los `*_name` son denormalizados (no whitelistados). `useTableQuery.searchFields` busca sobre la página visible. |
| **`weekStart` de la grilla = client-only** (`useState(null)` + `useEffect`) | `new Date()` que define la semana → SSR en UTC desfasaría el lunes en Lima `-05:00`. La grilla y `mi-agenda`/`calendario` no prefetchan citas en el RSC; cargan por semana con fetch-token. |
| **El default de fecha del wizard = client-only** | Igual razón; el drawer es cliente, `fromDate = toIsoDateLocal(new Date())` en `useEffect`. |
| **La grilla pinta en la TZ del branch** (vía `Intl` con `timeZone`) | `scheduled_for` es UTC; el día/hora del bloque se derivan en `branch.timezone`, nunca con `getHours()` del navegador ni en UTC (lección TZ: nunca derivar el día desde UTC). |
| Fechas-puro (`from_date`/`to_date`/columna del día) se parsean como **local** | `new Date(\`${d}T00:00:00\`)`, nunca como UTC (desfase de medianoche). |
| `scheduled_for` del slot se pasa **tal cual** (no se re-construye) | `AvailabilitySlot.starts_at` ya es un instante absoluto del backend; sólo se serializa. |
| Agrupación del timeline/slots "hoy/ayer" = client-only | `new Date()` que afecta render = client-only (igual que el timeline de crm). |
| **fetch-token** en grilla y paso Slot del wizard | Navegar semana / cambiar doctor-producto rápido no debe dejar que una respuesta vieja pise la nueva (idéntico a `DoctorAvailabilityTab`/`OfficeClosuresTab`). |
| `StatusControl` ofrece SOLO destinos permitidos por la matriz | `getStatusTransitions(status.id)` resuelve las aristas; previene `APPOINTMENT_TRANSITION_NOT_ALLOWED`. Estado terminal → controles deshabilitados. Shortcuts nombrados + genérico, ambos contra la misma matriz. |
| `attend`/`cancel`/`reschedule` revalidan tags de **crm** (cross-módulo) | attend→promote escribe customer/lead/activity; cancel/reschedule emiten `LeadActivity`. El action invalida `crm:*:{personId}` + `crm:persons` (aditivo; lo pide el TODO de crm). |
| `cancel` override = decidido por el **backend** por permiso, no flag del front | `CANCEL_TOO_LATE` salvo `APPOINTMENTS_CANCEL_OVERRIDE`; la UI avisa si el actor tiene override pero no manda un flag. |
| Doctor `active=false` excluido de nuevas reservas (decisión #3) | El wizard/compute no ofrece doctores inactivos; el backend devuelve `DOCTOR_INACTIVE`. Diverge de staff (donde `active` no era gate de auto-gestión). |
| `availability.actions.ts` NO revalida tags (lecturas on-the-fly) | `compute`/`check-slot` no persisten (ADR-006); `cache: "no-store"`. Caching Redis diferido (MVP). |
| Tag por-cita (`scheduling:appointment:{id}`) + global + cross-módulo crm | El detalle de una cita es independiente; el global cubre lista/grilla/`/me`. |
| `StatusBadge` usa el `color` del catálogo (hex BD), no `brandPalette` | `brandPalette` no tiene `accent`; el color del estado es configurable en BD. Otros colores (overlay de slots) → tokens Fluent semánticos. |
| `from-bot`/`cancel-from-bot` NO en el `ENDPOINTS` del front | Los consume el motor de bots server-side (SYSTEM); el front nunca los llama. |
| `calendar.ts` se REUSA del módulo staff | `GRID_*`/`WEEKDAY_SHORT`/`timeToMinutes` ya existen; no duplicar. |
| Sin bulk actions, sin duplicar, sin import CSV | Postergados al MVP+1 (igual que catalog/clinic/staff/crm). |

## Checklist de implementación (mapeado a fases F0–F5)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md#checklist-de-implementación) y [`ui.md`](./ui.md). Cada checkbox es lado frontend.

### F0 — Prep (andamiaje compartido)

- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `SCHEDULING` (`APPOINTMENT_STATUSES`, `AVAILABILITY`, `APPOINTMENTS` con nested transitions/shortcuts, `ME_SCHEDULING`). Verbos `PUT`, rutas `/active`, shortcuts `POST`. **No** incluir `from-bot`/`cancel-from-bot`.
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `scheduling` ("Agenda" → Citas `APPOINTMENTS_READ`, Calendario `APPOINTMENTS_READ`, Estados de cita `APPOINTMENT_STATUSES_READ`, Mi agenda `MY_APPOINTMENTS_READ`; grupo gated `MENU-SCHEDULING`).
- [ ] Registrar íconos `CalendarLtrRegular`/`CalendarClockRegular`/`CalendarWeekStartRegular`/`TagRegular`/`PersonClockRegular` en el `iconMap` del `Sidebar.tsx` (con fallbacks verificados).
- [ ] Crear `src/types/scheduling.types.ts` (TODAS las interfaces + enums `AppointmentSource`/`CheckSlotReason`; reusa `UserAuditInfo`/`DoctorOption`/`BranchOption`/`PersonOption`/`ProductOption`).
- [ ] Crear `src/lib/constants/scheduling.ts` (`APPOINTMENT_SOURCE_META`, `CHECK_SLOT_REASON_LABELS`). Confirmar que `src/lib/constants/calendar.ts` (de staff) ya existe y se reusa.
- [ ] Crear los skeletons inertes de las 4 páginas (placeholders) — registrar las rutas sin lógica. (Traducción ya hecha.)
- [ ] **Permisos test (F0)**: con `MENU-SCHEDULING` (rol ASESOR/DOCTOR) el grupo "Agenda" aparece con sus items según permisos finos; el DOCTOR no ve "Estados de cita". Sin `MENU-SCHEDULING`, el grupo no aparece. (Los 13 permisos + roles ya están en `seed.py` — ver [`../_seed-and-roles.md`](../_seed-and-roles.md); los introduce backend F0.)

### F1 — AppointmentStatus + matriz

- [ ] Crear `src/lib/schemas/appointment-status.schema.ts` (`code` slug minúsculas, sin `is_won`, con `is_active_attention`; `transitionTargetsSchema`).
- [ ] Crear `src/actions/appointment-status.actions.ts` (CRUD + active + getTransitions/setTransitions; tag `scheduling:statuses`).
- [ ] Crear `src/app/(main)/scheduling/estados/page.tsx` (`metadata.title = "Estados de cita"`, prefetch `defaultSort = display_order`, `limit: 50`) + `_components/AppointmentStatusesClient.tsx` (`defaultPageSize: 50`) + `AppointmentStatusDrawer.tsx` + `StatusMatrixEditor.tsx` (reusa el de crm).
- [ ] **Smoke test (F1)**: `/scheduling/estados` muestra los 8 estados seed con swatch + badges (Inicial/Final/En atención). Crear estado, editar color/orden, eliminar (uno sin uso). Abrir el `StatusMatrixEditor` de "Agendada" → preselecciona Confirmada/En recepción/No asistió/Cancelada/Reagendada → cambiar → guardar → recargar persiste.
- [ ] **Validación test (F1)**: `code` con mayúsculas/espacios → error inline Zod en español; 2º `is_initial` → `MULTIPLE_INITIAL_STATUS` (400) en `MessageBar`; eliminar estado en uso → `APPOINTMENT_STATUS_IN_USE` (409).
- [ ] **Permisos test (F1)**: con `APPOINTMENT_STATUSES_READ` sin `_WRITE`, la tabla se ve pero sin "Nuevo estado"/Editar/Eliminar ni editor de matriz editable.

### F2 — Appointment + availability + booking (la fase MÁS pesada)

- [ ] Crear `src/lib/schemas/appointment.schema.ts` (`availabilityRequestSchema`, `bookingWizardSchema`, `appointmentUpdateSchema`, `appointmentTransitionSchema`, `appointmentCancelSchema`, `appointmentRescheduleSchema`).
- [ ] Crear `src/actions/availability.actions.ts` (`computeAvailability`/`checkSlot`, `cache: "no-store"`, sin tags) y `src/actions/appointment.actions.ts` (list/get/create/update + calendar + transición + 7 shortcuts + cancel/reschedule + `/me`; tags `scheduling:appointments`/`scheduling:appointment:{id}` + cross crm).
- [ ] Crear `src/app/(main)/scheduling/citas/page.tsx` (`metadata.title = "Citas"`, prefetch `defaultSort = scheduled_for`, dropdowns de filtro; deep-link `?doctor_id=`/`?status_id=`/`?office_id=`/`?branch_id=`/`?product_id=`/`?date=` → `FilterCondition` columnas reales) + `_components/AppointmentsClient.tsx` (tabla denormalizados NO sortables, búsqueda client-side, filtros chip).
- [ ] Crear `_components/BookingWizardDrawer.tsx` + `WizardStepPerson`/`WizardStepServiceDoctor`/`WizardStepSlot`/`WizardStepConfirm` (paso Slot llama `computeAvailability`, fetch-token, `fromDate` client-only, slots agrupados por día client-only).
- [ ] Crear `_components/AppointmentDetailDrawer.tsx` (carga `getAppointment`, cabecera + editar no-estado; tabs/botones de lifecycle = placeholders hasta F3).
- [ ] **Smoke test (F2)**: `/scheduling/citas` → "Nueva cita" → Paciente → Producto+Doctor+Sede+Consultorio → paso Slot computa y lista horarios → elegir uno → Confirmar → cita creada → aparece en la lista con badge "Agendada". Abrir detalle → cabecera correcta.
- [ ] **Filtro/deep-link test (F2)**: `/scheduling/citas?doctor_id=X&date=2026-06-10` filtra + chips; ✕ limpia. **Verificar que NO se ordene por columna denormalizada** (no rompe a 400).
- [ ] **Invariantes test (F2)**: reservar un slot ya tomado (dos pestañas / concurrencia) → `SLOT_TAKEN` (400) en `MessageBar` del wizard sin cerrar; doctor inactivo no aparece como opción / `DOCTOR_INACTIVE`; producto sin vertical del doctor → sin slots o `DOCTOR_NOT_APT_FOR_VERTICAL`. Todos en español.
- [ ] **TZ test (F2)**: con `fromDate` cerca de medianoche en Lima (`-05:00`), el paso Slot agrupa los horarios bajo el día correcto (client-only), no desfasado a UTC.
- [ ] **Permisos test (F2)**: sin `APPOINTMENTS_CREATE` no aparece "Nueva cita"; sin `APPOINTMENTS_UPDATE` la edición no-estado del detalle está disabled; sin `APPOINTMENTS_READ` el RSC del listado redirige.

### F3 — Lifecycle + audit

- [ ] Implementar `AppointmentStatusControl.tsx` (shortcuts gated por matriz `getStatusTransitions` + genérico `transitionAppointment`), `RescheduleDialog.tsx` (re-corre Slot, excluye la vieja), `CancelDialog.tsx` (reason + `CANCEL_TOO_LATE`/override), `AppointmentTimeline.tsx` (status_history + change_log entrelazados, agrupación client-only).
- [ ] **Smoke test (F3)**: en una cita "Agendada" → Confirmar → "Confirmada"; check-in → "En recepción"; start → "En atención" (badge marca is_active_attention); attend → "Atendida" **y** la persona se promueve a cliente (verificar en `/crm/personas/{id}` tab Cliente, sin refresh manual gracias al cross-tag). Cancelar dentro de la ventana sin override → `CANCEL_TOO_LATE`; con override → cancela. Reagendar una "Agendada" → la vieja queda "Reagendada", nace una nueva con `previous_appointment_id`. Timeline muestra todos los cambios.
- [ ] **Matriz test (F3)**: el `StatusControl` sólo ofrece destinos permitidos; estado final deshabilita acciones; si la matriz cambió, `APPOINTMENT_TRANSITION_NOT_ALLOWED` (400) en `MessageBar`.
- [ ] **attend→promote test (F3)**: atender la cita de una persona que NO es cliente → se crea customer is_initial + cierra el lead is_won (si la matriz crm lo permite) + emite `APPOINTMENT_ATTENDED`; atender la de una persona que YA es cliente → no-op CRM + sólo `APPOINTMENT_ATTENDED`. Ambos en la misma transacción.
- [ ] **Permisos test (F3)**: sin `APPOINTMENTS_TRANSITION` los shortcuts de estado no aparecen; sin `APPOINTMENTS_CANCEL` no aparece Cancelar; sin `APPOINTMENTS_RESCHEDULE` no aparece Reagendar; sin `APPOINTMENTS_CANCEL_OVERRIDE` la cancelación tardía falla con `CANCEL_TOO_LATE`.

### F4 — Calendar grid + Mi agenda

- [ ] Crear `_components/ScheduleGrid.tsx` (grilla bespoke: citas como bloques color-estado + overlay de slots libres; `weekStart` client-only, posicionamiento en TZ del branch vía `Intl`, fetch-token, navegación de semana, "hoy" client-only).
- [ ] Crear `src/app/(main)/scheduling/calendario/page.tsx` (`metadata.title = "Calendario"`, sólo catálogos prefetch; NO citas en RSC) + `_components/CalendarClient.tsx` (toolbar doctor/producto/sede/semana, monta `<ScheduleGrid load={getCalendar}>`, click slot → wizard prefilled, click cita → detalle).
- [ ] Crear `src/app/(main)/scheduling/mi-agenda/page.tsx` (`metadata.title = "Mi agenda"`, `requirePermission("MY_APPOINTMENTS_READ")`) + `_components/MyAgendaClient.tsx` (monta `<ScheduleGrid load={getMyCalendar} canBook={false}>` + tabla "Mis próximas citas"; maneja 403 `NOT_A_DOCTOR` como estado vacío).
- [ ] **Smoke test (F4)**: `/scheduling/calendario` → elegir doctor + servicio → la grilla pinta las citas de la semana (color por estado) + overlay de slots libres → click en un slot libre → abre el wizard prefilled (sólo pide paciente) → confirmar → la cita aparece en la grilla. Navegar ‹ › semanas (fetch-token correcto). `/scheduling/mi-agenda` como doctor → ve su agenda read-only.
- [ ] **TZ test (F4)**: una cita a las 23:30 hora Lima de un branch en `America/Lima` se pinta en el día correcto y la fila ~23:30 (no desfasada a UTC ni a la TZ del navegador si difiere). Resaltado de "hoy" en el día correcto.
- [ ] **Scoping test (F4)**: el DOCTOR en "Mi agenda" sólo ve sus propias citas (service filtra por `doctor_id == current.doctor.id`); no puede ver/abrir citas de otro doctor (anti-IDOR).
- [ ] **Permisos test (F4)**: sin `APPOINTMENTS_READ` el RSC del calendario redirige; sin `APPOINTMENTS_CREATE` el overlay de slots no es clickeable (read-only); sin `MY_APPOINTMENTS_READ` "Mi agenda" no se ve y su RSC redirige.

### F5 — Bot facade + tools (cierra el loop)

> **Sin trabajo de frontend de UI**: F5 registra `book_from_bot`/`cancel_from_bot` + las 3 tools en el motor de bots (backend). El front **no** expone `from-bot`/`cancel-from-bot` (los consume el motor server-side). El único impacto frontend posible es que las citas creadas por el bot aparezcan con `source: "bot"` en la lista/grilla/timeline — ya cubierto por `APPOINTMENT_SOURCE_META.bot = "Bot"`.

- [ ] **Verificación cross-módulo (F5)**: una cita creada por el bot (vía tool `book_appointment`) aparece en `/scheduling/citas` con badge de origen "Bot" y en la grilla; su timeline muestra el cambio inicial con actor "Sistema". Una cancelación por bot (`cancel_appointment`) respeta `min_hours_to_cancel` (el bot NO hace override). El timeline crm de la persona muestra `APPOINTMENT_BOOKED`/`APPOINTMENT_CANCELLED` (emitidos por el bot facade).

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog**. Para `scheduling` no hay deuda de traducción del template — todos los strings nuevos nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Citas", "Calendario", "Estados de cita", "Mi agenda").
- [ ] Todos los `label` de `NAV_ITEMS.scheduling` en español ("Agenda", "Citas", "Calendario", "Estados de cita", "Mi agenda").
- [ ] Empty states, placeholders, badges (estados de cita por nombre del catálogo + Inicial/Final/En atención; origen Bot/Asesor/Administración), copy del wizard ("Buscar disponibilidad", "No hay horarios disponibles", "Confirmar reserva"), confirm dialogs y `MessageBar` en español (ver tabla de copy en [`ui.md`](./ui.md#texto-ux-writing)).
- [ ] Mensajes de error de dominio que vienen del backend ya en español (`OFFICE_NOT_IN_BRANCH`, `OFFICE_NOT_APT_FOR_VERTICAL`, `DOCTOR_NOT_IN_BRANCH`, `DOCTOR_NOT_APT_FOR_VERTICAL`, `SLOT_TAKEN`, `OFFICE_SLOT_TAKEN`, `NO_AVAILABILITY_BLOCK`, `OFFICE_CLOSED`, `CANCEL_TOO_LATE`, `DOCTOR_INACTIVE`, `APPOINTMENT_TRANSITION_NOT_ALLOWED`, `MULTIPLE_INITIAL_STATUS`, `APPOINTMENT_STATUS_IN_USE`) — los `detail` se devuelven en español para mostrarse directo; el `code` queda en inglés (coordinar con [`backend.md`](./backend.md#códigos-de-error)).

## TODOs deliberados (postergados al MVP+1)

- [ ] **Drag en la grilla** (crear cita arrastrando, mover/redimensionar bloques) — el MVP usa click→wizard. Diferir (igual que el drag de `DoctorAvailabilityTab`).
- [ ] **Guía de fondo en la grilla** (banda del `OfficeOperatingHours` + franjas de `OfficeClosure` como contexto visual) — refinamiento; el overlay de slots libres ya comunica disponibilidad.
- [ ] **Vista día/mes** del calendario (el MVP es semana). Diferir.
- [ ] **Grilla visual from×to** del editor de matriz — el MVP usa multiselect por estado (reusado de crm).
- [ ] **Resolver `change_log` FK a nombres** (mostrar "Doctor: Juan → Pedro" en vez de UUIDs) — el backend tendría que denormalizar previous/new value; hoy se muestra el valor serializado o "(referencia)".
- [ ] **Crear paciente desde el wizard** (paso Paciente) — el MVP linkea a `/crm/personas`; si el negocio lo pide, embeber un mini-create o `find_by_identifier_or_create`.
- [ ] **Cache Redis de `compute_available_slots`** (TTL 30-60s) — diferido (ADR-006); el front re-computa al re-entrar al paso Slot.
- [ ] **Lista de espera / waitlist** (notificar si un slot popular se cancela) — postergado (del `scheduling.md` plano).
- [ ] **Vista responsive** del calendario y de la tabla de citas — el MVP asume desktop.
- [ ] **i18n framework** — por ahora strings literales en español directo (mismo criterio que catalog/clinic/staff/crm).
