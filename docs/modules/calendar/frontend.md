# Módulo `calendar` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-06-22
> **Audiencia**: developer implementando `frontend/src/.../calendar/` (la vista de config vive bajo `/clinic` por UX) + la MOD del overlay en `scheduling`.
> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), el [`design.md`](./design.md) y el [ADR-014](../../decisions/ADR-014-external-calendar-integration.md). Como moldes de referencia: el frontend de [`../scheduling/frontend.md`](../scheduling/frontend.md) (la **grilla** `CalendarGrid` que se extiende con el overlay + el posicionamiento en hora local del navegador + el calendario frontend-only) y [`../clinic/frontend.md`](../clinic/frontend.md) (entidad con sub-recursos + el **replace atómico** de `OfficeOperatingHours` = molde directo del mapeo de sources).

> **Contrato autoritativo**: este doc respeta la [SPEC compartida](../../../C:/tmp/calendar_spec.md) (consolidada con [`README.md`](./README.md)) — nombres de entidades, campos, endpoints, permisos, códigos de error y **fases** son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, **manda la spec**.

> **Alcance Fase 1 (LOCKED, NO re-litigar)** — el frontend sólo construye lo que sigue; todo lo demás es roadmap diferido (B1–B4) que **no se codea**:
> 1. **Config de la clínica**: pantalla `/clinic/calendarios-externos` para conectar (OAuth) una cuenta Google/Microsoft, listar sus calendarios y **mapearlos a sedes** (`CalendarSource`), con salud de la conexión.
> 2. **Overlay informativo** (F2): los eventos externos de una sede se dibujan como **capa visual distinta** sobre la grilla **existente** `scheduling/_components/CalendarGrid.tsx` (NO se crea grilla nueva) + un aviso suave en el `BookingWizard`. **No bloquea** la reserva ni toca `compute_available_slots` — es puramente aditivo.
> 3. **Separación de módulo**: la ruta vive bajo `/clinic` por UX (junto a Sedes/Consultorios), pero **toda la lógica/tipos/actions/endpoints son `calendar.*`** (`types/calendar.types.ts`, `actions/calendar.actions.ts`, `ENDPOINTS.CALENDAR`, tag `calendar:connections`). El árbol de `/clinic` sólo hospeda la página; no hereda nada de clinic salvo `BranchOption` para el dropdown de mapeo.

> **Convenciones heredadas de catalog/clinic/staff/crm/scheduling shipped** (presentes desde ya):
> 1. **Verbos HTTP**: updates completos = **`PUT`** (no `PATCH`). El mapeo de sources es un **`PUT` bulk replace atómico** (molde `replaceOfficeHours`, no per-row).
> 2. **Dropdowns**: los `/active` (u `/options`) devuelven **lista cruda** (`response_model=list[...]`, sin envelope) — no se lee `.data`. (El `/calendars` de una conexión también devuelve `SingleResponse[list[...]]` → SÍ se lee `.data`; ver matiz abajo.)
> 3. **TZ** (lección recurrente staff/crm/scheduling): cualquier `new Date()`/now que afecte render = **client-only**. Los eventos externos son **instantes UTC** (`starts_at`/`ends_at` ISO 8601 con offset) → se posicionan en la grilla con los helpers **ya existentes** `localMinutesOf`/`localDateIsoOf` de [`lib/utils/calendarWeek.ts`](../../../frontend/src/lib/utils/calendarWeek.ts) (UTC→hora local de pared), nunca con `getHours()` derivado de UTC ni en SSR. La salud (`last_checked_at`, "hace N min") es relativa-a-`new Date()` → client-only.
> 4. **OAuth = redirect del navegador**: el `startOAuth` es una Server Action que devuelve `{ auth_url }`; el **cliente** hace `window.location.href = auth_url` (no se puede `redirect()` a un host externo de forma transparente desde el action sin perder el control del flujo). El **callback** es un endpoint **público del backend** que, al terminar, hace **302** de vuelta a la página (`return_to`), con `?calendar_error=CODE` si falló.

---

## Estructura de archivos a crear / modificar

```
frontend/src/
├── types/
│   └── calendar.types.ts                    ← NUEVO. CalendarProvider/ConnectionStatus (enums),
│                                                CalendarConnectionItem/Detail, CalendarSourceItem/Create,
│                                                CalendarSourcesReplace, ExternalCalendarOption,
│                                                ExternalEventItem, ExternalEventsResponse, SourceHealth,
│                                                OAuthStartResponse, CalendarProviderOption
│                                                (reusa UserAuditInfo de audit.types; BranchOption de clinic)
├── lib/
│   ├── schemas/
│   │   └── calendar.schema.ts                ← NUEVO. sourceCreateSchema (external ids min 1,
│   │                                             branch_id opcional/nullable, is_enabled bool),
│   │                                             sourcesReplaceSchema ({ sources: [...] }, min 0)
│   └── constants/
│       ├── endpoints.ts                      ← EXTEND con el bloque CALENDAR (OAUTH start/callback,
│       │                                         CONNECTIONS list/get/delete/calendars/sources,
│       │                                         EXTERNAL_EVENTS)
│       ├── navigation.ts                     ← EXTEND el grupo "Clínica" con el child
│       │                                         "Calendarios externos" (gated MENU-CALENDAR /
│       │                                         CALENDAR_CONNECTIONS_READ)
│       └── calendar-providers.ts             ← NUEVO (chico): CALENDAR_PROVIDER_META (label + ícono ES),
│                                                 CONNECTION_STATUS_META (label + intent del badge),
│                                                 CALENDAR_ERROR_LABELS (?calendar_error=CODE → español)
├── actions/
│   └── calendar.actions.ts                   ← NUEVO. startOAuth, listConnections, getConnection,
│                                                disconnect, listExternalCalendars, replaceSources
│                                                (revalidateTag "calendar:connections"),
│                                                fetchExternalEvents (lectura, sin revalidate)
└── app/(main)/
    ├── clinic/calendarios-externos/          ← NUEVO (la ruta vive bajo /clinic por UX)
    │   ├── page.tsx                          ← RSC. requirePermission("CALENDAR_CONNECTIONS_READ");
    │   │                                        lee ?calendar_error= ; prefetch listConnections +
    │   │                                        listActiveBranches (dropdown de mapeo)
    │   └── _components/
    │       ├── CalendarConnectionsClient.tsx ← orquesta: header (Conectar Google/Outlook), lista de
    │       │                                    ConnectionCard, banner de ?calendar_error, empty state
    │       ├── ConnectionCard.tsx            ← una conexión: ícono provider + email + badge salud +
    │       │                                    Reconectar/Desconectar + monta SourceMappingTable
    │       └── SourceMappingTable.tsx        ← filas calendario→sede (Dropdown Branch + Switch is_enabled)
    │                                            + "Guardar mapeo" (PUT replace). Molde OfficeHoursTab.
    └── scheduling/                            ← MOD (F2, NO nuevos archivos de ruta)
        ├── _components/CalendarGrid.tsx       ← MOD: aceptar eventos kind "external" (capa atenuada/rayada)
        │                                        + leyenda. (Ya soporta `CalendarEvent.kind`; se agrega un valor.)
        └── calendario/_components/CalendarClient.tsx ← MOD: llamar fetchExternalEvents(branchId, from, to)
                                                  y mapear los ExternalEventItem a CalendarEvent kind "external"
```

> **Por qué la ruta vive bajo `/clinic` pero el código es `calendar.*`**: decisión de la spec §11/§12 — UX-wise "Calendarios externos" pertenece al grupo **Clínica** (junto a Sedes/Consultorios), pero la separación de módulos manda: tipos, schemas, actions, endpoints y tag son `calendar`. Es el mismo criterio que `scheduling` usó al reutilizar `BranchOption`/`ProductOption`/`DoctorOption` de otros módulos sin redefinirlos: **la página importa de `calendar` + un `BranchOption` de clinic; nada más cruza**.

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas.

