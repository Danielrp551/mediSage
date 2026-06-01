import { z } from "zod";

// code = slug estable en MAYÚSCULAS (ej. NUEVO, NO_INTERESADO). Inmutable post-create
// idealmente; el update no lo incluye (espeja el backend, que no permite renombrar code).
const CODE_SLUG_REGEX = /^[A-Z][A-Z0-9_]*$/;
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{6})$/;

const leadStatusBase = z.object({
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
  is_won: z.boolean().optional().default(false),
  display_order: z.number({ invalid_type_error: "Número entero" }).int("Entero").min(0).default(0),
});

function refineWonRequiresFinal(
  data: { is_won?: boolean; is_final?: boolean },
  ctx: z.RefinementCtx,
) {
  if (data.is_won && !data.is_final) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["is_won"],
      message: "Un estado ganado debe ser también final.",
    });
  }
}

export const leadStatusCreateSchema = leadStatusBase
  .extend({
    code: z
      .string()
      .min(1, "Obligatorio")
      .max(40, "Máximo 40 caracteres")
      .regex(CODE_SLUG_REGEX, "Mayúsculas, números y guiones bajos (ej. NUEVO)"),
  })
  .superRefine(refineWonRequiresFinal);

export const leadStatusUpdateSchema = leadStatusBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineWonRequiresFinal);

// Body de PUT /lead-statuses/{id}/transitions (reemplaza aristas de salida).
export const transitionTargetsSchema = z.object({
  to_ids: z.array(z.string()),
});

export type LeadStatusCreateInput = z.infer<typeof leadStatusCreateSchema>;
export type LeadStatusUpdateInput = z.infer<typeof leadStatusUpdateSchema>;
export type TransitionTargetsInput = z.infer<typeof transitionTargetsSchema>;
