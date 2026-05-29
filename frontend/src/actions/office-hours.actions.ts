"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { officeHoursReplaceSchema } from "@/lib/schemas/office-hours.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { OfficeOperatingHoursRow } from "@/types/clinic.types";
import type { MutationResult } from "./user.actions";

const HOURS_TAG = "clinic:office-hours";

export async function listOfficeHours(officeId: string): Promise<OfficeOperatingHoursRow[]> {
  // GET returns a SingleResponse envelope ({success, data:[...]}), one row per
  // block (ordered day → opens_at). Read `data`.
  const res = await backendClient.get<ApiSingle<OfficeOperatingHoursRow[]>>(
    ENDPOINTS.OFFICES.OPERATING_HOURS(officeId),
    { tags: [HOURS_TAG, `clinic:office-hours:${officeId}`] },
  );
  return res.data;
}

// Bulk atomic replace — the ENTIRE weekly pattern is sent and replaces what
// exists. There is no per-row create/update/delete (mirrors the backend).
export async function replaceOfficeHours(
  officeId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<OfficeOperatingHoursRow[]>>> {
  const parsed = officeHoursReplaceSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<OfficeOperatingHoursRow[]>>(
      ENDPOINTS.OFFICES.OPERATING_HOURS(officeId), // ← PUT bulk
      parsed.data, // { hours: [...] }
    );
    // Per-office tag: one office's pattern is independent of another's.
    revalidateTag(`clinic:office-hours:${officeId}`, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
