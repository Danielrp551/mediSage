# Módulo `staff` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-05-29
> **Audiencia**: developer implementando `frontend/src/.../staff/`.
> **Pre-requisito**: leer [`README.md`](README.md), [`backend.md`](backend.md), [`ui.md`](ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), y como molde de referencia el frontend de [`../clinic/frontend.md`](../clinic/frontend.md) (módulo completo en prod del que `staff` copia patrones).

> **Contrato autoritativo**: este doc respeta la [spec compartida de staff](README.md) — nombres de entidades, campos, endpoints, permisos y códigos de error son **vinculantes** y deben coincidir con `backend.md` y `ui.md`. Donde haya tensión, manda la spec.

> **Alineación con clinic + catalog (shipped)**, dos convenciones heredadas que el lector debe tener presentes desde ya:
> 1. **Verbos HTTP**: los updates completos usan **`PUT`** (no `PATCH`). El overview viejo de `staff.md` decía `PATCH`; se alinea a la convención shipped (`branch.actions.ts`/`vertical.actions.ts` ya usan `backendClient.put(...)`).
> 2. **Dropdowns**: los endpoints de "lista plana de activos" se llaman **`/active`** (no `/options`). El overview viejo decía `/doctors/options`; se alinea a `/doctors/active?branch_id=&vertical_id=`.
> 3. **Detalle de Doctor = página dedicada** `/staff/doctors/{id}` con tabs (Perfil · Disponibilidad · Auditoría), **no** un drawer — exactamente el patrón "entidad con sub-recursos" que estrenó el detalle de Office en clinic. La **lista** de doctores conserva un drawer de creación; ver/editar uno navega a su página de detalle.

