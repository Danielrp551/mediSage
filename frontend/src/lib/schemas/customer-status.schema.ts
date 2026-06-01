import { z } from "zod";

// Idéntico a `lead-status.schema.ts` menos `is_won` (CustomerStatus no lo tiene) y
// sin el refine `is_won ⟹ is_final`. `transitionTargetsSchema` se reusa desde
// lead-status (no se duplica).
const CODE_SLUG_REGEX = /^[A-Z][A-Z0-9_]*$/;
const HEX_COLOR_REGEX = /^#([0-9a-fA-F]{6})$/;

const customerStatusBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500).nullable().optional(),
  color: z
    .string()
    .regex(HEX_COLOR_REGEX, "Color hex como #RRGGBB")
    .nullable()
    .optional()
    .or(z.literal("")),
  is_initial: z.boolean().optional().default(false),
  is_final: z.boolean().optional().default(false),
  display_order: z.number({ invalid_type_error: "Número entero" }).int().min(0).default(0),
});

export const customerStatusCreateSchema = customerStatusBase.extend({
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(40)
    .regex(CODE_SLUG_REGEX, "Mayúsculas, números y guiones bajos"),
});

export const customerStatusUpdateSchema = customerStatusBase
  .partial()
  .extend({ active: z.boolean().optional() });

export type CustomerStatusCreateInput = z.infer<typeof customerStatusCreateSchema>;
export type CustomerStatusUpdateInput = z.infer<typeof customerStatusUpdateSchema>;
