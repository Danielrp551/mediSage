"use server";

/**
 * Estado lead + customer de una Person + transiciones + history + promote
 * (F3 + F4). Estos actions CRUZAN tags (estado lead/customer + timeline +
 * listado): un promote puede cerrar el lead como ganado y siempre crea la ficha
 * de cliente, así que invalida lead + customer + actividad + listado a la vez.
 */

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

// ── Customer lifecycle (F4) ─────────────────────────────

// Estado cliente actual (o null vía 200 con data null si la persona no es cliente).
export async function getCustomerStatus(
  personId: string,
): Promise<PersonCustomerStatusDetail | null> {
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
): Promise<MutationResult<ApiSingle<PersonCustomerStatusDetail | null>>> {
  const parsed = customerTransitionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    // Si el destino es is_final, el backend cierra el estado cliente y devuelve null.
    const data = await backendClient.post<ApiSingle<PersonCustomerStatusDetail | null>>(
      ENDPOINTS.PERSONS.CUSTOMER_TRANSITION(personId),
      parsed.data,
    );
    // Invalidar estado cliente + el badge de cliente del listado.
    revalidateTag(customerTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 CUSTOMER_TRANSITION_NOT_ALLOWED / NOT_A_CUSTOMER / 404 CUSTOMER_STATUS_NOT_FOUND.
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
    // El promote nace la ficha de cliente Y puede cerrar el lead activo como ganado
    // (emite STATUS_CHANGE) → invalida customer + lead + actividad + listado.
    revalidateTag(customerTag(personId), "max");
    revalidateTag(leadTag(personId), "max");
    revalidateTag(activityTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 ALREADY_CUSTOMER en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
