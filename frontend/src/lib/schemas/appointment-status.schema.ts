import { z } from "zod";

// code = slug estable en MAYÚSCULAS (ej. SCHEDULED, NO_SHOW). Inmutable post-create;
// el update no lo incluye (espeja el backend, que no permite renombrar code). El
// backend NO valida el pattern (igual que crm.LeadStatus); el casing se impone acá.
const CODE_SLUG_REGEX = /^[A-Z][A-Z0-9_]*$/;
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{6})$/;

const appointmentStatusBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  color: z
    .string()
    .regex(HEX_COLOR_REGEX, "Color hex como #RRGGBB")
    .nullable()
    .optional()
    .or(z.literal("")),
  is_initial: z.boolean().optional().default(false),
  is_final: z.boolean().optional().default(false),
  is_active_attention: z.boolean().optional().default(false),
  display_order: z.number({ invalid_type_error: "Número entero" }).int("Entero").min(0).default(0),
});

export const appointmentStatusCreateSchema = appointmentStatusBase.extend({
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(40, "Máximo 40 caracteres")
    .regex(CODE_SLUG_REGEX, "Mayúsculas, números y guiones bajos (ej. SCHEDULED)"),
});

export const appointmentStatusUpdateSchema = appointmentStatusBase
  .partial()
  .extend({ active: z.boolean().optional() });

// Body de PUT /appointment-statuses/{id}/transitions (reemplaza aristas de salida).
export const transitionTargetsSchema = z.object({
  to_ids: z.array(z.string()),
});

export type AppointmentStatusCreateInput = z.infer<typeof appointmentStatusCreateSchema>;
export type AppointmentStatusUpdateInput = z.infer<typeof appointmentStatusUpdateSchema>;
export type TransitionTargetsInput = z.infer<typeof transitionTargetsSchema>;