> **Sobre `loading.tsx`**: igual que clinic/scheduling shipped — **no** se crea. La página de config no es una `DataTable` (es cards); el `CalendarConnectionsClient` renderiza su propio `Spinner`/skeleton mientras hidrata. La grilla de scheduling ya tiene su skeleton.

> **NO se crean** (diferido B2/B3, documentado como roadmap, **NO codear**): vistas per-doctor, push de citas, panel de sync/webhooks, 3er proveedor CalDAV. La interfaz de tipos los admite sin reescritura, pero el frontend de Fase 1 no los toca.

---

## Tipos TS — `types/calendar.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic) y la spec §10/§12). Importable desde server actions y client components. **Reusa** `UserAuditInfo` de `audit.types.ts`; **reusa** `BranchOption` de `clinic.types.ts` para el dropdown de mapeo — no se redefinen.

```ts
import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de calendar/enums.py; valores EXACTOS, code-level no catálogo BD) ──

// Proveedor de calendario externo. "caldav" está RESERVADO en el enum del backend
// pero NO se seedea/usa en Fase 1 (3er proveedor diferido, B4). El front lista sólo
// google + microsoft en CALENDAR_PROVIDER_META → los botones "Conectar".
export type CalendarProvider = "google" | "microsoft"; // | "caldav" (diferido)

export const CALENDAR_PROVIDERS: readonly CalendarProvider[] = ["google", "microsoft"] as const;

// Salud de la conexión. connected = OK; needs_reauth = el refresh dio invalid_grant
// (mostrar "Reconectar"); revoked = el usuario desconectó del lado del proveedor;
// error = fallo transitorio de list/refresh (ver last_error).
export type ConnectionStatus = "connected" | "needs_reauth" | "revoked" | "error";

// ── CalendarConnection (cuenta OAuth a nivel clínica) ───────────
// Los TOKENS NO viajan al front nunca (viven en Secret Manager; el backend sólo expone
// metadatos + el puntero secret_name del lado servidor, que el schema Item NO incluye).

export interface CalendarConnectionItem {
  id: string;
  provider: CalendarProvider;
  account_email: string; // identidad de la cuenta (de Google userinfo / Graph /me)
  display_name: string | null; // etiqueta amigable (default = account_email)
  status: ConnectionStatus;
  scopes: string | null; // space-separated, auditoría (no se muestra prominente)
  last_checked_at: string | null; // timestamptz ISO; "Última revisión: hace N" = client-only
  sources_count: number; // cuántos CalendarSource cuelgan (para el resumen de la card)
  is_active: boolean; // ActiveMixin = pausa manual de la conexión entera
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle: la conexión + sus sources (selectinload en el backend) + last_error. Un solo GET
// puebla la ConnectionCard expandida (la lista de calendarios mapeados).
export interface CalendarConnectionDetail extends CalendarConnectionItem {
  last_error: string | null; // último error de refresh/list (observabilidad, tooltip)
  sources: CalendarSourceItem[];
}

// ── CalendarSource (un calendario concreto mapeado a una sede) ──
// El flag "habilitado para lectura" se expone como is_enabled (NO una 2ª columna boolean;
// reusa ActiveMixin.active del backend, precedente bots BotConfigurationVersion.is_active).

export interface CalendarSourceItem {
  id: string;
  connection_id: string;
  external_calendar_id: string; // id del calendario en el proveedor
  external_calendar_name: string; // denorm para mostrar
  branch_id: string | null; // null = "todas las sedes"
  branch_name: string | null; // denorm (null si branch_id null o sede borrada)
  is_enabled: boolean; // habilitado para la lectura del overlay
}

// Body de cada fila del replace. external_calendar_name viaja desde la opción elegida
// (list_calendars) para denormalizar sin re-fetch. is_enabled default true.
export interface CalendarSourceCreate {
  external_calendar_id: string;
  external_calendar_name: string;
  branch_id?: string | null; // opcional/nullable = "todas las sedes"
  is_enabled?: boolean; // default true
}

// Body de PUT /connections/{id}/sources — REEMPLAZA el set completo (atómico). min 0
// (mandar [] borra todos los mapeos de esa conexión). Molde OfficeOperatingHoursReplace.
export interface CalendarSourcesReplace {
  sources: CalendarSourceCreate[];
}

// ── ExternalCalendarOption (de list_calendars, para el dropdown de mapeo) ──
// Lista LIVE devuelta por GET /connections/{id}/calendars (SingleResponse[list[...]]).
// primary marca el calendario principal de la cuenta (se sugiere mapearlo primero).
export interface ExternalCalendarOption {
  id: string; // = external_calendar_id
  name: string;
  primary: boolean;
}

// ── ExternalEvent (overlay informativo, F2) ─────────────────────
// Instantes UTC (ISO 8601 con offset). El render los ubica en la grilla en hora local de
// pared con localMinutesOf/localDateIsoOf (igual que scheduled_for de las citas).
export interface ExternalEventItem {
  external_id: string;
  title: string; // detalle (título del evento); NO free/busy opaco
  starts_at: string; // ISO 8601 UTC
  ends_at: string; // ISO 8601 UTC
  all_day: boolean; // evento de día completo → se trata aparte (banda, no bloque horario)
  branch_id: string | null; // sede del source (null = "todas las sedes")
  branch_name: string | null;
  source_id: string; // CalendarSource del que vino (trazabilidad)
}

// Salud por conexión devuelta junto a los eventos (best-effort: si una conexión falla,
// su evento NO aparece pero su salud SÍ → aviso suave en la grilla, nunca un 5xx).
export interface SourceHealth {
  connection_id: string;
  status: ConnectionStatus;
  error?: string | null; // detalle del fallo de esa conexión (tooltip)
}

// Respuesta de GET /external-events. events = lo que se pinta; sources_health = el aviso.
export interface ExternalEventsResponse {
  events: ExternalEventItem[];
  sources_health: SourceHealth[];
}

// ── OAuth ───────────────────────────────────────────────────────
// Respuesta de GET /oauth/{provider}/start. El client redirige el navegador a auth_url.
export interface OAuthStartResponse {
  auth_url: string;
}

// Para los botones "Conectar X" del header (label + provider). El ícono lo resuelve
// CALENDAR_PROVIDER_META en lib/constants/calendar-providers.ts (no va en el type).
export interface CalendarProviderOption {
  value: CalendarProvider;
  label: string; // "Google" / "Outlook"
}
```

> **Nota sobre clases de tiempo** (igual que clinic/scheduling):
> - `last_checked_at`, `created_on`/`updated_on`, `starts_at`/`ends_at` → `timestamptz` ISO 8601 con offset. La salud relativa ("hace N min") y la posición del evento en la grilla se derivan **client-only** (`localMinutesOf`/`localDateIsoOf` para la grilla; `formatDate`/relativa de `lib/utils/date.ts` para la salud).
> - El rango del overlay (`from`/`to` de `fetchExternalEvents`) son **instantes UTC** (la grilla ya calcula `weekFromIso = weekStart.toISOString()` en `CalendarClient`) — se reusan tal cual, **no** son fechas-puro.
> - **No hay** campos de hora-de-pared (`time` sin TZ) en este módulo (a diferencia de `OperatingHours`): los eventos externos son siempre instantes absolutos.

> **`secret_name` NUNCA cruza al front**: el `CalendarConnectionItem`/`Detail` del backend **omite** el puntero a Secret Manager y, obviamente, los tokens. El front sólo ve metadatos + salud. (Si aparece `secret_name` en el JSON, es un bug del schema backend — reportar.)

---

## Zod schemas — `lib/schemas/calendar.schema.ts`

> **Regla del template** ([frontend/CLAUDE.md](../../../frontend/CLAUDE.md)): los Zod viven en `src/lib/schemas/` y los importan **tanto el form (cliente) como el Server Action (server)** → drift imposible. Mensajes visibles en **español**; `path`/nombres de campo en inglés.