> **Cambio de modelo vs el overview viejo** (crítico): la disponibilidad **ya no** es patrón semanal recurrente (`DoctorAvailabilityPattern`) + excepciones (`DoctorAvailabilityOverride`). Es **una sola entidad `DoctorAvailability` de bloques concretos por fecha** (sin recurrencia, sin `day_of_week`, sin `is_available`). Implicancia frontend: no hay "tab Horarios bulk-PUT" + "tab Excepciones CRUD" como en clinic; hay **un solo tab "Disponibilidad" = grilla semanal tipo calendario** que pinta y persiste bloques fechados. Ver [`README.md`](README.md#cambio-vs-lo-documentado-importante) y [`ui.md`](ui.md).

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── staff.types.ts                   ← Doctor*, DoctorAvailability* (reusa BranchOption/VerticalOption/UserAuditInfo)
├── lib/
│   ├── schemas/
│   │   ├── doctor.schema.ts             ← doctorCreate (nested user) + doctorUpdate
│   │   └── doctor-availability.schema.ts ← bloque (closes>opens) + bulk (no-overlap por día)
│   └── constants/
│       ├── endpoints.ts                 ← EXTEND con DOCTORS + DOCTOR availability + ME
│       ├── navigation.ts                ← EXTEND con grupo 'Staff'
│       └── calendar.ts                  ← NUEVO: grano de la grilla (horas visibles, paso, etiquetas día)
├── actions/
│   ├── doctor.actions.ts
│   ├── doctor-availability.actions.ts   ← admin (por doctor): list/create/update/deleteDoctorAvailability
│   └── me.actions.ts                    ← F3 self-service: getMyDoctor/updateMyDoctor + list/create/update/deleteMyAvailability
└── app/(main)/staff/
    ├── doctors/
    │   ├── page.tsx                     ← LISTA de doctores (drawer de creación)
    │   ├── _components/
    │   │   ├── DoctorsClient.tsx
    │   │   └── DoctorCreateDrawer.tsx   ← solo create (NESTED user+doctor); ver/editar navega al detalle
    │   └── [id]/
    │       ├── page.tsx                 ← PÁGINA DE DETALLE con tab routing
    │       └── _components/
    │           ├── DoctorDetailShell.tsx
    │           ├── DoctorProfileTab.tsx
    │           ├── DoctorAvailabilityTab.tsx   ← la grilla semanal (la pieza más pesada del proyecto)
    │           └── DoctorAuditTab.tsx
    └── me/                              ← F3 — self-service del doctor logueado
        ├── perfil/
        │   ├── page.tsx                 ← "Mi perfil"
        │   └── _components/MyProfileClient.tsx
        └── agenda/
            ├── page.tsx                 ← "Mi agenda"
            └── _components/MyAvailabilityClient.tsx
```

> **Por qué no hay `staff/layout.tsx`**: igual que en catalog/clinic — `doctors` (lista) y las páginas `me/*` son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El detalle del doctor sí tiene un shell propio (`DoctorDetailShell`), pero es un **componente cliente** dentro de `[id]/page.tsx`, no un `layout.tsx` de ruta — los tabs viven en una sola URL, no en sub-rutas (mismo criterio que `OfficeDetailShell`).

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas. Mantiene componentes locales colocados con su page.

> **Sobre `loading.tsx`**: catalog y clinic shipped **no** incluyeron `loading.tsx` (el `DataTable` ya renderiza su propio skeleton vía `isLoading`). `staff` sigue ese mismo criterio. El estado de carga del detalle del doctor se maneja dentro de los tabs (la grilla de disponibilidad tiene su propio skeleton). No se crean `loading.tsx`.

> **`me/` reusa, no duplica**: `MyAvailabilityClient` (F3) **monta el mismo componente de grilla** que `DoctorAvailabilityTab` (F2) en modo self — la grilla es genérica respecto al "de quién es la agenda"; sólo cambian las server actions que llama (`/me/...` en vez de `/doctors/{id}/...`) y el permiso que la pone read-only. Ver [DoctorAvailabilityTab](#doctoravailabilitytabtsx--la-grilla-semanal).

## Tipos TS — `types/staff.types.ts`

Espejo de los Pydantic schemas del backend (ver [`backend.md`](backend.md#schemas-pydantic-v2-variantes-createupdateitemdetailoption)). Importable desde server actions y client components. **Reusa** `BranchOption` de `clinic.types.ts`, `VerticalOption` de `catalog.types.ts` y `UserAuditInfo` de `audit.types.ts` — no se redefinen.

```ts
import type { UserAuditInfo } from "./audit.types";
import type { VerticalOption } from "./catalog.types";
import type { BranchOption } from "./clinic.types";

// ── Doctor ──────────────────────────────────────────────

// Fila de listado. El backend DENORMALIZA full_name/email del User (evita join
// en la tabla) y los counts del M:N (mismo patrón que OfficeItem.verticals_count).
export interface DoctorItem {
  id: string;
  user_id: string;
  full_name: string; // denormalizado del User
  email: string; // denormalizado del User
  cmp_code: string | null;
  slot_duration_min: number; // default 30
  active: boolean;
  branches_count: number; // denormalizado — # de sedes asignadas
  verticals_count: number; // denormalizado — # de verticales cubiertas
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// El detalle agrega bio/foto/firma + el user resuelto + las dos relaciones M:N
// expandidas. `user` viaja como UserAuditInfo (id/full_name/email basta para el
// header de solo-lectura del perfil).
export interface DoctorDetail extends DoctorItem {
  bio: string | null;
  photo_url: string | null;
  signature_url: string | null;
  user: UserAuditInfo;
  branches: BranchOption[]; // sedes vivas; soft-deleted filtradas server-side
  verticals: VerticalOption[]; // verticales vivas; soft-deleted filtradas server-side
}

// Para dropdowns (selección de un doctor en scheduling/crm a futuro).
export interface DoctorOption {
  id: string;
  full_name: string;
  cmp_code: string | null;
}

// Payload anidado del User al crear un doctor (espejo del UserCreate del admin,
// SIN role_ids/permission_ids — el service le asigna el role DOCTOR). Si falta
// `password`, el backend lo genera y lo devuelve en `generated_password`.
export interface DoctorUserCreatePayload {
  email: string;
  first_name: string;
  last_name: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  phone?: string | null;
  password?: string;
}

export interface DoctorCreatePayload {
  user: DoctorUserCreatePayload; // NESTED — crea User + Doctor en una transacción
  cmp_code?: string | null;
  bio?: string | null;
  photo_url?: string | null;
  signature_url?: string | null;
  slot_duration_min?: number; // default 30
  branch_ids: string[]; // M:N doctor_branch al crear
  vertical_ids: string[]; // M:N doctor_vertical al crear
}

// La respuesta del POST /doctors espeja UserCreatedResponse: devuelve el detalle
// + la contraseña temporal SI se generó (null si el admin la escribió).
export interface DoctorCreatedResponse {
  data: DoctorDetail;
  generated_password: string | null;
}

// user_id es INMUTABLE post-create → NO está en el update. branch_ids/vertical_ids
// presentes = REEMPLAZO TOTAL del M:N (mismo contrato que office.vertical_ids).
export interface DoctorUpdatePayload {
  cmp_code?: string | null;
  bio?: string | null;
  photo_url?: string | null;
  signature_url?: string | null;
  slot_duration_min?: number;
  branch_ids?: string[]; // si presente, reemplaza doctor_branch entero
  vertical_ids?: string[]; // si presente, reemplaza doctor_vertical entero
  active?: boolean;
}

// ── DoctorAvailability (bloque concreto por fecha) ──────
// NO hay day_of_week, NO hay is_available, NO hay recurrencia. Un bloque = un
// rango horario en UNA fecha concreta, en (branch, office).

export interface DoctorAvailabilityItem {
  id: string;
  doctor_id: string;
  branch_id: string;
  branch_name: string; // denormalizado — render sin join
  office_id: string;
  office_code: string; // denormalizado
  office_name: string; // denormalizado
  date: string; // "YYYY-MM-DD" (Date sin TZ; se interpreta en branch.timezone)
  opens_at: string; // "HH:MM" local time (Time sin TZ) — NO pasa por new Date()
  closes_at: string; // "HH:MM"; backend CHECK closes_at > opens_at
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Un bloque a crear (sin doctor_id — viaja en la URL).
export interface DoctorAvailabilityCreatePayload {
  branch_id: string;
  office_id: string;
  date: string; // "YYYY-MM-DD"
  opens_at: string; // "HH:MM"
  closes_at: string; // "HH:MM"
}

// Alta masiva: el body del POST. "Llenar varios a la vez" (arrastrar el mismo
// horario sobre varios días, o el form de Agregar disponibilidad).
export interface DoctorAvailabilityBulkCreatePayload {
  blocks: DoctorAvailabilityCreatePayload[];
}

// Editar un bloque (mover/redimensionar). Todos los campos opcionales.
export interface DoctorAvailabilityUpdatePayload {
  branch_id?: string;
  office_id?: string;
  date?: string;
  opens_at?: string;
  closes_at?: string;
}
```

> **Nota sobre las dos clases de tiempo** (igual que clinic, ver [`README.md`](README.md#convenciones-heredadas-repetir-en-las-fichas)):
> - `DoctorAvailability.date` → `Date` **sin TZ**, viaja como `"YYYY-MM-DD"`. La grilla la ubica en la columna del día. **No** se construye con `new Date(date)` para comparar contra "hoy" salvo cuidando el desfase de medianoche (parsear como local: `new Date(`${date}T00:00:00`)`).
> - `DoctorAvailability.opens_at/closes_at` → `Time` **sin TZ**, viajan como `"HH:MM"`. La UI los muestra tal cual y los posiciona en la grilla por minutos-desde-medianoche; se interpretan en `branch.timezone`. **No** se pasan por `new Date()`.
> - Las columnas de auditoría (`created_on`, `updated_on`) sí son `timestamptz` ISO 8601 → se formatean con `lib/utils/date.ts` (`formatDate`).

> **Por qué `DoctorItem` denormaliza `full_name`/`email`**: el listado de doctores no quiere un join contra `user` por fila. El backend los copia en el `Item` (mismo criterio que `OfficeItem.branch_name`). Implicancia de cache: renombrar/editar el User correspondiente deja stale ese denormalizado — lo cubre el tag `staff:doctors` (ver [Server Actions](#server-actions)); como el User se edita en el módulo `admin` (no aquí), el back-port honesto es invalidar `staff:doctors` desde el `updateUser` del admin sólo si se quiere consistencia inmediata. Por ahora es eventual (se refleja al recrear cache). Documentado como TODO.

## Zod schemas

### `lib/schemas/doctor.schema.ts`

El create lleva un **payload anidado `user`** — se reaprovecha la forma del `userCreateSchema` del admin para la parte de user (mismas reglas de documento, mismos límites), **sin** `role_ids`/`permission_ids` (el service asigna el role DOCTOR). El `password` es opcional (si falta, el backend lo genera).

```ts
import { z } from "zod";

import { CODE_SLUG_REGEX } from "./vertical.schema"; // (no se usa para cmp_code; ver nota)
import { DOCUMENT_RULES, DOCUMENT_TYPES, type DocumentType } from "./user.schema";

// ── Parte "user" anidada (espejo del admin userCreateSchema, sin RBAC) ──

// Reusa el refinamiento de documento del admin (cuando type Y number vienen,
// el number debe matchear el formato del type). Idéntico a refineDocument.
function refineDoctorUserDocument<
  T extends { document_type?: DocumentType | null; document_number?: string | null },
>(data: T, ctx: z.RefinementCtx): void {
  const type = data.document_type;
  const number = data.document_number?.trim();
  if (!type || !number) return;
  const rule = DOCUMENT_RULES[type];
  if (!rule.regex.test(number)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["user", "document_number"], // path anidado para que el form lo encuentre
      message: rule.message,
    });
  }
}

const doctorUserSchema = z.object({
  email: z.string().email("Correo inválido"),
  first_name: z.string().min(1, "Obligatorio").max(80, "Máximo 80 caracteres"),
  last_name: z.string().min(1, "Obligatorio").max(80, "Máximo 80 caracteres"),
  second_last_name: z.string().max(80).optional().nullable(),
  document_type: z.enum(DOCUMENT_TYPES).optional().nullable(),
  document_number: z.string().max(40).optional().nullable(),
  phone: z.string().max(40).optional().nullable(),
  // Opcional: si el admin lo deja vacío, el backend genera una contraseña
  // temporal y la devuelve en generated_password (igual que admin.user.create).
  password: z.string().min(8, "Mínimo 8 caracteres").max(128).optional().or(z.literal("")),
});

// ── Campos propios del Doctor ──

const doctorProfileBase = z.object({
  // CMP es texto libre acotado (Colegio Médico u homólogo); NO es un slug.
  cmp_code: z.string().max(40, "Máximo 40 caracteres").nullable().optional(),
  bio: z.string().max(5000).nullable().optional(),
  photo_url: z.string().url("URL inválida").max(500).nullable().optional().or(z.literal("")),
  signature_url: z.string().url("URL inválida").max(500).nullable().optional().or(z.literal("")),
  slot_duration_min: z
    .number({ invalid_type_error: "Número en minutos" })
    .int("Entero")
    .min(5, "Mínimo 5 minutos")
    .max(240, "Máximo 240 minutos")
    .default(30),
});

export const doctorCreateSchema = doctorProfileBase.extend({
  user: doctorUserSchema.superRefine(refineDoctorUserDocument),
  branch_ids: z.array(z.string()).min(1, "Elige al menos una sede"),
  vertical_ids: z.array(z.string()).min(1, "Elige al menos una vertical"),
});

// Update: NO incluye `user` (el user se gestiona en admin) ni `user_id` (inmutable).
// branch_ids/vertical_ids opcionales: presentes = full replace del M:N.
export const doctorUpdateSchema = doctorProfileBase.partial().extend({
  branch_ids: z.array(z.string()).optional(),
  vertical_ids: z.array(z.string()).optional(),
  active: z.boolean().optional(),
});

export type DoctorCreateInput = z.infer<typeof doctorCreateSchema>;
export type DoctorUpdateInput = z.infer<typeof doctorUpdateSchema>;
```

> **`cmp_code` NO es un slug**: a diferencia de `code` en branch/office, `cmp_code` es el número del Colegio Médico (texto libre, nullable para no-médicos). No reusar `CODE_SLUG_REGEX`. La unicidad/forma no se valida en Zod más allá del largo; el backend lo indexa pero no exige unicidad estricta. (El import de `vertical.schema` arriba se deja sólo si se reutiliza algo más; quitarlo si no.)

> **`branch_ids`/`vertical_ids` con `min(1)` en create, opcionales en update**: en create el front empuja a elegir al menos una sede y una vertical (un doctor sin sede no puede recibir disponibilidad — invariante #2 del backend lo rechazaría). En update son opcionales porque su ausencia = "no tocar el M:N"; cuando vienen, reemplazan el set entero (mismo contrato que `office.vertical_ids`). El backend valida que existan y estén vivos (400 si no).

> **`user_id` inmutable post-create**: no aparece en `doctorUpdateSchema`. La relación 1:1 con el User no se reasigna (ADR-002). El `DoctorProfileTab` muestra email/nombre del user como **solo-lectura**.

### `lib/schemas/doctor-availability.schema.ts`

Dos schemas: el de un bloque (`closes_at > opens_at`) y el de alta masiva (`blocks: [...]`) que además valida **no-solapamiento por fecha** — **espeja el invariante #3 del backend** (`AVAILABILITY_OVERLAP`) para prevenir el 422 en cliente, en español.

```ts
import { z } from "zod";

// "HH:MM" 24h, 00:00–23:59. Stored as `time` (no TZ) on the backend.
export const TIME_HHMM_REGEX = /^([01]\d|2[0-3]):[0-5]\d$/;
// "YYYY-MM-DD". Stored as `date` (no TZ) on the backend.
export const DATE_ISO_REGEX = /^\d{4}-\d{2}-\d{2}$/;

const timeField = z.string().regex(TIME_HHMM_REGEX, "Hora como HH:MM (24h)");
const dateField = z.string().regex(DATE_ISO_REGEX, "Fecha como AAAA-MM-DD");

// Un bloque concreto. Mirror del model_validator del backend (closes>opens) y de
// los FK obligatorios (branch_id/office_id). El emparejamiento office↔branch y el
// doctor↔branch son invariantes de service (OFFICE_NOT_IN_BRANCH / DOCTOR_NOT_IN_BRANCH),
// no validables en Zod (cruzan datos): se muestran como error de servidor.
export const doctorAvailabilityBlockSchema = z
  .object({
    branch_id: z.string().min(1, "Elige una sede"),
    office_id: z.string().min(1, "Elige un consultorio"),
    date: dateField,
    opens_at: timeField,
    closes_at: timeField,
  })
  .superRefine((block, ctx) => {
    // Un bloque nunca cruza medianoche; si hiciera falta, se modela como dos
    // bloques en dos fechas. Espeja el CHECK ck_doctor_availability_closes_after_opens.
    if (block.closes_at <= block.opens_at) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["closes_at"],
        message: "La hora de cierre debe ser mayor que la de apertura.",
      });
    }
  });

// Alta masiva. Permite varios bloques (mismo doctor) repartidos en varias fechas.
// Además del closes>opens por bloque (ya validado arriba), valida NO-SOLAPAMIENTO
// entre bloques del MISMO día dentro del propio body (el backend además cruza con
// los existentes en BD). Adyacentes (next.opens == prev.closes) son válidos.
export const doctorAvailabilityBulkSchema = z
  .object({
    blocks: z.array(doctorAvailabilityBlockSchema).min(1, "Agrega al menos un bloque"),
  })
  .superRefine((data, ctx) => {
    // Agrupar por fecha, ordenar por apertura, marcar cur.opens < prev.closes.
    const byDate = new Map<string, { i: number; opens: string; closes: string }[]>();
    data.blocks.forEach((b, i) => {
      const arr = byDate.get(b.date) ?? [];
      arr.push({ i, opens: b.opens_at, closes: b.closes_at });
      byDate.set(b.date, arr);
    });
    for (const group of byDate.values()) {
      group.sort((a, b) => a.opens.localeCompare(b.opens));
      for (let k = 1; k < group.length; k++) {
        const prev = group[k - 1];
        const cur = group[k];
        if (cur.opens < prev.closes) {
          // adyacentes (==) OK; solapados (<) error
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["blocks", cur.i, "opens_at"],
            message: "Este bloque se solapa con otro del mismo día.",
          });
        }
      }
    }
  });

// Editar un bloque: todos opcionales, pero si vienen opens_at Y closes_at se
// valida la relación. (El cross-field completo y el no-overlap con vecinos del día
// los hace el backend con los datos de BD; aquí sólo el sanity local.)
export const doctorAvailabilityUpdateSchema = z
  .object({
    branch_id: z.string().min(1).optional(),
    office_id: z.string().min(1).optional(),
    date: dateField.optional(),
    opens_at: timeField.optional(),
    closes_at: timeField.optional(),
  })
  .superRefine((b, ctx) => {
    if (b.opens_at && b.closes_at && b.closes_at <= b.opens_at) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["closes_at"],
        message: "La hora de cierre debe ser mayor que la de apertura.",
      });
    }
  });

export type DoctorAvailabilityBlockInput = z.infer<typeof doctorAvailabilityBlockSchema>;
export type DoctorAvailabilityBulkInput = z.infer<typeof doctorAvailabilityBulkSchema>;
export type DoctorAvailabilityUpdateInput = z.infer<typeof doctorAvailabilityUpdateSchema>;
```

> **Validación por bloque + no-overlap por día = espejo del backend** (`AVAILABILITY_OVERLAP`, invariante #3). Igual que `officeHoursReplaceSchema._no_overlaps` en clinic, pero aquí agrupando por **`date`** (no por `day_of_week`). El cliente previene el error en español; el backend es la fuente de verdad y además cruza contra los bloques ya persistidos en esa fecha (que el cliente puede no conocer si su ventana visible no los trae). La grilla **también** marca inline el solape al pintar (ver [DoctorAvailabilityTab](#doctoravailabilitytabtsx--la-grilla-semanal)).

> **Lo que Zod NO puede validar** (queda como error de servidor en español): `OFFICE_NOT_IN_BRANCH` (el office elegido no pertenece a la sede elegida) y `DOCTOR_NOT_IN_BRANCH` (el doctor no está asignado a esa sede). Ambos cruzan datos que el form no tiene completos. La UI los mitiga **filtrando** el selector de consultorio a los offices de la sede elegida y el selector de sede a las sedes del doctor — pero la verdad la pone el service.

## Constantes de la grilla — `lib/constants/calendar.ts`

Parámetros del calendario semanal y etiquetas de día en español. **Nuevo** (clinic tenía `timezones.ts`/`WEEKDAY_LABELS`; staff necesita su propia configuración de grilla).

```ts
// Rango horario visible de la grilla y grano de fila. El paso se cruza con
// slot_duration_min del doctor para sugerir alturas/snap; por defecto 30 min.
export const GRID_START_HOUR = 6; // 06:00
export const GRID_END_HOUR = 22; // 22:00
export const GRID_STEP_MIN = 30; // alto de fila / snap del drag

// Etiquetas de día para los encabezados de columna. La semana se muestra de
// Lunes a Domingo (índice 0 = lunes), coherente con la convención Python que ya
// usa clinic (WEEKDAY_LABELS). Para fechas concretas se compone "Lun 12".
export const WEEKDAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"] as const;

// minutos-desde-medianoche ↔ "HH:MM" para posicionar/parsear bloques en la grilla.
export function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}
export function minutesToTime(min: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(min / 60))}:${pad(min % 60)}`;
}
```

> **Reusar las utilidades de fecha del template** (`lib/utils/date.ts`): `formatDate` para las columnas de auditoría. Para componer "Lun 12" en los encabezados de columna se parte de la fecha de inicio de la semana visible y se suman días; **no** usar `Date.getDay()` para etiquetar el día sin tener en cuenta que `WEEKDAY_SHORT` es 0=lunes (igual nota que clinic con `WEEKDAY_LABELS`). El cómputo de "lunes de la semana de X" vive en un helper local del componente (`startOfWeek(date)`), no en `date.ts` (que es genérico del template).

## Endpoints constants — extender `lib/constants/endpoints.ts`

```ts
const STAFF = "/api/v1/staff"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, VERTICALS, SERVICES, PRODUCTS,
  //   BRANCHES, OFFICES (existentes) …

  // ── Staff module ──────────────────────────────────────────
  DOCTORS: {
    LIST: `${STAFF}/doctors/list`,
    ACTIVE: `${STAFF}/doctors/active`, // ?branch_id= & ?vertical_id= ; lista cruda DoctorOption
    GET: (id: string) => `${STAFF}/doctors/${id}`,
    CREATE: `${STAFF}/doctors`, // NESTED user+doctor → 201
    UPDATE: (id: string) => `${STAFF}/doctors/${id}`, // ← PUT (NOT PATCH)
    DELETE: (id: string) => `${STAFF}/doctors/${id}`, // soft delete (NO toca User)
    // Nested: disponibilidad de UN doctor (admin).
    AVAILABILITY_LIST: (id: string) => `${STAFF}/doctors/${id}/availability`, // ?from=&to=
    AVAILABILITY_CREATE: (id: string) => `${STAFF}/doctors/${id}/availability`, // bulk
    AVAILABILITY_UPDATE: (id: string, blockId: string) =>
      `${STAFF}/doctors/${id}/availability/${blockId}`, // ← PUT
    AVAILABILITY_DELETE: (id: string, blockId: string) =>
      `${STAFF}/doctors/${id}/availability/${blockId}`,
  },
  // ── Self-service (el doctor logueado) — F3 ────────────────
  ME: {
    DOCTOR_GET: `${STAFF}/me/doctor`,
    DOCTOR_UPDATE: `${STAFF}/me/doctor`, // ← PUT (solo bio/photo/signature/slot)
    AVAILABILITY_LIST: `${STAFF}/me/availability`, // ?from=&to=
    AVAILABILITY_CREATE: `${STAFF}/me/availability`, // bulk
    AVAILABILITY_UPDATE: (blockId: string) => `${STAFF}/me/availability/${blockId}`, // ← PUT
    AVAILABILITY_DELETE: (blockId: string) => `${STAFF}/me/availability/${blockId}`,
  },
} as const;
```

> **Query params**: `DOCTORS.ACTIVE` acepta `?branch_id=` y/o `?vertical_id=` (dropdown filtrable). `AVAILABILITY_LIST` (admin y `/me`) acepta `?from=&to=` con fechas ISO `YYYY-MM-DD` que filtran `date` entre `from..to` — se concatenan en el action a partir del rango de la semana visible. Igual patrón que `OFFICES.ACTIVE`/`CLOSURES_LIST` en clinic.

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `staff` entre `clinic` y `admin`:

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … */ },
  { key: "catalog", /* … */ },
  { key: "clinic", /* … */ },

  // ── NEW ───────────────────────────────────────────
  {
    key: "staff",
    label: "Staff",
    icon: "PeopleTeamRegular",
    children: [
      {
        key: "doctors",
        label: "Doctores",
        icon: "DoctorRegular",
        url: "/staff/doctors",
        permissions: ["MENU-STAFF"],
      },
      // F3 — self-service. Se muestran a quien tenga el permiso correspondiente;
      // un admin que no es doctor verá "Mi perfil" pero el RSC redirige (NOT_A_DOCTOR).
      {
        key: "my-profile",
        label: "Mi perfil",
        icon: "PersonRegular",
        url: "/staff/me/perfil",
        permissions: ["MY_DOCTOR_PROFILE_READ"],
      },
      {
        key: "my-agenda",
        label: "Mi agenda",
        icon: "CalendarLtrRegular",
        url: "/staff/me/agenda",
        permissions: ["MY_AVAILABILITY_READ"],
      },
    ],
  },

  { key: "admin", /* … */ },
];
```

> **Íconos** (todos existen en `@fluentui/react-icons` v9): grupo `PeopleTeamRegular`, Doctores `DoctorRegular`, Mi perfil `PersonRegular`, Mi agenda `CalendarLtrRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que catalog/clinic). Alternativas válidas: `StethoscopeRegular` (Doctores) si `DoctorRegular` no resuelve en la versión instalada.

