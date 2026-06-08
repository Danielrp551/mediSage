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