Sólo el mapeo de sources necesita Zod (el OAuth no tiene form — es un redirect; el disconnect es un `ConfirmDialog` sin payload). Molde directo de `office-hours.schema.ts` (el replace bulk de `OfficeOperatingHours`).

```ts
import { z } from "zod";

// Una fila del mapeo: un calendario externo → una sede (o "todas"). external_calendar_id
// y _name vienen de la opción elegida (list_calendars), no los teclea el usuario.
const sourceCreateSchema = z.object({
  external_calendar_id: z.string().min(1, "Calendario obligatorio"),
  external_calendar_name: z.string().min(1, "Nombre de calendario obligatorio"),
  // null/ausente = "todas las sedes" (decisión LOCKED #3). El backend valida que la sede
  // exista (404 BRANCH_NOT_FOUND) — Zod sólo asegura el shape.
  branch_id: z.string().min(1).nullable().optional(),
  is_enabled: z.boolean().optional().default(true),
});

// Body del PUT bulk replace. min 0: mandar [] borra todos los mapeos de la conexión
// (mismo criterio que officeHoursReplaceSchema con hours: []).
export const sourcesReplaceSchema = z.object({
  sources: z.array(sourceCreateSchema),
});

export type SourceCreateInput = z.infer<typeof sourceCreateSchema>;
export type SourcesReplaceInput = z.infer<typeof sourcesReplaceSchema>;
```

> **Sin refine de unicidad en Zod**: el UNIQUE parcial `(connection_id, external_calendar_id)` lo garantiza la BD; en la práctica el `SourceMappingTable` parte de la lista LIVE de `list_calendars` (un calendario aparece **una** vez), así que no hay forma de duplicar `external_calendar_id` desde la UI. Si el backend devuelve un conflicto (race), se muestra el `detail` en español en un `MessageBar`. **No** se valida `branch_id` contra la lista de sedes en Zod (cruza con datos del server) → el backend responde `BRANCH_NOT_FOUND` (404) si se mapea a una sede inexistente (lección §20/§22: validar el FK antes de insertar).

> **El OAuth NO tiene Zod**: `startOAuth(provider, returnTo)` recibe un `provider` que es un literal del enum (`CalendarProvider`) y un `returnTo` que arma el client (la ruta actual). Si llegara un provider fuera del adapter, el backend responde `CALENDAR_PROVIDER_NOT_SUPPORTED` (400). El `disconnect` es un `DELETE` sin body.

---

## Constantes de presentación — `lib/constants/calendar-providers.ts`

Metadata de proveedor + salud + traducción de los `?calendar_error=`. **Nuevo** (chico). Los íconos son Fluent existentes (NO se introduce librería nueva); el color de los badges sale de tokens semánticos Fluent (NO de `brandPalette`, que no tiene `accent` — lección operativa transversal).

```ts
import type { CalendarProvider, ConnectionStatus } from "@/types/calendar.types";

// Proveedor → label + ícono (Fluent). Verificar que el ícono exista en la versión instalada;
// fallback a CalendarLtrRegular si CalendarSyncRegular no está (ver nota de navegación).
export const CALENDAR_PROVIDER_META: Record<
  CalendarProvider,
  { label: string; connectLabel: string; icon: string }
> = {
  google: { label: "Google", connectLabel: "Conectar Google", icon: "CalendarLtrRegular" },
  microsoft: {
    label: "Outlook",
    connectLabel: "Conectar Outlook",
    icon: "CalendarLtrRegular",
  },
};

// Salud → label ES + intent del Badge Fluent (success/warning/danger). connected = verde;
// needs_reauth = ámbar (acción: Reconectar); revoked/error = rojo.
export const CONNECTION_STATUS_META: Record<
  ConnectionStatus,
  { label: string; intent: "success" | "warning" | "danger" }
> = {
  connected: { label: "Conectada", intent: "success" },
  needs_reauth: { label: "Reconectar", intent: "warning" },
  revoked: { label: "Revocada", intent: "danger" },
  error: { label: "Error", intent: "danger" },
};

// El callback público del backend hace 302 a la página con ?calendar_error=CODE cuando el
// OAuth falla. La página traduce el code (inglés) a un mensaje español para un MessageBar.
// Los codes espejan los del service (spec §8) que pueden disparar el redirect de error.
export const CALENDAR_ERROR_LABELS: Record<string, string> = {
  CALENDAR_OAUTH_STATE_INVALID:
    "La sesión de conexión expiró o no es válida. Vuelve a intentar conectar.",
  CALENDAR_OAUTH_EXCHANGE_FAILED:
    "No se pudo completar la autorización con el proveedor. Intenta de nuevo.",
  CALENDAR_CONNECTION_ALREADY_EXISTS: "Esta cuenta ya está conectada.",
  CALENDAR_PROVIDER_NOT_SUPPORTED: "Proveedor de calendario no soportado.",
  CALENDAR_CREDENTIALS_MISSING:
    "La integración no está configurada en este entorno. Contacta al administrador.",
};
```

> **Íconos**: el grupo "Clínica" y el child "Calendarios externos" usan un ícono Fluent existente. `CalendarSyncRegular` es el ideal semántico, pero **debe verificarse en el `iconMap` del `Sidebar.tsx`** contra la versión instalada de `@fluentui/react-icons`; si no existe, **fallback a `CalendarLtrRegular`** (que ya está registrado — lo usa scheduling). **No** introducir una librería de íconos nueva (lección Next 16 del template).

---

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque `CALENDAR` completo. **Orden de rutas backend**: las estáticas (`/oauth/...`, `/connections/list`, `/external-events`) van ANTES de `/connections/{id}` (la spec §9 lo exige para no capturar `list`/`external-events` como un `{id}`). En el front sólo importan las URLs.

```ts
const CALENDAR = "/api/v1/calendar"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, CATALOG, CLINIC, STAFF, CRM,
  //   CONVERSATIONS, BOTS, SCHEDULING, MARKETING (existentes) …

  // ── Calendar module (#9, ADR-014) ────────────────────────
  // Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún. Las rutas
  // backend se montan por fase (conexión+mapeo F1, lectura/overlay F2).
  // El callback OAUTH.CALLBACK es PÚBLICO (sin JWT, gateado por `state`): lo invoca
  // el navegador del usuario tras el consentimiento, NO el frontend vía backendClient.
  // Va acá sólo como referencia documental de la URL pública del backend.
  CALENDAR: {
    // OAuth (start = JWT del actor; callback = público con ?code&state).
    OAUTH_START: (provider: string) => `${CALENDAR}/oauth/${provider}/start`, // GET ?return_to= → {auth_url}
    OAUTH_CALLBACK: (provider: string) => `${CALENDAR}/oauth/${provider}/callback`, // PÚBLICO, 302 back
    // Conexiones (config de la clínica).
    CONNECTIONS_LIST: `${CALENDAR}/connections/list`, // POST + QueryRequest. PaginatedResponse[CalendarConnectionItem]
    CONNECTION_GET: (id: string) => `${CALENDAR}/connections/${id}`, // SingleResponse[CalendarConnectionDetail] (+ sources)
    CONNECTION_DELETE: (id: string) => `${CALENDAR}/connections/${id}`, // 204 (soft-delete + revoke + borra secreto)
    CONNECTION_CALENDARS: (id: string) => `${CALENDAR}/connections/${id}/calendars`, // GET live list_calendars → SingleResponse[list[ExternalCalendarOption]]
    CONNECTION_SOURCES: (id: string) => `${CALENDAR}/connections/${id}/sources`, // PUT bulk replace → SingleResponse[CalendarConnectionDetail]
    // Overlay informativo (F2).
    EXTERNAL_EVENTS: `${CALENDAR}/external-events`, // GET ?branch_id=&from=&to= → SingleResponse[ExternalEventsResponse]
  },
} as const;
```