> El sidebar (`components/layout/Sidebar/Sidebar.tsx`) ya filtra items por `permissions` vs `useAuth().permissions`. Sin `MENU-STAFF` no se ve "Doctores". El detalle del doctor (`/staff/doctors/[id]`) **no** está en `NAV_ITEMS` (se llega desde la lista) — su gating es `requirePermission("DOCTORS_READ")` en el RSC. "Mi perfil"/"Mi agenda" se gatean por sus permisos `MY_*` (que el role DOCTOR tiene; ADMIN también los tiene pero su RSC redirige si no es doctor).

## Server Actions

Mismo molde que clinic/catalog: validar con Zod en el action → llamar backend client → `revalidateTag(...)`. Reusa el `MutationResult<T>` exportado por `user.actions.ts` (no se redefine). Tags:

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `staff:doctors` | listas y detalle de doctores | crear/editar/borrar doctor; **también** en cada mutación de disponibilidad por-doctor (admin) |
| `staff:availability:{doctorId}` | bloques de disponibilidad de UN doctor | crear(bulk)/editar/borrar un bloque de ese doctor (admin) |
| `staff:me` | perfil del doctor logueado (`/me/doctor`) | `updateMyDoctor` + cada mutación de disponibilidad self-service |
| `staff:me:availability` | bloques de disponibilidad del doctor logueado (`/me`) | crear/editar/borrar un bloque self-service |

> **Por qué tag por-doctor** (`staff:availability:{id}`): la agenda de un doctor es independiente de la de otro; taggear por id evita invalidar el cache de todos al guardar uno (mismo criterio que `clinic:office-hours:${officeId}`). Las mutaciones de disponibilidad admin revalidan **además** `staff:doctors` (el listado/detalle también puede reflejar la agenda). El `/me` usa tags fijos `staff:me` + `staff:me:availability` —separados de `staff:doctors` porque el doctor no ve la lista admin— y su id se resuelve server-side desde el token.

