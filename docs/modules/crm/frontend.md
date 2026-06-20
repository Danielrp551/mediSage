# Módulo `crm` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-05-31
> **Audiencia**: developer implementando `frontend/src/.../crm/`.
> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), y como molde de referencia el frontend de [`../staff/frontend.md`](../staff/frontend.md) (módulo completo más reciente del que `crm` copia patrones) y [`../clinic/frontend.md`](../clinic/frontend.md) (CRUD/catálogos/detalle con sub-recursos).

> **Contrato autoritativo**: este doc respeta la spec compartida de crm (consolidada en [`README.md`](./README.md)) — nombres de entidades, campos, endpoints, permisos y códigos de error son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, manda la spec.

> **Modelo confirmado** (ADR-003, [`../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md`](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md)): `Person` raíz + estados lead/customer en tablas hijas separadas (1:0..1, `UNIQUE person_id`), que pueden **coexistir**. Lead y cliente son dos hilos paralelos. Catálogos `LeadStatus`/`CustomerStatus` configurables en BD con flags `is_initial`/`is_final`/`is_won`. Identificadores multicanal con dedup `UNIQUE(channel_type, identifier)`. Timeline `LeadActivity` polimórfica. **Matriz de transiciones configurable** ([ADR-008](../../decisions/README.md)) modela las aristas permitidas del grafo de estados. **FKs forward diferidas** ([ADR-009](../../decisions/README.md)): `source_campaign_id`/`related_appointment_id`/`related_conversation_id` son `varchar(36)` nullable **sin** FK ni relationship — el frontend las trata como strings opacos de solo lectura por ahora.

> **Convenciones heredadas de catalog/clinic/staff shipped** (el lector debe tenerlas presentes desde ya):
> 1. **Verbos HTTP**: los updates completos usan **`PUT`** (no `PATCH`). El overview viejo de `crm` decía `PATCH` en varios sitios — **deprecado**; se alinea a la convención shipped (`branch.actions.ts`/`doctor.actions.ts` ya usan `backendClient.put(...)`).
> 2. **Dropdowns**: los endpoints de "lista plana de activos" se llaman **`/active`** (no `/options`). El overview viejo decía `/options`; se alinea a `/persons/active`, `/lead-statuses/active`, `/customer-statuses/active`. `/active` devuelve **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`).
> 3. **Detalle de Person = página dedicada** `/crm/personas/{id}` con tabs (Resumen · Identificadores · Lead · Cliente · Actividad · Auditoría), **no** un drawer — exactamente el patrón "entidad con sub-recursos" que estrenó Office en clinic y Doctor en staff. La **lista** de personas conserva un drawer de creación; ver/editar una navega a su página de detalle.
> 4. **Lección hotfix `cd10c78` de staff** (crítica para crm, que tiene muchos denormalizados): `defaultSort`, columnas `isSortable` y `searchFields` **SOLO** sobre columnas reales de `ALLOWED_FIELDS`. Ordenar/filtrar server-side por una columna denormalizada (`primary_identifier`, `lead_status_name`, `assigned_advisor`, `last_activity_at`) devuelve **400 → error boundary del RSC**. El `defaultSort` del client y el `sorting` del prefetch RSC **DEBEN coincidir** (si difieren, el primer paint pide una página y el client otra → flash + refetch). Búsqueda por nombre/identificador = **client-side** (denormalizados, no whitelistados).

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── crm.types.ts                      ← Person*, Identifier*, LeadStatus*, CustomerStatus*,
│                                            Transition*, PersonLeadStatus*, PersonCustomerStatus*,
│                                            *History*, LeadAssignment*, LeadActivity*, enums
│                                            (reusa UserAuditInfo de audit.types)
├── lib/
│   ├── schemas/
│   │   ├── person.schema.ts              ← personCreate (con identifiers nested opcionales) + personUpdate
│   │   ├── contact-identifier.schema.ts  ← identifier (channel_type enum, is_primary, verified)
│   │   ├── lead-status.schema.ts         ← leadStatusCreate/Update (superRefine is_won⟹is_final) + transitions body
│   │   ├── customer-status.schema.ts     ← customerStatusCreate/Update (sin is_won) + transitions body
│   │   ├── lifecycle.schema.ts           ← createLead, leadTransition, customerTransition, promote
│   │   └── lead-activity.schema.ts       ← activity (superRefine por activity_type) + activityUpdate
│   └── constants/
│       ├── endpoints.ts                  ← EXTEND con bloque CRM (PERSONS, IDENTIFIERS nested,
│       │                                    LEAD_STATUSES, CUSTOMER_STATUSES, LEAD_LIFECYCLE,
│       │                                    ASSIGNMENT, ME_LEADS, ACTIVITIES)
│       ├── navigation.ts                 ← EXTEND con grupo 'CRM' (MENU-CRM)
│       └── crm.ts                         ← NUEVO: CHANNEL_TYPE_META (ícono+label ES por canal),
│                                            ACTIVITY_TYPE_META (ícono+color+label ES por tipo),
│                                            ACTIVITY_OUTCOME_LABELS, ACTIVITY_FILTER_GROUPS
├── actions/
│   ├── person.actions.ts                 ← list/active/search/get/create/update/delete
│   ├── contact-identifier.actions.ts     ← list/create/update/delete (nested under person)
│   ├── lead-status.actions.ts            ← CRUD + active + getTransitions/setTransitions
│   ├── customer-status.actions.ts        ← CRUD + active + getTransitions/setTransitions
│   ├── lead-lifecycle.actions.ts         ← getLeadStatus/createLead/transitionLead/promote/leadHistory
│   │                                        + getCustomerStatus/transitionCustomer/customerHistory
│   ├── lead-assignment.actions.ts        ← getAssignment/assign(manual)/assignAuto + listMyLeads
│   └── lead-activity.actions.ts          ← listActivities/createActivity/updateActivity/deleteActivity
└── app/(main)/crm/
    ├── personas/
    │   ├── page.tsx                      ← LISTA de personas (drawer de creación)
    │   ├── _components/
    │   │   ├── PersonsClient.tsx
    │   │   └── PersonCreateDrawer.tsx    ← Person + identificadores iniciales (lista add/remove)
    │   └── [id]/
    │       ├── page.tsx                  ← PÁGINA DE DETALLE con tab routing
    │       └── _components/
    │           ├── PersonDetailShell.tsx        ← header + TabList (6 tabs)
    │           ├── PersonSummaryTab.tsx         ← datos editables + badges estado + asesor
    │           ├── IdentifiersTab.tsx           ← multicanal CRUD + marcar principal/verificado
    │           ├── LeadTab.tsx                  ← estado + TransitionControl + history + Promover
    │           ├── CustomerTab.tsx              ← estado + transición customer + history
    │           ├── ActivityTimeline.tsx         ← el feed pesado (orquesta lo de abajo)
    │           │   ├── ActivityComposer.tsx     ← tabs Nota/Llamada/Seguimiento
    │           │   ├── ActivityFilterChips.tsx  ← chips por grupo de tipo
    │           │   ├── ActivityDayGroup.tsx     ← sección "Hoy"/"Ayer"/fecha
    │           │   └── ActivityCard.tsx         ← tarjeta tipada memoizada (React.memo)
    │           └── PersonAuditTab.tsx           ← created/updated by/on (patrón shipped)
    ├── mis-leads/
    │   ├── page.tsx                      ← leads asignados al asesor logueado
    │   └── _components/MyLeadsClient.tsx
    ├── estados-lead/
    │   ├── page.tsx                      ← catálogo LeadStatus + editor de matriz
    │   └── _components/
    │       ├── LeadStatusesClient.tsx
    │       ├── LeadStatusDrawer.tsx
    │       └── StatusMatrixEditor.tsx    ← multiselect "transiciones permitidas hacia…"
    └── estados-cliente/
        ├── page.tsx                      ← catálogo CustomerStatus + editor de matriz
        └── _components/
            ├── CustomerStatusesClient.tsx
            ├── CustomerStatusDrawer.tsx
            └── (reusa StatusMatrixEditor)
```

> **Componentes compartidos entre tabs** (no rutas — `_components/` colocados con el detalle): `StatusBadge` (badge color por `LeadStatus`/`CustomerStatus`), `AssignmentControl` (mostrar/cambiar/auto-asignar asesor), `TransitionControl` (dropdown SOLO con destinos permitidos por la matriz). Se ubican en `personas/[id]/_components/` y se reusan desde `PersonSummaryTab`, `LeadTab`, `CustomerTab` y las celdas de las tablas (`StatusBadge` también lo usa `PersonsClient` y `MyLeadsClient`). Si crece el reuso cross-página, promover `StatusBadge` a `components/crm/` — por ahora colocado.

> **Por qué no hay `crm/layout.tsx`**: igual que en catalog/clinic/staff — `personas` (lista), `mis-leads`, `estados-lead`, `estados-cliente` son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El detalle de la persona sí tiene un shell propio (`PersonDetailShell`), pero es un **componente cliente** dentro de `[id]/page.tsx`, no un `layout.tsx` de ruta — los tabs viven en una sola URL (`?tab=`), no en sub-rutas (mismo criterio que `OfficeDetailShell`/`DoctorDetailShell`).

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas. Mantiene componentes locales colocados con su page.

> **Sobre `loading.tsx`**: catalog/clinic/staff shipped **no** incluyeron `loading.tsx` (el `DataTable` ya renderiza su propio skeleton vía `isLoading`). `crm` sigue ese mismo criterio. El estado de carga del detalle de la persona se maneja dentro de cada tab (el timeline tiene su propio skeleton). No se crean `loading.tsx`.

## Tipos TS — `types/crm.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic)). Importable desde server actions y client components. **Reusa** `UserAuditInfo` de `audit.types.ts` — no se redefine. **Sin** dependencias a otros módulos de dominio (las 3 columnas forward son strings opacos, no `*Option` de marketing/scheduling/conversations — esos módulos no existen aún).

