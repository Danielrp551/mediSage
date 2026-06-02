"use server";

/**
 * Timeline de actividad del módulo crm (F5 — timeline rico + composer).
 *
 * - `listActivities`: feed completo (NO paginado) que alimenta el tab Actividad.
 *   El backend devuelve `SingleResponse[list[ActivityItem]]` → toda la lista en
 *   `.data`, más reciente primero. Los chips re-consultan con `activity_type`.
 * - `createActivity` / `updateActivity` / `deleteActivity`: el composer y las
 *   acciones por tarjeta. "Borrar" = `active=false` (desaparece del feed).
 *
 * Una nota/llamada/seguimiento toca `last_activity_at` del lead (denormalizado en
 * el listado de personas) → además del tag de actividad se revalida `crm:persons`.
 */

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  leadActivityCreateSchema,
  leadActivityUpdateSchema,
} from "@/lib/schemas/lead-activity.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { ActivityListRequest, LeadActivityItem } from "@/types/crm.types";

import type { MutationResult } from "./user.actions";

const activityTag = (id: string) => `crm:activity:${id}`;
const PERSONS_TAG = "crm:persons";

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
    // 422 si el tipo es de sistema o falta scheduled_for en FOLLOW_UP_SCHEDULED
    // (el Zod ya lo previene; defensa en profundidad).
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateActivity(
  personId: string,
  activityId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<LeadActivityItem>>> {
  const parsed = leadActivityUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<LeadActivityItem>>(
      ENDPOINTS.PERSONS.ACTIVITY(personId, activityId), // ← PUT
      parsed.data,
    );
    // 404 ACTIVITY_NOT_FOUND (no existe / no es de esta persona / ya borrada) en español.
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteActivity(
  personId: string,
  activityId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PERSONS.ACTIVITY(personId, activityId)); // 204
    // 404 ACTIVITY_NOT_FOUND al re-borrar.
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