### `actions/doctor.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { doctorCreateSchema, doctorUpdateSchema } from "@/lib/schemas/doctor.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  DoctorCreatedResponse,
  DoctorDetail,
  DoctorItem,
  DoctorOption,
} from "@/types/staff.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const DOCTORS_TAG = "staff:doctors";

export async function listDoctors(query: QueryRequest): Promise<ApiPaginated<DoctorItem>> {
  return backendClient.post<ApiPaginated<DoctorItem>>(ENDPOINTS.DOCTORS.LIST, query, {
    tags: [DOCTORS_TAG],
  });
}

export async function listActiveDoctors(
  branchId?: string,
  verticalId?: string,
): Promise<DoctorOption[]> {
  const params = new URLSearchParams();
  if (branchId) params.set("branch_id", branchId);
  if (verticalId) params.set("vertical_id", verticalId);
  const qs = params.toString();
  const url = qs ? `${ENDPOINTS.DOCTORS.ACTIVE}?${qs}` : ENDPOINTS.DOCTORS.ACTIVE;
  // `/active` devuelve una lista CRUDA (response_model=list[...]) — sin envelope,
  // no se lee `.data`.
  return backendClient.get<DoctorOption[]>(url, { tags: [DOCTORS_TAG] });
}

export async function getDoctor(id: string): Promise<ApiSingle<DoctorDetail>> {
  // DoctorDetail incluye user (UserAuditInfo), branches (BranchOption[]) y
  // verticals (VerticalOption[]); soft-deleted filtradas server-side.
  return backendClient.get<ApiSingle<DoctorDetail>>(ENDPOINTS.DOCTORS.GET(id), {
    tags: [DOCTORS_TAG],
  });
}