```ts
import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de crm/enums.py; valores EXACTOS) ─────────

// Slugs estables que cruzan con conversations.ChannelAccount.channel_type a futuro.
export type ChannelType =
  | "whatsapp"
  | "telegram"
  | "web"
  | "phone"
  | "email"
  | "instagram"
  | "facebook"
  | "other";

export const CHANNEL_TYPES: readonly ChannelType[] = [
  "whatsapp",
  "telegram",
  "web",
  "phone",
  "email",
  "instagram",
  "facebook",
  "other",
] as const;

// Enum COMPLETO desde el inicio (contrato estable). En el MVP crm sólo se EMITEN
// NOTE/CALL_ATTEMPT/FOLLOW_UP_*/STATUS_CHANGE/REASSIGNED/CAMPAIGN_ATTRIBUTION;
// los MESSAGE_*/CONVERSATION_*/APPOINTMENT_* están presentes pero los emite
// conversations/scheduling más adelante (el front debe saber renderizarlos
// cuando aparezcan en el timeline). Ver README §1.2.
export type ActivityType =
  | "CALL_ATTEMPT"
  | "NOTE"
  | "STATUS_CHANGE"
  | "FOLLOW_UP_SCHEDULED"
  | "FOLLOW_UP_COMPLETED"
  | "MESSAGE_SENT"
  | "CONVERSATION_TAKEN"
  | "CONVERSATION_RELEASED"
  | "APPOINTMENT_BOOKED"
  | "APPOINTMENT_CANCELLED"
  | "APPOINTMENT_ATTENDED"
  | "REASSIGNED"
  | "CAMPAIGN_ATTRIBUTION";

// Sólo aplica a CALL_ATTEMPT (resultado de la llamada).
export type ActivityOutcome =
  | "successful"
  | "no_answer"
  | "busy"
  | "wrong_number"
  | "not_interested"
  | "interested";

// ── Person ──────────────────────────────────────────────

// Fila de listado. El backend DENORMALIZA (batch maps, sin N+1) el contacto
// principal, los estados lead/customer (code/name/color), el asesor y la última
// actividad. NINGUNO de estos denormalizados está en ALLOWED_FIELDS → NO son
// server-sortable/filterable (lección cd10c78). Filtro por estado/asesor en el
// listado = deep-link traducido a EXISTS/JOIN server-side (campos "virtuales"),
// NO order-by sobre el denormalizado.
export interface PersonItem {
  id: string;
  first_name: string;
  last_name: string;
  second_last_name: string | null;
  full_name: string; // denormalizado — first + last (+ second) compuesto server-side
  document_type: string | null;
  document_number: string | null;
  // Contacto principal: el identifier is_primary preferido (whatsapp/phone/email)
  // resuelto server-side. null si la persona no tiene identifiers.
  primary_identifier: PersonPrimaryIdentifier | null;
  // Estado lead ACTIVO (null si no tiene PersonLeadStatus vivo). Subset del catálogo.
  lead_status: LeadStatusSummary | null;
  // Estado cliente ACTIVO (null si no es cliente). Subset del catálogo.
  customer_status: CustomerStatusSummary | null;
  // Asesor dueño del lead activo (null si no tiene LeadAssignment).
  assigned_advisor: UserAuditInfo | null;
  // Denormalizado de PersonLeadStatus.last_activity_at (timestamptz, ISO 8601 o null).
  last_activity_at: string | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Subset del identifier principal embebido en PersonItem/PersonDetail.
export interface PersonPrimaryIdentifier {
  channel_type: ChannelType;
  identifier: string;
  verified: boolean;
}

// Subset de LeadStatus para badges en listados/detalle (evita el join completo).
export interface LeadStatusSummary {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
  is_won: boolean;
}

// Subset de CustomerStatus (sin is_won).
export interface CustomerStatusSummary {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
}

// Detalle de la persona: identidad completa + identifiers expandidos. Los estados
// lead/customer y la asignación se cargan en sus tabs (sub-recursos), NO viajan
// inflando el detalle (mismo criterio que DoctorDetail no trae la disponibilidad).
export interface PersonDetail {
  id: string;
  first_name: string;
  last_name: string;
  second_last_name: string | null;
  full_name: string;
  document_type: string | null;
  document_number: string | null;
  birth_date: string | null; // "YYYY-MM-DD" (date sin TZ)
  gender: string | null; // texto libre, sin enum
  address: string | null;
  notes: string | null;
  identifiers: PersonContactIdentifierItem[]; // multicanal, soft-deleted filtradas server-side
  // Resúmenes para el header (los detalles completos los traen los tabs).
  lead_status: LeadStatusSummary | null;
  customer_status: CustomerStatusSummary | null;
  assigned_advisor: UserAuditInfo | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Para dropdowns (selección de una persona en scheduling/conversations a futuro,
// y el endpoint /persons/search del bot). Lista CRUDA (sin envelope).
export interface PersonOption {
  id: string;
  full_name: string;
  document_number: string | null;
  primary_identifier: PersonPrimaryIdentifier | null;
}

// Identificadores iniciales opcionales que viajan ANIDADOS en el create de Person.
export interface PersonIdentifierCreatePayload {
  channel_type: ChannelType;
  identifier: string;
  is_primary?: boolean; // default false
  verified?: boolean; // default false
}

export interface PersonCreatePayload {
  first_name: string;
  last_name: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  birth_date?: string | null; // "YYYY-MM-DD"
  gender?: string | null;
  address?: string | null;
  notes?: string | null;
  // Identificadores iniciales (opcional). El service valida dedup en el mismo body
  // y contra BD (UNIQUE(channel_type, identifier) parcial). NO crea lead automático.
  identifiers?: PersonIdentifierCreatePayload[];
}

export interface PersonUpdatePayload {
  first_name?: string;
  last_name?: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  birth_date?: string | null;
  gender?: string | null;
  address?: string | null;
  notes?: string | null;
  active?: boolean;
}

// ── PersonContactIdentifier ─────────────────────────────

export interface PersonContactIdentifierItem {
  id: string;
  person_id: string;
  channel_type: ChannelType;
  identifier: string; // valor (phone E.164, email, chat_id…)
  is_primary: boolean;
  verified: boolean;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface ContactIdentifierCreatePayload {
  channel_type: ChannelType;
  identifier: string;
  is_primary?: boolean;
  verified?: boolean;
}

export interface ContactIdentifierUpdatePayload {
  channel_type?: ChannelType;
  identifier?: string;
  is_primary?: boolean;
  verified?: boolean;
}

// ── LeadStatus (catálogo configurable) ──────────────────

export interface LeadStatusItem {
  id: string;
  code: string; // slug mayúsculas, ej. "NUEVO"
  name: string;
  description: string | null;
  color: string | null; // hex para badges
  is_initial: boolean; // exactamente uno true por catálogo
  is_final: boolean; // terminal
  is_won: boolean; // terminal positivo; sólo válido si is_final=true
  display_order: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Para dropdowns y el TransitionControl (lista cruda en /active).
export interface LeadStatusOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
  is_won: boolean;
}

export interface LeadStatusCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_won?: boolean;
  display_order?: number;
}

export interface LeadStatusUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  is_won?: boolean;
  display_order?: number;
  active?: boolean;
}

// ── CustomerStatus (catálogo) — igual SIN is_won ────────

export interface CustomerStatusItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  color: string | null;
  is_initial: boolean;
  is_final: boolean;
  display_order: number;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface CustomerStatusOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_final: boolean;
}

export interface CustomerStatusCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  display_order?: number;
}

export interface CustomerStatusUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  is_initial?: boolean;
  is_final?: boolean;
  display_order?: number;
  active?: boolean;
}

// ── Matriz de transiciones (ADR-008) ────────────────────
// Respuesta de GET /lead-statuses/{id}/transitions: los estados a los que el
// estado {id} PUEDE ir (las aristas de salida ya resueltas a Options).
export interface TransitionTargets {
  from_id: string;
  to: LeadStatusOption[]; // (CustomerStatusOption[] para el catálogo customer)
}

// Body de PUT /lead-statuses/{id}/transitions — REEMPLAZA las aristas de salida.
export interface TransitionTargetsReplacePayload {
  to_ids: string[];
}

// ── PersonLeadStatus (estado lead activo) ───────────────

export interface PersonLeadStatusDetail {
  id: string;
  person_id: string;
  lead_status: LeadStatusOption; // estado actual resuelto
  source_campaign_id: string | null; // forward FK (varchar opaco, solo lectura)
  entered_status_at: string; // timestamptz ISO 8601
  last_activity_at: string | null;
  active: boolean;
  created_on: string;
  updated_on: string;
}

// Body de POST /persons/{id}/lead-status (crear lead; nace en is_initial).
export interface CreateLeadPayload {
  source_campaign_id?: string | null;
  reason?: string | null;
}

// ── PersonCustomerStatus (estado cliente activo) ────────

export interface PersonCustomerStatusDetail {
  id: string;
  person_id: string;
  customer_status: CustomerStatusOption;
  became_customer_at: string; // primera vez (timestamptz ISO 8601)
  entered_status_at: string; // estado actual
  active: boolean;
  created_on: string;
  updated_on: string;
}

// ── Transiciones de estado de un Person ─────────────────

export interface LeadTransitionPayload {
  to_lead_status_id: string;
  reason?: string | null;
}

export interface CustomerTransitionPayload {
  to_customer_status_id: string;
  reason?: string | null;
}

// Body opcional del promote-to-customer (estado inicial implícito = is_initial).
export interface PromoteToCustomerPayload {
  reason?: string | null;
}

// ── Historiales (timeline de cambios de estado) ─────────
// SIN soft-delete (audit trail honesto). from_*_status_id null en el primer cambio.

export interface LeadStatusHistoryItem {
  id: string;
  person_id: string;
  from_lead_status: LeadStatusSummary | null; // null al crear (NULL→initial)
  to_lead_status: LeadStatusSummary;
  source_campaign_id: string | null;
  changed_at: string; // timestamptz ISO 8601
  changed_by: string | null; // FK lógica → user (null/SYSTEM si automático)
  changed_by_user: UserAuditInfo | null; // resuelto batch; null si SYSTEM/hard-deleted
  reason: string | null;
}

export interface CustomerStatusHistoryItem {
  id: string;
  person_id: string;
  from_customer_status: CustomerStatusSummary | null;
  to_customer_status: CustomerStatusSummary;
  changed_at: string;
  changed_by: string | null;
  changed_by_user: UserAuditInfo | null;
  reason: string | null;
}

// ── LeadAssignment (owner del lead) ─────────────────────

export interface LeadAssignmentDetail {
  id: string;
  person_id: string;
  advisor: UserAuditInfo; // asesor dueño resuelto
  assigned_at: string; // timestamptz ISO 8601
  assigned_by: string | null; // null/SYSTEM si round-robin automático
  assigned_by_user: UserAuditInfo | null;
  reason: string | null;
}

export interface AssignmentPayload {
  advisor_user_id: string;
  reason?: string | null;
}

// Fila de /me/leads/list (leads del asesor logueado). Mismo perfil que PersonItem
// recortado a lo que el asesor necesita; trae el próximo seguimiento denormalizado.
export interface MyLeadItem {
  person_id: string;
  full_name: string;
  primary_identifier: PersonPrimaryIdentifier | null;
  lead_status: LeadStatusSummary | null;
  last_activity_at: string | null;
  next_follow_up_at: string | null; // próximo FOLLOW_UP_SCHEDULED pendiente (o null)
}

// ── LeadActivity (timeline polimórfico) ─────────────────
// SIN soft-delete: "borrar" = active=false (el feed normal filtra active=true).

export interface LeadActivityItem {
  id: string;
  person_id: string;
  advisor_user_id: string | null; // null/SYSTEM para actividades del sistema
  advisor: UserAuditInfo | null; // resuelto batch; null si SYSTEM/hard-deleted
  activity_type: ActivityType;
  content: string | null;
  scheduled_for: string | null; // timestamptz — FOLLOW_UP_SCHEDULED
  completed_at: string | null;
  outcome: ActivityOutcome | null; // sólo CALL_ATTEMPT
  payload: Record<string, unknown> | null; // datos específicos por tipo (JSONB)
  related_appointment_id: string | null; // forward FK (varchar opaco)
  related_conversation_id: string | null; // forward FK (varchar opaco)
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Crear una actividad (sólo los tipos editables por el asesor en el MVP). El
// activity_type discrimina qué campos son obligatorios (ver Zod superRefine).
export interface LeadActivityCreatePayload {
  activity_type: Extract<
    ActivityType,
    "NOTE" | "CALL_ATTEMPT" | "FOLLOW_UP_SCHEDULED" | "FOLLOW_UP_COMPLETED"
  >;
  content?: string | null;
  scheduled_for?: string | null; // obligatorio para FOLLOW_UP_SCHEDULED
  completed_at?: string | null;
  outcome?: ActivityOutcome | null; // sólo CALL_ATTEMPT
  payload?: Record<string, unknown> | null;
}

// Editar una actividad: SOLO content/outcome/completed_at/scheduled_for (el backend
// rechaza cambiar activity_type/person_id/advisor). Todos opcionales.
export interface LeadActivityUpdatePayload {
  content?: string | null;
  outcome?: ActivityOutcome | null;
  completed_at?: string | null;
  scheduled_for?: string | null;
}

// Body de POST /persons/{id}/activities/list — filtros del timeline (re-query
// del lado servidor; alternativa al filtrado client-side de los chips).
export interface ActivityListRequest {
  activity_type?: ActivityType[]; // vacío/ausente = todos
  date_from?: string; // "YYYY-MM-DD"
  date_to?: string;
}
```

