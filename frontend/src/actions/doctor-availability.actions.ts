"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  doctorAvailabilityBulkSchema,
  doctorAvailabilityUpdateSchema,
} from "@/lib/schemas/doctor-availability.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import type { MutationResult } from "./user.actions";

const DOCTORS_TAG = "staff:doctors";
const availabilityTag = (doctorId: string) => `staff:availability:${doctorId}`;

// El backend acepta "HH:MM" o "HH:MM:SS"; el contrato pide enviar "HH:MM:SS". El
// form trabaja en "HH:MM", así que normalizamos agregando ":00" cuando falta.
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

// GET ?from=&to= (inclusive sobre `date`) → SingleResponse<Item[]> → se lee `.data`.
// `from`/`to` son "YYYY-MM-DD"; la grilla manda siempre el rango de la semana visible.
export async function listDoctorAvailability(
  doctorId: string,
  from?: string,
  to?: string,
): Promise<DoctorAvailabilityItem[]> {
  const res = await backendClient.get<ApiSingle<DoctorAvailabilityItem[]>>(
    `${ENDPOINTS.DOCTORS.AVAILABILITY_LIST(doctorId)}${rangeQs(from, to)}`,
    { tags: [DOCTORS_TAG, availabilityTag(doctorId)] },
  );
  return res.data;
}

// POST bulk: body { blocks: [...] }. La transacción es todo-o-nada en el backend.
// 201 → SingleResponse<Item[]> (los bloques creados).
export async function createDoctorAvailability(
  doctorId: string,
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
      ENDPOINTS.DOCTORS.AVAILABILITY_CREATE(doctorId),
      body,
    );
    revalidateTag(DOCTORS_TAG, "max");
    revalidateTag(availabilityTag(doctorId), "max");
    return { ok: true, data: res.data };
  } catch (e) {
    // 400 AVAILABILITY_OVERLAP / OFFICE_NOT_IN_BRANCH / DOCTOR_NOT_IN_BRANCH en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// PUT /{blockId}: body DoctorAvailabilityUpdatePayload (todo opcional) → SingleResponse<Item>.
export async function updateDoctorAvailability(
  doctorId: string,
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
      ENDPOINTS.DOCTORS.AVAILABILITY_UPDATE(doctorId, blockId),
      body,
    );
    revalidateTag(DOCTORS_TAG, "max");
    revalidateTag(availabilityTag(doctorId), "max");
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// DELETE /{blockId} → 204.
export async function deleteDoctorAvailability(
  doctorId: string,
  blockId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.DOCTORS.AVAILABILITY_DELETE(doctorId, blockId));
    revalidateTag(DOCTORS_TAG, "max");
    revalidateTag(availabilityTag(doctorId), "max");
    return { ok: true };
  } catch (e) {
    // 404 AVAILABILITY_NOT_FOUND si el bloque no existe o no es del doctor (ownership).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