> **Matiz de envelopes en este módulo** (no todo es lista cruda):
> - `CONNECTIONS_LIST` → `PaginatedResponse` → `.data.items`.
> - `CONNECTION_GET` / `CONNECTION_SOURCES` (PUT) → `SingleResponse[CalendarConnectionDetail]` → `.data`.
> - `CONNECTION_CALENDARS` → `SingleResponse[list[ExternalCalendarOption]]` → `.data` (es **live** del proveedor, no un `/active` de BD; por eso lleva envelope, **a diferencia** del patrón `/active` crudo). **No** se confunde con un dropdown de BD.
> - `OAUTH_START` → `SingleResponse[{auth_url}]` → `.data.auth_url`.
> - `EXTERNAL_EVENTS` → `SingleResponse[ExternalEventsResponse]` → `.data`.
> - `OAUTH_CALLBACK` no se llama desde `backendClient` **jamás** — es el navegador del usuario el que aterriza ahí tras el consentimiento. Va en `ENDPOINTS` sólo como documentación de la URL pública (igual que los webhooks de conversations y el dispatch de bots, que también figuran como referencia muerta).

---

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Agregar el child `external-calendars` al grupo **"Clínica"** existente (junto a Sedes/Consultorios). El grupo ya existe (`key: "clinic"`); sólo se **suma** un hijo:

```ts
{
  key: "clinic",
  label: "Clínica",
  icon: "BuildingMultipleRegular",
  children: [
    {
      key: "branches",
      label: "Sedes",
      icon: "BuildingRegular",
      url: "/clinic/branches",
      permissions: ["MENU-CLINIC"],
    },
    {
      key: "offices",
      label: "Consultorios",
      icon: "ConferenceRoomRegular",
      url: "/clinic/offices",
      permissions: ["MENU-CLINIC"],
    },
    // ── NEW (calendar #9, vive bajo /clinic por UX; lógica = módulo calendar) ──
    {
      key: "external-calendars",
      label: "Calendarios externos",
      icon: "CalendarLtrRegular", // CalendarSyncRegular si existe en la versión instalada (verificar iconMap)
      url: "/clinic/calendarios-externos",
      // Gating fino: lo ven ADMIN (4 perms) y ASESOR (config read-only). El DOCTOR NO ve
      // este item (sólo tiene CALENDAR_EXTERNAL_EVENTS_READ = el overlay, sin menú de config).
      permissions: ["CALENDAR_CONNECTIONS_READ"],
    },
  ],
},
```

> **Gating del item**: el child lleva `permissions: ["CALENDAR_CONNECTIONS_READ"]` (lo tienen ADMIN y ASESOR — la spec §7). El **DOCTOR** sólo tiene `CALENDAR_EXTERNAL_EVENTS_READ` (el overlay en la grilla), así que **no** ve este item de menú; sí ve los eventos externos cuando entra a `/scheduling/calendario`. `MENU-CALENDAR` existe en el set de permisos (lo introduce backend F0) pero, igual que scheduling con `MENU-SCHEDULING`, el item del nav se gatea con el permiso fino `CALENDAR_CONNECTIONS_READ`, no con `MENU-CALENDAR` (que queda como permiso "de menú" reservado). El page RSC valida con `requirePermission("CALENDAR_CONNECTIONS_READ")`.

> **Íconos**: registrar `CalendarLtrRegular` (o `CalendarSyncRegular` si se confirma su existencia) en el `iconMap` del `Sidebar.tsx` — `CalendarLtrRegular` **ya está registrado** (lo usa el grupo Agenda de scheduling), así que el fallback es gratis. **No** introducir librerías de íconos nuevas.

---

## Server Actions — `actions/calendar.actions.ts`

Mismo molde que clinic/scheduling: validar con Zod en el action (donde aplica) → llamar `backendClient` → `revalidateTag(TAG, "max")` en las mutaciones. Reusa el `MutationResult<T>` exportado por `user.actions.ts`. **Next 16 exige el 2º argumento de `revalidateTag`** (`"max"`); omitirlo es error.

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `calendar:connections` | lista de conexiones + detalle (sources) de la config | conectar (callback, vía revalidate del path tras el redirect), desconectar, **guardar mapeo** (replace sources) |

> **Una sola familia de tag** (no por-conexión): la config de la clínica tiene típicamente 1-2 conexiones; no vale la pena un tag por-id (a diferencia de `scheduling:appointment:{id}`). Un cambio en cualquier conexión invalida `calendar:connections` y la página re-pinta el set completo. La **lectura del overlay** (`fetchExternalEvents`) **NO** lleva tag (es live on-demand, como `availability.actions.ts` de scheduling) → `cache: "no-store"`.

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { sourcesReplaceSchema } from "@/lib/schemas/calendar.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  CalendarConnectionDetail,
  CalendarConnectionItem,
  CalendarProvider,
  ExternalCalendarOption,
  ExternalEventsResponse,
  OAuthStartResponse,
} from "@/types/calendar.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const CONNECTIONS_TAG = "calendar:connections";

