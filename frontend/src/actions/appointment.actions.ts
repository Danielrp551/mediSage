"use server";

import { revalidateTag } from "next/cache";

import {
  appointmentCancelSchema,
  appointmentCreateSchema,
  appointmentRescheduleSchema,
  appointmentUpdateSchema,
} from "@/lib/schemas/appointment.schema";
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

// ── Ciclo de vida (F3b) ──────────────────────────────────────────────────────
// DECISIÓN F3a (NO re-litigar): usar los SHORTCUTS nombrados (/confirm, /check-in,
// /start, /attend, /no-show, /cancel, /reschedule), NUNCA el /transition genérico —
// los side-effects ricos (cancel→guard min_hours; attend→promote a cliente +
// LeadActivity) viven SOLO en los shortcuts. La matriz (getAppointmentTransitions)
// decide qué botón mostrar. Todas devuelven la cita actualizada y revalidan el tag.

// Helper interno (NO exportado → no es un server action): POST a un shortcut sin body.
// FastAPI ignora el body en los shortcuts (no declaran request schema).
async function postShortcut(
  endpoint: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(endpoint);
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 de la matriz (APPOINTMENT_TRANSITION_NOT_ALLOWED) o 409 del attend
    // (NO_INITIAL_CUSTOMER_STATUS) → mensaje del backend en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function confirmAppointment(
  id: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  return postShortcut(ENDPOINTS.APPOINTMENTS.CONFIRM(id));
}

export async function checkInAppointment(
  id: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  return postShortcut(ENDPOINTS.APPOINTMENTS.CHECK_IN(id));
}

export async function startAppointment(
  id: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  return postShortcut(ENDPOINTS.APPOINTMENTS.START(id));
}

// /attend → ATTENDED + promote_to_customer ATÓMICO (misma tx) + LeadActivity. En prod
// no falla (crm tiene estados-cliente seeded); si NO_INITIAL_CUSTOMER_STATUS, el backend
// revierte la atención entera y responde 409.
export async function attendAppointment(
  id: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  return postShortcut(ENDPOINTS.APPOINTMENTS.ATTEND(id));
}

export async function noShowAppointment(
  id: string,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  return postShortcut(ENDPOINTS.APPOINTMENTS.NO_SHOW(id));
}

// POST /appointments/{id}/cancel. El override de min_hours_to_cancel es por PERMISO
// (server-side): si el actor no tiene APPOINTMENTS_CANCEL_OVERRIDE y la cita está dentro
// de product.min_hours_to_cancel, el backend responde CANCEL_TOO_LATE (400).
export async function cancelAppointment(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentCancelSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  const cancellation_reason = parsed.data.cancellation_reason?.trim()
    ? parsed.data.cancellation_reason
    : null;
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.CANCEL(id),
      { cancellation_reason },
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// POST /appointments/{id}/reschedule. doctor_id/office_id se OMITEN si no se mandan (el
// backend reusa los de la cita vieja). Devuelve la cita NUEVA (la vieja queda RESCHEDULED,
// misma tx). Puede fallar con SLOT_TAKEN/invariantes 1-8 (el backend los revalida).
export async function rescheduleAppointment(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentRescheduleSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  const reason = parsed.data.reason?.trim() ? parsed.data.reason : null;
  const body: Record<string, unknown> = { scheduled_for: parsed.data.scheduled_for, reason };
  if (parsed.data.doctor_id) body.doctor_id = parsed.data.doctor_id;
  if (parsed.data.office_id) body.office_id = parsed.data.office_id;
  try {
    const data = await backendClient.post<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.RESCHEDULE(id),
      body,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// PUT /appointments/{id} — SOLO columnas no-estado (→ change_log). El backend re-deriva
// branch_id/duration_min si cambia office/product y revalida invariantes 1-8 (puede dar
// SLOT_TAKEN/DOCTOR_NOT_IN_BRANCH/…). `notes` se manda siempre (""→null limpia la nota).
export async function updateAppointment(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<AppointmentDetail>>> {
  const parsed = appointmentUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  const reason = parsed.data.reason?.trim() ? parsed.data.reason : null;
  const body: Record<string, unknown> = {
    notes: parsed.data.notes?.trim() ? parsed.data.notes : null,
    reason,
  };
  if (parsed.data.doctor_id) body.doctor_id = parsed.data.doctor_id;
  if (parsed.data.office_id) body.office_id = parsed.data.office_id;
  if (parsed.data.product_id) body.product_id = parsed.data.product_id;
  try {
    const data = await backendClient.put<ApiSingle<AppointmentDetail>>(
      ENDPOINTS.APPOINTMENTS.UPDATE(id),
      body,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