> **Nota sobre las clases de tiempo** (igual que clinic/staff, ver [`../staff/frontend.md`](../staff/frontend.md)):
> - `Person.birth_date` → `Date` **sin TZ**, viaja como `"YYYY-MM-DD"`. **No** se construye con `new Date(birth_date)` para comparar contra "hoy" sin cuidar el desfase de medianoche (parsear como local: `new Date(\`${birth_date}T00:00:00\`)`).
> - Las columnas `timestamptz` (`entered_status_at`, `last_activity_at`, `changed_at`, `assigned_at`, `scheduled_for`, `completed_at`, `created_on`, `updated_on`) son ISO 8601 con offset → se formatean con `lib/utils/date.ts` (`formatDate` / fecha relativa). El **timeline** muestra timestamps relativos ("hace 2 h") y agrupa por día — el cálculo de "hoy"/"ayer" es **client-only** (ver [ActivityTimeline](#activitytimelinetsx--el-feed-pesado)).

> **Por qué `PersonItem` denormaliza tanto** (`full_name`, `primary_identifier`, `lead_status`, `customer_status`, `assigned_advisor`, `last_activity_at`): el listado de personas no quiere 5 joins por fila. El backend los resuelve con batch maps (sin N+1, patrón clinic/staff). **Implicancia crítica de cache + sort**: estos campos **no** están en `ALLOWED_FIELDS` del `PersonRepository` → **no** son server-sortable ni server-filterable (la lección `cd10c78`). El `defaultSort` del listado debe ser una columna real (ver [Decisiones](#decisiones-del-frontend-recap)). Renombrar a la persona o cambiar su estado deja stale el denormalizado de un listado cacheado hasta que el tag se invalida — lo cubren los tags `crm:persons` / `crm:lead:{personId}` / `crm:activity:{personId}` (ver [Server Actions](#server-actions)).

## Zod schemas

> **Regla del template** ([frontend/CLAUDE.md](../../../frontend/CLAUDE.md)): los Zod viven en `src/lib/schemas/` y los importan **tanto el form (cliente) como el Server Action (server)** → drift imposible. Los mensajes visibles van en **español** (el usuario los lee); los `path` y nombres de campo en inglés.

### `lib/schemas/person.schema.ts`

El create lleva una lista **opcional** de `identifiers` anidados. La validación de cada identifier reusa el schema de `contact-identifier.schema.ts`. El dedup contra BD lo hace el backend (`IDENTIFIER_TAKEN`), pero el front previene el dedup **dentro del propio body** con un `superRefine` (dos identifiers con el mismo `(channel_type, identifier)`).

```ts
import { z } from "zod";

import { identifierFields } from "./contact-identifier.schema";

// Documento: texto libre acotado (DNI/RUC/CE). NO se valida formato estricto en
// Zod (el backend lo acepta como varchar); sólo el largo. Si el negocio pide
// validación por tipo, reusar DOCUMENT_RULES del admin (como hace doctor.schema).
const personBase = z.object({
  first_name: z.string().min(1, "Obligatorio").max(80, "Máximo 80 caracteres"),
  last_name: z.string().min(1, "Obligatorio").max(80, "Máximo 80 caracteres"),
  second_last_name: z.string().max(80, "Máximo 80 caracteres").nullable().optional(),
  document_type: z.string().max(20).nullable().optional(),
  document_number: z.string().max(40, "Máximo 40 caracteres").nullable().optional(),
  birth_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD")
    .nullable()
    .optional()
    .or(z.literal("")),
  gender: z.string().max(20).nullable().optional(),
  address: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
  notes: z.string().max(5000).nullable().optional(),
});

// Identificador inicial dentro del create de Person (mismas reglas que el CRUD
// anidado, pero embebido en la lista). `identifierFields` = el objeto Zod base
// reutilizado (ver contact-identifier.schema.ts).
const personInitialIdentifierSchema = z.object(identifierFields);

export const personCreateSchema = personBase.extend({
  identifiers: z.array(personInitialIdentifierSchema).optional().default([]),
}).superRefine((data, ctx) => {
  // Dedup dentro del propio body: dos identifiers con el mismo (channel_type, identifier)
  // serían rechazados por el backend (IDENTIFIER_TAKEN). Lo prevenimos en español.
  const seen = new Map<string, number>();
  (data.identifiers ?? []).forEach((it, i) => {
    const key = `${it.channel_type}::${it.identifier.trim().toLowerCase()}`;
    if (seen.has(key)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifiers", i, "identifier"],
        message: "Este identificador ya está repetido en la lista.",
      });
    } else {
      seen.set(key, i);
    }
  });
  // Como máximo un is_primary por (person, channel_type) en el body (el service
  // desmarca el anterior si hay; aquí evitamos ambigüedad de entrada).
  const primaryByChannel = new Set<string>();
  (data.identifiers ?? []).forEach((it, i) => {
    if (!it.is_primary) return;
    if (primaryByChannel.has(it.channel_type)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifiers", i, "is_primary"],
        message: "Sólo un identificador principal por canal.",
      });
    } else {
      primaryByChannel.add(it.channel_type);
    }
  });
});

export const personUpdateSchema = personBase.partial().extend({
  active: z.boolean().optional(),
});

export type PersonCreateInput = z.infer<typeof personCreateSchema>;
export type PersonUpdateInput = z.infer<typeof personUpdateSchema>;
```

> **`personCreateSchema` NO crea lead automáticamente**: espeja `person.create` del backend ([`backend.md`](./backend.md#person-service)) — crea la `Person` (+ identifiers nested opcionales). El lead se crea aparte (`POST /persons/{id}/lead-status` desde el tab Lead) o por `find_by_identifier_or_create` (orquestación del bot, sin UI en el MVP). El drawer **no** ofrece "crear lead al mismo tiempo" en el MVP (se hace desde el detalle).

### `lib/schemas/contact-identifier.schema.ts`

El `channel_type` es un **enum cerrado** (`ChannelType`) — espeja el enum Pydantic del backend. Validar contra los 8 valores. El formato del `identifier` depende del canal (phone E.164, email…); el `superRefine` valida lo razonable por canal en español (el backend no impone formato más allá del largo, así que es UX, no contrato).

```ts
import { z } from "zod";

import { CHANNEL_TYPES } from "@/types/crm.types";

// E.164 laxo y email; el resto (chat ids) sólo no-vacío + largo.
const E164_REGEX = /^\+?[1-9]\d{6,14}$/;

// Campos base reutilizados por el CRUD anidado Y por personCreateSchema.identifiers.
export const identifierFields = {
  channel_type: z.enum(CHANNEL_TYPES, {
    errorMap: () => ({ message: "Canal no válido" }),
  }),
  identifier: z.string().min(1, "Obligatorio").max(255, "Máximo 255 caracteres"),
  is_primary: z.boolean().optional().default(false),
  verified: z.boolean().optional().default(false),
} as const;

export const contactIdentifierCreateSchema = z
  .object(identifierFields)
  .superRefine((data, ctx) => {
    const v = data.identifier.trim();
    if (data.channel_type === "phone" || data.channel_type === "whatsapp") {
      if (!E164_REGEX.test(v)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["identifier"],
          message: "Teléfono en formato internacional (ej. +51999111222).",
        });
      }
    } else if (data.channel_type === "email") {
      if (!z.string().email().safeParse(v).success) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["identifier"],
          message: "Correo inválido.",
        });
      }
    }
  });

// Update: todos opcionales (cambiar canal/valor/principal/verificado). El
// superRefine sólo corre cuando vienen ambos canal+valor.
export const contactIdentifierUpdateSchema = z
  .object({
    channel_type: z.enum(CHANNEL_TYPES).optional(),
    identifier: z.string().min(1).max(255).optional(),
    is_primary: z.boolean().optional(),
    verified: z.boolean().optional(),
  })
  .superRefine((data, ctx) => {
    if (!data.channel_type || !data.identifier) return;
    const v = data.identifier.trim();
    if (
      (data.channel_type === "phone" || data.channel_type === "whatsapp") &&
      !E164_REGEX.test(v)
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifier"],
        message: "Teléfono en formato internacional (ej. +51999111222).",
      });
    }
  });

export type ContactIdentifierCreateInput = z.infer<typeof contactIdentifierCreateSchema>;
export type ContactIdentifierUpdateInput = z.infer<typeof contactIdentifierUpdateSchema>;
```

> **Lo que Zod NO puede validar** (queda como error de servidor en español): `IDENTIFIER_TAKEN` (409, viola `UNIQUE(channel_type, identifier)` parcial contra BD — el front no conoce los identifiers de otras personas). Se muestra en `MessageBar`.

### `lib/schemas/lead-status.schema.ts`

Catálogo. El `superRefine` espeja dos invariantes del backend: **`is_won ⟹ is_final`** (`WON_REQUIRES_FINAL`, 400) — un estado ganado debe ser terminal. La regla "exactamente un `is_initial` por catálogo" (`MULTIPLE_INITIAL_STATUS`, 400) **no** se valida en Zod (cruza con los demás registros del catálogo que el form no tiene completos) → error de servidor; la UI lo mitiga avisando al marcar `is_initial` que desmarcará el actual.

```ts
import { z } from "zod";

// code = slug estable en MAYÚSCULAS (ej. NUEVO, NO_INTERESADO). Inmutable post-create
// idealmente; el update no lo incluye (espeja el backend, que no permite renombrar code).
const CODE_SLUG_REGEX = /^[A-Z][A-Z0-9_]*$/;
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{6})$/;

const leadStatusBase = z.object({
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
  is_won: z.boolean().optional().default(false),
  display_order: z
    .number({ invalid_type_error: "Número entero" })
    .int("Entero")
    .min(0)
    .default(0),
});

function refineWonRequiresFinal(data: { is_won?: boolean; is_final?: boolean }, ctx: z.RefinementCtx) {
  if (data.is_won && !data.is_final) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["is_won"],
      message: "Un estado ganado debe ser también final.",
    });
  }
}

export const leadStatusCreateSchema = leadStatusBase
  .extend({
    code: z
      .string()
      .min(1, "Obligatorio")
      .max(40, "Máximo 40 caracteres")
      .regex(CODE_SLUG_REGEX, "Mayúsculas, números y guiones bajos (ej. NUEVO)"),
  })
  .superRefine(refineWonRequiresFinal);

export const leadStatusUpdateSchema = leadStatusBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineWonRequiresFinal);

// Body de PUT /lead-statuses/{id}/transitions (reemplaza aristas de salida).
export const transitionTargetsSchema = z.object({
  to_ids: z.array(z.string()),
});

export type LeadStatusCreateInput = z.infer<typeof leadStatusCreateSchema>;
export type LeadStatusUpdateInput = z.infer<typeof leadStatusUpdateSchema>;
export type TransitionTargetsInput = z.infer<typeof transitionTargetsSchema>;
```

### `lib/schemas/customer-status.schema.ts`

Idéntico a `lead-status.schema.ts` **menos `is_won`** (CustomerStatus no lo tiene). Sin el `refineWonRequiresFinal`. Reusa `transitionTargetsSchema` (se exporta desde aquí o se importa de lead-status; no duplicar).

```ts
import { z } from "zod";

const CODE_SLUG_REGEX = /^[A-Z][A-Z0-9_]*$/;
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{6})$/;

const customerStatusBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500).nullable().optional(),
  color: z.string().regex(HEX_COLOR_REGEX, "Color hex como #RRGGBB").nullable().optional().or(z.literal("")),
  is_initial: z.boolean().optional().default(false),
  is_final: z.boolean().optional().default(false),
  display_order: z.number({ invalid_type_error: "Número entero" }).int().min(0).default(0),
});

export const customerStatusCreateSchema = customerStatusBase.extend({
  code: z.string().min(1, "Obligatorio").max(40).regex(CODE_SLUG_REGEX, "Mayúsculas, números y guiones bajos"),
});

export const customerStatusUpdateSchema = customerStatusBase
  .partial()
  .extend({ active: z.boolean().optional() });

export type CustomerStatusCreateInput = z.infer<typeof customerStatusCreateSchema>;
export type CustomerStatusUpdateInput = z.infer<typeof customerStatusUpdateSchema>;
```

### `lib/schemas/lifecycle.schema.ts`

Las transiciones de estado (lead y customer) y el promote. Las transiciones son simples (`to_*_status_id` + `reason?`). La **validez de la arista** (`LEAD_TRANSITION_NOT_ALLOWED`, 400) **no** se valida en Zod — la conoce la matriz del backend; la UI la mitiga ofreciendo en el `TransitionControl` **solo** los destinos permitidos (ver [TransitionControl](#transitioncontrol)).

```ts
import { z } from "zod";

export const createLeadSchema = z.object({
  source_campaign_id: z.string().max(36).nullable().optional(),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

export const leadTransitionSchema = z.object({
  to_lead_status_id: z.string().min(1, "Elige un estado destino"),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

export const customerTransitionSchema = z.object({
  to_customer_status_id: z.string().min(1, "Elige un estado destino"),
  reason: z.string().max(255).nullable().optional(),
});

export const promoteToCustomerSchema = z.object({
  reason: z.string().max(255).nullable().optional(),
});

export type CreateLeadInput = z.infer<typeof createLeadSchema>;
export type LeadTransitionInput = z.infer<typeof leadTransitionSchema>;
export type CustomerTransitionInput = z.infer<typeof customerTransitionSchema>;
export type PromoteToCustomerInput = z.infer<typeof promoteToCustomerSchema>;
```

### `lib/schemas/lead-activity.schema.ts`

El composer del timeline crea actividades de 4 tipos (`NOTE`, `CALL_ATTEMPT`, `FOLLOW_UP_SCHEDULED`, `FOLLOW_UP_COMPLETED`). El `superRefine` valida **por tipo** qué campos son obligatorios — espeja la lógica del service ([`backend.md`](./backend.md#lead-activity-service)):
- `NOTE` → `content` obligatorio.
- `CALL_ATTEMPT` → `outcome` obligatorio; `content` opcional.
- `FOLLOW_UP_SCHEDULED` → `scheduled_for` obligatorio (futuro).
- `FOLLOW_UP_COMPLETED` → `completed_at` (default ahora) + `content` opcional.

```ts
import { z } from "zod";

import type { ActivityOutcome } from "@/types/crm.types";

const ACTIVITY_OUTCOMES = [
  "successful",
  "no_answer",
  "busy",
  "wrong_number",
  "not_interested",
  "interested",
] as const satisfies readonly ActivityOutcome[];

// Tipos que el asesor puede emitir desde el composer (los demás los emite el sistema).
const COMPOSER_ACTIVITY_TYPES = [
  "NOTE",
  "CALL_ATTEMPT",
  "FOLLOW_UP_SCHEDULED",
  "FOLLOW_UP_COMPLETED",
] as const;

export const leadActivityCreateSchema = z
  .object({
    activity_type: z.enum(COMPOSER_ACTIVITY_TYPES),
    content: z.string().max(5000, "Máximo 5000 caracteres").nullable().optional(),
    scheduled_for: z.string().datetime({ offset: true }).nullable().optional(),
    completed_at: z.string().datetime({ offset: true }).nullable().optional(),
    outcome: z.enum(ACTIVITY_OUTCOMES).nullable().optional(),
    payload: z.record(z.unknown()).nullable().optional(),
  })
  .superRefine((data, ctx) => {
    switch (data.activity_type) {
      case "NOTE":
        if (!data.content || !data.content.trim()) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["content"],
            message: "Escribe el contenido de la nota.",
          });
        }
        break;
      case "CALL_ATTEMPT":
        if (!data.outcome) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["outcome"],
            message: "Indica el resultado de la llamada.",
          });
        }
        break;
      case "FOLLOW_UP_SCHEDULED":
        if (!data.scheduled_for) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["scheduled_for"],
            message: "Elige la fecha y hora del seguimiento.",
          });
        }
        break;
      case "FOLLOW_UP_COMPLETED":
        // completed_at se default-ea a "ahora" en el composer si viene vacío.
        break;
    }
  });

// Editar: SOLO content/outcome/completed_at/scheduled_for (el backend rechaza el
// resto). Sin discriminación por tipo (no se cambia el tipo al editar).
export const leadActivityUpdateSchema = z.object({
  content: z.string().max(5000).nullable().optional(),
  outcome: z.enum(ACTIVITY_OUTCOMES).nullable().optional(),
  completed_at: z.string().datetime({ offset: true }).nullable().optional(),
  scheduled_for: z.string().datetime({ offset: true }).nullable().optional(),
});

export type LeadActivityCreateInput = z.infer<typeof leadActivityCreateSchema>;
export type LeadActivityUpdateInput = z.infer<typeof leadActivityUpdateSchema>;
```

> **`scheduled_for`/`completed_at` viajan como ISO 8601 con offset**: el composer compone el `Date` en local del usuario (input `datetime-local`) y lo serializa a ISO **client-only** (`new Date(...).toISOString()`) — coherente con la lección TZ (no construir esto en SSR; el composer es cliente). El backend almacena `timestamptz`. El render relativo del feed también es client-only.

## Constantes de presentación — `lib/constants/crm.ts`

Metadata de canal y de tipo de actividad: ícono Fluent, label en español y color (token Fluent — **no** `brandPalette.accent`, que no existe; ver [`ui.md`](./ui.md)). **Nuevo** (crm necesita su propia tabla de presentación; catalog/clinic/staff no tenían enums tan ricos).

```ts
import {
  CallRegular,
  ChatRegular,
  GlobeRegular,
  MailRegular,
  NoteRegular,
  PhoneRegular,
  ArrowSwapRegular,
  CalendarClockRegular,
  CheckmarkCircleRegular,
  PersonSwapRegular,
  MegaphoneRegular,
  SendRegular,
} from "@fluentui/react-icons";
import { tokens } from "@fluentui/react-components";

import type { ActivityType, ChannelType, ActivityOutcome } from "@/types/crm.types";

// ── Canales ──────────────────────────────────────────────
// Label en ES; el ícono se renderiza junto al identifier en tablas/tab.
export const CHANNEL_TYPE_META: Record<
  ChannelType,
  { label: string; icon: React.FC }
> = {
  whatsapp: { label: "WhatsApp", icon: ChatRegular },
  telegram: { label: "Telegram", icon: SendRegular },
  web: { label: "Web", icon: GlobeRegular },
  phone: { label: "Teléfono", icon: PhoneRegular },
  email: { label: "Correo", icon: MailRegular },
  instagram: { label: "Instagram", icon: ChatRegular },
  facebook: { label: "Facebook", icon: ChatRegular },
  other: { label: "Otro", icon: ChatRegular },
};

// ── Tipos de actividad ───────────────────────────────────
// Ícono + color (token Fluent, NO brandPalette.accent) + label ES por tipo. El
// timeline pinta la tarjeta según esto. Colores: usar tokens semánticos Fluent.
export const ACTIVITY_TYPE_META: Record<
  ActivityType,
  { label: string; icon: React.FC; color: string }
> = {
  NOTE: { label: "Nota", icon: NoteRegular, color: tokens.colorNeutralForeground2 },
  CALL_ATTEMPT: { label: "Llamada", icon: CallRegular, color: tokens.colorPaletteBlueForeground2 },
  FOLLOW_UP_SCHEDULED: { label: "Seguimiento programado", icon: CalendarClockRegular, color: tokens.colorPaletteMarigoldForeground2 },
  FOLLOW_UP_COMPLETED: { label: "Seguimiento realizado", icon: CheckmarkCircleRegular, color: tokens.colorPaletteGreenForeground2 },
  STATUS_CHANGE: { label: "Cambio de estado", icon: ArrowSwapRegular, color: tokens.colorPalettePurpleForeground2 },
  REASSIGNED: { label: "Reasignación", icon: PersonSwapRegular, color: tokens.colorNeutralForeground3 },
  CAMPAIGN_ATTRIBUTION: { label: "Atribución de campaña", icon: MegaphoneRegular, color: tokens.colorPaletteTealForeground2 },
  // Cross-módulo (emisión diferida; el front debe saber pintarlos cuando aparezcan).
  MESSAGE_SENT: { label: "Mensaje enviado", icon: SendRegular, color: tokens.colorNeutralForeground3 },
  CONVERSATION_TAKEN: { label: "Conversación tomada", icon: ChatRegular, color: tokens.colorNeutralForeground3 },
  CONVERSATION_RELEASED: { label: "Conversación liberada", icon: ChatRegular, color: tokens.colorNeutralForeground3 },
  APPOINTMENT_BOOKED: { label: "Cita agendada", icon: CalendarClockRegular, color: tokens.colorPaletteGreenForeground2 },
  APPOINTMENT_CANCELLED: { label: "Cita cancelada", icon: CalendarClockRegular, color: tokens.colorPaletteRedForeground2 },
};

// Resultado de llamada (label ES para el chip y el select del composer).
export const ACTIVITY_OUTCOME_LABELS: Record<ActivityOutcome, string> = {
  successful: "Exitosa",
  no_answer: "Sin respuesta",
  busy: "Ocupado",
  wrong_number: "Número equivocado",
  not_interested: "No interesado",
  interested: "Interesado",
};

// Chips de filtro del timeline → agrupan varios activity_type. "Todos" = sin filtro.
// "Sistema" agrupa los tipos emitidos por crm/otros módulos (no por el asesor).
export const ACTIVITY_FILTER_GROUPS: {
  key: string;
  label: string;
  types: ActivityType[] | null; // null = todos
}[] = [
  { key: "all", label: "Todos", types: null },
  { key: "notes", label: "Notas", types: ["NOTE"] },
  { key: "calls", label: "Llamadas", types: ["CALL_ATTEMPT"] },
  { key: "follow_ups", label: "Seguimientos", types: ["FOLLOW_UP_SCHEDULED", "FOLLOW_UP_COMPLETED"] },
  { key: "status", label: "Estado", types: ["STATUS_CHANGE"] },
  {
    key: "system",
    label: "Sistema",
    types: [
      "REASSIGNED",
      "CAMPAIGN_ATTRIBUTION",
      "MESSAGE_SENT",
      "CONVERSATION_TAKEN",
      "CONVERSATION_RELEASED",
      "APPOINTMENT_BOOKED",
      "APPOINTMENT_CANCELLED",
    ],
  },
];
```

> **Verificar los íconos en la versión instalada de `@fluentui/react-icons`** (mismo paso que catalog/clinic/staff): `ChatRegular`, `SendRegular`, `GlobeRegular`, `PhoneRegular`, `MailRegular`, `CallRegular`, `NoteRegular`, `ArrowSwapRegular`, `CalendarClockRegular`, `CheckmarkCircleRegular`, `PersonSwapRegular`, `MegaphoneRegular`. Si alguno no resuelve, usar un fallback razonable (ej. `PersonSwapRegular` → `ArrowSwapRegular`; `MegaphoneRegular` → `TagRegular`). **No** introducir librerías de íconos nuevas.

> **`brandPalette` NO tiene `accent`** (lección operativa transversal): para colores que no sean primary/primaryHover/primaryPressed/primarySelected, usar tokens Fluent semánticos (`tokens.colorPaletteRedForeground2`, etc.) como arriba. El `color` del `LeadStatus`/`CustomerStatus` viene del catálogo (hex configurable en BD) y se aplica directo al badge (no es de la paleta de marca).

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque CRM completo (todas las URLs de la spec §5). `/active` antes de `/{id}` en el backend; verbos `PUT` para updates. **Anidados** bajo `/persons/{id}` para identifiers, lifecycle, assignment, activities.

```ts
const CRM = "/api/v1/crm"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, VERTICALS, SERVICES, PRODUCTS,
  //   BRANCHES, OFFICES, DOCTORS, ME (existentes) …

  // ── CRM module ───────────────────────────────────────────
  PERSONS: {
    LIST: `${CRM}/persons/list`,
    CREATE: `${CRM}/persons`,
    GET: (id: string) => `${CRM}/persons/${id}`,
    UPDATE: (id: string) => `${CRM}/persons/${id}`, // ← PUT (not PATCH)
    DELETE: (id: string) => `${CRM}/persons/${id}`, // soft delete
    ACTIVE: `${CRM}/persons/active`, // raw PersonOption list
    SEARCH: `${CRM}/persons/search`, // ?q=&channel_type=&identifier= (lo usa el bot; raw list)
    // Nested: identificadores multicanal de UNA persona.
    IDENTIFIERS: (id: string) => `${CRM}/persons/${id}/identifiers`,
    IDENTIFIER: (id: string, identId: string) => `${CRM}/persons/${id}/identifiers/${identId}`, // PUT / DELETE
    // Nested: estado lead/customer + transiciones + history + promote.
    LEAD_STATUS: (id: string) => `${CRM}/persons/${id}/lead-status`, // GET / POST (crear lead)
    LEAD_TRANSITION: (id: string) => `${CRM}/persons/${id}/lead-status/transition`, // POST
    LEAD_HISTORY: (id: string) => `${CRM}/persons/${id}/lead-status/history`, // GET
    PROMOTE: (id: string) => `${CRM}/persons/${id}/promote-to-customer`, // POST
    CUSTOMER_STATUS: (id: string) => `${CRM}/persons/${id}/customer-status`, // GET
    CUSTOMER_TRANSITION: (id: string) => `${CRM}/persons/${id}/customer-status/transition`, // POST
    CUSTOMER_HISTORY: (id: string) => `${CRM}/persons/${id}/customer-status/history`, // GET
    // Nested: asignación (owner).
    ASSIGNMENT: (id: string) => `${CRM}/persons/${id}/assignment`, // GET / PUT (manual / "asignarme")
    ASSIGNMENT_AUTO: (id: string) => `${CRM}/persons/${id}/assignment/auto`, // POST (round-robin)
    // Nested: timeline.
    ACTIVITIES_LIST: (id: string) => `${CRM}/persons/${id}/activities/list`, // POST (filtros)
    ACTIVITIES_CREATE: (id: string) => `${CRM}/persons/${id}/activities`, // POST
    ACTIVITY: (id: string, actId: string) => `${CRM}/persons/${id}/activities/${actId}`, // PUT / DELETE
  },
  LEAD_STATUSES: {
    LIST: `${CRM}/lead-statuses/list`,
    CREATE: `${CRM}/lead-statuses`,
    UPDATE: (id: string) => `${CRM}/lead-statuses/${id}`, // ← PUT
    DELETE: (id: string) => `${CRM}/lead-statuses/${id}`, // 409 LEAD_STATUS_IN_USE si referenciado
    ACTIVE: `${CRM}/lead-statuses/active`, // raw LeadStatusOption list
    TRANSITIONS: (id: string) => `${CRM}/lead-statuses/${id}/transitions`, // GET (destinos) / PUT (reemplaza aristas)
  },
  CUSTOMER_STATUSES: {
    LIST: `${CRM}/customer-statuses/list`,
    CREATE: `${CRM}/customer-statuses`,
    UPDATE: (id: string) => `${CRM}/customer-statuses/${id}`, // ← PUT
    DELETE: (id: string) => `${CRM}/customer-statuses/${id}`, // 409 CUSTOMER_STATUS_IN_USE
    ACTIVE: `${CRM}/customer-statuses/active`, // raw CustomerStatusOption list
    TRANSITIONS: (id: string) => `${CRM}/customer-statuses/${id}/transitions`, // GET / PUT
  },
  ADVISORS: {
    ACTIVE: `${CRM}/advisors/active`, // raw AdvisorOption list (asesores; LEAD_ASSIGNMENTS_READ) — crm-owned, NO admin/users
  },
  ME_CRM: {
    LEADS_LIST: `${CRM}/me/leads/list`, // POST + QueryRequest — leads del asesor logueado (MY_LEADS_READ)
  },
} as const;
```

> **Query params**: `PERSONS.SEARCH` acepta `?q=&channel_type=&identifier=` (lo usa el bot vía `find_by_identifier`; el front lo usa poco en el MVP). `LEAD_HISTORY`/`CUSTOMER_HISTORY` y `ACTIVITIES_LIST` no llevan query (los filtros del timeline van en el **body** de `POST /activities/list`). El deep-link del listado de personas (`?lead_status_id=`/`?advisor_user_id=`) se traduce a `FilterCondition` en el page RSC, **no** a query param del endpoint (ver [Pages](#pages-rsc)).

> **`/active` y `/search` devuelven lista CRUDA** (`response_model=list[...]`, sin envelope) — no se lee `.data`. El resto (`/list`, `GET /{id}`, `POST`, `PUT`, history) usa los envelopes del template (`PaginatedResponse` / `SingleResponse`) y se lee con `.data`.

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `crm` entre `staff` y `admin`:

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … */ },
  { key: "catalog", /* … */ },
  { key: "clinic", /* … */ },
  { key: "staff", /* … */ },

  // ── NEW ───────────────────────────────────────────
  {
    key: "crm",
    label: "CRM",
    icon: "PeopleRegular",
    children: [
      {
        key: "persons",
        label: "Contactos",
        icon: "ContactCardRegular",
        url: "/crm/personas",
        permissions: ["PERSONS_READ"],
      },
      {
        key: "my-leads",
        label: "Mis leads",
        icon: "PersonRegular",
        url: "/crm/mis-leads",
        permissions: ["MY_LEADS_READ"],
      },
      {
        key: "lead-statuses",
        label: "Estados de lead",
        icon: "TagRegular",
        url: "/crm/estados-lead",
        permissions: ["LEAD_STATUSES_READ"],
      },
      {
        key: "customer-statuses",
        label: "Estados de cliente",
        icon: "TagMultipleRegular",
        url: "/crm/estados-cliente",
        permissions: ["CUSTOMER_STATUSES_READ"],
      },
    ],
  },

  { key: "admin", /* … */ },
];
```

> **Gating del grupo vs items**: el **grupo** "CRM" se muestra si el usuario tiene **alguno** de los permisos de sus hijos (el Sidebar colapsa grupos sin hijos visibles). La spec pide el grupo **gated `MENU-CRM`** — para honrarlo, agregar `MENU-CRM` como permiso del grupo padre **o** verificarlo en el RSC de cada page. Decisión: **cada item lleva su permiso fino** (`PERSONS_READ`, `MY_LEADS_READ`, `LEAD_STATUSES_READ`, `CUSTOMER_STATUSES_READ`) y el page RSC valida con `requirePermission(...)`. `MENU-CRM` es el permiso "de entrada" del módulo: el role `ASESOR` lo tiene (ver [`../_seed-and-roles.md`](../_seed-and-roles.md)); se usa como gate del grupo en el Sidebar si se prefiere un único toggle. **No** redefinir los permisos aquí — los 15 ya son canónicos en `_seed-and-roles.md`.

> **Íconos** (verificar que existan en `@fluentui/react-icons` v9; fallback si no): grupo CRM `PeopleRegular`, Contactos `ContactCardRegular`, Mis leads `PersonRegular`, Estados de lead `TagRegular`, Estados de cliente `TagMultipleRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que catalog/clinic/staff). Alternativas: `ContactCardRegular` → `PersonRegular`; `TagMultipleRegular` → `TagRegular`.

> El sidebar (`components/layout/Sidebar/Sidebar.tsx`) ya filtra items por `permissions` vs `useAuth().permissions`. El detalle de la persona (`/crm/personas/[id]`) **no** está en `NAV_ITEMS` (se llega desde la lista) — su gating es `requirePermission("PERSONS_READ")` en el RSC. El `ASESOR` ve Contactos/Mis leads/Estados (READ); crear/editar estados (`LEAD_STATUSES_WRITE`) es de `ADMIN`.

## Server Actions

Mismo molde que clinic/catalog/staff: validar con Zod en el action → llamar backend client → `revalidateTag(TAG, "max")`. Reusa el `MutationResult<T>` exportado por `user.actions.ts` (no se redefine). **Next 16 exige el 2º argumento de `revalidateTag`** (`"max"`) — lección del template ([feedback Next.js 16](../_seed-and-roles.md)); omitirlo es error de tipos/runtime.

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `crm:persons` | listas y detalle de personas, `/active`, `/search`, `/me/leads` | crear/editar/borrar persona; mutar identifiers, estado lead/customer, asignación (afectan denormalizados del listado) |
| `crm:identifiers:{personId}` | identificadores de UNA persona | crear/editar/borrar un identifier de esa persona |
| `crm:lead:{personId}` | estado lead + history + asignación de UNA persona | crear lead, transición lead, promote, asignar/auto |
| `crm:customer:{personId}` | estado cliente + history de UNA persona | promote, transición customer |
| `crm:activity:{personId}` | timeline de UNA persona | crear/editar/borrar actividad; también lo escriben transition/reassign (que emiten `STATUS_CHANGE`/`REASSIGNED`) |
| `crm:lead-statuses` | catálogo LeadStatus + `/active` + matriz | CRUD catálogo, editar transiciones |
| `crm:customer-statuses` | catálogo CustomerStatus + `/active` + matriz | CRUD catálogo, editar transiciones |

> **Por qué tags por-persona** (`crm:lead:{id}`, `crm:activity:{id}`, `crm:identifiers:{id}`): el detalle de una persona es independiente del de otra; taggear por id evita invalidar el cache de todas al mutar una (mismo criterio que `staff:availability:{doctorId}`). **Cross-tag**: una transición de lead que emite una `STATUS_CHANGE` debe invalidar **tanto** `crm:lead:{id}` (el estado) **como** `crm:activity:{id}` (el timeline) **y** `crm:persons` (el badge/`last_activity_at` denormalizado en el listado). El action de transición revalida los tres. Documentado en cada action.

### `actions/person.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { personCreateSchema, personUpdateSchema } from "@/lib/schemas/person.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { PersonDetail, PersonItem, PersonOption } from "@/types/crm.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";

export async function listPersons(query: QueryRequest): Promise<ApiPaginated<PersonItem>> {
  return backendClient.post<ApiPaginated<PersonItem>>(ENDPOINTS.PERSONS.LIST, query, {
    tags: [PERSONS_TAG],
  });
}

export async function listActivePersons(): Promise<PersonOption[]> {
  // `/active` devuelve lista CRUDA (sin envelope) — NO se lee `.data`.
  return backendClient.get<PersonOption[]>(ENDPOINTS.PERSONS.ACTIVE, { tags: [PERSONS_TAG] });
}

export async function searchPersons(
  q?: string,
  channelType?: string,
  identifier?: string,
): Promise<PersonOption[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (channelType) params.set("channel_type", channelType);
  if (identifier) params.set("identifier", identifier);
  const qs = params.toString();
  const url = qs ? `${ENDPOINTS.PERSONS.SEARCH}?${qs}` : ENDPOINTS.PERSONS.SEARCH;
  return backendClient.get<PersonOption[]>(url, { tags: [PERSONS_TAG] });
}

export async function getPerson(id: string): Promise<ApiSingle<PersonDetail>> {
  // PersonDetail incluye identifiers + resúmenes de estado para el header.
  return backendClient.get<ApiSingle<PersonDetail>>(ENDPOINTS.PERSONS.GET(id), {
    tags: [PERSONS_TAG],
  });
}

export async function createPerson(input: unknown): Promise<MutationResult<ApiSingle<PersonDetail>>> {
  const parsed = personCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<PersonDetail>>(
      ENDPOINTS.PERSONS.CREATE,
      parsed.data,
    );
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 IDENTIFIER_TAKEN (un identifier inicial ya existe) llega como e.message en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updatePerson(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonDetail>>> {
  const parsed = personUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<PersonDetail>>(
      ENDPOINTS.PERSONS.UPDATE(id), // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deletePerson(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PERSONS.DELETE(id)); // soft delete
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/contact-identifier.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  contactIdentifierCreateSchema,
  contactIdentifierUpdateSchema,
} from "@/lib/schemas/contact-identifier.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { PersonContactIdentifierItem } from "@/types/crm.types";
import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const identifiersTag = (personId: string) => `crm:identifiers:${personId}`;

export async function listIdentifiers(personId: string): Promise<PersonContactIdentifierItem[]> {
  // GET devuelve SingleResponse[list[Item]] → se lee `.data` (NO es /active).
  const res = await backendClient.get<ApiSingle<PersonContactIdentifierItem[]>>(
    ENDPOINTS.PERSONS.IDENTIFIERS(personId),
    { tags: [identifiersTag(personId)] },
  );
  return res.data;
}

export async function createIdentifier(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonContactIdentifierItem>>> {
  const parsed = contactIdentifierCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PersonContactIdentifierItem>>(
      ENDPOINTS.PERSONS.IDENTIFIERS(personId),
      parsed.data,
    );
    revalidateTag(identifiersTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max"); // primary_identifier denormalizado en el listado
    return { ok: true, data };
  } catch (e) {
    // 409 IDENTIFIER_TAKEN en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateIdentifier(
  personId: string,
  identId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonContactIdentifierItem>>> {
  const parsed = contactIdentifierUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<PersonContactIdentifierItem>>(
      ENDPOINTS.PERSONS.IDENTIFIER(personId, identId), // ← PUT
      parsed.data,
    );
    revalidateTag(identifiersTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteIdentifier(
  personId: string,
  identId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PERSONS.IDENTIFIER(personId, identId)); // soft delete
    revalidateTag(identifiersTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 404 IDENTIFIER_NOT_FOUND si el identifier no existe o no es de la persona (ownership).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/lead-status.actions.ts`

Catálogo + matriz. `customer-status.actions.ts` es el mismo molde con `CUSTOMER_STATUSES` y `crm:customer-statuses`.

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  leadStatusCreateSchema,
  leadStatusUpdateSchema,
  transitionTargetsSchema,
} from "@/lib/schemas/lead-status.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { LeadStatusItem, LeadStatusOption, TransitionTargets } from "@/types/crm.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const TAG = "crm:lead-statuses";

export async function listLeadStatuses(query: QueryRequest): Promise<ApiPaginated<LeadStatusItem>> {
  return backendClient.post<ApiPaginated<LeadStatusItem>>(ENDPOINTS.LEAD_STATUSES.LIST, query, {
    tags: [TAG],
  });
}

export async function listActiveLeadStatuses(): Promise<LeadStatusOption[]> {
  // Lista CRUDA. La consume el TransitionControl y los dropdowns de estado.
  return backendClient.get<LeadStatusOption[]>(ENDPOINTS.LEAD_STATUSES.ACTIVE, { tags: [TAG] });
}

export async function createLeadStatus(input: unknown): Promise<MutationResult<ApiSingle<LeadStatusItem>>> {
  const parsed = leadStatusCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<LeadStatusItem>>(
      ENDPOINTS.LEAD_STATUSES.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 MULTIPLE_INITIAL_STATUS / WON_REQUIRES_FINAL en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateLeadStatus(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<LeadStatusItem>>> {
  const parsed = leadStatusUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<LeadStatusItem>>(
      ENDPOINTS.LEAD_STATUSES.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteLeadStatus(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.LEAD_STATUSES.DELETE(id));
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 LEAD_STATUS_IN_USE si hay PersonLeadStatus/History referenciándolo.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Matriz de transiciones ──────────────────────────────

export async function getLeadTransitions(id: string): Promise<TransitionTargets> {
  // GET devuelve SingleResponse[TransitionTargets] → se lee `.data`.
  const res = await backendClient.get<ApiSingle<TransitionTargets>>(
    ENDPOINTS.LEAD_STATUSES.TRANSITIONS(id),
    { tags: [TAG] },
  );
  return res.data;
}

export async function setLeadTransitions(
  id: string,
  input: unknown, // { to_ids: [...] } — reemplaza las aristas de salida
): Promise<MutationResult<ApiSingle<TransitionTargets>>> {
  const parsed = transitionTargetsSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<TransitionTargets>>(
      ENDPOINTS.LEAD_STATUSES.TRANSITIONS(id), // ← PUT (reemplaza)
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/lead-lifecycle.actions.ts`

Estado lead/customer de una persona + transiciones + history + promote. **Estos actions cruzan tags** (estado + timeline + listado).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  createLeadSchema,
  customerTransitionSchema,
  leadTransitionSchema,
  promoteToCustomerSchema,
} from "@/lib/schemas/lifecycle.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type {
  CustomerStatusHistoryItem,
  LeadStatusHistoryItem,
  PersonCustomerStatusDetail,
  PersonLeadStatusDetail,
} from "@/types/crm.types";
import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const leadTag = (id: string) => `crm:lead:${id}`;
const customerTag = (id: string) => `crm:customer:${id}`;
const activityTag = (id: string) => `crm:activity:${id}`;

// Lead activo actual (o null vía 200 con data null — el backend devuelve null, no 404).
export async function getLeadStatus(personId: string): Promise<PersonLeadStatusDetail | null> {
  const res = await backendClient.get<ApiSingle<PersonLeadStatusDetail | null>>(
    ENDPOINTS.PERSONS.LEAD_STATUS(personId),
    { tags: [leadTag(personId)] },
  );
  return res.data;
}

export async function getLeadHistory(personId: string): Promise<LeadStatusHistoryItem[]> {
  const res = await backendClient.get<ApiSingle<LeadStatusHistoryItem[]>>(
    ENDPOINTS.PERSONS.LEAD_HISTORY(personId),
    { tags: [leadTag(personId)] },
  );
  return res.data;
}

export async function createLead(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonLeadStatusDetail>>> {
  const parsed = createLeadSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PersonLeadStatusDetail>>(
      ENDPOINTS.PERSONS.LEAD_STATUS(personId),
      parsed.data,
    );
    // El lead nace + escribe history; afecta el badge del listado.
    revalidateTag(leadTag(personId), "max");
    revalidateTag(activityTag(personId), "max"); // por si emite CAMPAIGN_ATTRIBUTION
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 NO_INITIAL_LEAD_STATUS / 409 ALREADY_HAS_ACTIVE_LEAD en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function transitionLead(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonLeadStatusDetail | null>>> {
  const parsed = leadTransitionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    // Si el destino es is_final, el backend cierra el lead (soft-delete) y devuelve null/cerrado.
    const data = await backendClient.post<ApiSingle<PersonLeadStatusDetail | null>>(
      ENDPOINTS.PERSONS.LEAD_TRANSITION(personId),
      parsed.data,
    );
    // Emite STATUS_CHANGE → invalidar estado + timeline + listado (badge/last_activity).
    revalidateTag(leadTag(personId), "max");
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 LEAD_TRANSITION_NOT_ALLOWED / NO_ACTIVE_LEAD en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function promoteToCustomer(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonCustomerStatusDetail>>> {
  const parsed = promoteToCustomerSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PersonCustomerStatusDetail>>(
      ENDPOINTS.PERSONS.PROMOTE(personId),
      parsed.data,
    );
    // Crea customer + cierra lead (si is_won) + emite actividad.
    revalidateTag(customerTag(personId), "max");
    revalidateTag(leadTag(personId), "max");
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 ALREADY_CUSTOMER / 400 NO_ACTIVE_LEAD en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// getCustomerStatus / getCustomerHistory / transitionCustomer siguen el mismo molde
// con ENDPOINTS.PERSONS.CUSTOMER_* , customerTag(personId) + activityTag + PERSONS_TAG.
export async function getCustomerStatus(personId: string): Promise<PersonCustomerStatusDetail | null> {
  const res = await backendClient.get<ApiSingle<PersonCustomerStatusDetail | null>>(
    ENDPOINTS.PERSONS.CUSTOMER_STATUS(personId),
    { tags: [customerTag(personId)] },
  );
  return res.data;
}

export async function getCustomerHistory(personId: string): Promise<CustomerStatusHistoryItem[]> {
  const res = await backendClient.get<ApiSingle<CustomerStatusHistoryItem[]>>(
    ENDPOINTS.PERSONS.CUSTOMER_HISTORY(personId),
    { tags: [customerTag(personId)] },
  );
  return res.data;
}

export async function transitionCustomer(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonCustomerStatusDetail>>> {
  const parsed = customerTransitionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PersonCustomerStatusDetail>>(
      ENDPOINTS.PERSONS.CUSTOMER_TRANSITION(personId),
      parsed.data,
    );
    revalidateTag(customerTag(personId), "max");
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **`getLeadStatus`/`getCustomerStatus` devuelven `T | null`** (no 404): el backend responde `SingleResponse[null]` (no `PERSON_NOT_FOUND`) cuando la persona existe pero no tiene lead/customer activo — el tab muestra el estado vacío "Sin lead activo · Crear lead". El `PERSON_NOT_FOUND` (404) lo maneja el RSC del detalle (ver [Pages](#pages-rsc)).

### `actions/lead-assignment.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { LeadAssignmentDetail, MyLeadItem } from "@/types/crm.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const leadTag = (id: string) => `crm:lead:${id}`;
const activityTag = (id: string) => `crm:activity:${id}`;

export async function getAssignment(personId: string): Promise<LeadAssignmentDetail | null> {
  const res = await backendClient.get<ApiSingle<LeadAssignmentDetail | null>>(
    ENDPOINTS.PERSONS.ASSIGNMENT(personId),
    { tags: [leadTag(personId)] },
  );
  return res.data; // null si no hay asignación (ASSIGNMENT_NOT_FOUND es para acciones, no para GET vacío)
}

export async function assignAdvisor(
  personId: string,
  input: { advisor_user_id: string; reason?: string | null },
): Promise<MutationResult<ApiSingle<LeadAssignmentDetail>>> {
  try {
    const data = await backendClient.put<ApiSingle<LeadAssignmentDetail>>(
      ENDPOINTS.PERSONS.ASSIGNMENT(personId), // ← PUT (manual / "asignarme")
      input,
    );
    // Emite REASSIGNED → invalida estado + timeline + listado (asesor denormalizado).
    revalidateTag(leadTag(personId), "max");
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 ADVISOR_NOT_FOUND / ADVISOR_NOT_ASESOR en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function assignAuto(
  personId: string,
): Promise<MutationResult<ApiSingle<LeadAssignmentDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<LeadAssignmentDetail>>(
      ENDPOINTS.PERSONS.ASSIGNMENT_AUTO(personId),
      {},
    );
    revalidateTag(leadTag(personId), "max");
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 NO_ADVISOR_AVAILABLE en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// Mis leads (asesor logueado). El backend resuelve el asesor del token.
export async function listMyLeads(query: QueryRequest): Promise<ApiPaginated<MyLeadItem>> {
  return backendClient.post<ApiPaginated<MyLeadItem>>(ENDPOINTS.ME_CRM.LEADS_LIST, query, {
    tags: [PERSONS_TAG], // se invalida al reasignar/transicionar (afecta la lista del asesor)
  });
}
```

### `actions/lead-activity.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  leadActivityCreateSchema,
  leadActivityUpdateSchema,
} from "@/lib/schemas/lead-activity.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { ActivityListRequest, LeadActivityItem } from "@/types/crm.types";
import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const activityTag = (id: string) => `crm:activity:${id}`;

export async function listActivities(
  personId: string,
  filters: ActivityListRequest = {},
): Promise<ApiPaginated<LeadActivityItem>> {
  // POST con body de filtros (activity_type[], rango fecha). PaginatedResponse → `.data`.
  return backendClient.post<ApiPaginated<LeadActivityItem>>(
    ENDPOINTS.PERSONS.ACTIVITIES_LIST(personId),
    filters,
    { tags: [activityTag(personId)] },
  );
}

export async function createActivity(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<LeadActivityItem>>> {
  const parsed = leadActivityCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<LeadActivityItem>>(
      ENDPOINTS.PERSONS.ACTIVITIES_CREATE(personId),
      parsed.data,
    );
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max"); // last_activity_at denormalizado en el listado
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateActivity(
  personId: string,
  actId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<LeadActivityItem>>> {
  const parsed = leadActivityUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<LeadActivityItem>>(
      ENDPOINTS.PERSONS.ACTIVITY(personId, actId), // ← PUT (solo content/outcome/completed_at/scheduled_for)
      parsed.data,
    );
    revalidateTag(activityTag(personId), "max");
    return { ok: true, data };
  } catch (e) {
    // 404 ACTIVITY_NOT_FOUND si no existe o es ajena.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteActivity(
  personId: string,
  actId: string,
): Promise<MutationResult<null>> {
  try {
    // "Borrar" = active=false (no hay soft-delete real); desaparece del feed.
    await backendClient.delete(ENDPOINTS.PERSONS.ACTIVITY(personId, actId));
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/crm/personas/page.tsx` (LISTA)

Análogo a `staff/doctors/page.tsx` / `clinic/offices/page.tsx`. El create vive en un drawer; ver/editar navega al detalle. **Deep-link**: `?lead_status_id=`/`?customer_status_id=`/`?advisor_user_id=` traducidos a `FilterCondition` (campos **virtuales** que el repo traduce a EXISTS/JOIN, igual que `?branch_id=` en staff). El `defaultSort` del prefetch usa una columna **real** de `ALLOWED_FIELDS` (`created_on`), no un denormalizado — debe coincidir con el `defaultSort` del client (lección `cd10c78`).

```tsx
import { listLeadStatuses } from "@/actions/lead-status.actions"; // para el dropdown de filtro (o /active)
import { listActiveLeadStatuses } from "@/actions/lead-status.actions";
import { listActiveCustomerStatuses } from "@/actions/customer-status.actions";
import { listPersons } from "@/actions/person.actions";
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { PersonsClient } from "./_components/PersonsClient";

export const metadata = { title: "Contactos" };

interface PageProps {
  searchParams: Promise<{
    lead_status_id?: string;
    customer_status_id?: string;
    advisor_user_id?: string;
    has_active_lead?: string;
  }>;
}

export default async function PersonsPage({ searchParams }: PageProps) {
  await requirePermission("PERSONS_READ");
  const { lead_status_id, customer_status_id, advisor_user_id, has_active_lead } =
    await searchParams;

  // Deep-link → FilterCondition sobre campos VIRTUALES whitelistados en ALLOWED_FIELDS
  // (el repo los traduce a EXISTS/JOIN; NO son order-by de denormalizados).
  const conditions: FilterCondition[] = [];
  if (lead_status_id)
    conditions.push({ field: "lead_status_id", operator: "eq", value: lead_status_id });
  if (customer_status_id)
    conditions.push({ field: "customer_status_id", operator: "eq", value: customer_status_id });
  if (advisor_user_id)
    conditions.push({ field: "advisor_user_id", operator: "eq", value: advisor_user_id });
  if (has_active_lead === "true")
    conditions.push({ field: "has_active_lead", operator: "eq", value: true });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  // Los catálogos activos pueblan los Dropdowns de filtro (estado lead/cliente).
  const [initialData, leadStatuses, customerStatuses] = await Promise.all([
    listPersons({
      pagination: { skip: 0, limit: 10 },
      // defaultSort = columna REAL (created_on), NO un denormalizado. DEBE coincidir
      // con el defaultSort del PersonsClient (sino: flash + refetch en el primer paint).
      sorting: { sort_by: "created_on", sort_order: "desc" },
      filters,
    }),
    listActiveLeadStatuses(),
    listActiveCustomerStatuses(),
  ]);

  return (
    <PersonsClient
      initialData={initialData}
      leadStatuses={leadStatuses}
      customerStatuses={customerStatuses}
    />
  );
}
```

> **Por qué los filtros son campos virtuales y NO denormalizados de `PersonItem`**: el `PersonItem.lead_status` es un objeto denormalizado para *render* (badge). Para *filtrar/ordenar* server-side, el `ALLOWED_FIELDS` del `PersonRepository` expone campos **virtuales** (`lead_status_id`, `customer_status_id`, `advisor_user_id`, `has_active_lead`) que el repo traduce a `EXISTS(... person_lead_status ...)` / `JOIN` — exactamente como `staff` traduce `?branch_id=` a un EXISTS sobre `doctor_branch`. **Ordenar** por `lead_status_name` o `assigned_advisor` (el texto denormalizado) **NO** está permitido → 400 (lección `cd10c78`). La tabla **no** marca esas columnas como `isSortable`; ordenar por nombre/última actividad denormalizada = client-side sobre la página visible, o no se ofrece.

### Página de detalle de la Persona — `app/(main)/crm/personas/[id]/page.tsx`

Página dedicada con tabs (Resumen · Identificadores · Lead · Cliente · Actividad · Auditoría), análoga al detalle de Office/Doctor. Un solo `getPerson` puebla el header + el tab Resumen + Identificadores (que viajan en `PersonDetail`); los sub-recursos pesados (lead, customer, timeline) cargan en cliente al abrir su tab.

```tsx
import { notFound } from "next/navigation";

import { listActiveLeadStatuses } from "@/actions/lead-status.actions";
import { listActiveCustomerStatuses } from "@/actions/customer-status.actions";
import { getPerson } from "@/actions/person.actions";
import { requirePermission } from "@/lib/auth/session";
import { HttpError } from "@/types/api.types";

import { PersonDetailShell } from "./_components/PersonDetailShell";

type TabId = "summary" | "identifiers" | "lead" | "customer" | "activity" | "audit";
const ALLOWED_TABS: Record<TabId, true> = {
  summary: true,
  identifiers: true,
  lead: true,
  customer: true,
  activity: true,
  audit: true,
};

interface PageProps {
  params: Promise<{ id: string }>;
  // Tab routing en query param, NO sub-ruta: ?tab=lead|activity|… Una URL, deep-linkable.
  searchParams: Promise<{ tab?: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const res = await getPerson(id);
    return { title: `${res.data.full_name} · Contacto` };
  } catch {
    return { title: "Contacto" };
  }
}

export default async function PersonDetailPage({ params, searchParams }: PageProps) {
  await requirePermission("PERSONS_READ");
  const { id } = await params;
  const { tab } = await searchParams;

  let person;
  try {
    person = await getPerson(id);
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) notFound(); // 404 PERSON_NOT_FOUND
    throw e; // que error.tsx maneje el resto
  }

  // Catálogos activos para el TransitionControl (tab Lead/Cliente). Las transiciones
  // permitidas POR ESTADO ACTUAL las trae getLeadTransitions en cliente; estos son
  // los Options para resolver nombres/colores.
  const [leadStatuses, customerStatuses] = await Promise.all([
    listActiveLeadStatuses(),
    listActiveCustomerStatuses(),
  ]);

  const initialTab: TabId =
    tab && tab in ALLOWED_TABS ? (tab as TabId) : "summary";

  return (
    <PersonDetailShell
      person={person.data}
      leadStatuses={leadStatuses}
      customerStatuses={customerStatuses}
      initialTab={initialTab}
    />
  );
}
```

> **Por qué tab en query param y no sub-rutas** (mismo criterio que Doctor/Office): un solo `getPerson` poblando el header (nombre, doc, badges de estado, asesor) sirve a las 6 vistas; sub-rutas duplicarían ese fetch o forzarían un `layout.tsx`. El `?tab=` es deep-linkable, sobrevive refresh. Los tabs **lead/customer/activity** cargan sus datos en cliente (`getLeadStatus`/`getLeadHistory`, `getCustomerStatus`, `listActivities`) cuando se seleccionan — no en el RSC (primer paint instantáneo).

### `app/(main)/crm/mis-leads/page.tsx`

Lista de los leads asignados al asesor logueado (`POST /me/leads/list`). El backend resuelve el asesor del token. Mismo patrón `useTableQuery` + `defaultSort` sobre columna real.

```tsx
import { listMyLeads } from "@/actions/lead-assignment.actions";
import { requirePermission } from "@/lib/auth/session";

import { MyLeadsClient } from "./_components/MyLeadsClient";

export const metadata = { title: "Mis leads" };

export default async function MyLeadsPage() {
  await requirePermission("MY_LEADS_READ");
  const initialData = await listMyLeads({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "last_activity_at", sort_order: "desc" }, // ver nota: columna real del query /me
    filters: null,
  });
  return <MyLeadsClient initialData={initialData} />;
}
```

> **`/me/leads/list` ordena por `last_activity_at`**: a diferencia del listado general de personas (donde `last_activity_at` es un denormalizado NO whitelistado), el endpoint `/me/leads` parte de `person_lead_status` (que **sí** tiene `last_activity_at` como columna real) → el backend lo expone como sortable en **ese** query. Confirmar con [`backend.md`](./backend.md#me-leads) qué columnas son `ALLOWED_FIELDS` de `/me/leads` y que el `defaultSort` del client coincida. Si `last_activity_at` no es sortable allí, usar `entered_status_at` o `created_on`.

### Pages de catálogos — `estados-lead` / `estados-cliente`

```tsx
// app/(main)/crm/estados-lead/page.tsx
import { listLeadStatuses } from "@/actions/lead-status.actions";
import { requirePermission } from "@/lib/auth/session";

import { LeadStatusesClient } from "./_components/LeadStatusesClient";

export const metadata = { title: "Estados de lead" };

export default async function LeadStatusesPage() {
  await requirePermission("LEAD_STATUSES_READ");
  const initialData = await listLeadStatuses({
    pagination: { skip: 0, limit: 50 }, // catálogo chico; una sola página suele bastar
    sorting: { sort_by: "display_order", sort_order: "asc" }, // columna real
    filters: null,
  });
  return <LeadStatusesClient initialData={initialData} />;
}
```

> `estados-cliente/page.tsx` es idéntico con `listCustomerStatuses` + `requirePermission("CUSTOMER_STATUSES_READ")` + `metadata.title = "Estados de cliente"`.

## Client components — esqueletos

> **No reproduzco los archivos completos** — siguen el patrón exacto de `staff/doctors/_components/*` + `clinic/offices/_components/*` + `admin/users/_components/UserDrawer.tsx`. Documento las diferencias específicas a crm. El **`ActivityTimeline` es la pieza sustancialmente nueva** y se detalla aparte. La UI detallada (mockups, estados, copy) vive en [`ui.md`](./ui.md).

### `PersonsClient.tsx`

Sigue el patrón de `DoctorsClient.tsx` (lista con filtros + drawer de creación + RowActions que navegan). Diferencias:

- Recibe `leadStatuses: LeadStatusOption[]` y `customerStatuses: CustomerStatusOption[]` como props (para los Dropdowns de filtro).
- `useTableQuery`: `queryKey: "crm:persons"`, `fetcher: listPersons`, `searchFields: ["full_name", "document_number"]` (**client-side**: `full_name` y los identificadores son denormalizados, no server-searchable; el `useTableQuery` busca sobre la página visible), `defaultSort: { field: "created_on", order: "desc" }` (**columna real**, coincide con el prefetch RSC), `initialData`.
- State `leadStatusFilter`/`customerStatusFilter`/`advisorFilter`/`hasActiveLead` sincronizados con URL (`nuqs`); Dropdowns en la toolbar (Estado lead, Estado cliente, Asesor) + toggle "Con lead activo" + chips "Filtrado por: …" con ✕ (mismo flujo que el filtro de sede en `DoctorsClient`). El dropdown de Asesor se puebla con `listActiveAdvisors()` → `GET /crm/advisors/active` (`ENDPOINTS.CRM.ADVISORS.ACTIVE`, gated `LEAD_ASSIGNMENTS_READ`; crm-owned, **no** `admin/users` — el ASESOR no tiene `USERS_VIEW`).
- Columns: `actions`, `full_name` (Nombre), `primary_identifier` (Contacto principal — ícono de canal vía `CHANNEL_TYPE_META` + valor + badge "verificado"), `lead_status` (badge color vía `StatusBadge`), `customer_status` (badge), `assigned_advisor` (full_name o "—"), `last_activity_at` (fecha relativa, `?? "—"`), `active` (Badge "Activo"/"Inactivo" — femenino "persona" pero el badge es neutro; usar "Activo"/"Inactivo"). **Ninguna de las columnas denormalizadas es `isSortable`** (lección `cd10c78`); sólo `created_on`/`updated_on` (reales) podrían serlo si el backend las whitelista. Ver [`ui.md`](./ui.md#pantallas).
- **RowActions = navegación** (como doctores):
  ```ts
  { key: "view",  label: "Ver",    icon: <EyeRegular />,  onSelect: (p) => router.push(`/crm/personas/${p.id}`) },
  { key: "edit",  label: "Editar", icon: <EditRegular />, permissions: ["PERSONS_UPDATE"], onSelect: (p) => router.push(`/crm/personas/${p.id}?tab=summary`) },
  { key: "delete",label: "Eliminar",icon: <DeleteRegular />, permissions: ["PERSONS_DELETE"], danger: true, onSelect: (p) => { setDeleteError(null); setDeleteTarget(p); } },
  ```
- Botón "Nuevo contacto" gated `PERSONS_CREATE` → abre `PersonCreateDrawer`.
- **`ConfirmDialog`** para delete (soft): "Se eliminará el contacto. Sus identificadores, estados e historial dejarán de mostrarse." (es soft-delete; no hay 409 por hijos en el MVP — confirmar con backend si un Person con lead activo bloquea el delete).

### `PersonCreateDrawer.tsx`

Drawer **solo-create** (la edición vive en el detalle, tab Resumen). Combina el form de identidad con una **lista add/remove de identificadores iniciales** (canal + valor + principal + verificado). Puntos clave:

- `useForm<PersonCreateInput>({ resolver: zodResolver(personCreateSchema), defaultValues: { first_name: "", last_name: "", identifiers: [] } })`.
- **Sección Identidad**: `first_name`, `last_name`, `second_last_name`, `document_type` (Dropdown DNI/RUC/CE o Input), `document_number`, `birth_date` (`Input type="date"`), `gender` (Input texto libre), `address`, `notes` (Textarea).
- **Sección Identificadores iniciales** (`useFieldArray` de react-hook-form): cada fila = `Dropdown channel_type` (opciones de `CHANNEL_TYPES` con `CHANNEL_TYPE_META[c].label` + ícono) + `Input identifier` + `Checkbox is_primary` + `Checkbox verified` + botón quitar. Botón "Agregar identificador" hace `append({ channel_type: "whatsapp", identifier: "", is_primary: false, verified: false })`. El `superRefine` de `personCreateSchema` marca duplicados y `>1 principal por canal` inline.
- **Errores de servidor**: `409 IDENTIFIER_TAKEN` (un identifier inicial ya existe en otra persona) → `MessageBar intent="error"` sin cerrar el drawer.
- En `onSuccess`: `router.push(\`/crm/personas/${result.data.data.id}\`)` para llevar al detalle (donde se crea el lead, se asigna asesor, etc.). El POST devuelve `SingleResponse[PersonDetail]` → `result.data.data` es el `PersonDetail`.

### `PersonDetailShell.tsx`

Cliente. Molde directo de `DoctorDetailShell`/`OfficeDetailShell`. Recibe `person: PersonDetail`, `leadStatuses: LeadStatusOption[]`, `customerStatuses: CustomerStatusOption[]`, `initialTab`. Responsabilidades:

- Header: `person.full_name`, `document_type document_number` (si hay), **badges** de estado lead (`StatusBadge` con `person.lead_status`) y cliente (`person.customer_status`), asesor asignado (`person.assigned_advisor.full_name` o "Sin asignar"), botón/Link "Volver a contactos" (`/crm/personas`).
- `TabList` (Fluent) con 6 tabs: **Resumen · Identificadores · Lead · Cliente · Actividad · Auditoría**. Al cambiar de tab, actualizar `?tab=` con `nuqs` (`useQueryState`) para deep-link. Resolver el tab activo con fallback a `summary` (mismo patrón `ALLOWED_TABS[tab]` que `DoctorDetailShell`).
- **Gating de tabs por permisos** (`usePermissions`):
  - **Resumen** siempre visible (gated por `PERSONS_READ` del RSC); edición requiere `PERSONS_UPDATE`.
  - **Identificadores** visible con `PERSONS_READ`; CRUD requiere `PERSONS_UPDATE` (los endpoints de identifier piden `PERSONS_UPDATE`, no un permiso propio).
  - **Lead** visible con `LEAD_ACTIVITIES_READ` o `LEAD_STATUS_HISTORY_READ`; transicionar/crear lead/promover requiere `LEAD_ACTIVITIES_WRITE`; ver history requiere `LEAD_STATUS_HISTORY_READ`.
  - **Cliente** análogo (history `LEAD_STATUS_HISTORY_READ`; transición `LEAD_ACTIVITIES_WRITE`).
  - **Actividad** visible con `LEAD_ACTIVITIES_READ`; composer/editar/borrar requiere `LEAD_ACTIVITIES_WRITE`.
  - **Auditoría** visible con `PERSONS_READ`.
  ```tsx
  {activeTab === "summary" ? (
    <PersonSummaryTab person={person} leadStatuses={leadStatuses} customerStatuses={customerStatuses} />
  ) : activeTab === "identifiers" ? (
    <IdentifiersTab personId={person.id} canWrite={hasPermission("PERSONS_UPDATE")} />
  ) : activeTab === "lead" ? (
    <LeadTab personId={person.id} leadStatuses={leadStatuses} canWrite={hasPermission("LEAD_ACTIVITIES_WRITE")} />
  ) : activeTab === "customer" ? (
    <CustomerTab personId={person.id} customerStatuses={customerStatuses} canWrite={hasPermission("LEAD_ACTIVITIES_WRITE")} />
  ) : activeTab === "activity" ? (
    <ActivityTimeline personId={person.id} canWrite={hasPermission("LEAD_ACTIVITIES_WRITE")} />
  ) : (
    <PersonAuditTab person={person} />
  )}
  ```

### `PersonSummaryTab.tsx`

Form de edición inline del perfil de identidad (no drawer). Molde de `DoctorProfileTab`/`OfficeDetailsTab`. Diferencias:

- **Editables** (gated `PERSONS_UPDATE`; si falta, todo disabled): `first_name`, `last_name`, `second_last_name`, `document_type`, `document_number`, `birth_date`, `gender`, `address`, `notes`, `active` (Switch).
- **Bloque de estado** (solo lectura aquí; se gestiona en los tabs Lead/Cliente): `StatusBadge` del lead + del cliente, `AssignmentControl` (mostrar asesor + botones "Reasignar" / "Asignarme" / "Asignar automático" gated `LEAD_ASSIGNMENTS_WRITE`), contacto principal (ícono canal + valor).
- Submit → `updatePerson(person.id, values)`; en éxito `router.refresh()` para re-pintar el header. Errores de servidor en `MessageBar`.

### `IdentifiersTab.tsx`

Lista multicanal con CRUD inline. Molde de `OfficeClosuresTab` (lista + crear/editar/borrar con fetch en cliente). Diferencias:

- Carga `listIdentifiers(personId)` en cliente al abrir el tab (con `useState` + `useEffect`; **fetch-token** opcional —la lista es chica, pero usar el patrón monotónico si se re-fetchea tras mutar). Estado por id `Record<string, PersonContactIdentifierItem>` para edición/borrado O(1).
- Cada fila: ícono de canal (`CHANNEL_TYPE_META`), valor, badge "Principal" (si `is_primary`), badge "Verificado" (si `verified`), acciones (editar inline / borrar gated `PERSONS_UPDATE`).
- "Marcar como principal" → `updateIdentifier(personId, id, { is_primary: true })` (el backend desmarca el anterior del mismo canal en una tx). "Marcar verificado" → `updateIdentifier(..., { verified: true })`.
- Agregar → drawer/popover con `contactIdentifierCreateSchema` (canal + valor + principal + verificado) → `createIdentifier`. Error `IDENTIFIER_TAKEN` (409) en `MessageBar`.
- Tras cualquier mutación exitosa, re-`load()` (el tag `crm:identifiers:{personId}` se revalidó server-side).

### `LeadTab.tsx`

Estado lead actual + transición + history + promover. Carga en cliente al abrir el tab: `getLeadStatus(personId)` (puede ser `null` → estado vacío) + `getLeadHistory(personId)`.

- **Si no hay lead activo** (`null`): estado vacío "Esta persona no tiene un lead activo." + botón "Crear lead" gated `LEAD_ACTIVITIES_WRITE` → form con `source_campaign_id?` (Input opcional, solo lectura útil — es forward FK) + `reason?` → `createLead(personId, values)`. El lead nace en el `is_initial` del catálogo (`NO_INITIAL_LEAD_STATUS` 400 si no hay; mostrar en `MessageBar`).
- **Si hay lead activo**: `StatusBadge` del estado actual + `entered_status_at` (fecha) + `source_campaign_id` (solo lectura, "—" si null) + **`TransitionControl`** (dropdown SOLO con los destinos permitidos; ver [TransitionControl](#transitioncontrol)) + botón "Promover a cliente" gated `LEAD_ACTIVITIES_WRITE` (abre confirm con `reason?` → `promoteToCustomer`).
- **History** (gated `LEAD_STATUS_HISTORY_READ`): timeline simple de `LeadStatusHistoryItem` (from→to badges, `changed_at`, `changed_by_user.full_name ?? "Sistema"`, `reason`). Vertical, más reciente arriba. **No** es el timeline rico de actividades (eso es el tab Actividad) — es solo la traza de cambios de estado.
- Tras transicionar/promover, re-cargar `getLeadStatus`+`getLeadHistory` (los tags `crm:lead:{id}` se revalidaron). Si el destino fue `is_final`, `getLeadStatus` vuelve `null` → muestra el estado cerrado/vacío.

### `CustomerTab.tsx`

Análogo a `LeadTab` con la matriz customer: `getCustomerStatus(personId)` + `getCustomerHistory(personId)`. Sin "crear customer" manual (el customer nace por `promoteToCustomer` desde el tab Lead; aquí solo se transiciona si ya es cliente). `became_customer_at` mostrado en el header del tab. `TransitionControl` con `getCustomerTransitions`. Estado vacío si `null`: "Esta persona aún no es cliente. Promuévela desde el tab Lead."

### `TransitionControl`

Componente compartido. Dado el estado actual, ofrece **solo** los destinos permitidos por la matriz. Recibe `currentStatusId`, `kind: "lead" | "customer"`, `onTransition(toId, reason?)`, `disabled`. Carga `getLeadTransitions(currentStatusId)` (o `getCustomerTransitions`) en cliente → renderiza un `Menu`/`Dropdown` con los `TransitionTargets.to` (cada uno con su `StatusBadge`/color). Si el estado actual es **terminal** (`is_final`) → no hay destinos → control **deshabilitado** con hint "Estado final, sin transiciones." Al elegir un destino, abre un popover con `reason?` opcional → llama `onTransition`. El error `LEAD_TRANSITION_NOT_ALLOWED` (400) **no debería** ocurrir (solo se ofrecen destinos válidos), pero si la matriz cambió entre el load y el submit, se muestra en `MessageBar` (defensa).

### `AssignmentControl`

Componente compartido (usado en `PersonSummaryTab`). Recibe `personId`, `currentAdvisor: UserAuditInfo | null`, `canWrite`. Muestra el asesor actual (`full_name` o "Sin asignar"). Si `canWrite` (`LEAD_ASSIGNMENTS_WRITE`):
- **"Asignarme"** → `assignAdvisor(personId, { advisor_user_id: currentUser.id })` (el id del user logueado, de `useAuth()`).
- **"Reasignar"** → dropdown de asesores (`listActiveAdvisors()` → `GET /crm/advisors/active`, gated `LEAD_ASSIGNMENTS_READ`; crm-owned) → `assignAdvisor(personId, { advisor_user_id })`. Error `ADVISOR_NOT_ASESOR` (400) en `MessageBar`.
- **"Asignar automático"** (round-robin) → `assignAuto(personId)`. Error `NO_ADVISOR_AVAILABLE` (400).
Tras asignar, `router.refresh()` (re-pinta el header) — la asignación afecta `crm:lead:{id}` + `crm:persons`.

### `StatusBadge`

Componente compartido (tablas + tabs). Recibe `status: LeadStatusSummary | CustomerStatusSummary | null` + `kind`. Renderiza un `Badge` Fluent con el `color` del catálogo (hex) como fondo/borde y el `name`. Si `null` → "—" (o "Sin lead"/"Sin cliente" según contexto). El `color` viene de BD (configurable), **no** de `brandPalette` — se aplica como `style={{ backgroundColor: status.color ?? tokens.colorNeutralBackground3 }}` con contraste de texto calculado (o un `appearance="tint"` de Fluent si el color es claro). Documentar el cálculo de contraste como best-effort.

### `ActivityTimeline.tsx` — el feed pesado

> **Honestidad (igual que pide la spec)**: este timeline (composer + chips + feed agrupado por día + tarjetas tipadas) es **bespoke** dentro de Fluent UI 9 — se miran patrones de CRMs modernos (HubSpot/Pipedrive/Intercom) pero se ejecutan **DENTRO de Fluent** (tokens, primitivas propias, sin librería de timeline). Es **el componente más complejo de crm**. Construirlo **incrementalmente**: (1) feed read-only + composer de Nota + chips → (2) Llamada/Seguimiento en el composer + editar/borrar inline + filtro server-side. La capa de datos (cargar, filtrar, persistir vía actions) es idéntica en ambas etapas. La UI detallada (mockups, estados) está en [`ui.md`](./ui.md#timeline). Aquí documento **estructura de componentes y estado**, no la UI completa.

Props: `{ personId: string; canWrite: boolean }`.

**Estructura de sub-componentes** (todos en `personas/[id]/_components/`):

```
ActivityTimeline           (orquesta: estado, carga, filtros, agrupación)
├── ActivityComposer       (tabs Nota/Llamada/Seguimiento → form contextual → createActivity)
├── ActivityFilterChips    (chips por ACTIVITY_FILTER_GROUPS; filtra client-side o re-query)
└── ActivityDayGroup[]     (una sección por día: "Hoy"/"Ayer"/"12 may")
    └── ActivityCard[]     (tarjeta tipada, React.memo)
```

**Shape del estado** (lo central):

```ts
// Actividades cargadas, indexadas por id para edición/borrado O(1).
const [activities, setActivities] = useState<Record<string, LeadActivityItem>>({});
// Filtro activo (key de ACTIVITY_FILTER_GROUPS). "all" = sin filtro.
const [activeFilter, setActiveFilter] = useState<string>("all");
const [loading, setLoading] = useState(true);
const [listError, setListError] = useState<string | null>(null);
// Token monotónico para descartar respuestas fuera de orden (idéntico a OfficeClosuresTab):
// al cambiar de filtro rápido, una respuesta vieja no debe pisar la nueva.
const reqIdRef = useRef(0);
```

**Carga + filtro** (patrón fetch-token + `load` reutilizable, como `OfficeClosuresTab`/`DoctorAvailabilityTab`):

```ts
const load = useCallback(() => {
  const reqId = ++reqIdRef.current;
  setLoading(true);
  setListError(null);
  // El filtro puede ser client-side (cargar todo, filtrar en render) o server-side
  // (re-query con activity_type[]). MVP: re-query server-side por grupo (menos memoria).
  const group = ACTIVITY_FILTER_GROUPS.find((g) => g.key === activeFilter);
  const filters = group?.types ? { activity_type: group.types } : {};
  void listActivities(personId, filters)
    .then((res) => {
      if (reqId !== reqIdRef.current) return; // respuesta superada → descartar
      setActivities(Object.fromEntries(res.data.items.map((a) => [a.id, a])));
      setLoading(false);
    })
    .catch(() => {
      if (reqId !== reqIdRef.current) return;
      setActivities({});
      setListError("No se pudo cargar la actividad. Intenta de nuevo.");
      setLoading(false);
    });
}, [personId, activeFilter]);

useEffect(() => { load(); }, [load]);
```

**Agrupación por día** (`new Date()` **client-only** — lección TZ de staff; el SSR en UTC desfasaría "hoy" en TZ negativas como Lima `-05:00`):

```ts
// Computado en el cliente (este componente es "use client") con la TZ del navegador.
const dayGroups = useMemo(() => {
  const list = Object.values(activities).sort(
    (a, b) => new Date(b.created_on).getTime() - new Date(a.created_on).getTime(),
  );
  // groupByDay devuelve [{ label: "Hoy"|"Ayer"|"12 may", items: [...] }] usando
  // new Date() (hoy del navegador). NO se hace en SSR.
  return groupByDay(list);
}, [activities]);
```

**`ActivityCard`** (memoizada, regla vercel-react: sin re-render innecesario):

```tsx
export const ActivityCard = React.memo(function ActivityCard({
  activity,
  canWrite,
  onEdit,
  onDelete,
}: {
  activity: LeadActivityItem;
  canWrite: boolean;
  onEdit: (a: LeadActivityItem) => void;
  onDelete: (a: LeadActivityItem) => void;
}) {
  const meta = ACTIVITY_TYPE_META[activity.activity_type];
  const Icon = meta.icon;
  // ícono+color por tipo, actor (advisor.full_name + avatar inicial, "Sistema" si null),
  // timestamp relativo (formatRelative client-only), content, outcome chip (llamadas),
  // seguimientos futuros (scheduled_for > now) resaltados con banda/acento.
  // Editar/borrar (gated canWrite) solo para tipos editables (NOTE/CALL_ATTEMPT/FOLLOW_UP_*).
  return (/* … Fluent Card con tokens, sin brandPalette.accent … */);
});
```

**`ActivityComposer`** (gated `canWrite`): tabs rápidas **Nota / Llamada / Seguimiento** → form contextual:
- **Nota**: `Textarea content` → `createActivity(personId, { activity_type: "NOTE", content })`.
- **Llamada**: `Dropdown outcome` (ACTIVITY_OUTCOME_LABELS) + `Textarea content` opcional + (opcional) duración en `payload` → `{ activity_type: "CALL_ATTEMPT", outcome, content }`.
- **Seguimiento**: `Input datetime-local scheduled_for` (serializado a ISO **client-only**) + canal recordatorio en `payload` → `{ activity_type: "FOLLOW_UP_SCHEDULED", scheduled_for }`.
Botón "Registrar" → `createActivity` → en éxito, `load()` (re-fetch) + reset del form.

**Estados** (todos en español):
- **loading**: skeletons de tarjetas.
- **vacío**: "Sin actividad aún · registra la primera nota" (solo con `canWrite`; read-only: "Sin actividad registrada.").
- **error**: `MessageBar intent="error"` con `listError`/`result.error`.
- **read-only** (`!canWrite`): feed visible, sin composer, sin editar/borrar.

**Editar/borrar**: editar nota/outcome inline (popover con `leadActivityUpdateSchema`) → `updateActivity`; "eliminar" = `active=false` (`deleteActivity`) → desaparece del feed. Tras cualquier mutación, `load()`.

### `PersonAuditTab.tsx`

Idéntico al `DoctorAuditTab`/`OfficeAuditTab`: Badge de estado (`Activo`/`Inactivo`), id de la persona, `created_on`/`created_by_user.full_name`, `updated_on`/`updated_by_user.full_name`. Reusa el layout de grid (`formatDate`, `?? "—"` cuando el actor fue hard-deleted).

### `LeadStatusesClient.tsx` / `CustomerStatusesClient.tsx`

Molde de catalog (`VerticalsClient`): tabla simple + drawer CRUD. Diferencias:

- `useTableQuery`: `queryKey: "crm:lead-statuses"`, `fetcher: listLeadStatuses`, `defaultSort: { field: "display_order", order: "asc" }` (**columna real**, coincide con el prefetch), `searchFields: ["code", "name"]`.
- Columns: `actions`, `display_order`, `code`, `name`, `color` (swatch — cuadrito con `style={{ backgroundColor: color }}`), `is_initial`/`is_final`/`is_won` (badges "Inicial"/"Final"/"Ganado"), `active`. `customer-statuses` sin la columna `is_won`.
- **RowActions**: Editar (gated `LEAD_STATUSES_WRITE`) → `LeadStatusDrawer`; Eliminar (gated `LEAD_STATUSES_WRITE`, danger). Error `LEAD_STATUS_IN_USE` (409) en `ConfirmDialog`/`MessageBar` ("No se puede eliminar: hay leads o historial usando este estado.").
- Botón "Nuevo estado" gated `LEAD_STATUSES_WRITE`.
- **Editor de matriz**: un botón "Transiciones" por fila (o un acordeón) que abre el `StatusMatrixEditor` para ese estado. Alternativa: una sección dedicada bajo la tabla.

### `LeadStatusDrawer.tsx`

Drawer create/edit. `useForm` con `leadStatusCreateSchema`/`leadStatusUpdateSchema`. Campos: `code` (solo en create; disabled en edit), `name`, `description`, `color` (color picker o Input hex + swatch preview), `display_order`, y los **switches** `is_initial`/`is_final`/`is_won`. El `superRefine` marca `is_won` sin `is_final` inline. Al marcar `is_initial` mostrar hint "Esto desmarcará el estado inicial actual." (el backend lo desmarca; `MULTIPLE_INITIAL_STATUS` 400 si algo falla → `MessageBar`). `customer-status` sin `is_won`.

### `StatusMatrixEditor.tsx`

Editor de las aristas de salida de un estado. Recibe `statusId`, `allStatuses: LeadStatusOption[]` (todos los del catálogo), `kind: "lead" | "customer"`. Carga `getLeadTransitions(statusId)` → preselecciona los `to.id`. Renderiza un **multiselect** (`SearchableOptionList`, mismo helper que roles/permisos en `UserDrawer` — cero código nuevo) con todos los estados **menos el propio** (un estado no transiciona a sí mismo). Al guardar → `setLeadTransitions(statusId, { to_ids })` (reemplaza). MVP = multiselect por estado; la **grilla visual from×to** es diferible (spec §8.5). Estado terminal (`is_final`) → multiselect vacío/deshabilitado con hint "Estado final: sin transiciones de salida."

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| `PUT` para updates (no `PATCH`) | Alineación a catalog/clinic/staff shipped (`backendClient.put`); el overview viejo de crm decía `PATCH`. Evita drift back↔front. |
| `/active` para dropdowns (no `/options`) | Misma convención que `BRANCHES.ACTIVE`/`DOCTORS.ACTIVE` shipped; el overview viejo decía `/options`. `/search` se conserva (endpoint funcional del bot, distinto del dropdown). |
| `revalidateTag(TAG, "max")` (2º arg) | Next 16 exige el 2º argumento; omitirlo es error (lección del template). Todos los actions lo pasan. |
| Persona drawer-de-creación; detalle = página con 6 tabs | La persona tiene muchos sub-recursos (identificadores, lead, cliente, timeline, auditoría); no caben en un drawer. Reusa el patrón "entidad con sub-recursos" de Office/Doctor. |
| Tab del detalle en `?tab=` (query param) | Un solo `getPerson` sirve al header + Resumen + Identificadores; deep-linkable; sin `layout.tsx` extra. Lead/Cliente/Actividad cargan en cliente. |
| **`defaultSort`/`isSortable`/`searchFields` SOLO sobre columnas reales de `ALLOWED_FIELDS`** | **Lección hotfix `cd10c78` de staff**: ordenar/filtrar server-side por una columna denormalizada (`primary_identifier`, `lead_status_name`, `assigned_advisor`, `last_activity_at`) devuelve 400 → error boundary del RSC. El `defaultSort` del client (`created_on`) **DEBE coincidir** con el `sorting` del prefetch RSC, sino flash + refetch. |
| Búsqueda por nombre/identificador = **client-side** | `full_name` y los identificadores son denormalizados (no whitelistados). `useTableQuery.searchFields` busca sobre la página visible; no genera `FilterCondition` server-side. |
| Deep-link `?lead_status_id=`/`?customer_status_id=`/`?advisor_user_id=`/`?has_active_lead=` → **campos virtuales** | El page RSC los traduce a `FilterCondition` sobre campos virtuales whitelistados (`lead_status_id`, etc.) que el repo convierte a EXISTS/JOIN — como `staff` con `?branch_id=`. NO son order-by de denormalizados. |
| Filtro del timeline = re-query server-side por grupo de tipo | `listActivities(personId, { activity_type: [...] })` en el body; menos memoria que cargar todo y filtrar client-side. El "hoy"/"ayer" de la agrupación sigue siendo client-only. |
| **Agrupación "hoy"/"ayer" del timeline = client-only** | `new Date()` que afecta render = client-only (lección TZ de staff; SSR en UTC desfasa el día en TZ negativas como Lima `-05:00`). El timeline es `"use client"`; la agrupación se computa con la TZ del navegador. |
| `scheduled_for`/`completed_at` serializados a ISO client-only | El composer compone el `Date` local (input `datetime-local`) y hace `.toISOString()` en cliente. No construir en SSR. |
| `getLeadStatus`/`getCustomerStatus`/`getAssignment` devuelven `T \| null` | El backend responde `SingleResponse[null]` (no 404) cuando la persona existe pero no tiene lead/customer/asignación — el tab muestra el estado vacío, no error. El 404 `PERSON_NOT_FOUND` lo maneja el RSC. |
| `TransitionControl` ofrece SOLO destinos permitidos por la matriz | `getLeadTransitions(currentStatusId)` resuelve las aristas; previene `LEAD_TRANSITION_NOT_ALLOWED`. Estado terminal → control deshabilitado. |
| `StatusBadge` usa el `color` del catálogo (hex BD), no `brandPalette` | `brandPalette` no tiene `accent`; el color del estado es configurable en BD. Para otros colores (íconos de actividad) → tokens Fluent semánticos. |
| Tags por-persona (`crm:lead:{id}`, `crm:activity:{id}`, `crm:identifiers:{id}`) + cross-tag | El detalle de una persona es independiente; taggear por id evita invalidar todas. Una transición/reasignación cruza tags (estado + timeline + `crm:persons` por los denormalizados del listado). |
| `ActivityCard` memoizada (`React.memo`) + estado por id | Listas largas sin re-render innecesario (reglas vercel-react); edición/borrado O(1). |
| Identificadores iniciales nested en el create de Person (opcional) | Espeja `person.create` del backend; el dedup intra-body se valida con `superRefine` en español; el dedup contra BD es `IDENTIFIER_TAKEN` del servidor. |
| 3 columnas forward (`source_campaign_id`/`related_*`) = strings opacos solo lectura | ADR-009: son `varchar(36)` sin FK ni relationship; el front no las resuelve a entidades (esos módulos no existen). Se muestran como texto o "—". |
| Person create NO crea lead automáticamente | Espeja el backend: el lead se crea desde el tab Lead (`POST /lead-status`) o por `find_by_identifier_or_create` (bot, sin UI MVP). |
| Sin bulk actions, sin duplicar, sin import CSV | Postergados al MVP+1 (igual que catalog/clinic/staff). |

## Checklist de implementación (mapeado a fases F0–F5)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md#checklist-de-implementación) y [`ui.md`](./ui.md). Cada checkbox es lado frontend.

### F0 — Prep (andamiaje compartido)

- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `CRM` (`PERSONS` con nested IDENTIFIERS/LEAD_STATUS/CUSTOMER_STATUS/ASSIGNMENT/ACTIVITIES, `LEAD_STATUSES`, `CUSTOMER_STATUSES`, `ME_CRM`). Verbos `PUT`, rutas `/active`/`/search`.
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `crm` ("CRM" → Contactos `PERSONS_READ`, Mis leads `MY_LEADS_READ`, Estados de lead `LEAD_STATUSES_READ`, Estados de cliente `CUSTOMER_STATUSES_READ`; grupo gated `MENU-CRM`).
- [ ] Registrar íconos `PeopleRegular`/`ContactCardRegular`/`PersonRegular`/`TagRegular`/`TagMultipleRegular` en el `iconMap` del `Sidebar.tsx` (con fallbacks verificados).
- [ ] Crear `src/types/crm.types.ts` (TODAS las interfaces + enums `ChannelType`/`ActivityType`/`ActivityOutcome`; reusa `UserAuditInfo`).
- [ ] Crear `src/lib/constants/crm.ts` (`CHANNEL_TYPE_META`, `ACTIVITY_TYPE_META`, `ACTIVITY_OUTCOME_LABELS`, `ACTIVITY_FILTER_GROUPS`).
- [ ] **Permisos test (F0)**: como user con `MENU-CRM` (rol ASESOR), el grupo "CRM" aparece con sus items según permisos finos. Sin ninguno de los permisos hijos, el grupo no aparece. (Los 15 permisos CRM + roles ya están en `seed.py` — ver [`../_seed-and-roles.md`](../_seed-and-roles.md). El SYSTEM user + role los introduce backend F0.)

### F1 — Person + Identifiers

- [ ] Crear `src/lib/schemas/person.schema.ts` (identidad + identifiers nested opcionales, `superRefine` dedup intra-body + ≤1 principal por canal) y `contact-identifier.schema.ts` (enum `channel_type` + `superRefine` por canal).
- [ ] Crear `src/actions/person.actions.ts` (list/active/search/get/create/update/delete; tag `crm:persons`) y `contact-identifier.actions.ts` (list/create/update/delete; tag `crm:identifiers:{id}` + `crm:persons`).
- [ ] Crear `src/app/(main)/crm/personas/page.tsx` (`metadata.title = "Contactos"`, prefetch con `defaultSort = created_on` + dropdowns de filtro; deep-link `?lead_status_id=`/`?advisor_user_id=` → campos virtuales).
- [ ] Crear `_components/PersonsClient.tsx` (tabla con columnas denormalizadas NO sortables, búsqueda client-side, filtros chip, RowActions navegan) + `PersonCreateDrawer.tsx` (identidad + `useFieldArray` de identificadores iniciales, navega al detalle al crear).
- [ ] Crear `src/app/(main)/crm/personas/[id]/page.tsx` (detail RSC, `?tab=` routing, `getPerson` + catálogos activos; 404 `PERSON_NOT_FOUND` → `notFound()`) + `_components/PersonDetailShell.tsx` + `PersonSummaryTab.tsx` + `IdentifiersTab.tsx` + `PersonAuditTab.tsx` (tabs Lead/Cliente/Actividad = **placeholders** hasta F3–F5).
- [ ] **Smoke test (F1)**: `/crm/personas` → "Nuevo contacto" → identidad + 1 identificador WhatsApp principal → crear → navega a `/crm/personas/{id}` → tab Identificadores muestra el identificador con ícono+verificado → editar identidad (tab Resumen) → header refleja cambios → soft-delete desde la lista.
- [ ] **Filtro/deep-link test (F1)**: `/crm/personas?lead_status_id=X` filtra + chip; combinable con `?advisor_user_id=Y`; `?has_active_lead=true` toggle; ✕ limpia. **Verificar que NO se intente ordenar por columna denormalizada** (no rompe a 400).
- [ ] **Error test (F1)**: crear contacto con un identificador ya usado en otra persona → `409 IDENTIFIER_TAKEN` en `MessageBar` sin cerrar el drawer; duplicar un identificador dentro del mismo drawer → error inline Zod en español.
- [ ] **Permisos test (F1)**: sin `PERSONS_CREATE` no aparece "Nuevo contacto"; sin `PERSONS_UPDATE` el RowAction "Editar" no aparece, el Resumen está disabled y el tab Identificadores es read-only; sin `PERSONS_DELETE` no aparece "Eliminar"; sin `PERSONS_READ` el RSC del detalle redirige.

### F2 — Catálogos + matriz

- [ ] Crear `src/lib/schemas/lead-status.schema.ts` (`superRefine` is_won⟹is_final + `transitionTargetsSchema`) y `customer-status.schema.ts` (sin is_won).
- [ ] Crear `src/actions/lead-status.actions.ts` (CRUD + active + getTransitions/setTransitions; tag `crm:lead-statuses`) y `customer-status.actions.ts` (idem; tag `crm:customer-statuses`).
- [ ] Crear `src/app/(main)/crm/estados-lead/page.tsx` (`metadata.title = "Estados de lead"`, prefetch `defaultSort = display_order`) + `_components/LeadStatusesClient.tsx` + `LeadStatusDrawer.tsx` + `StatusMatrixEditor.tsx` (multiselect "transiciones permitidas hacia…", reusa `SearchableOptionList`).
- [ ] Crear `src/app/(main)/crm/estados-cliente/page.tsx` + `_components/CustomerStatusesClient.tsx` + `CustomerStatusDrawer.tsx` (reusa `StatusMatrixEditor` con `kind="customer"`).
- [ ] **Smoke test (F2)**: `/crm/estados-lead` muestra los 7 estados seed con swatch + badges de flags. Crear un estado nuevo, editar color/orden, eliminar (uno sin uso). Abrir el `StatusMatrixEditor` de "NUEVO" → preselecciona INTENTANDO_CONTACTAR/NO_INTERESADO → cambiar → guardar → recargar persiste. Idem `/crm/estados-cliente` (5 estados, sin is_won).
- [ ] **Validación test (F2)**: marcar `is_won` sin `is_final` → error inline Zod en español; intentar 2º `is_initial` → `MULTIPLE_INITIAL_STATUS` (400) en `MessageBar`; eliminar un estado en uso → `LEAD_STATUS_IN_USE` (409) en confirm/`MessageBar`.
- [ ] **Permisos test (F2)**: con `LEAD_STATUSES_READ` sin `_WRITE`, la tabla se ve pero no hay "Nuevo estado"/Editar/Eliminar ni editor de matriz editable; idem customer con `CUSTOMER_STATUSES_*`.

### F3 — Lead lifecycle (estado + asignación + actividad base)

- [ ] Crear `src/lib/schemas/lifecycle.schema.ts` (createLead/leadTransition/customerTransition/promote) y `lead-activity.schema.ts` (composer `superRefine` por tipo + update).
- [ ] Crear `src/actions/lead-lifecycle.actions.ts` (getLeadStatus `T|null`/createLead/transitionLead/promote/getLeadHistory + customer; cross-tag `crm:lead:{id}` + `crm:activity:{id}` + `crm:persons`), `lead-assignment.actions.ts` (getAssignment/assignAdvisor/assignAuto + listMyLeads) y `lead-activity.actions.ts` (list/create/update/delete; tag `crm:activity:{id}`).
- [ ] Implementar el tab **Lead** (`LeadTab.tsx` con estado vacío "crear lead", `StatusBadge`, `TransitionControl` con destinos de la matriz, history, "Promover a cliente"), `TransitionControl`, `AssignmentControl` (en `PersonSummaryTab`).
- [ ] Crear `src/app/(main)/crm/mis-leads/page.tsx` (`metadata.title = "Mis leads"`, `requirePermission("MY_LEADS_READ")`, `defaultSort` sobre columna real del query `/me`) + `_components/MyLeadsClient.tsx` (tabla; click → `/crm/personas/{id}`).
- [ ] **Smoke test (F3)**: en una persona sin lead → tab Lead → "Crear lead" → nace en el estado inicial (NUEVO) → `TransitionControl` ofrece solo INTENTANDO_CONTACTAR/NO_INTERESADO → transicionar → history muestra el cambio + se emite `STATUS_CHANGE` (visible en tab Actividad). Asignarme/Reasignar/Auto desde `AssignmentControl` → header refleja el asesor. Transicionar a un `is_final` → lead se cierra (estado vacío). `/crm/mis-leads` lista los leads asignados al asesor logueado.
- [ ] **Matriz/transición test (F3)**: el `TransitionControl` solo ofrece destinos permitidos; un estado terminal lo deshabilita; si la matriz cambió, `LEAD_TRANSITION_NOT_ALLOWED` (400) en `MessageBar`.
- [ ] **Error test (F3)**: crear lead sin estado inicial configurado → `NO_INITIAL_LEAD_STATUS` (400); crear 2º lead activo → `ALREADY_HAS_ACTIVE_LEAD` (409); asignar a un user sin rol ASESOR → `ADVISOR_NOT_ASESOR` (400); round-robin sin asesores → `NO_ADVISOR_AVAILABLE` (400). Todos en español en `MessageBar`.
- [ ] **Permisos test (F3)**: sin `LEAD_ACTIVITIES_WRITE` el tab Lead es read-only (sin transicionar/crear/promover); sin `LEAD_ASSIGNMENTS_WRITE` el `AssignmentControl` no muestra los botones; sin `LEAD_STATUS_HISTORY_READ` la sección history no aparece; sin `MY_LEADS_READ` "Mis leads" no se ve y su RSC redirige.

### F4 — Customer lifecycle

- [ ] Completar `lead-lifecycle.actions.ts` con getCustomerStatus `T|null`/getCustomerHistory/transitionCustomer (ya esbozados en F3) + el `promote` ya cierra el lead `is_won`.
- [ ] Implementar el tab **Cliente** (`CustomerTab.tsx`: estado vacío "promover desde Lead", `StatusBadge`, `TransitionControl` con matriz customer, `became_customer_at`, history).
- [ ] **Smoke test (F4)**: en un lead activo en estado ganable → "Promover a cliente" (tab Lead) → se crea `PersonCustomerStatus(is_initial=ACTIVO)`, el lead se cierra con `is_won`, se emite actividad → tab Cliente muestra el estado + `became_customer_at` → transicionar customer (ACTIVO→EN_TRATAMIENTO) según matriz → history persiste.
- [ ] **Error test (F4)**: promover una persona ya cliente → `ALREADY_CUSTOMER` (409); promover sin lead activo → `NO_ACTIVE_LEAD` (400). En `MessageBar`.
- [ ] **Coexistencia test (F4)** (ADR-003): una persona que ya es cliente puede tener un **nuevo** lead activo (otro hilo) → ambos badges visibles en el header; ambos tabs funcionan independientes.

### F5 — Timeline + orquestación

- [ ] Implementar `ActivityTimeline.tsx` completo + sub-componentes (`ActivityComposer` con tabs Nota/Llamada/Seguimiento, `ActivityFilterChips`, `ActivityDayGroup`, `ActivityCard` memoizada). Estado por id + fetch-token + agrupación "hoy"/"ayer" **client-only** + filtro server-side por grupo.
- [ ] **Smoke test (F5)**: tab Actividad → composer "Nota" → registrar → aparece en "Hoy" → "Llamada" con outcome → chip de outcome en la tarjeta → "Seguimiento" con `scheduled_for` futuro → tarjeta resaltada. Chips de filtro (Notas/Llamadas/Seguimientos/Estado/Sistema) re-query correctamente. Editar una nota inline; "eliminar" (`active=false`) → desaparece del feed.
- [ ] **TZ test (F5)**: con el reloj cerca de medianoche en TZ Lima (`-05:00`), una actividad creada "hoy" aparece bajo "Hoy" (no "Ayer"/"Mañana") — confirma que la agrupación es client-only y no SSR en UTC.
- [ ] **Tipos cross-módulo test (F5)**: una actividad `STATUS_CHANGE`/`REASSIGNED`/`CAMPAIGN_ATTRIBUTION` (emitida por el sistema) se renderiza con su ícono+color de `ACTIVITY_TYPE_META` y actor "Sistema". Los tipos `MESSAGE_*`/`CONVERSATION_*`/`APPOINTMENT_*` (emisión diferida) no rompen el render si llegaran (el `ACTIVITY_TYPE_META` los cubre).
- [ ] **Permisos test (F5)**: sin `LEAD_ACTIVITIES_WRITE` el timeline es read-only (sin composer, sin editar/borrar); sin `LEAD_ACTIVITIES_READ` el tab Actividad no aparece.

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog**. Para `crm` no hay deuda de traducción del template — todos los strings nuevos nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Contactos", "{nombre} · Contacto", "Mis leads", "Estados de lead", "Estados de cliente").
- [ ] Todos los `label` de `NAV_ITEMS.crm` en español ("CRM", "Contactos", "Mis leads", "Estados de lead", "Estados de cliente").
- [ ] Empty states, placeholders, badges, confirm dialogs, copy del timeline ("Sin actividad aún · registra la primera nota", "Hoy"/"Ayer", "Registrar") y `MessageBar` en español (ver tabla de copy en [`ui.md`](./ui.md#texto-ux-writing)).
- [ ] Mensajes de error de dominio que vienen del backend ya en español (`PERSON_NOT_FOUND`, `IDENTIFIER_TAKEN`, `LEAD_STATUS_IN_USE`, `NO_INITIAL_LEAD_STATUS`, `MULTIPLE_INITIAL_STATUS`, `WON_REQUIRES_FINAL`, `LEAD_TRANSITION_NOT_ALLOWED`, `NO_ACTIVE_LEAD`, `ALREADY_HAS_ACTIVE_LEAD`, `ALREADY_CUSTOMER`, `ADVISOR_NOT_ASESOR`, `NO_ADVISOR_AVAILABLE`, `ACTIVITY_NOT_FOUND`) — los `detail` se devuelven en español para mostrarse directo; el `code` queda en inglés (coordinar con [`backend.md`](./backend.md#códigos-de-error)).

## TODOs deliberados (postergados al MVP+1)

- [ ] **Grilla visual from×to** del editor de matriz de transiciones — el MVP usa multiselect por estado (spec §8.5). Diferir la matriz visual.
- [ ] **Dropdown de Asesor** en filtros/`AssignmentControl`: `listActiveAdvisors()` → `GET /crm/advisors/active` (crm-owned, gated `LEAD_ASSIGNMENTS_READ`; reusa la query de candidatos del round-robin sin `FOR UPDATE` — ver [`backend.md`](./backend.md#get-advisorsactive--lead_assignments_read--lista-cruda-listadvisoroption)). Requiere el helper aditivo `user_repository.list_active_by_role(db, "ASESOR")` en admin.
- [ ] **Drag/quick-actions en el timeline** (reordenar, completar seguimiento con un click) — refinamiento etapa 2 del timeline.
- [ ] **Resolver las columnas forward** (`source_campaign_id` → nombre de campaña, `related_appointment_id` → cita, `related_conversation_id` → conversación) cuando existan marketing/scheduling/conversations (ADR-009). Hoy son strings opacos de solo lectura.
- [ ] **`find_by_identifier_or_create` desde UI**: en el MVP es función de service (la usa el bot, sin endpoint público ni UI). Si el negocio pide "buscar persona por teléfono y crear si no existe" desde el panel del asesor, exponer un flujo sobre `/persons/search`.
- [ ] **Invalidación cross-módulo**: cuando conversations/scheduling emitan actividades en el timeline de una persona, deberán `revalidateTag("crm:activity:{personId}")` desde sus actions (back-port aditivo).
- [ ] **Vista responsive del timeline y de la tabla de personas** — el MVP asume desktop.
- [ ] **i18n framework** — por ahora strings literales en español directo en componentes (mismo criterio que catalog/clinic/staff).