export async function createDoctor(
  input: unknown,
): Promise<MutationResult<DoctorCreatedResponse>> {
  const parsed = doctorCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    // El POST devuelve { data: DoctorDetail, generated_password } (NO envelope
    // SingleResponse plano: espeja UserCreatedResponse). El drawer lee
    // result.data.generated_password igual que UserDrawer.
    const data = await backendClient.post<DoctorCreatedResponse>(
      ENDPOINTS.DOCTORS.CREATE,
      parsed.data,
    );
    revalidateTag(DOCTORS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 EMAIL_TAKEN (email del user ya existe) y 400 (branch/vertical inexistente
    // o muerto) llegan aquí como e.message en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateDoctor(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<DoctorDetail>>> {
  const parsed = doctorUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<DoctorDetail>>(
      ENDPOINTS.DOCTORS.UPDATE(id), // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(DOCTORS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteDoctor(id: string): Promise<MutationResult<null>> {
  try {
    // Soft delete del Doctor; NO borra ni desactiva el User (ADR-002).
    await backendClient.delete(ENDPOINTS.DOCTORS.DELETE(id));
    revalidateTag(DOCTORS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **`createDoctor` lee la respuesta SIN `.data` de envelope**: el POST de doctor devuelve `DoctorCreatedResponse` (`{ data: DoctorDetail, generated_password }`) — la misma forma que `UserCreatedResponse` (que tampoco es `ApiSingle`). El backend client devuelve ese objeto tal cual; el drawer lo consume como `result.data.data` (el detalle) y `result.data.generated_password`. Los **GET de listas** sí usan envelope `PaginatedResponse` / `SingleResponse` y se leen con `.data` (salvo `/active`, lista cruda).

### `actions/doctor-availability.actions.ts`

Contiene **solo** las variantes por-doctor (admin, F2): `listDoctorAvailability` / `createDoctorAvailability` / `updateDoctorAvailability` / `deleteDoctorAvailability`. Las variantes `/me` (self, F3) viven en su propio archivo [`actions/me.actions.ts`](#actionsmeactionsts--self-service-f3) — no se mezclan aquí. Cada mutación revalida **dos** tags: `staff:doctors` (el listado/detalle denormaliza la disponibilidad) **y** `staff:availability:{doctorId}` (la agenda de ese doctor).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  doctorAvailabilityBulkSchema,
  doctorAvailabilityUpdateSchema,
} from "@/lib/schemas/doctor-availability.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import type { MutationResult } from "./user.actions";

const DOCTORS_TAG = "staff:doctors";
const availabilityTag = (doctorId: string) => `staff:availability:${doctorId}`;

// El backend acepta "HH:MM" o "HH:MM:SS"; el form trabaja en "HH:MM", así que
// normalizamos agregando ":00" cuando falta antes de mandar al backend.
function toHms(time: string): string {
  return time.length === 5 ? `${time}:00` : time;
}

function rangeQs(from?: string, to?: string): string {
  const p = new URLSearchParams();
  if (from) p.set("from", from);
  if (to) p.set("to", to);
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

export async function listDoctorAvailability(
  doctorId: string,
  from?: string,
  to?: string,
): Promise<DoctorAvailabilityItem[]> {
  // GET devuelve SingleResponse[list[Item]] → se lee `.data` (NO es /active).
  const res = await backendClient.get<ApiSingle<DoctorAvailabilityItem[]>>(
    `${ENDPOINTS.DOCTORS.AVAILABILITY_LIST(doctorId)}${rangeQs(from, to)}`,
    { tags: [DOCTORS_TAG, availabilityTag(doctorId)] },
  );
  return res.data;
}

export async function createDoctorAvailability(
  doctorId: string,
  input: unknown, // { blocks: [...] }
): Promise<MutationResult<DoctorAvailabilityItem[]>> {
  const parsed = doctorAvailabilityBulkSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  const body = {
    blocks: parsed.data.blocks.map((b) => ({
      ...b,
      opens_at: toHms(b.opens_at),
      closes_at: toHms(b.closes_at),
    })),
  };
  try {
    const res = await backendClient.post<ApiSingle<DoctorAvailabilityItem[]>>(
      ENDPOINTS.DOCTORS.AVAILABILITY_CREATE(doctorId),
      body,
    );
    revalidateTag(DOCTORS_TAG, "max");
    revalidateTag(availabilityTag(doctorId), "max");
    return { ok: true, data: res.data };
  } catch (e) {
    // 400 AVAILABILITY_OVERLAP / OFFICE_NOT_IN_BRANCH / DOCTOR_NOT_IN_BRANCH en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateDoctorAvailability(
  doctorId: string,
  blockId: string,
  input: unknown,
): Promise<MutationResult<DoctorAvailabilityItem>> {
  const parsed = doctorAvailabilityUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  const body: Record<string, string> = { ...parsed.data };
  if (parsed.data.opens_at) body.opens_at = toHms(parsed.data.opens_at);
  if (parsed.data.closes_at) body.closes_at = toHms(parsed.data.closes_at);
  try {
    const res = await backendClient.put<ApiSingle<DoctorAvailabilityItem>>(
      ENDPOINTS.DOCTORS.AVAILABILITY_UPDATE(doctorId, blockId),
      body,
    );
    revalidateTag(DOCTORS_TAG, "max");
    revalidateTag(availabilityTag(doctorId), "max");
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteDoctorAvailability(
  doctorId: string,
  blockId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.DOCTORS.AVAILABILITY_DELETE(doctorId, blockId)); // 204
    revalidateTag(DOCTORS_TAG, "max");
    revalidateTag(availabilityTag(doctorId), "max");
    return { ok: true };
  } catch (e) {
    // 404 AVAILABILITY_NOT_FOUND si el bloque no existe o no es del doctor (ownership).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **`listDoctorAvailability` lee `.data`** (envelope `SingleResponse[list[Item]]`), a diferencia de `listActiveDoctors`/`listActiveOffices` que son listas crudas (`/active`). Es la única lista de staff que NO es `/active` y por eso lleva envelope — coincide con el contrato del backend (`GET /doctors/{id}/availability → SingleResponse[list[Item]]`).

### `actions/me.actions.ts` — self-service (F3)

El self-service del doctor logueado vive en su **propio archivo** `me.actions.ts` (separado de `doctor-availability.actions.ts`). Reúne el perfil (`getMyDoctor` / `updateMyDoctor`) y la disponibilidad self (`listMyAvailability` / `createMyAvailability` / `updateMyAvailability` / `deleteMyAvailability`). Las firmas van **sin `doctorId`** — el backend lo resuelve del token; si el user no tiene perfil, devuelve `403 NOT_A_DOCTOR` (se deja propagar). Tags propios, **separados** de `staff:doctors` (el doctor no ve la lista admin): `staff:me` (perfil) y `staff:me:availability` (agenda).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { doctorSelfUpdateSchema } from "@/lib/schemas/doctor.schema";
import {
  doctorAvailabilityBulkSchema,
  doctorAvailabilityUpdateSchema,
} from "@/lib/schemas/doctor-availability.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { DoctorAvailabilityItem, DoctorDetail } from "@/types/staff.types";

import type { MutationResult } from "./user.actions";

const ME_TAG = "staff:me";
const ME_AVAILABILITY_TAG = "staff:me:availability";

// Mismo helper que doctor-availability.actions.ts.
function toHms(time: string): string {
  return time.length === 5 ? `${time}:00` : time;
}

function rangeQs(from?: string, to?: string): string {
  const p = new URLSearchParams();
  if (from) p.set("from", from);
  if (to) p.set("to", to);
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

// GET /me/doctor → SingleResponse<DoctorDetail>. El 403 NOT_A_DOCTOR se propaga
// (el RSC lo captura para mostrar el estado vacío).
export async function getMyDoctor(): Promise<ApiSingle<DoctorDetail>> {
  return backendClient.get<ApiSingle<DoctorDetail>>(ENDPOINTS.ME.DOCTOR_GET, { tags: [ME_TAG] });
}

// PUT /me/doctor → SingleResponse<DoctorDetail>. Body = subset self-service
// (cmp_code/bio/photo_url/signature_url/slot_duration_min); NO branch_ids/
// vertical_ids/active (el schema no los tiene).
export async function updateMyDoctor(
  input: unknown,
): Promise<MutationResult<ApiSingle<DoctorDetail>>> {
  const parsed = doctorSelfUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<DoctorDetail>>(
      ENDPOINTS.ME.DOCTOR_UPDATE, // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(ME_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function listMyAvailability(
  from?: string,
  to?: string,
): Promise<DoctorAvailabilityItem[]> {
  const res = await backendClient.get<ApiSingle<DoctorAvailabilityItem[]>>(
    `${ENDPOINTS.ME.AVAILABILITY_LIST}${rangeQs(from, to)}`,
    { tags: [ME_TAG, ME_AVAILABILITY_TAG] },
  );
  return res.data;
}

export async function createMyAvailability(
  input: unknown,
): Promise<MutationResult<DoctorAvailabilityItem[]>> {
  const parsed = doctorAvailabilityBulkSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  const body = {
    blocks: parsed.data.blocks.map((b) => ({
      ...b,
      opens_at: toHms(b.opens_at),
      closes_at: toHms(b.closes_at),
    })),
  };
  try {
    const res = await backendClient.post<ApiSingle<DoctorAvailabilityItem[]>>(
      ENDPOINTS.ME.AVAILABILITY_CREATE,
      body,
    );
    revalidateTag(ME_TAG, "max");
    revalidateTag(ME_AVAILABILITY_TAG, "max");
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// updateMyAvailability(blockId, input) / deleteMyAvailability(blockId) siguen el
// mismo molde con ENDPOINTS.ME.AVAILABILITY_UPDATE(blockId) / _DELETE(blockId) y
// revalidan ambos tags (ME_TAG + ME_AVAILABILITY_TAG).
```

> **El perfil self (`/me/doctor`)** se valida con `doctorSelfUpdateSchema` = `doctorProfileBase.partial()`: `cmp_code/bio/photo_url/signature_url/slot_duration_min` — el self **no** edita branch_ids/vertical_ids/active (eso es admin). `updateMyDoctor` revalida `staff:me` (no `staff:doctors`, que no aplica al self porque no ve la lista). El 403 `NOT_A_DOCTOR` se propaga como error.

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/staff/doctors/page.tsx` (LISTA)

Análogo a `clinic/offices/page.tsx` (filtros por `branch_id`/`vertical_id` en query params). El create vive en un drawer; ver/editar navega al detalle.

```tsx
import { listActiveBranches } from "@/actions/branch.actions";
import { listDoctors } from "@/actions/doctor.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import type { QueryRequest } from "@/types/query.types";

import { DoctorsClient } from "./_components/DoctorsClient";

export const metadata = { title: "Doctores" };

interface PageProps {
  searchParams: Promise<{ branch_id?: string; vertical_id?: string }>;
}

export default async function DoctorsPage({ searchParams }: PageProps) {
  await requirePermission("MENU-STAFF");
  const { branch_id, vertical_id } = await searchParams;

  const conditions = [];
  if (branch_id) conditions.push({ field: "branch_id", operator: "eq", value: branch_id });
  if (vertical_id) conditions.push({ field: "vertical_id", operator: "eq", value: vertical_id });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  // Las sedes y verticales activas pueblan los Dropdowns de filtro Y el drawer de
  // creación (multiselect). Reusan los /active de clinic y catalog.
  const [initialData, branches, verticals] = await Promise.all([
    listDoctors({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "full_name", sort_order: "asc" },
      filters,
    }),
    listActiveBranches(),
    listActiveVerticals(),
  ]);

  return <DoctorsClient initialData={initialData} branches={branches} verticals={verticals} />;
}
```

> **El filtro `branch_id`/`vertical_id` aplica sobre el M:N**: el backend traduce esos `FilterCondition` a un EXISTS/join contra `doctor_branch`/`doctor_vertical` (ver [`backend.md`](backend.md), `ALLOWED_FIELDS` incluye `branch_id`/`vertical_id` virtuales). El frontend sólo arma el `QueryRequest` con esos campos; la traducción es del repo.

### Página de detalle del Doctor — `app/(main)/staff/doctors/[id]/page.tsx`

Página dedicada con tabs (Perfil · Disponibilidad · Auditoría), análoga al detalle de Office en clinic. Un solo `getDoctor` puebla el header; los sub-recursos (la disponibilidad) cargan en cliente al abrir su tab.

```tsx
import { notFound } from "next/navigation";

import { listActiveBranches } from "@/actions/branch.actions";
import { getDoctor } from "@/actions/doctor.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { HttpError } from "@/types/api.types";

import { DoctorDetailShell } from "./_components/DoctorDetailShell";

interface PageProps {
  params: Promise<{ id: string }>;
  // Tab routing en query param, NO sub-ruta: ?tab=availability|audit. Una URL,
  // deep-linkable, sin layout.tsx anidado.
  searchParams: Promise<{ tab?: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const res = await getDoctor(id);
    return { title: `${res.data.full_name} · Doctor` };
  } catch {
    return { title: "Doctor" };
  }
}

export default async function DoctorDetailPage({ params, searchParams }: PageProps) {
  await requirePermission("DOCTORS_READ");
  const { id } = await params;
  const { tab } = await searchParams;

  let doctor;
  try {
    doctor = await getDoctor(id);
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) notFound(); // 404 DOCTOR_NOT_FOUND
    throw e; // que error.tsx maneje el resto
  }

  // Sedes y verticales activas pueblan los multiselect del tab Perfil (editar M:N).
  const [branches, verticals] = await Promise.all([listActiveBranches(), listActiveVerticals()]);

  return (
    <DoctorDetailShell
      doctor={doctor.data}
      branches={branches}
      verticals={verticals}
      initialTab={tab === "availability" || tab === "audit" ? tab : "profile"}
    />
  );
}
```

> **Por qué tab en query param y no sub-rutas** (`/doctors/[id]/availability`): un solo `getDoctor` poblando el header (nombre, CMP, estado, sedes/verticales count) sirve a las tres vistas; sub-rutas duplicarían ese fetch o forzarían un `layout.tsx` con su propio data-loading. El `?tab=` es deep-linkable, sobrevive refresh y no exige `layout.tsx`. La **disponibilidad** carga sus propios datos en el cliente (`listDoctorAvailability(doctorId, from, to)`) cuando se selecciona el tab y se navega entre semanas — no en el RSC. Mismo criterio que `OfficeDetailShell`/`OfficeClosuresTab`.

### Pages `/me` (F3)

`app/(main)/staff/me/perfil/page.tsx` → `await requirePermission("MY_DOCTOR_PROFILE_READ")`, `getMyDoctor()`, renderiza `MyProfileClient`. `app/(main)/staff/me/agenda/page.tsx` → `await requirePermission("MY_AVAILABILITY_READ")`, renderiza `MyAvailabilityClient`. Ambas manejan el 403 `NOT_A_DOCTOR`: si `getMyDoctor()` lanza 403, mostrar un estado vacío "Tu cuenta no tiene un perfil de doctor asociado" en vez de `notFound()` (es un caso de negocio, no un 404).

```tsx
// staff/me/perfil/page.tsx (esqueleto)
export const metadata = { title: "Mi perfil" };

export default async function MyProfilePage() {
  await requirePermission("MY_DOCTOR_PROFILE_READ");
  let me;
  try {
    me = await getMyDoctor();
  } catch (e) {
    if (e instanceof HttpError && e.status === 403) {
      return <NotADoctorEmptyState />; // "Tu cuenta no tiene perfil de doctor."
    }
    throw e;
  }
  return <MyProfileClient doctor={me.data} />;
}
```

## Client components — esqueletos

> **No reproduzco los archivos completos** — siguen el patrón exacto de `clinic/offices/_components/*` + `admin/users/_components/UserDrawer.tsx`. Documento las diferencias específicas a staff. La **grilla de disponibilidad es la única pieza sustancialmente nueva** y se detalla aparte.

### `DoctorsClient.tsx`

Sigue el patrón de `OfficesClient.tsx` (lista con filtros + drawer de creación + RowActions que navegan). Diferencias:

- Recibe `branches: BranchOption[]` y `verticals: VerticalOption[]` como props (para los filtros y para el create drawer).
- `useTableQuery`: `queryKey: "staff:doctors"`, `fetcher: listDoctors`, `searchFields: ["full_name", "email", "cmp_code"]`, `defaultSort: { field: "full_name", order: "asc" }`, `initialData`.
- State `branchFilter`/`verticalFilter` (`string | null`) sincronizados con URL (`nuqs`); dos Dropdowns en la toolbar (Sede, Vertical) + chips "Filtrado por: …" con ✕ (mismo flujo que el filtro de sede en `OfficesClient`).
- Columns: `actions`, `full_name` (nombre), `email`, `cmp_code`, `slot_duration_min` ("{n} min"), `branches_count` (numeric), `verticals_count` (numeric), `active` (Badge "Activo"/"Deshabilitado" — masculino), `updated_on` (`formatDate`). Ver [`ui.md`](ui.md#pantallas).
- **RowActions = navegación, no drawer** (como offices):
  ```ts
  { key: "view",  label: "Ver",    icon: <EyeRegular />,  onSelect: (d) => router.push(`/staff/doctors/${d.id}`) },
  { key: "edit",  label: "Editar", icon: <EditRegular />, permissions: ["DOCTORS_UPDATE"], onSelect: (d) => router.push(`/staff/doctors/${d.id}?tab=profile`) },
  { key: "delete",label: "Eliminar",icon: <DeleteRegular />, permissions: ["DOCTORS_DELETE"], danger: true, onSelect: (d) => { setDeleteError(null); setDeleteTarget(d); } },
  ```
- Botón "Nuevo doctor" gated `DOCTORS_CREATE` → abre `DoctorCreateDrawer`.
- **`ConfirmDialog`** para delete: el soft-delete del doctor no tiene 409 (no borra el User ni tiene hijos que lo bloqueen), pero el dialog aclara: "Se deshabilitará el perfil de doctor. El usuario asociado **no** se elimina." (ADR-002).

### `DoctorCreateDrawer.tsx`

Drawer **solo-create** (no edit/view — la edición vive en el detalle). Combina el form anidado del `UserDrawer` (parte user + generated password) con el `SearchableOptionList` para los M:N. 3 tabs: **Datos del doctor** · **Usuario** · (sin Auditoría — no existe aún). Diferencias y puntos clave:

- `useForm<DoctorCreateInput>({ resolver: zodResolver(doctorCreateSchema), defaultValues: { user: { email: "", first_name: "", last_name: "" }, slot_duration_min: 30, branch_ids: [], vertical_ids: [] } })`.
- **Tab "Usuario"**: replica los campos de `UserDrawer.DetailsTab` pero **anidados bajo `user.`** (`name="user.email"`, `name="user.first_name"`, etc.), incluida la lógica de `document_type`/`document_number` con `DOCUMENT_RULES` (hint dinámico + re-validar en blur/cambio). Agrega un campo **`user.password` opcional** con texto de ayuda: "Déjalo vacío para generar una contraseña temporal automáticamente."
- **Tab "Datos del doctor"**: `cmp_code`, `bio` (Textarea), `photo_url`, `signature_url`, `slot_duration_min` (Input numérico, default 30, hint "Grano de tu calendario para agendar"), y los **dos multiselect**:
  ```tsx
  <Controller
    control={form.control}
    name="branch_ids"
    render={({ field }) => (
      <SearchableOptionList
        options={branches.map((b) => ({ id: b.id, primary: b.name, secondary: b.city }))}
        selected={field.value}
        disabled={false}
        onToggle={(id) => field.onChange(
          field.value.includes(id) ? field.value.filter((x) => x !== id) : [...field.value, id],
        )}
        searchPlaceholder="Buscar sedes…"
        emptyMessage="Ninguna sede coincide con la búsqueda."
      />
    )}
  />
  ```
  (idéntico para `vertical_ids` con `verticals`, `secondary: v.code`). Mismo helper que roles/permisos en `UserDrawer` y verticales en `OfficeCreateDrawer` — cero código nuevo.
- **Generated-password handling** (copiado de `UserDrawer`): tras `createDoctor(values)` exitoso, si `result.data.generated_password` viene, mostrar un `MessageBar intent="info"` con la contraseña en `<code>` y el texto "Doctor creado. Contraseña temporal (cópiala ahora — no se mostrará otra vez): …" **sin cerrar el drawer** (igual flujo que `UserDrawer`). Si no hay password generada (el admin la escribió), `onSuccess` cierra el drawer.
- En `onSuccess` (tras mostrar/omitir el password): `router.push(`/staff/doctors/${result.data.data.id}`)` para llevar al usuario directo al detalle recién creado (donde configurará la disponibilidad). `result.data.data` = el `DoctorDetail` dentro de `DoctorCreatedResponse`.
- **Errores de servidor**: `409 EMAIL_TAKEN` y `400` (branch/vertical inexistente) llegan como `result.error` → `MessageBar intent="error"`.

### `DoctorDetailShell.tsx`

Cliente. Molde directo de `OfficeDetailShell`. Recibe `doctor: DoctorDetail`, `branches: BranchOption[]`, `verticals: VerticalOption[]`, `initialTab`. Responsabilidades:

- Header: `doctor.full_name`, Badge de estado (`Activo`/`Deshabilitado`), subtítulo compuesto (`CMP {cmp_code}` si hay · `{branches_count} sedes` · `{verticals_count} verticales` · `{slot_duration_min} min/slot`), botón/Link "Volver a doctores" (`/staff/doctors`).
- `TabList` (Fluent) con 3 tabs: **Perfil · Disponibilidad · Auditoría**. Al cambiar de tab, actualizar `?tab=` con `nuqs` (`useQueryState`) para deep-link. Resolver el tab activo con fallback a `profile` si la URL apunta a un tab no permitido (mismo patrón `allowed[tab]` que `OfficeDetailShell`).
- Gating de tabs por permisos (`usePermissions`): el tab **Disponibilidad** se muestra si `DOCTOR_AVAILABILITY_READ`; si además falta `DOCTOR_AVAILABILITY_WRITE`, la grilla se monta en **modo solo-lectura** (sin pintar/editar/borrar). Perfil siempre visible (gated por `DOCTORS_READ` del RSC); su edición requiere `DOCTORS_UPDATE`.
  ```tsx
  type TabId = "profile" | "availability" | "audit";

  {activeTab === "profile" ? (
    <DoctorProfileTab doctor={doctor} branches={branches} verticals={verticals} />
  ) : activeTab === "availability" ? (
    <DoctorAvailabilityTab
      doctorId={doctor.id}
      doctorBranches={doctor.branches}
      canWrite={hasPermission("DOCTOR_AVAILABILITY_WRITE")}
    />
  ) : (
    <DoctorAuditTab doctor={doctor} />
  )}
  ```

### `DoctorProfileTab.tsx`

Form de edición inline del perfil (no drawer). Molde de `OfficeDetailsTab`. Diferencias:

- **Solo-lectura (display, no input)**: `user.full_name` y `user.email` — el User es inmutable desde staff (se edita en admin). Mostrarlos como texto fijo con un hint "Gestionado en Administración → Usuarios".
- **Editables** (gated `DOCTORS_UPDATE`; si falta, todo disabled): `cmp_code`, `bio` (Textarea), `photo_url`, `signature_url`, `slot_duration_min`, `active` (Switch/Checkbox).
- **Dos multiselect** (`SearchableOptionList`) precargados con `doctor.branches.map(b => b.id)` y `doctor.verticals.map(v => v.id)`. Al guardar mandan `branch_ids`/`vertical_ids` completos → backend reemplaza ambos M:N.
- Submit → `updateDoctor(doctor.id, values)`; en éxito `router.refresh()` para re-pintar el header (counts/estado nuevos). Errores de servidor (p.ej. branch/vertical inexistente) en `MessageBar`.
- Si hay `photo_url`, mostrar un preview (avatar) y, si `signature_url`, un thumbnail — best-effort, no bloqueante.

### `DoctorAvailabilityTab.tsx` — la grilla semanal

> **Honestidad (igual que pide la spec)**: esta grilla con drag es **custom/bespoke** — Fluent UI 9 no trae componente de calendario, y **no** se introduce ninguna librería de calendario (se respeta el design system: tokens Fluent, primitivas propias). Es **el componente más complejo del proyecto**. Construirla **incrementalmente**: (1) ver semana + click-para-crear-bloque + editar/borrar + alta masiva por **form** ("Agregar disponibilidad"); (2) el **drag** para crear, redimensionar y arrastrar-multi-día como refinamiento posterior. La capa de datos (cargar rango, persistir vía actions) es idéntica en ambas etapas, así que la etapa 2 no reescribe la 1.

Props: `{ doctorId: string; doctorBranches: BranchOption[]; canWrite: boolean }`. (La variante self `MyAvailabilityClient` monta el mismo componente con las actions `/me` inyectadas — ver [abajo](#reuse-self-vs-admin).)

**Shape del estado** (lo central):

```ts
// Lunes de la semana visible (Date local a medianoche). Navegación ‹ › / "Hoy".
const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(new Date()));

// Bloques de la semana visible, indexados por id para edición/borrado O(1). Se
// rellena con el resultado de listDoctorAvailability(from, to) del rango de la semana.
const [blocks, setBlocks] = useState<Record<string, DoctorAvailabilityItem>>({});

// Consultorio "activo" para pintar: al crear un bloque se usa este (branch, office).
// El selector de sede se limita a doctorBranches; el de consultorio a los offices
// de esa sede (listActiveOffices(branchId) de clinic). Color por consultorio.
const [activeBranchId, setActiveBranchId] = useState<string | null>(null);
const [activeOfficeId, setActiveOfficeId] = useState<string | null>(null);

const [loading, setLoading] = useState(true);
const [listError, setListError] = useState<string | null>(null);
const [saving, setSaving] = useState(false);

// Selección/edición de un bloque existente (abre popover/inline editor).
const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);

// Token monotónico para descartar respuestas fuera de orden (idéntico al de
// OfficeClosuresTab): al navegar de semana rápido, una respuesta vieja no debe
// pisar la lista de la semana nueva.
const reqIdRef = useRef(0);
```

**Carga de la ventana** (mismo patrón fetch-token + `load` reutilizable que `OfficeClosuresTab`):

```ts
const load = useCallback(() => {
  const reqId = ++reqIdRef.current;
  setLoading(true);
  setListError(null);
  const from = toIsoDate(weekStart); // "YYYY-MM-DD" del lunes
  const to = toIsoDate(addDays(weekStart, 6)); // domingo
  void listDoctorAvailability(doctorId, from, to)
    .then((rows) => {
      if (reqId !== reqIdRef.current) return; // respuesta superada → descartar
      setBlocks(Object.fromEntries(rows.map((r) => [r.id, r])));
      setLoading(false);
    })
    .catch(() => {
      if (reqId !== reqIdRef.current) return;
      setBlocks({});
      setListError("No se pudo cargar la disponibilidad. Intenta de nuevo.");
      setLoading(false);
    });
}, [doctorId, weekStart]);

useEffect(() => { load(); }, [load]);
```

**Layout de la grilla**:

- Columnas = Lun..Dom de `weekStart`, con encabezado "Lun 12" (componer con `WEEKDAY_SHORT[i]` + día del mes de `addDays(weekStart, i)`). Filas = horas `GRID_START_HOUR..GRID_END_HOUR` con paso `GRID_STEP_MIN`. Toolbar superior: ‹ semana › + "Hoy" + (opcional) salto a fecha (`Input type="date"` que hace `setWeekStart(startOfWeek(...))`).
- Cada bloque se posiciona en su columna (por `block.date`) con `top`/`height` calculados de `timeToMinutes(block.opens_at)`/`closes_at` relativos a `GRID_START_HOUR`. **Color por consultorio** (`office_id` → color estable de una paleta de tokens Fluent). Etiqueta dentro: `office_code` + `opens_at`–`closes_at`.
- **Guía de fondo** (best-effort, opcional en etapa 1): la banda del `OfficeOperatingHours` del consultorio activo como fondo tenue, y los `OfficeClosure` del rango como franjas hachuradas (ambos **solo lectura**, vienen de clinic vía `listOfficeHours`/`listClosures`). Documentar como refinamiento; **no** bloquea pintar (invariante #4 es suave: scheduling intersecta, staff no bloquea).

**Interacción** (gated por `canWrite`; si `false`, todo lo de abajo se desactiva y la grilla queda en solo-lectura):

- **Click en celda vacía** → crea un bloque en `(activeBranchId, activeOfficeId, date_de_la_columna)` con un default sugerido (p.ej. `opens_at` = hora de la celda, `closes_at` = +`slot_duration_min` o +`GRID_STEP_MIN`). Persiste vía `createDoctorAvailability(doctorId, { blocks: [oneBlock] })`.
- **Click en un bloque** → lo selecciona (`selectedBlockId`); abre un editor inline/popover con `opens_at`/`closes_at` (Inputs) + botón Borrar. Guardar → `updateDoctorAvailability(doctorId, id, patch)`; Borrar → `deleteDoctorAvailability(doctorId, id)`.
- **Drag (etapa 2)**: arrastrar en celdas vacías de **una** columna crea un bloque del rango arrastrado (snap a `GRID_STEP_MIN`); arrastrar el mismo rango horizontalmente sobre **varias** columnas crea el mismo horario en todos esos días → **alta masiva** `createDoctorAvailability(doctorId, { blocks: [...] })`. Arrastrar los bordes de un bloque existente lo redimensiona (PUT); arrastrar su cuerpo lo mueve de día/hora (PUT con `date`/`opens_at`/`closes_at`).
- **Botón "Agregar disponibilidad"** (alterno al drag, para quien prefiere form): abre un drawer con consultorio + días marcados del rango + uno o más bloques horarios → arma `blocks: [...]` (producto cartesiano días × bloques) → `createDoctorAvailability` bulk. Valida con `doctorAvailabilityBulkSchema` antes de enviar (incluido el no-overlap por día).

**Validación inline**: al crear/editar se valida `closes_at > opens_at` y el **no-solapamiento del mismo día** contra los `blocks` ya en estado (espeja invariante #3). Bloques en conflicto se marcan en rojo y el guardar se desactiva. El backend reconfirma y puede devolver `AVAILABILITY_OVERLAP`/`OFFICE_NOT_IN_BRANCH`/`DOCTOR_NOT_IN_BRANCH` → mostrar en `MessageBar` y, si aplica, resaltar el bloque ofensor.

**Persistencia → recarga**: tras cualquier mutación exitosa, `load()` (la respuesta del POST bulk también puede usarse para merge optimista, pero `load()` es la fuente simple y correcta). El tag `staff:availability:{doctorId}` se revalidó server-side; `load()` re-lee la ventana actual.

**Estados** (todos en español):

- **loading**: skeleton de la grilla (columnas + filas atenuadas) o `Spinner` con "Cargando disponibilidad…".
- **vacío**: overlay "Aún no hay disponibilidad esta semana — pinta bloques o usa **Agregar disponibilidad**." (solo si `canWrite`; en read-only: "Este doctor no tiene disponibilidad esta semana.").
- **guardando**: indicador sutil ("Guardando…") + inputs/celdas no interactivos durante el `saving`.
- **error**: `MessageBar intent="error"` con `listError`/`result.error`.
- **read-only** (`!canWrite`): grilla visible, sin click-crear, sin drag, sin editor, sin "Agregar disponibilidad".

> <a name="reuse-self-vs-admin"></a>**Reuse self vs admin**: para no duplicar la grilla, extraer un `<AvailabilityGrid>` que reciba como props las funciones de datos (`list`, `create`, `update`, `remove`), `branches` y `canWrite`. `DoctorAvailabilityTab` lo monta con las actions por-doctor de `doctor-availability.actions.ts` (`(from,to)=>listDoctorAvailability(doctorId,from,to)`, etc.); `MyAvailabilityClient` (F3) lo monta con las actions `/me` de `me.actions.ts` (`listMyAvailability`, `createMyAvailability`, …) y `canWrite = hasPermission("MY_AVAILABILITY_WRITE")`. Misma UI, distinta capa de datos.

### `DoctorAuditTab.tsx`

Idéntico al `AuditTab` de `UserDrawer.tsx` / `OfficeAuditTab.tsx`: Badge de estado (`Activo`/`Deshabilitado`), id del doctor, `user_id` (con nota "1:1 con el usuario"), `created_on`/`created_by_user.full_name`, `updated_on`/`updated_by_user.full_name`. Reusa el mismo layout de grid (`formatDate`, `?? "—"` cuando el actor fue hard-deleted).

### `MyProfileClient.tsx` / `MyAvailabilityClient.tsx` (F3)

- **`MyProfileClient`**: versión reducida de `DoctorProfileTab` — `cmp_code`, `bio`, `photo_url`, `signature_url`, `slot_duration_min` editables (gated `MY_DOCTOR_PROFILE_WRITE`, validados con `doctorSelfUpdateSchema`). **No** muestra ni edita `branch_ids`/`vertical_ids` ni `active` (eso es admin). User (nombre/email) solo-lectura. Submit → `updateMyDoctor(values)`.
- **`MyAvailabilityClient`**: monta `<AvailabilityGrid>` con las actions `/me` (ver [reuse](#reuse-self-vs-admin)). Mismo look que el tab de admin; `canWrite = MY_AVAILABILITY_WRITE`. El selector de sede se limita a las sedes del propio doctor (`getMyDoctor().data.branches`).

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| `PUT` para updates (no `PATCH`) | Alineación a clinic/catalog shipped (`backendClient.put`); el overview viejo decía `PATCH`. Evita drift back↔front. |
| `/active` para dropdowns (no `/options`) | Misma convención que `BRANCHES.ACTIVE`/`OFFICES.ACTIVE` shipped; el overview viejo decía `/options`. |
| Doctores drawer-de-creación; detalle = página con tabs | El doctor tiene 3 sub-vistas (Perfil/Disponibilidad/Auditoría); la disponibilidad (calendario) no cabe en un drawer. Reusa el patrón "entidad con sub-recursos" de Office. |
| Lista conserva drawer de creación NESTED | Crear es rápido; tras crear navega al detalle a configurar disponibilidad. |
| Tab del detalle en `?tab=` (query param) | Un solo `getDoctor` sirve a las 3 vistas; deep-linkable; sin `layout.tsx` extra. |
| Disponibilidad carga en cliente por semana, no en RSC | Primer paint instantáneo; la ventana se hidrata on-demand y al navegar semanas (fetch-token para descartar respuestas viejas). |
| Modelo = bloques concretos por fecha (no pattern+override) | Confirmado por el usuario: los doctores re-definen sus horarios cada mes. "No disponible" = sin bloque; "vacaciones" = sin bloques. Reemplaza ADR-006 pattern/override. |
| Calendario semanal **custom/bespoke**, sin librería | Fluent no trae calendario; se respeta el design system. Pieza más pesada del proyecto; construir incremental (click→form primero, drag después). |
| `createDoctorAvailability` SIEMPRE es bulk (`{ blocks: [...] }`) | Un solo endpoint POST cubre 1 bloque (click) y N bloques (drag-multi-día / form). El backend valida overlap dentro del body + contra BD. |
| Estado de bloques indexado por id (`Record<id, Item>`) | Edición/borrado O(1); el fetch-token rellena la ventana visible. |
| Zod no-overlap por `date` (espeja `AVAILABILITY_OVERLAP`) | Previene el 422 en cliente en español; el backend reconfirma (y cruza con BD). |
| `user_id` inmutable; delete NO toca el User | ADR-002: el Doctor es 1:1 con User; el soft-delete deshabilita sólo el perfil. El form lo refleja (user solo-lectura). |
| Create empuja al menos 1 sede y 1 vertical | Un doctor sin sede no puede recibir disponibilidad (invariante #2). Update las deja opcionales (ausencia = no tocar; presencia = replace). |
| Generated-password handling reusa el de `UserDrawer` | El POST devuelve `DoctorCreatedResponse` con `generated_password` (espejo de `UserCreatedResponse`); mismo `MessageBar` "cópiala ahora". |
| `cmp_code` es texto libre, no slug | Es el número del Colegio Médico; nullable para no-médicos. No reusar `CODE_SLUG_REGEX`. |
| Multiselect de sedes/verticales reusa `SearchableOptionList` | Mismo helper que roles/permisos en `UserDrawer` y verticales en `OfficeCreateDrawer`; cero código nuevo. |
| Grilla genérica reusada en `/me` (self) y admin | `<AvailabilityGrid>` recibe las funciones de datos como props; F3 inyecta las actions `/me`. Misma UI, distinta capa de datos. |
| Horas (`time`) y fechas (`date`) NO pasan por `new Date()` para lógica | Son local-time/local-date sin TZ; se posicionan por minutos/columna. Solo auditoría (`timestamptz`) usa `lib/utils/date.ts`. |
| `WEEKDAY_SHORT` indexado 0=lunes (convención Python/clinic) | Coherente con `WEEKDAY_LABELS` de clinic; usar `Date.getDay()` (0=domingo) se desfasaría. |
| 403 `NOT_A_DOCTOR` en `/me` → estado vacío, no 404 | Es un caso de negocio (admin sin perfil de doctor), no un recurso inexistente. |
| Sin bulk actions, sin duplicar, sin import CSV | Postergados al MVP+1 (igual que catalog/clinic). |

## Checklist de implementación (mapeado a fases F0–F3)

> Las fases espejan el plan de [`backend.md`](backend.md#checklist-de-implementación) y [`ui.md`](ui.md). Cada checkbox es lado frontend.

### F0 — Prep (andamiaje compartido)

- [ ] Extender `src/lib/constants/endpoints.ts` con `DOCTORS` (incluye nested `AVAILABILITY_*`) + `ME`. Verbos `PUT`, rutas `/active`.
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `staff` ("Staff" → Doctores; F3: Mi perfil, Mi agenda), `permissions: ["MENU-STAFF"]` / `["MY_*"]`.
- [ ] Registrar íconos `PeopleTeamRegular`, `DoctorRegular`, `PersonRegular`, `CalendarLtrRegular` en el `iconMap` del `Sidebar.tsx`.
- [ ] Crear `src/types/staff.types.ts` (todas las interfaces; reusa `BranchOption`/`VerticalOption`/`UserAuditInfo`).
- [ ] Crear `src/lib/constants/calendar.ts` (`GRID_*`, `WEEKDAY_SHORT`, `timeToMinutes`/`minutesToTime`).
- [ ] **Permisos test (F0)**: como user con `MENU-STAFF`, el grupo "Staff" aparece con "Doctores". Sin `MENU-STAFF`, no aparece. (Los 11 permisos STAFF + roles DOCTOR/ASESOR los seedea el backend en F0 — ver [`backend.md`](backend.md) y [`_seed-and-roles.md`](../_seed-and-roles.md).)

### F1 — Doctor (+M:N doctor_branch/doctor_vertical)

- [ ] Crear `src/lib/schemas/doctor.schema.ts` (nested `user` espejo de admin + `cmp_code`/`bio`/`slot_duration_min` + `branch_ids`/`vertical_ids`).
- [ ] Crear `src/actions/doctor.actions.ts` (list/active[branch_id,vertical_id]/get/create[NESTED→DoctorCreatedResponse]/update[PUT]/delete; tag `staff:doctors`).
- [ ] Crear `src/app/(main)/staff/doctors/page.tsx` (`metadata.title = "Doctores"`, prefetch + `listActiveBranches` + `listActiveVerticals`, filtros `branch_id`/`vertical_id`).
- [ ] Crear `_components/DoctorsClient.tsx` (tabla, filtros sede/vertical con chips, RowActions navegan) + `DoctorCreateDrawer.tsx` (tabs Usuario+Datos, multiselect vía `SearchableOptionList`, generated-password como `UserDrawer`, navega al detalle al crear).
- [ ] Crear `src/app/(main)/staff/doctors/[id]/page.tsx` (detail RSC, `?tab=` routing, `getDoctor` + `listActiveBranches` + `listActiveVerticals`) + `_components/DoctorDetailShell.tsx` + `DoctorProfileTab.tsx` + `DoctorAuditTab.tsx` (tab Disponibilidad = **placeholder** hasta F2).
- [ ] **Smoke test (F1)**: `/staff/doctors` → tabla vacía → "Nuevo doctor" → llenar usuario + datos + sedes + verticales sin password → crear → ver `MessageBar` con contraseña temporal → navega a `/staff/doctors/{id}` → editar bio/slot/sedes/verticales → header refleja counts nuevos → soft-delete → la fila desaparece y el `MessageBar`/confirm aclara que el usuario no se borra.
- [ ] **Filtro/deep-link test (F1)**: `/staff/doctors?branch_id=X` → tabla filtrada + chip; `?vertical_id=Y` combinable; ✕ limpia.
- [ ] **Error test (F1)**: crear doctor con un email ya usado → `409 EMAIL_TAKEN` en `MessageBar` sin cerrar el drawer.
- [ ] **Permisos test (F1)**: sin `DOCTORS_CREATE` no aparece "Nuevo doctor"; sin `DOCTORS_UPDATE` el RowAction "Editar" no aparece y el ProfileTab está disabled; sin `DOCTORS_DELETE` no aparece "Eliminar"; sin `DOCTORS_READ` el RSC del detalle redirige.

### F2 — DoctorAvailability (la grilla semanal)

- [ ] Crear `src/lib/schemas/doctor-availability.schema.ts` (`doctorAvailabilityBlockSchema` closes>opens + `doctorAvailabilityBulkSchema` no-overlap por `date` + `doctorAvailabilityUpdateSchema`).
- [ ] Crear `src/actions/doctor-availability.actions.ts` (admin: `listDoctorAvailability[from,to]` lee `.data`, `createDoctorAvailability` bulk, `updateDoctorAvailability` PUT, `deleteDoctorAvailability` 204; revalida `staff:doctors` + `staff:availability:{id}`).
- [ ] Crear `_components/DoctorAvailabilityTab.tsx` + `<AvailabilityGrid>` reutilizable (estado `blocks` por id, `weekStart`, consultorio activo, **fetch-token** como `OfficeClosuresTab`, carga por rango de semana, click-crear + editar/borrar + "Agregar disponibilidad" bulk; drag como refinamiento etapa 2).
- [ ] Reusar `listActiveOffices(branchId)` de clinic para poblar el selector de consultorio (filtrado por la sede activa, que a su vez se limita a `doctor.branches`).
- [ ] **Smoke test (F2)**: en un doctor con sede S1/consultorio O1, elegir O1 activo → click en Lun 09:00 → bloque 09:00–09:30 creado y persistido → recargar el tab → persiste. Editar a 09:00–13:00 → guardar → reemplazo verificado. Borrar → desaparece. Navegar a la semana siguiente y volver → ventana correcta (fetch-token).
- [ ] **Bulk test (F2)**: "Agregar disponibilidad" → O1 + días Lun/Mié/Vie + bloque 16:00–20:00 → crea 3 bloques (uno por día) en una sola llamada.
- [ ] **Validación inline test (F2)**: poner `closes_at ≤ opens_at` → error inline, guardar bloqueado. Crear dos bloques solapados el mismo día → marca de solape, guardar bloqueado (espeja `AVAILABILITY_OVERLAP`).
- [ ] **Error de servicio test (F2)**: forzar un office que no pertenece a la sede (manipulando estado) → backend devuelve `OFFICE_NOT_IN_BRANCH` en `MessageBar`. Idem `DOCTOR_NOT_IN_BRANCH` si se elige una sede a la que el doctor no pertenece (mitigado por filtrar el selector a `doctor.branches`).
- [ ] **Permisos test (F2)**: con `DOCTOR_AVAILABILITY_READ` pero sin `_WRITE`, la grilla se ve en solo-lectura (sin click-crear, sin "Agregar disponibilidad", sin editor); sin `DOCTOR_AVAILABILITY_READ` el tab Disponibilidad no aparece.

### F3 — Self-service `/me`

- [ ] Crear `src/actions/me.actions.ts` con las variantes self: `getMyDoctor`/`updateMyDoctor` (subset cmp_code/bio/photo/signature/slot vía `doctorSelfUpdateSchema`) + `listMyAvailability`/`createMyAvailability`/`updateMyAvailability`/`deleteMyAvailability` (tags `staff:me` + `staff:me:availability`).
- [ ] Crear `src/app/(main)/staff/me/perfil/page.tsx` (`requirePermission("MY_DOCTOR_PROFILE_READ")`, maneja 403 `NOT_A_DOCTOR` con estado vacío) + `_components/MyProfileClient.tsx`.
- [ ] Crear `src/app/(main)/staff/me/agenda/page.tsx` (`requirePermission("MY_AVAILABILITY_READ")`) + `_components/MyAvailabilityClient.tsx` que **monta `<AvailabilityGrid>`** con las actions `/me`.
- [ ] **Smoke test (F3)**: logueado como user con role DOCTOR → "Mi perfil" edita cmp/bio/slot (no ve sedes/verticales/estado) → guarda. "Mi agenda" → pinta un bloque → persiste. Logueado como admin **sin** perfil de doctor → "Mi perfil" muestra el estado vacío `NOT_A_DOCTOR` (no 404, no crash).
- [ ] **Permisos test (F3)**: con `MY_AVAILABILITY_READ` sin `_WRITE`, "Mi agenda" es solo-lectura.

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog**. Para `staff` no hay deuda de traducción del template — todos los strings nuevos nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Doctores", "{nombre} · Doctor", "Mi perfil", "Mi agenda").
- [ ] Todos los `label` de `NAV_ITEMS.staff` en español ("Staff", "Doctores", "Mi perfil", "Mi agenda").
- [ ] Empty states, placeholders, badges (`Activo`/`Deshabilitado` — **masculino**, "Creado el"), confirm dialogs, copy de la grilla ("Agregar disponibilidad", "Aún no hay disponibilidad esta semana", "Hoy") y `MessageBar` informativos en español (ver tabla de copy en [`ui.md`](ui.md#texto-ux-writing)).
- [ ] Mensajes de error de dominio que vienen del backend ya en español (`EMAIL_TAKEN`, `AVAILABILITY_OVERLAP`, `OFFICE_NOT_IN_BRANCH`, `DOCTOR_NOT_IN_BRANCH`, `DOCTOR_NOT_FOUND`, `AVAILABILITY_NOT_FOUND`, `NOT_A_DOCTOR`) — los `detail` se devuelven en español para mostrarse directo; el `code` queda en inglés (coordinar con [`backend.md`](backend.md)).

## TODOs deliberados (postergados al MVP+1)

- [ ] **Drag-and-drop completo** en la grilla (crear arrastrando, redimensionar bordes, mover bloque, arrastrar-multi-día) — etapa 2 de la grilla. MVP entrega click-crear + editor + "Agregar disponibilidad" bulk.
- [ ] **Guía visual de `OfficeOperatingHours`/`OfficeClosure`** como fondo de la grilla (banda tenue + franjas hachuradas) — refinamiento. Requiere cruzar `listOfficeHours`/`listClosures` de clinic; no bloquea pintar (invariante #4 es suave).
- [ ] **Copiar disponibilidad** de una semana a la siguiente / "duplicar la semana" — atajo UX para doctores con horario estable mes a mes. Postergar; "Agregar disponibilidad" bulk basta para MVP.
- [ ] **Vista responsive de la grilla** (un día a la vez o scroll horizontal en pantallas angostas) — el MVP asume desktop; agregar el modo "día" después.
- [ ] **Invalidación cross-módulo `admin.user` → `staff:doctors`**: hoy renombrar el User deja stale el `full_name`/`email` denormalizado del `DoctorItem` hasta que el cache se recree. Back-portar un `revalidateTag("staff:doctors")` en `updateUser` (admin) si se quiere consistencia inmediata. Postergar (es eventual y tolerable).
- [ ] **Preview/upload real de `photo_url`/`signature_url`** (hoy son inputs de URL) — integrar storage (GCS signed URL) cuando exista. Postergar.
- [ ] **i18n framework** — por ahora strings literales en español directo en componentes. Postergar (mismo criterio que catalog/clinic).
