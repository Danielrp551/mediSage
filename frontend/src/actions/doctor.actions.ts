"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { doctorCreateSchema, doctorUpdateSchema } from "@/lib/schemas/doctor.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { QueryRequest } from "@/types/query.types";
import type {
  DoctorCreatedResponse,
  DoctorDetail,
  DoctorItem,
  DoctorOption,
} from "@/types/staff.types";

import type { MutationResult } from "./user.actions";

const DOCTORS_TAG = "staff:doctors";

export async function listDoctors(query: QueryRequest): Promise<ApiPaginated<DoctorItem>> {
  return backendClient.post<ApiPaginated<DoctorItem>>(ENDPOINTS.DOCTORS.LIST, query, {
    tags: [DOCTORS_TAG],
  });
}

export async function listActiveDoctors(
  branchId?: string,
  verticalId?: string,
): Promise<DoctorOption[]> {
  const params = new URLSearchParams();
  if (branchId) params.set("branch_id", branchId);
  if (verticalId) params.set("vertical_id", verticalId);
  const qs = params.toString();
  const url = qs ? `${ENDPOINTS.DOCTORS.ACTIVE}?${qs}` : ENDPOINTS.DOCTORS.ACTIVE;
  // `/active` devuelve una lista CRUDA (response_model=list[...]) — sin envelope.
  return backendClient.get<DoctorOption[]>(url, { tags: [DOCTORS_TAG] });
}

export async function getDoctor(id: string): Promise<ApiSingle<DoctorDetail>> {
  // DoctorDetail incluye user (UserAuditInfo), branches (BranchOption[]) y
  // verticals (VerticalOption[]); soft-deleted filtradas server-side.
  return backendClient.get<ApiSingle<DoctorDetail>>(ENDPOINTS.DOCTORS.GET(id), {
    tags: [DOCTORS_TAG],
  });
}

export async function createDoctor(input: unknown): Promise<MutationResult<DoctorCreatedResponse>> {
  const parsed = doctorCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    // El POST devuelve { data: DoctorDetail, generated_password } (NO envelope
    // SingleResponse plano: espeja UserCreatedResponse).
    const data = await backendClient.post<DoctorCreatedResponse>(
      ENDPOINTS.DOCTORS.CREATE,
      parsed.data,
    );
    revalidateTag(DOCTORS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 EMAIL_TAKEN (email del user ya existe) y 400 (branch/vertical
    // inexistente o muerto) llegan aquí como e.message en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateDoctor(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<DoctorDetail>>> {
  const parsed = doctorUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<DoctorDetail>>(
      ENDPOINTS.DOCTORS.UPDATE(id), // ← PUT, not PATCH
      parsed.data, // branch_ids/vertical_ids (when present) = full replace
    );
    revalidateTag(DOCTORS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteDoctor(id: string): Promise<MutationResult<null>> {
  try {
    // Soft delete del Doctor; NO borra ni desactiva el User (ADR-002).
    await backendClient.delete(ENDPOINTS.DOCTORS.DELETE(id));
    revalidateTag(DOCTORS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
