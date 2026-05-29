"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { serviceCreateSchema, serviceUpdateSchema } from "@/lib/schemas/service.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { ServiceDetail, ServiceItem, ServiceOption } from "@/types/catalog.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const SERVICES_TAG = "catalog:services";
// Renaming a service invalidates products too: ProductItem denormalizes
// `service_name` (phase 3). Invalidating the not-yet-used tag now is a no-op
// but means phase 3 doesn't have to retrofit this action.
const PRODUCTS_TAG = "catalog:products";

export async function listServices(query: QueryRequest): Promise<ApiPaginated<ServiceItem>> {
  return backendClient.post<ApiPaginated<ServiceItem>>(ENDPOINTS.SERVICES.LIST, query, {
    tags: [SERVICES_TAG],
  });
}

export async function listActiveServices(verticalId?: string): Promise<ServiceOption[]> {
  const url = verticalId
    ? `${ENDPOINTS.SERVICES.ACTIVE}?vertical_id=${encodeURIComponent(verticalId)}`
    : ENDPOINTS.SERVICES.ACTIVE;
  return backendClient.get<ServiceOption[]>(url, { tags: [SERVICES_TAG] });
}

export async function getService(id: string): Promise<ApiSingle<ServiceDetail>> {
  return backendClient.get<ApiSingle<ServiceDetail>>(ENDPOINTS.SERVICES.GET(id), {
    tags: [SERVICES_TAG],
  });
}

export async function createService(
  input: unknown,
): Promise<MutationResult<ApiSingle<ServiceDetail>>> {
  const parsed = serviceCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<ServiceDetail>>(
      ENDPOINTS.SERVICES.CREATE,
      parsed.data,
    );
    revalidateTag(SERVICES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateService(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<ServiceDetail>>> {
  const parsed = serviceUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<ServiceDetail>>(
      ENDPOINTS.SERVICES.UPDATE(id),
      parsed.data,
    );
    revalidateTag(SERVICES_TAG, "max");
    // Cross-tag: a renamed service makes the denormalized `service_name` in
    // cached products stale.
    if ("name" in parsed.data) {
      revalidateTag(PRODUCTS_TAG, "max");
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteService(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.SERVICES.DELETE(id));
    revalidateTag(SERVICES_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
