import { z } from "zod";

// Body de POST /appointments (book) — lo arma el wizard al confirmar el slot.
// `branch_id` lo DERIVA el backend de office; `duration_min` lo COPIA de product;
// `status_id` nace en el is_initial; `source` lo fija la action (default "advisor").
// Todos los ids son UUID requeridos; `scheduled_for` es el ISO 8601 UTC del slot
// elegido (lo produce el paso de disponibilidad). Espeja AppointmentCreatePayload.
export const appointmentCreateSchema = z.object({
  person_id: z.string().min(1, "Selecciona un contacto"),
  doctor_id: z.string().min(1, "Selecciona un doctor"),
  office_id: z.string().min(1, "Selecciona un consultorio"),
  product_id: z.string().min(1, "Selecciona un producto"),
  scheduled_for: z.string().min(1, "Selecciona un horario disponible"),
  notes: z.string().max(2000, "Máximo 2000 caracteres").nullable().optional().or(z.literal("")),
});

export type AppointmentCreateInput = z.infer<typeof appointmentCreateSchema>;

// Body de POST /appointments/{id}/cancel — `cancellation_reason` es opcional (max 255 en
// el backend). El override de min_hours_to_cancel es por PERMISO (APPOINTMENTS_CANCEL_OVERRIDE),
// NO un flag del body; el backend responde CANCEL_TOO_LATE (400) si el actor no lo tiene.
export const appointmentCancelSchema = z.object({
  cancellation_reason: z
    .string()
    .max(255, "Máximo 255 caracteres")
    .nullable()
    .optional()
    .or(z.literal("")),
});

export type AppointmentCancelInput = z.infer<typeof appointmentCancelSchema>;

// Body de POST /appointments/{id}/reschedule — `scheduled_for` es el ISO 8601 UTC del
// nuevo slot (lo produce el AvailabilityPicker). doctor_id/office_id opcionales = el
// backend reusa los de la cita vieja si no se mandan. El backend marca la vieja
// RESCHEDULED y crea la NUEVA con previous_appointment_id (misma tx).
export const appointmentRescheduleSchema = z.object({
  scheduled_for: z.string().min(1, "Selecciona un horario disponible"),
  doctor_id: z.string().optional(),
  office_id: z.string().optional(),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional().or(z.literal("")),
});

export type AppointmentRescheduleInput = z.infer<typeof appointmentRescheduleSchema>;

// Body de PUT /appointments/{id} — SOLO columnas no-estado (→ change_log). scheduled_for
// NO se edita aquí (usa /reschedule); status_id tampoco (usa /transition o shortcuts).
// branch_id/duration_min los re-deriva el backend si cambia office/product. `reason` se
// escribe en change_log.reason (max 255 en el backend).
export const appointmentUpdateSchema = z.object({
  doctor_id: z.string().optional(),
  office_id: z.string().optional(),
  product_id: z.string().optional(),
  notes: z.string().max(2000, "Máximo 2000 caracteres").nullable().optional().or(z.literal("")),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional().or(z.literal("")),
});

export type AppointmentUpdateInput = z.infer<typeof appointmentUpdateSchema>;
