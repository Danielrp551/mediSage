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

export async function createLeadStatus(
  input: unknown,
): Promise<MutationResult<ApiSingle<LeadStatusItem>>> {
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
