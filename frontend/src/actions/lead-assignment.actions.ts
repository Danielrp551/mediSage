"use server";

/**
 * Asignación de owner del lead (F3): asesor actual + reasignar manual /
 * "asignarme" + round-robin automático + dropdown de asesores + bandeja del
 * asesor logueado (Mis leads).
 */

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { AdvisorOption, LeadAssignmentDetail, MyLeadItem } from "@/types/crm.types";
import type { QueryRequest } from "@/types/query.types";

import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const leadTag = (id: string) => `crm:lead:${id}`;
const activityTag = (id: string) => `crm:activity:${id}`;

// Asesor dueño actual. El backend devuelve 404 ASSIGNMENT_NOT_FOUND cuando la
// persona no tiene asignación → lo traducimos a `null` (estado vacío, NO error).
// Un PERSON_NOT_FOUND (404) lo maneja el RSC del detalle, no este fetch en cliente.
export async function getAssignment(personId: string): Promise<LeadAssignmentDetail | null> {
  try {
    const res = await backendClient.get<ApiSingle<LeadAssignmentDetail>>(
      ENDPOINTS.PERSONS.ASSIGNMENT(personId),
      { tags: [leadTag(personId)] },
    );
    return res.data;
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) return null;
    throw e;
  }
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

// Asesores activos para el dropdown de reasignación. Lista CRUDA (sin envelope).
// crm-owned (GET /crm/advisors/active, gated LEAD_ASSIGNMENTS_READ), NO admin/users.
export async function listActiveAdvisors(): Promise<AdvisorOption[]> {
  return backendClient.get<AdvisorOption[]>(ENDPOINTS.ADVISORS.ACTIVE, { tags: [PERSONS_TAG] });
}

// Mis leads (asesor logueado). El backend resuelve el asesor del token.
export async function listMyLeads(query: QueryRequest): Promise<ApiPaginated<MyLeadItem>> {
  return backendClient.post<ApiPaginated<MyLeadItem>>(ENDPOINTS.ME_CRM.LEADS_LIST, query, {
    tags: [PERSONS_TAG], // se invalida al reasignar/transicionar (afecta la lista del asesor)
  });
}
