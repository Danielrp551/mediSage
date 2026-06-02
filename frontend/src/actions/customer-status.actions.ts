"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  customerStatusCreateSchema,
  customerStatusUpdateSchema,
} from "@/lib/schemas/customer-status.schema";
import { transitionTargetsSchema } from "@/lib/schemas/lead-status.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  CustomerStatusItem,
  CustomerStatusOption,
  CustomerTransitionTargets,
} from "@/types/crm.types";
import type { QueryRequest } from "@/types/query.types";

import type { MutationResult } from "./user.actions";

const TAG = "crm:customer-statuses";

export async function listCustomerStatuses(
  query: QueryRequest,
): Promise<ApiPaginated<CustomerStatusItem>> {
  return backendClient.post<ApiPaginated<CustomerStatusItem>>(
    ENDPOINTS.CUSTOMER_STATUSES.LIST,
    query,
    { tags: [TAG] },
  );
}

export async function listActiveCustomerStatuses(): Promise<CustomerStatusOption[]> {
  // Lista CRUDA. La consume el TransitionControl y los dropdowns de estado.
  return backendClient.get<CustomerStatusOption[]>(ENDPOINTS.CUSTOMER_STATUSES.ACTIVE, {
    tags: [TAG],
  });
}

export async function createCustomerStatus(
  input: unknown,
): Promise<MutationResult<ApiSingle<CustomerStatusItem>>> {
  const parsed = customerStatusCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<CustomerStatusItem>>(
      ENDPOINTS.CUSTOMER_STATUSES.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 MULTIPLE_INITIAL_STATUS en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateCustomerStatus(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<CustomerStatusItem>>> {
  const parsed = customerStatusUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<CustomerStatusItem>>(
      ENDPOINTS.CUSTOMER_STATUSES.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteCustomerStatus(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CUSTOMER_STATUSES.DELETE(id));
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 CUSTOMER_STATUS_IN_USE si hay un cliente vivo (PersonCustomerStatus) en ese estado.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Matriz de transiciones ──────────────────────────────

export async function getCustomerTransitions(id: string): Promise<CustomerTransitionTargets> {
  // GET devuelve SingleResponse[CustomerTransitionTargets] → se lee `.data`.
  const res = await backendClient.get<ApiSingle<CustomerTransitionTargets>>(
    ENDPOINTS.CUSTOMER_STATUSES.TRANSITIONS(id),
    { tags: [TAG] },
  );
  return res.data;
}

export async function setCustomerTransitions(
  id: string,
  input: unknown, // { to_ids: [...] } — reemplaza las aristas de salida
): Promise<MutationResult<ApiSingle<CustomerTransitionTargets>>> {
  const parsed = transitionTargetsSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<CustomerTransitionTargets>>(
      ENDPOINTS.CUSTOMER_STATUSES.TRANSITIONS(id), // ← PUT (reemplaza)
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
