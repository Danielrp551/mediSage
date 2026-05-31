"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { doctorSelfUpdateSchema } from "@/lib/schemas/doctor.schema";
import {
  doctorAvailabilityBulkSchema,
  doctorAvailabilityUpdateSchema,
} from "@/lib/schemas/doctor-availability.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { DoctorAvailabilityItem, DoctorDetail } from "@/types/staff.types";

import type { MutationResult } from "./user.actions";

// Cache tags del self-service. Separados de `staff:doctors` (la lista admin) — el
// doctor no ve esa lista; revalidar la suya no debe invalidar la del admin.
const ME_TAG = "staff:me";
const ME_AVAILABILITY_TAG = "staff:me:availability";

// El backend acepta "HH:MM" o "HH:MM:SS"; el contrato pide enviar "HH:MM:SS". El
// form trabaja en "HH:MM", así que normalizamos agregando ":00" cuando falta
// (mismo helper que doctor-availability.actions.ts).
function toHms(time: string): string {
  return time.length === 5 ? `${time}:00` : time;
}

function rangeQs(from?: string, to?: string): string {
  const p = new URLSearchParams();
  if (from) p.set("from", from);
  if (to) p.set("to", to);
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

// GET /me/doctor → SingleResponse<DoctorDetail>. El backend resuelve el doctor
// desde el token; si el user no tiene perfil devuelve 403 NOT_A_DOCTOR (se deja
// propagar — el RSC lo captura para mostrar el estado vacío).
export async function getMyDoctor(): Promise<ApiSingle<DoctorDetail>> {
  return backendClient.get<ApiSingle<DoctorDetail>>(ENDPOINTS.ME.DOCTOR_GET, { tags: [ME_TAG] });
}

// PUT /me/doctor → SingleResponse<DoctorDetail>. Body = subset self-service
// (cmp_code/bio/photo_url/signature_url/slot_duration_min). NO se envían
// branch_ids/vertical_ids/active (el schema no los tiene).
export async function updateMyDoctor(
  input: unknown,
): Promise<MutationResult<ApiSingle<DoctorDetail>>> {
  const parsed = doctorSelfUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<DoctorDetail>>(
      ENDPOINTS.ME.DOCTOR_UPDATE, // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(ME_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 403 NOT_A_DOCTOR llega aquí como e.message en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// GET /me/availability?from=&to= → SingleResponse<Item[]> → se lee `.data`.
// `from`/`to` son "YYYY-MM-DD"; la grilla manda siempre el rango de la semana visible.
export async function listMyAvailability(
  from?: string,
  to?: string,
): Promise<DoctorAvailabilityItem[]> {
  const res = await backendClient.get<ApiSingle<DoctorAvailabilityItem[]>>(
    `${ENDPOINTS.ME.AVAILABILITY_LIST}${rangeQs(from, to)}`,
    { tags: [ME_TAG, ME_AVAILABILITY_TAG] },
  );
  return res.data;
}

// POST bulk: body { blocks: [...] }. Transacción todo-o-nada en el backend.
// 201 → SingleResponse<Item[]> (los bloques creados). El doctor sale del token.
export async function createMyAvailability(
  input: unknown,
): Promise<MutationResult<DoctorAvailabilityItem[]>> {
  const parsed = doctorAvailabilityBulkSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  const body = {
    blocks: parsed.data.blocks.map((b) => ({
      ...b,
      opens_at: toHms(b.opens_at),
      closes_at: toHms(b.closes_at),
    })),
  };
  try {
    const res = await backendClient.post<ApiSingle<DoctorAvailabilityItem[]>>(
      ENDPOINTS.ME.AVAILABILITY_CREATE,
      body,
    );
    revalidateTag(ME_TAG, "max");
    revalidateTag(ME_AVAILABILITY_TAG, "max");
    return { ok: true, data: res.data };
  } catch (e) {
    // 400 AVAILABILITY_OVERLAP / OFFICE_NOT_IN_BRANCH / DOCTOR_NOT_IN_BRANCH en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// PUT /me/availability/{blockId}: body DoctorAvailabilityUpdatePayload (todo
// opcional) → SingleResponse<Item>.
export async function updateMyAvailability(
  blockId: string,
  input: unknown,
): Promise<MutationResult<DoctorAvailabilityItem>> {
  const parsed = doctorAvailabilityUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  const body: Record<string, string> = { ...parsed.data };
  if (parsed.data.opens_at) body.opens_at = toHms(parsed.data.opens_at);
  if (parsed.data.closes_at) body.closes_at = toHms(parsed.data.closes_at);
  try {
    const res = await backendClient.put<ApiSingle<DoctorAvailabilityItem>>(
      ENDPOINTS.ME.AVAILABILITY_UPDATE(blockId),
      body,
    );
    revalidateTag(ME_TAG, "max");
    revalidateTag(ME_AVAILABILITY_TAG, "max");
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// DELETE /me/availability/{blockId} → 204.
export async function deleteMyAvailability(blockId: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.ME.AVAILABILITY_DELETE(blockId));
    revalidateTag(ME_TAG, "max");
    revalidateTag(ME_AVAILABILITY_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 404 AVAILABILITY_NOT_FOUND si el bloque no existe o no es del doctor (ownership).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
