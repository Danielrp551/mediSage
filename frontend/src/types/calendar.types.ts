/**
 * Espejo TS de los Pydantic schemas del módulo `calendar` (#9) — ver
 * `docs/modules/calendar/{README,backend,ui,frontend}.md` + ADR-014. Importable desde server
 * actions y client components. Reusa `UserAuditInfo` de `audit.types` — NO se redefine.
 *
 * AUTORIDAD DE SHAPE: el contrato de runtime es `backend.md` (los Pydantic que serializan el
 * JSON); `frontend.md` es el molde de naming/precisión. Reconciliaciones aplicadas (auditoría
 * de la fase de doc):
 *   - `CalendarConnectionItem.is_active` (NO `active`): el backend serializa el flag de pausa
 *     manual de la conexión bajo la key `is_active` (ActiveMixin expuesto).
 *   - `ExternalEventItem.branch_id`/`branch_name` son `string | null`: un evento de un
 *     `CalendarSource` mapeado a "todas las sedes" (`branch_id IS NULL`) los emite null.
 *   - `CalendarProviderOption.label` = "Google" / "Outlook" (label corto consistente; el botón
 *     usa "Conectar Google"/"Conectar Outlook").
 *
 * Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún. Las pantallas llegan por
 * fase: config de la clínica (conexiones + mapeo, F1), overlay en la grilla de scheduling (F2).
 *
 * Notas de contrato que el código no expresa solo:
 *   - `starts_at`/`ends_at`/`last_checked_at`/`created_on`/`updated_on` son `timestamptz` ISO 8601
 *     con offset (instantes UTC). El overlay los ubica en la grilla en HORA LOCAL DEL NAVEGADOR
 *     (helpers `calendarWeek.ts`), igual que las citas de la grilla shippeada (el overlay comparte
 *     su base temporal; render en la TZ de la sede = mejora diferida conjunta de la grilla).
 *   - `secret_name`/tokens NUNCA cruzan al front: el Item/Detail del backend los omite.
 */

import type { UserAuditInfo } from "./audit.types";

// ── Enums (espejo de calendar/enums.py; valores EXACTOS) ───

// Proveedor del calendario externo. Python: CalendarProvider(StrEnum). `caldav` reservado (futuro).
export type CalendarProvider = "google" | "microsoft";

// Salud de la conexión. Python: ConnectionStatus(StrEnum).
export type ConnectionStatus = "connected" | "needs_reauth" | "revoked" | "error";

// ── CalendarConnection (cuenta OAuth de la clínica; tokens en Secret Manager) ──

export interface CalendarConnectionItem {
  id: string;
  provider: CalendarProvider;
  account_email: string; // identidad de la cuenta conectada (de userinfo / Graph /me)
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

// Detalle: la conexión + sus sources (selectinload en el backend) + last_error.
export interface CalendarConnectionDetail extends CalendarConnectionItem {
  last_error: string | null; // último error de refresh/list (observabilidad, tooltip)
  sources: CalendarSourceItem[];
}

// ── CalendarSource (un calendario concreto mapeado a una sede) ──
// El flag "habilitado para lectura" se expone como is_enabled (reusa ActiveMixin.active del
// backend; precedente bots BotConfigurationVersion.is_active — NO una 2ª columna boolean).

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
export interface ExternalCalendarOption {
  id: string; // = external_calendar_id
  name: string;
  primary: boolean; // calendario principal de la cuenta (se sugiere mapearlo primero)
}

// ── ExternalEvent (overlay informativo, F2) ─────────────────────
// Instantes UTC (ISO 8601 con offset). El render los ubica en la grilla en hora local del
// navegador con localMinutesOf/localDateIsoOf (igual que scheduled_for de las citas).
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

// Salud por conexión devuelta junto a los eventos (best-effort: si una conexión falla, su
// evento NO aparece pero su salud SÍ → aviso suave en la grilla, nunca un 5xx).
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

// Para los botones "Conectar X" del header (label + provider).
export interface CalendarProviderOption {
  value: CalendarProvider;
  label: string; // "Google" / "Outlook"
}
