"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  appointmentStatusCreateSchema,
  appointmentStatusUpdateSchema,
  transitionTargetsSchema,
} from "@/lib/schemas/appointment-status.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { QueryRequest } from "@/types/query.types";
import type {
  AppointmentStatusItem,
  AppointmentStatusOption,
  TransitionTargets,
} from "@/types/scheduling.types";

import type { MutationResult } from "./user.actions";

const TAG = "scheduling:appointment-statuses";

export async function listAppointmentStatuses(
  query: QueryRequest,
): Promise<ApiPaginated<AppointmentStatusItem>> {
  return backendClient.post<ApiPaginated<AppointmentStatusItem>>(
    ENDPOINTS.APPOINTMENT_STATUSES.LIST,
    query,
    { tags: [TAG] },
  );
}

export async function listActiveAppointmentStatuses(): Promise<AppointmentStatusOption[]> {
  // Lista CRUDA. La consumen el editor de matriz y los dropdowns de estado.
  return backendClient.get<AppointmentStatusOption[]>(ENDPOINTS.APPOINTMENT_STATUSES.ACTIVE, {
    tags: [TAG],
  });
}

export async function createAppointmentStatus(
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentStatusItem>>> {
  const parsed = appointmentStatusCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<AppointmentStatusItem>>(
      ENDPOINTS.APPOINTMENT_STATUSES.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 MULTIPLE_INITIAL_STATUS / 409 APPOINTMENT_STATUS_CODE_TAKEN en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateAppointmentStatus(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentStatusItem>>> {
  const parsed = appointmentStatusUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<AppointmentStatusItem>>(
      ENDPOINTS.APPOINTMENT_STATUSES.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteAppointmentStatus(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.APPOINTMENT_STATUSES.DELETE(id));
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 APPOINTMENT_STATUS_IN_USE si hay citas en este estado (F2).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Matriz de transiciones ──────────────────────────────

export async function getAppointmentTransitions(id: string): Promise<TransitionTargets> {
  // GET devuelve SingleResponse[TransitionTargets] → se lee `.data`.
  const res = await backendClient.get<ApiSingle<TransitionTargets>>(
    ENDPOINTS.APPOINTMENT_STATUSES.TRANSITIONS(id),
    { tags: [TAG] },
  );
  return res.data;
}

export async function setAppointmentTransitions(
  id: string,
  input: unknown, // { to_ids: [...] } — reemplaza las aristas de salida
): Promise<MutationResult<ApiSingle<TransitionTargets>>> {
  const parsed = transitionTargetsSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<TransitionTargets>>(
      ENDPOINTS.APPOINTMENT_STATUSES.TRANSITIONS(id), // ← PUT (reemplaza)
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
