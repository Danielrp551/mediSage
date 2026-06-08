"use server";

import { revalidateTag } from "next/cache";

import { appointmentCreateSchema } from "@/lib/schemas/appointment.schema";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { QueryRequest } from "@/types/query.types";
import type {
  AppointmentDetail,
  AppointmentItem,
  AvailabilityRequest,
  AvailabilityResponse,
} from "@/types/scheduling.types";

import type { MutationResult } from "./user.actions";

const TAG = "scheduling:appointments";

export async function listAppointments(
  query: QueryRequest,
): Promise<ApiPaginated<AppointmentItem>> {
  return backendClient.post<ApiPaginated<AppointmentItem>>(ENDPOINTS.APPOINTMENTS.LIST, query, {
    tags: [TAG],
  });
}

export async function getAppointment(id: string): Promise<AppointmentDetail> {
  // GET devuelve SingleResponse[AppointmentDetail] (+ status_history + change_log) → `.data`.
  const res = await backendClient.get<ApiSingle<AppointmentDetail>>(
    ENDPOINTS.APPOINTMENTS.GET(id),
    {
      tags: [TAG],
    },
  );
  return res.data;
}

export async function createAppointment(
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  // notes "" → null (el campo es opcional); `source`/`branch_id`/`duration_min` los
  // resuelve el backend (source default=advisor; branch de office; duration de product).
  const notes = parsed.data.notes?.trim() ? parsed.data.notes : null;
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.CREATE,
      { ...parsed.data, notes },
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 de un invariante (SLOT_TAKEN/OFFICE_SLOT_TAKEN/DOCTOR_INACTIVE/…) en español;
    // el wizard lo muestra y permite recomputar la disponibilidad.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function computeAvailability(
  input: AvailabilityRequest,
): Promise<AvailabilityResponse> {
  // POST /availability/compute → SingleResponse[AvailabilityResponse] → `.data`.
  // NO se cachea (cómputo on-the-fly, cambia con cada reserva). Sin tags → no-store.
  const res = await backendClient.post<ApiSingle<AvailabilityResponse>>(
    ENDPOINTS.AVAILABILITY.COMPUTE,
    input,
  );
  return res.data;
}
