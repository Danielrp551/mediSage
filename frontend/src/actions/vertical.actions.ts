"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  verticalCreateSchema,
  verticalUpdateSchema,
} from "@/lib/schemas/vertical.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  VerticalDetail,
  VerticalItem,
  VerticalOption,
} from "@/types/catalog.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const VERTICALS_TAG = "catalog:verticals";

export async function listVerticals(
  query: QueryRequest,
): Promise<ApiPaginated<VerticalItem>> {
  return backendClient.post<ApiPaginated<VerticalItem>>(
    ENDPOINTS.VERTICALS.LIST,
    query,
    { tags: [VERTICALS_TAG] },
  );
}

export async function listActiveVerticals(): Promise<VerticalOption[]> {
  return backendClient.get<VerticalOption[]>(ENDPOINTS.VERTICALS.ACTIVE, {
    tags: [VERTICALS_TAG],
  });
}

export async function getVertical(id: string): Promise<ApiSingle<VerticalDetail>> {
  return backendClient.get<ApiSingle<VerticalDetail>>(ENDPOINTS.VERTICALS.GET(id), {
    tags: [VERTICALS_TAG],
  });
}

export async function createVertical(
  input: unknown,
): Promise<MutationResult<ApiSingle<VerticalDetail>>> {
  const parsed = verticalCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<VerticalDetail>>(
      ENDPOINTS.VERTICALS.CREATE,
      parsed.data,
    );
    revalidateTag(VERTICALS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateVertical(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<VerticalDetail>>> {
  const parsed = verticalUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<VerticalDetail>>(
      ENDPOINTS.VERTICALS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(VERTICALS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteVertical(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.VERTICALS.DELETE(id));
    revalidateTag(VERTICALS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
