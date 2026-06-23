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

// Una sola familia de tag: la config tiene típicamente 1-2 conexiones; no vale un tag por-id.
// Conectar (vuelta del callback = navegación fresca), desconectar y guardar-mapeo lo invalidan.
const CONNECTIONS_TAG = "calendar:connections";

// ── OAuth start (el CLIENTE redirige el navegador al auth_url) ──────────────────────────────
// NO usa redirect() del action: devuelve el auth_url y el cliente hace
// `window.location.href = auth_url`. Así el flujo arranca con un gesto del usuario y el
// callback (302 del backend) aterriza de vuelta en la página con ?calendar_error si falla.
// Backend: GET /calendar/oauth/{provider}/start?return_to= → SingleResponse[{auth_url}]
// (gated CALENDAR_CONNECTIONS_WRITE).
export async function startOAuth(
  provider: CalendarProvider,
  returnTo: string,
): Promise<MutationResult<OAuthStartResponse>> {
  try {
    const res = await backendClient.get<ApiSingle<OAuthStartResponse>>(
      `${ENDPOINTS.CALENDAR.OAUTH_START(provider)}?return_to=${encodeURIComponent(returnTo)}`,
    );
    return { ok: true, data: res.data }; // { auth_url }
  } catch (e) {
    // 400 CALENDAR_PROVIDER_NOT_SUPPORTED / CALENDAR_CREDENTIALS_MISSING (detail ya en español).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Conexiones ──────────────────────────────────────────────────────────────────────────────

// POST /calendar/connections/list (gated CALENDAR_CONNECTIONS_READ) → PaginatedResponse.
export async function listConnections(
  query: QueryRequest,
): Promise<ApiPaginated<CalendarConnectionItem>> {
  return backendClient.post<ApiPaginated<CalendarConnectionItem>>(
    ENDPOINTS.CALENDAR.CONNECTIONS_LIST,
    query,
    { tags: [CONNECTIONS_TAG] },
  );
}

// GET /calendar/connections/{id} (READ) → SingleResponse[CalendarConnectionDetail] (+ sources
// embebidos por selectinload, para la card expandida).
export async function getConnection(id: string): Promise<ApiSingle<CalendarConnectionDetail>> {
  return backendClient.get<ApiSingle<CalendarConnectionDetail>>(
    ENDPOINTS.CALENDAR.CONNECTION_GET(id),
    { tags: [CONNECTIONS_TAG] },
  );
}

// DELETE /calendar/connections/{id} (WRITE) → 204 (soft-delete + revoke best-effort + borra el
// secreto del lado backend).
export async function disconnect(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CALENDAR.CONNECTION_DELETE(id)); // 204
    revalidateTag(CONNECTIONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 404 CALENDAR_CONNECTION_NOT_FOUND si ya no existe (detail en español).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Mapeo de calendarios → sedes ──────────────────────────────────────────────────────────────

// Lista LIVE de calendarios de la cuenta (de list_calendars del proveedor). La consume el
// SourceMappingTable para ofrecer las filas a mapear. ⚠ Backend la gatea con
// CALENDAR_CONNECTIONS_WRITE (no READ): un usuario read-only NO debe llamarla (403) → la tabla
// read-only se arma sólo con los sources ya guardados (getConnection). Lectura on-demand: SIN
// tag → `backendClient` la sirve `cache: "no-store"` automáticamente (omitir tags = no-store).
// GET /calendar/connections/{id}/calendars → SingleResponse[list[ExternalCalendarOption]].
export async function listExternalCalendars(
  connectionId: string,
): Promise<ExternalCalendarOption[]> {
  const res = await backendClient.get<ApiSingle<ExternalCalendarOption[]>>(
    ENDPOINTS.CALENDAR.CONNECTION_CALENDARS(connectionId),
  );
  return res.data; // [{ id, name, primary }]
}

// Bulk atomic REPLACE del mapeo (soft-delete los viejos + insert el set nuevo, patrón
// replaceOfficeHours). Mandar { sources: [] } borra todos los mapeos de la conexión.
// PUT /calendar/connections/{id}/sources (WRITE) → SingleResponse[CalendarConnectionDetail].
export async function replaceSources(
  connectionId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<CalendarConnectionDetail>>> {
  const parsed = sourcesReplaceSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<CalendarConnectionDetail>>(
      ENDPOINTS.CALENDAR.CONNECTION_SOURCES(connectionId), // ← PUT bulk replace
      parsed.data, // { sources: [...] }
    );
    revalidateTag(CONNECTIONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 404 BRANCH_NOT_FOUND (sede inexistente) / CALENDAR_CONNECTION_NOT_FOUND (detail en español).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Overlay informativo (F2) — lectura best-effort, sin revalidate ──────────────────────────
// La consume el CalendarClient de scheduling (mapea los ExternalEventItem a CalendarEvent
// kind "external"). from/to = los MISMOS instantes UTC que la grilla ya calcula
// (weekFromIso/weekToIso). El backend es best-effort: NUNCA 5xx — si una conexión falla, viaja
// en sources_health. Lectura live on-demand: SIN tag → backendClient sirve cache:"no-store".
// GET /calendar/external-events?branch_id=&from=&to= → SingleResponse[ExternalEventsResponse].
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
  );
  return res.data; // { events, sources_health }
}
