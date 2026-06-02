"use server";

/**
 * Timeline de actividad (F3, Iteración A = read-only). Sólo `listActivities`:
 * el feed que alimenta el tab Actividad (muestra STATUS_CHANGE/REASSIGNED/
 * CAMPAIGN_ATTRIBUTION que F3 ya emite).
 *
 * El composer (create/update/delete) llega en F5 — sus rutas de backend aún no
 * existen, no se incluyen aquí.
 *
 * ⚠ El backend devuelve `SingleResponse[list[ActivityItem]]` (NO paginado) — la
 * lista entera va en `.data`.
 */

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { type ApiSingle } from "@/types/api.types";
import type { ActivityListRequest, LeadActivityItem } from "@/types/crm.types";

const activityTag = (id: string) => `crm:activity:${id}`;

export async function listActivities(
  personId: string,
  filters: ActivityListRequest = {},
): Promise<ApiSingle<LeadActivityItem[]>> {
  // POST con body de filtros (activity_type[], rango fecha). SingleResponse → `.data`.
  return backendClient.post<ApiSingle<LeadActivityItem[]>>(
    ENDPOINTS.PERSONS.ACTIVITIES_LIST(personId),
    filters,
    { tags: [activityTag(personId)] },
  );
}
