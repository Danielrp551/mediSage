"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { officeClosureCreateSchema } from "@/lib/schemas/office-closure.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { OfficeClosureItem } from "@/types/clinic.types";
import type { MutationResult } from "./user.actions";

const CLOSURES_TAG = "clinic:office-closures";

export async function listClosures(
  officeId: string,
  from?: string,
  to?: string,
): Promise<OfficeClosureItem[]> {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  const base = ENDPOINTS.OFFICES.CLOSURES(officeId);
  const url = qs ? `${base}?${qs}` : base;
  // GET returns a SingleResponse envelope ({success, data:[...]}). Read `data`.
  const res = await backendClient.get<ApiSingle<OfficeClosureItem[]>>(url, {
    tags: [CLOSURES_TAG, `clinic:office-closures:${officeId}`],
  });
  return res.data;
}

export async function createClosure(
  officeId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<OfficeClosureItem>>> {
  const parsed = officeClosureCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    // The datetime-local strings are converted to ISO 8601 with offset before
    // sending so the backend stores correct timestamptz instants.
    const payload = {
      ...parsed.data,
      starts_at: new Date(parsed.data.starts_at).toISOString(),
      ends_at: new Date(parsed.data.ends_at).toISOString(),
    };
    const data = await backendClient.post<ApiSingle<OfficeClosureItem>>(
      ENDPOINTS.OFFICES.CLOSURES(officeId),
      payload,
    );
    revalidateTag(`clinic:office-closures:${officeId}`, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteClosure(
  officeId: string,
  closureId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.OFFICES.CLOSURE(officeId, closureId));
    revalidateTag(`clinic:office-closures:${officeId}`, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