// ── OAuth start (el client redirige el navegador al auth_url) ────
// NO usa redirect() del action: devuelve el auth_url y el CLIENTE hace
// window.location.href = auth_url. Así el flujo arranca con un gesto del usuario y el
// callback (302 del backend) aterriza de vuelta en la página con ?calendar_error si falla.
export async function startOAuth(
  provider: CalendarProvider,
  returnTo: string,
): Promise<MutationResult<OAuthStartResponse>> {
  try {
    const data = await backendClient.get<ApiSingle<OAuthStartResponse>>(
      `${ENDPOINTS.CALENDAR.OAUTH_START(provider)}?return_to=${encodeURIComponent(returnTo)}`,
    );
    return { ok: true, data: data.data }; // { auth_url }
  } catch (e) {
    // 400 CALENDAR_PROVIDER_NOT_SUPPORTED / CALENDAR_CREDENTIALS_MISSING en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Conexiones ──────────────────────────────────────────────────

export async function listConnections(
  query: QueryRequest,
): Promise<ApiPaginated<CalendarConnectionItem>> {
  return backendClient.post<ApiPaginated<CalendarConnectionItem>>(
    ENDPOINTS.CALENDAR.CONNECTIONS_LIST,
    query,
    { tags: [CONNECTIONS_TAG] },
  );
}

export async function getConnection(id: string): Promise<ApiSingle<CalendarConnectionDetail>> {
  // Incluye los sources embebidos (selectinload) para la ConnectionCard expandida.
  return backendClient.get<ApiSingle<CalendarConnectionDetail>>(
    ENDPOINTS.CALENDAR.CONNECTION_GET(id),
    { tags: [CONNECTIONS_TAG] },
  );
}

export async function disconnect(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CALENDAR.CONNECTION_DELETE(id)); // 204
    revalidateTag(CONNECTIONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 404 CALENDAR_CONNECTION_NOT_FOUND si ya no existe.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Mapeo de calendarios → sedes ────────────────────────────────

// Lista LIVE de calendarios de la cuenta (de list_calendars del proveedor). La consume
// el SourceMappingTable para ofrecer las filas a mapear. NO es un /active de BD → lleva
// envelope SingleResponse (se lee .data). Lectura on-demand: sin tag (cache: "no-store").
export async function listExternalCalendars(
  connectionId: string,
): Promise<ExternalCalendarOption[]> {
  const res = await backendClient.get<ApiSingle<ExternalCalendarOption[]>>(
    ENDPOINTS.CALENDAR.CONNECTION_CALENDARS(connectionId),
    { cache: "no-store" },
  );
  return res.data; // [{ id, name, primary }]
}

// Bulk atomic REPLACE del mapeo (soft-delete los viejos + insert el set nuevo, patrón
// replaceOfficeHours). Mandar { sources: [] } borra todos los mapeos de la conexión.
export async function replaceSources(
  connectionId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<CalendarConnectionDetail>>> {
  const parsed = sourcesReplaceSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<CalendarConnectionDetail>>(
      ENDPOINTS.CALENDAR.CONNECTION_SOURCES(connectionId), // ← PUT bulk replace
      parsed.data, // { sources: [...] }
    );
    revalidateTag(CONNECTIONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 404 BRANCH_NOT_FOUND (sede inexistente) / CALENDAR_CONNECTION_NOT_FOUND en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Overlay informativo (F2) — lectura best-effort, sin revalidate ─
// La consume el CalendarClient de scheduling (mapea los ExternalEventItem a CalendarEvent
// kind "external"). from/to son instantes UTC ISO (los mismos weekFromIso/weekToIso que la
// grilla ya calcula). NUNCA tira 5xx: si una conexión falla, viene en sources_health.
export async function fetchExternalEvents(params: {
  branchId: string;
  from: string; // ISO 8601 UTC
  to: string; // ISO 8601 UTC
}): Promise<ExternalEventsResponse> {
  const qs = new URLSearchParams({
    branch_id: params.branchId,
    from: params.from,
    to: params.to,
  });
  const res = await backendClient.get<ApiSingle<ExternalEventsResponse>>(
    `${ENDPOINTS.CALENDAR.EXTERNAL_EVENTS}?${qs.toString()}`,
    { cache: "no-store" }, // live, on-demand; sin tag (igual que availability de scheduling)
  );
  return res.data; // { events, sources_health }
}
```

> **El OAuth NO redirige desde el action**: el `startOAuth` **devuelve** `{ auth_url }`; el redirect lo hace el cliente (`window.location.href = auth_url`). Razón: `redirect()` de Next desde un Server Action lanza una excepción de control de flujo que Next captura para navegar — pero a un **host externo** (el consentimiento de Google/Microsoft) conviene un `window.location` explícito del cliente para que el botón sea un gesto del usuario y el flujo OAuth (popup vs full-page) quede en manos del componente. El **regreso** sí es un 302 del backend (el callback público) → aterriza en `/clinic/calendarios-externos?calendar_error=...` (o sin query si OK), y el RSC re-lee `listConnections` (cache invalidado por el navegar fresco).

> **`fetchExternalEvents` y `listExternalCalendars` NO revalidan tags** (lecturas live on-demand): `cache: "no-store"`. Los calendarios de la cuenta y los eventos del proveedor cambian fuera de medisage; cachearlos daría datos viejos. El overlay re-consulta al navegar la semana (la grilla ya re-fetcha por `weekFromIso`).

> **El callback NO es una action**: no hay `oauthCallback` en este archivo. El callback lo sirve el **backend** (`GET /calendar/oauth/{provider}/callback`, público, gateado por `state`); el navegador del usuario lo golpea directo tras autorizar, y el backend hace 302 de vuelta a la página. El frontend sólo **lee** el `?calendar_error=` resultante en el RSC.

---

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/clinic/calendarios-externos/page.tsx`

RSC que prefetcha las conexiones + las sedes (para el dropdown de mapeo) y lee el `?calendar_error=` que el callback público pudo dejar al volver de un OAuth fallido. Molde de `clinic/offices/page.tsx` (prefetch + `listActiveBranches` en paralelo).

```tsx
import { listConnections } from "@/actions/calendar.actions";
import { listActiveBranches } from "@/actions/branch.actions"; // clinic (dropdown de mapeo)
import { requirePermission } from "@/lib/auth/session";

import { CalendarConnectionsClient } from "./_components/CalendarConnectionsClient";

export const metadata = { title: "Calendarios externos" };

interface PageProps {
  // El callback público del backend hace 302 de vuelta con ?calendar_error=CODE si el OAuth
  // falló; si fue OK, vuelve sin query. (return_to lo fijó el client al iniciar el OAuth.)
  searchParams: Promise<{ calendar_error?: string }>;
}

export default async function ExternalCalendarsPage({ searchParams }: PageProps) {
  await requirePermission("CALENDAR_CONNECTIONS_READ");
  const sp = await searchParams;

  const [initialData, branches] = await Promise.all([
    listConnections({
      pagination: { skip: 0, limit: 25 }, // pocas conexiones (1-2 típico); una página basta
      sorting: { sort_by: "created_on", sort_order: "asc" },
      filters: null,
    }),
    listActiveBranches(),
  ]);

  return (
    <CalendarConnectionsClient
      initialData={initialData}
      branches={branches}
      oauthError={sp.calendar_error ?? null}
    />
  );
}
```

> **Por qué se lee `?calendar_error` en el RSC** (no en el client): el callback público del backend hace un **302 server-side** a la página → la query llega en el primer render del RSC. Pasarlo como prop al client (`oauthError`) deja que el `CalendarConnectionsClient` lo muestre en un `MessageBar` traducido (`CALENDAR_ERROR_LABELS[code]`) y lo limpie de la URL con `router.replace` tras leerlo (para que un refresh no re-muestre el error). Si OK, no hay query → no hay banner.

> **`requirePermission("CALENDAR_CONNECTIONS_READ")`**: ADMIN y ASESOR pasan; el DOCTOR (sólo `CALENDAR_EXTERNAL_EVENTS_READ`) es redirigido (no tiene la página de config). El backend reconfirma el permiso en cada endpoint (no se confía en el front).

---

## Client components — esqueletos

> **No reproduzco los archivos completos** — siguen el patrón de `clinic/.../OfficesClient` (lista + drawer) + el **replace multi-fila** de `OfficeHoursTab`/`OfficeClosuresTab` (el molde directo del mapeo). Documento las diferencias específicas a `calendar`. La UI detallada (mockups ASCII, copy) vive en [`ui.md`](./ui.md).

### `CalendarConnectionsClient.tsx`

Orquestador de la pantalla de config (no es una `DataTable` — es una lista de cards). Props: `{ initialData: ApiPaginated<CalendarConnectionItem>; branches: BranchOption[]; oauthError: string | null }`.

- **Header**: título "Calendarios externos" + botones **"Conectar Google"** / **"Conectar Outlook"** (gated `CALENDAR_CONNECTIONS_WRITE` con `<PermissionGuard>`). Cada botón → `onConnect(provider)`:
  ```ts
  const onConnect = async (provider: CalendarProvider) => {
    const returnTo = window.location.pathname; // "/clinic/calendarios-externos"
    const res = await startOAuth(provider, returnTo);
    if (res.ok && res.data) window.location.href = res.data.auth_url; // redirect del navegador
    else setActionError(res.error ?? "No se pudo iniciar la conexión.");
  };
  ```
- **Banner de error OAuth**: si `oauthError`, mostrar un `MessageBar intent="error"` con `CALENDAR_ERROR_LABELS[oauthError] ?? "No se pudo completar la conexión."`; tras montarlo, `router.replace("/clinic/calendarios-externos")` (sin query) para que un refresh no lo repita. **client-only** (usa `window`/`router`).
- **Lista de conexiones**: `initialData.data.items.map(c => <ConnectionCard ... />)`. Re-fetch tras una mutación vía `router.refresh()` (el tag `calendar:connections` ya se revalidó en el action) o un `useQuery` con `queryKey: ["calendar:connections"]` sobre `listConnections` (mismo criterio que las listas de clinic; con tan pocas filas, `router.refresh()` basta).
- **Empty state** (sin conexiones): card con CTA "Aún no hay calendarios conectados. Conecta la cuenta de Google o de Outlook de la clínica para empezar." + los dos botones de conectar (si tiene WRITE).
- **Estados**: loading (spinner mientras hidrata), success, error (banner). Gating: con sólo `CALENDAR_CONNECTIONS_READ` (sin WRITE) → ve las cards y el mapeo en **read-only** (sin botones de conectar/guardar/desconectar).

### `ConnectionCard.tsx`

Una conexión OAuth. Props: `{ connection: CalendarConnectionItem; branches: BranchOption[]; onChanged: () => void }`.

- **Cabecera de la card**: ícono del provider (`CALENDAR_PROVIDER_META[provider].icon`) + `account_email` (+ `display_name` si difiere) + `<Badge>` de salud (`CONNECTION_STATUS_META[status]` → label + intent). "Última revisión: hace N" (`last_checked_at` relativo, **client-only**). Si `status !== "connected"`, un hint del `last_error` (tooltip) y el botón "Reconectar" prominente.
- **Acciones** (gated `CALENDAR_CONNECTIONS_WRITE`):
  - **"Reconectar"** → re-OAuth (mismo `startOAuth(provider, returnTo)` que el header; re-consiente, refresca tokens — útil tras `needs_reauth`/`revoked`).
  - **"Desconectar"** → `ConfirmDialog` ("¿Desconectar {account_email}? Se eliminarán los calendarios mapeados y se revocará el acceso.") → `disconnect(connection.id)` → `onChanged()`. El backend soft-deletea + revoke best-effort + borra el secreto.
- **Mapeo**: al expandir la card (o inline), carga `getConnection(connection.id)` (sources embebidos) + `listExternalCalendars(connection.id)` (la lista LIVE del proveedor) en cliente (fetch-token) y monta `<SourceMappingTable>`. Si `listExternalCalendars` falla (proveedor caído / token vencido) → `MessageBar` suave "No se pudieron cargar los calendarios de esta cuenta ahora. Intenta Reconectar." (best-effort, no rompe la card).

### `SourceMappingTable.tsx`

El corazón del mapeo. **Molde directo de `OfficeHoursTab`/`OfficeClosuresTab`** (multi-fila local + `PUT` bulk replace). Props: `{ connectionId: string; calendars: ExternalCalendarOption[]; existingSources: CalendarSourceItem[]; branches: BranchOption[]; onSaved: () => void; readOnly: boolean }`.

- **Filas**: una por calendario de `calendars` (la lista LIVE). Cada fila combina el calendario con su mapeo existente (si `existingSources` tiene un `external_calendar_id` que coincide, prepuebla `branch_id`/`is_enabled`; si no, `branch_id = null`, `is_enabled = false`). Layout por fila:
  ```
  {calendar.name}  [ Sede ▾ ]  [ Switch is_enabled ]
  ```
  - `<Dropdown>` de sede: opciones = `branches` + una opción **"Todas las sedes"** (`value = ""` → `branch_id = null`). El calendario "primary" se marca con un sutil hint.
  - `<Switch>` `is_enabled`: el flag "habilitado para lectura". Sólo los enabled entran al overlay.
- **Estado local**: un `useState<Record<externalCalendarId, { branch_id: string | null; is_enabled: boolean }>>` (form controlado, **no** react-hook-form — es una matriz de filas, igual que `OfficeHoursTab` que maneja un array de bloques en estado local). 
- **"Guardar mapeo"** (gated `CALENDAR_CONNECTIONS_WRITE`): compone el body completo desde el estado de TODAS las filas (incluye `external_calendar_name` desde la opción para denormalizar) → `replaceSources(connectionId, { sources })` (replace atómico — manda el set completo, no diffs) → en éxito `onSaved()` (re-fetch) + toast/MessageBar "Mapeo guardado". Error `BRANCH_NOT_FOUND` (sede borrada entre el load y el save) → `MessageBar` en español sin cerrar.
- **`readOnly`** (sólo `CALENDAR_CONNECTIONS_READ`): Dropdowns/Switches deshabilitados, sin "Guardar mapeo" — sólo se ve el mapeo actual.

> **Por qué el body es el set COMPLETO** (replace, no diff): igual que `replaceOfficeHours`, el `PUT /connections/{id}/sources` reemplaza atómicamente todo el mapeo de la conexión (soft-delete los viejos + insert el set nuevo). El front arma `sources` con **todas** las filas que tienen una sede elegida o `is_enabled=true` (o todas, dejando que el backend decida) — la decisión exacta de qué filas incluir la fija [`backend.md`](./backend.md); el criterio simple es **mandar una fila por cada calendario que el usuario quiere mapear/habilitar**, y omitir los que dejó sin sede y deshabilitados. Mandar `{ sources: [] }` desmapea todo.

---

## MOD del overlay en `scheduling` (F2)

> **Regla no-negociable** (lección §23 / design.md §5.2): el overlay es **best-effort y aditivo**. Si `fetchExternalEvents` falla o `sources_health` reporta una conexión caída, la grilla **renderiza las citas normalmente** + un aviso suave; **nunca** rompe la grilla ni la reserva, **nunca** un 5xx visible. La capa externa no toca `compute_available_slots` ni los slots libres.

### `CalendarGrid.tsx` — extender `CalendarEvent.kind`

La grilla real ([`scheduling/_components/CalendarGrid.tsx`](../../../frontend/src/app/(main)/scheduling/_components/CalendarGrid.tsx)) **ya es genérica**: recibe `columns`/`events`/`onEventClick`/`nowIndicator` y pinta cada `CalendarEvent` posicionado por `startMin`/`endMin` (minutos locales) con `layoutOverlaps`. Su `CalendarEvent.kind` hoy es `"appointment" | "free"`. La MOD de F2 **agrega un tercer valor** y un estilo:

```ts
// CalendarGrid.tsx — extender el union (MOD mínima, retrocompatible):
export interface CalendarEvent {
  id: string;
  columnKey: string;
  startMin: number;
  endMin: number;
  title: string;
  subtitle?: string;
  color?: string | null;
  kind: "appointment" | "free" | "external"; // ← + "external" (overlay informativo)
  ariaLabel?: string;
}
```

- **Estilo de la capa externa** (`makeStyles`, nuevo `eventExternal`): visualmente **distinta** de las citas (fondo lleno por estado) y de los huecos libres (contorno punteado de marca). Patrón sugerido: **fondo rayado/atenuado** (`backgroundImage` con un `repeating-linear-gradient` tenue + `colorNeutralBackground3`), texto `colorNeutralForeground2`, sin el color de marca (para que se lea como "ajeno"). En el `render` del botón, `kind === "external"` ⇒ aplicar `styles.eventExternal` (rama nueva junto a `isFree`).
- **No-clicable para reservar**: para `kind === "external"`, el `onEventClick` **no abre el detalle ni reserva** (es informativo). Opciones: pasar el evento al handler y que el `CalendarClient` lo ignore (no hace nada para `external`), o renderizar el bloque externo como un `div` no-botón (sin `onClick`). La etiqueta accesible (`ariaLabel`) = `"Evento externo: {title} · {hora}"` para que un lector de pantalla lo distinga de una cita.
- **Día completo (`all_day`)**: los eventos `all_day` no tienen hora-de-pared útil → **no** se posicionan como bloque horario. MVP: omitirlos del overlay de bloques (o renderizarlos como una banda fina en la cabecera del día). Documentar como simplificación; el detalle (banda all-day) es refinamiento.
- **Leyenda**: la grilla (o el `CalendarClient` encima) muestra una **leyenda** bajo la toolbar: "● Cita medisage  ▦ Evento externo  ▢ Horario libre". La leyenda es parte de la UI de scheduling extendida (ver [`ui.md`](./ui.md)).

### `CalendarClient.tsx` — alimentar el overlay

El `CalendarClient` real ([`scheduling/calendario/_components/CalendarClient.tsx`](../../../frontend/src/app/(main)/scheduling/calendario/_components/CalendarClient.tsx)) ya arma `weekEvents`/`dayEvents` combinando `fetchAppointmentsInRange` (citas) + `computeAvailability` (huecos libres) y los pasa a `<CalendarGrid events={...}>`. La MOD de F2 **agrega una tercera query** y mapea sus resultados a eventos `kind: "external"`:

```ts
// CalendarClient.tsx — MOD (modo semana; la sede sale del doctor/branch elegido).
// branchId del overlay = la sede activa de la toolbar (el overlay es por sede). Si la
// toolbar no expone branch explícito, derivarlo del doctor/contexto (ver nota).
const externalQuery = useQuery({
  queryKey: ["sched-cal-external", weekFromIso, weekToIso, branchId],
  // from/to = los MISMOS instantes UTC que ya usa la grilla (weekFromIso/weekToIso).
  queryFn: () => fetchExternalEvents({ branchId: branchId as string, from: weekFromIso, to: weekToIso }),
  enabled: view === "week" && !!weekStart && !!branchId, // sólo si hay sede
});

// Mapear ExternalEventItem → CalendarEvent kind "external" (mismos helpers TZ que las citas).
const externalEvents = useMemo<CalendarEvent[]>(() => {
  const out: CalendarEvent[] = [];
  for (const ev of externalQuery.data?.events ?? []) {
    if (ev.all_day) continue; // MVP: los all-day no se posicionan como bloque (ver CalendarGrid)
    const startMin = localMinutesOf(ev.starts_at); // UTC → minutos locales de pared
    out.push({
      id: `ext-${ev.source_id}-${ev.external_id}`,
      columnKey: localDateIsoOf(ev.starts_at), // UTC → "YYYY-MM-DD" local
      startMin,
      endMin: localMinutesOf(ev.ends_at),
      title: ev.title,
      subtitle: minutesToTime(startMin),
      kind: "external",
      ariaLabel: `Evento externo: ${ev.title} · ${minutesToTime(startMin)}`,
    });
  }
  return out;
}, [externalQuery.data]);

// Y se concatenan a los eventos de la semana que recibe la grilla:
//   const events = view === "week" ? [...weekEvents, ...externalEvents] : dayEvents;
```

- **TZ idéntica a las citas**: los eventos externos se ubican con `localMinutesOf`/`localDateIsoOf` (de [`calendarWeek.ts`](../../../frontend/src/lib/utils/calendarWeek.ts)) — los mismos helpers que ya posicionan `scheduled_for`. Como la grilla actual posiciona en la **hora local del navegador** (no la del branch — limitación conocida ya documentada en la grilla de scheduling), el overlay es **consistente** con las citas: ambos en hora de pared local. *(Si en el futuro la grilla migra a posicionar en `branch.timezone` vía `Intl({timeZone})`, el overlay debe migrar igual — pero hoy se alinea con lo que la grilla shippeada hace, no se diverge.)*
- **Aviso de salud** (`sources_health`): si `externalQuery.data?.sources_health` trae alguna conexión `!== "connected"`, mostrar un `MessageBar intent="warning"` suave sobre la grilla: "Algunos calendarios externos no se pudieron leer (revisa la conexión)." — **sin** bloquear nada. Si `externalQuery.isError` (el endpoint entero falló, que no debería por ser best-effort), simplemente **no** se agregan eventos externos y la grilla pinta citas + huecos normalmente (el overlay es opcional).
- **Gating**: el overlay sólo se consulta/muestra si el usuario tiene `CALENDAR_EXTERNAL_EVENTS_READ` (`usePermissions().hasPermission("CALENDAR_EXTERNAL_EVENTS_READ")` → `enabled` de la query). El DOCTOR/ASESOR/ADMIN lo tienen; un rol sin ese permiso ve la grilla sin overlay (y el backend lo rechazaría igual con 403).
- **Sede del overlay**: el overlay es **por sede** (`branch_id`). El modo semana de la grilla hoy filtra por doctor, no por sede explícita. Para F2 hay que **exponer/derivar la sede** (un `Dropdown branch_id` en la toolbar, o derivarla del doctor elegido si el doctor atiende en una sola sede). La fuente de la sede la fija [`ui.md`](./ui.md); el contrato del action (`fetchExternalEvents` requiere `branchId`) es fijo. Mientras no haya sede, el overlay no se consulta (`enabled: !!branchId`).

### Aviso suave en el `BookingWizard` (Pantalla 2.b, F2)

Refinamiento advisory (decisión LOCKED #5): cuando el usuario elige un slot en el `BookingWizard` (paso Slot/Confirmar) y ese slot **solapa** un evento externo de la misma sede, mostrar un `MessageBar intent="info"` ("Hay un evento externo a esta hora en esta sede.") **sin** impedir la reserva. Implementación: el wizard ya conoce `branch_id` + `scheduled_for` + `duration_min` → llama `fetchExternalEvents({ branchId, from, to })` para la ventana del día y chequea solape en cliente (`localMinutesOf`). Es **puramente informativo**: no valida, no bloquea, no manda nada al backend. Si la lectura externa falla, **no** se muestra el aviso (best-effort).

---

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| **OAuth = `startOAuth` devuelve `auth_url`, el CLIENTE redirige** (`window.location.href`) | El consentimiento es un host externo; el redirect debe ser un gesto del usuario. El `redirect()` del action se reserva para rutas internas. El **regreso** es un 302 del callback público del backend. |
| **El callback es un endpoint PÚBLICO del backend, no una action** | Lo golpea el navegador del usuario tras autorizar (gateado por `state` JWT, no por JWT de sesión). El front sólo lee el `?calendar_error=` resultante en el RSC. |
| **`?calendar_error=CODE` se lee en el RSC y se traduce con `CALENDAR_ERROR_LABELS`** | El 302 del backend llega en el primer render; se pasa como prop al client, se muestra en `MessageBar` y se limpia de la URL (`router.replace`) para no repetirlo en un refresh. |
| **Ruta bajo `/clinic` pero todo el código es `calendar.*`** | UX: pertenece al grupo Clínica; separación de módulos: tipos/schemas/actions/endpoints/tag = `calendar`. Sólo `BranchOption` cruza desde clinic. |
| **Mapeo de sources = `PUT` bulk replace atómico** (molde `replaceOfficeHours`) | El set completo reemplaza lo existente (soft-delete viejos + insert nuevos); sin per-row CRUD. `{ sources: [] }` desmapea todo. |
| **`is_enabled` (no una 2ª columna boolean)** | Reusa `ActiveMixin.active` del backend (precedente bots `BotConfigurationVersion.is_active`); el front lo ve como `is_enabled`. |
| **`branch_id` nullable = "Todas las sedes"** (opción `value=""` en el Dropdown) | Decisión LOCKED #3; el `sourceCreateSchema` lo deja `nullable().optional()`. El backend valida la FK (404 `BRANCH_NOT_FOUND`). |
| **`listExternalCalendars`/`fetchExternalEvents` = live, `cache: "no-store"`, sin tag** | Datos del proveedor externo que cambian fuera de medisage; cachearlos daría datos viejos (igual criterio que `availability.actions.ts` de scheduling). |
| **Un solo tag `calendar:connections`** (no por-id) | 1-2 conexiones típicas; no vale un tag por-conexión. Conectar/desconectar/guardar-mapeo lo invalidan. |
| **Overlay = `CalendarEvent.kind: "external"` en la grilla EXISTENTE** | No se crea grilla nueva; se extiende el union de `CalendarGrid` con un valor + un estilo atenuado/rayado + leyenda. Aditivo y retrocompatible. |
| **Overlay no-clicable para reservar; eventos `all_day` omitidos del MVP** | Es informativo (no agenda); los all-day no tienen hora-de-pared → banda en cabecera = refinamiento diferido. |
| **Overlay best-effort: nunca rompe la grilla ni un 5xx** | Lección §23 / design.md §5.2: la lectura externa es aislada; si falla, la grilla pinta citas normalmente + un aviso suave de `sources_health`. |
| **Overlay alineado a la TZ que la grilla shippeada usa** (hora local del navegador vía `localMinutesOf`) | Consistencia con las citas (que ya se posicionan así); no se diverge. Si la grilla migra a `branch.timezone`, el overlay migra con ella. |
| **`secret_name`/tokens NUNCA cruzan al front** | El schema Item/Detail del backend los omite; el front sólo ve metadatos + salud. |
| **Aviso suave en el `BookingWizard` (F2)** | Advisory (decisión LOCKED #5): informa solape con un evento externo sin bloquear la reserva; best-effort. |
| **Íconos Fluent existentes** (`CalendarLtrRegular`, fallback de `CalendarSyncRegular`) | No introducir librería de íconos nueva (lección Next 16 del template); `CalendarLtrRegular` ya está en el `iconMap`. |

---

## Checklist de implementación (mapeado a fases F0–F2)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Cada checkbox es lado frontend.

### F0 — Prep (andamiaje compartido, sin migración, módulo backend inerte)

- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `CALENDAR` (OAUTH start/callback, CONNECTIONS list/get/delete/calendars/sources, EXTERNAL_EVENTS). El `OAUTH_CALLBACK` va como referencia documental (público, no se llama desde `backendClient`).
- [ ] Extender `src/lib/constants/navigation.ts`: child `external-calendars` ("Calendarios externos") en el grupo "Clínica", gated `CALENDAR_CONNECTIONS_READ`, ícono `CalendarLtrRegular` (verificar `CalendarSyncRegular` en el `iconMap`).
- [ ] Crear `src/types/calendar.types.ts` (TODAS las interfaces + enums `CalendarProvider`/`ConnectionStatus`; reusa `UserAuditInfo`/`BranchOption`).
- [ ] Crear `src/lib/constants/calendar-providers.ts` (`CALENDAR_PROVIDER_META`, `CONNECTION_STATUS_META`, `CALENDAR_ERROR_LABELS`).
- [ ] Crear el skeleton inerte de `app/(main)/clinic/calendarios-externos/page.tsx` (placeholder con `requirePermission`; sin lógica hasta F1).
- [ ] **Permisos test (F0)**: el child "Calendarios externos" aparece para ADMIN y ASESOR (tienen `CALENDAR_CONNECTIONS_READ`), NO para DOCTOR (sólo `CALENDAR_EXTERNAL_EVENTS_READ`); un usuario sin ninguno no ve el item. Rutas backend `/calendar/*` → 404 (módulo no registrado). (Los 4 permisos + roles ya en `seed.py` — ver [`../_seed-and-roles.md`](../_seed-and-roles.md); los introduce backend F0.)

### F1 — Conexión + mapeo (la pantalla de config)

- [ ] Crear `src/lib/schemas/calendar.schema.ts` (`sourceCreateSchema`, `sourcesReplaceSchema`; `branch_id` nullable/optional, `is_enabled` default true).
- [ ] Crear `src/actions/calendar.actions.ts` (`startOAuth`, `listConnections`, `getConnection`, `disconnect`, `listExternalCalendars`, `replaceSources` con `revalidateTag("calendar:connections")`; `fetchExternalEvents` se usa recién en F2 pero puede crearse acá).
- [ ] Implementar `app/(main)/clinic/calendarios-externos/page.tsx` (prefetch `listConnections` + `listActiveBranches`; lee `?calendar_error`) + `_components/CalendarConnectionsClient.tsx` (header conectar Google/Outlook + banner de error + lista de cards + empty state) + `ConnectionCard.tsx` (ícono provider + email + badge salud + Reconectar/Desconectar + monta mapeo) + `SourceMappingTable.tsx` (filas calendario→sede + Switch + "Guardar mapeo", molde `OfficeHoursTab`).
- [ ] **Smoke test (F1)**: "Conectar Google" → redirige al consentimiento → vuelve → aparece la card `clinica@gmail.com` con badge "Conectada". Expandir → lista de calendarios de la cuenta → mapear "Sede Miraflores" → sede + activar → "Guardar mapeo" → recargar persiste. "Desconectar" con `ConfirmDialog` → la card desaparece.
- [ ] **Error OAuth test (F1)**: cancelar el consentimiento / state inválido → vuelve con `?calendar_error=CALENDAR_OAUTH_STATE_INVALID` → `MessageBar` en español + URL limpia tras leerlo. Conectar 2 veces la misma cuenta → `CALENDAR_CONNECTION_ALREADY_EXISTS` (409 vía redirect o action).
- [ ] **Validación test (F1)**: guardar un mapeo a una sede borrada entre el load y el save → `BRANCH_NOT_FOUND` (404) en `MessageBar` sin cerrar.
- [ ] **Permisos test (F1)**: con `CALENDAR_CONNECTIONS_READ` sin `_WRITE` → ve las cards y el mapeo en read-only (sin Conectar/Guardar/Desconectar). El DOCTOR no llega a la página (RSC redirige).

### F2 — Lectura informativa (overlay + aviso en el wizard)

- [ ] MOD `scheduling/_components/CalendarGrid.tsx`: extender `CalendarEvent.kind` con `"external"` + estilo `eventExternal` (rayado/atenuado, distinto de cita y de hueco) + leyenda + no-clicable para reservar.
- [ ] MOD `scheduling/calendario/_components/CalendarClient.tsx`: agregar `externalQuery` (`fetchExternalEvents`, `enabled: !!branchId && hasPermission("CALENDAR_EXTERNAL_EVENTS_READ")`), mapear a `CalendarEvent` kind "external" (con `localMinutesOf`/`localDateIsoOf`), concatenar a `events`, y mostrar el `MessageBar` suave de `sources_health`. Exponer/derivar la sede del overlay (Dropdown branch o del doctor).
- [ ] (Opcional F2) Aviso suave en el `BookingWizard`: `MessageBar info` si el slot elegido solapa un evento externo de la sede (best-effort, no bloquea).
- [ ] **Smoke test (F2)**: en `/scheduling/calendario` con una sede que tiene un calendario externo habilitado → los eventos externos se pintan como capa rayada/atenuada, claramente distintos de las citas (color por estado) y los huecos libres (punteado de marca); la leyenda los explica. Click en un evento externo → no abre detalle ni reserva. Navegar semana → el overlay re-fetcha.
- [ ] **TZ test (F2)**: un evento externo a las 23:30 hora local se pinta en el día y la fila correctos (mismo helper que las citas, hora de pared local; consistente con `scheduled_for`).
- [ ] **Aislamiento test (F2)** (lección §23): con una conexión en `needs_reauth`/caída → `sources_health` la marca → `MessageBar` suave; la grilla pinta las citas y los huecos **normalmente** (nunca un 5xx, nunca grilla rota). Desconectar la cuenta → el overlay desaparece, la grilla sigue intacta.
- [ ] **Permisos test (F2)**: sin `CALENDAR_EXTERNAL_EVENTS_READ` la grilla no consulta/muestra el overlay (y el backend lo rechazaría con 403); el ADMIN/ASESOR/DOCTOR sí lo ven.

### Diferidas (B1–B4) — documentar, NO codear

- [ ] **B1 modo bloqueante** (busy externo → `compute_available_slots` MINUS): NO se construye; sólo roadmap en README/design.
- [ ] **B2 per-doctor + push** (events.insert, títulos PHI-min, vistas per-doctor): NO se construye.
- [ ] **B3 sync** (webhooks Google watch / Graph subscriptions + syncToken/delta + Cloud Tasks + tabla `ExternalEvent`): NO se construye.
- [ ] **B4 3er proveedor CalDAV**: el enum reserva `caldav` pero el front NO lo lista en `CALENDAR_PROVIDER_META` ni ofrece "Conectar CalDAV".

## TODOs deliberados (postergados al MVP+1 / fases diferidas)

- [ ] **Banda all-day en la cabecera del día** del overlay — el MVP omite los eventos `all_day` de los bloques horarios.
- [ ] **Posicionar la grilla en `branch.timezone`** (vía `Intl({timeZone})`) — hoy la grilla shippeada usa hora local del navegador; el overlay se alinea con ella. Migrar ambos juntos si/cuando la grilla migre.
- [ ] **Refresh/auto-recheck de salud** de las conexiones desde la UI (botón "Revisar ahora") — el MVP muestra `last_checked_at` y deja el recheck al backend en cada lectura.
- [ ] **Filtro de calendarios** en `SourceMappingTable` cuando una cuenta tiene decenas de calendarios — el MVP lista todos.
- [ ] **Vistas per-doctor / "Mi agenda" con overlay** — diferido al per-doctor (B2); la spec dice que "Mi agenda" se naturaliza ahí.
- [ ] **i18n framework** — strings literales en español directo (mismo criterio que catalog/clinic/staff/crm/scheduling).
