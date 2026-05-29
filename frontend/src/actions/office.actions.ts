"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { officeCreateSchema, officeUpdateSchema } from "@/lib/schemas/office.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { OfficeDetail, OfficeItem, OfficeOption } from "@/types/clinic.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const OFFICES_TAG = "clinic:offices";

export async function listOffices(query: QueryRequest): Promise<ApiPaginated<OfficeItem>> {
  return backendClient.post<ApiPaginated<OfficeItem>>(ENDPOINTS.OFFICES.LIST, query, {
    tags: [OFFICES_TAG],
  });
}

export async function listActiveOffices(
  branchId?: string,
  verticalId?: string,
): Promise<OfficeOption[]> {
  const params = new URLSearchParams();
  if (branchId) params.set("branch_id", branchId);
  if (verticalId) params.set("vertical_id", verticalId);
  const qs = params.toString();
  const url = qs ? `${ENDPOINTS.OFFICES.ACTIVE}?${qs}` : ENDPOINTS.OFFICES.ACTIVE;
  // `/active` returns a RAW list (response_model=list[...]) — no envelope.
  return backendClient.get<OfficeOption[]>(url, { tags: [OFFICES_TAG] });
}

export async function getOffice(id: string): Promise<ApiSingle<OfficeDetail>> {
  // OfficeDetail includes `branch` (BranchOption) and `verticals`
  // (VerticalOption[]) — soft-deleted verticals are filtered out server-side
  // via a join on `vertical.deleted_at IS NULL`. The frontend trusts that.
  return backendClient.get<ApiSingle<OfficeDetail>>(ENDPOINTS.OFFICES.GET(id), {
    tags: [OFFICES_TAG],
  });
}

export async function createOffice(
  input: unknown,
): Promise<MutationResult<ApiSingle<OfficeDetail>>> {
  const parsed = officeCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<OfficeDetail>>(
      ENDPOINTS.OFFICES.CREATE,
      parsed.data,
    );
    revalidateTag(OFFICES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateOffice(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<OfficeDetail>>> {
  const parsed = officeUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<OfficeDetail>>(
      ENDPOINTS.OFFICES.UPDATE(id), // ← PUT, not PATCH
      parsed.data, // vertical_ids (when present) is a full replace of office_vertical
    );
    revalidateTag(OFFICES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteOffice(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.OFFICES.DELETE(id));
    revalidateTag(OFFICES_TAG, "max");
    return { ok: true };
  } catch (e) {
    // Offices have no domain children, so no 409 guard — but surface any error.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
