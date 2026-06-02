"use server";

/**
 * Estado lead de una Person + transiciones + history (F3). Estos actions
 * CRUZAN tags (estado + timeline + listado).
 *
 * F3 = lead-only. `promoteToCustomer` / getCustomerStatus / transitionCustomer
 * llegan en F4 (sus rutas de backend aún no existen) — NO se incluyen aquí.
 */

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { createLeadSchema, leadTransitionSchema } from "@/lib/schemas/lifecycle.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { LeadStatusHistoryItem, PersonLeadStatusDetail } from "@/types/crm.types";

import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const leadTag = (id: string) => `crm:lead:${id}`;
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
    // Si el destino es is_final, el backend cierra el lead (soft-delete) y devuelve null.
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
