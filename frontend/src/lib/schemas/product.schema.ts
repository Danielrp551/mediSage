import { z } from "zod";

import { CODE_SLUG_60_REGEX } from "./vertical.schema";

export const SUPPORTED_CURRENCIES = ["PEN", "USD", "EUR"] as const;
export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number];

const codeField = z
  .string()
  .min(3, "Mínimo 3 caracteres")
  .max(60, "Máximo 60 caracteres")
  .regex(
    CODE_SLUG_60_REGEX,
    "Slug en minúsculas: letras, dígitos, '_'. Empieza con letra, termina con letra o dígito.",
  );

// Pricing is a numeric string to align with the backend's Decimal-as-string
// wire format. Allow `350`, `350.4`, `350.45`; reject 3+ decimals.
const priceField = z
  .string()
  .regex(/^\d+(\.\d{1,2})?$/, "Usa un número como 350 o 350.00")
  .refine((s) => parseFloat(s) >= 0, "El precio debe ser ≥ 0")
  .refine((s) => parseFloat(s) < 10_000_000, "Máximo 9,999,999.99");

const productBase = z.object({
  name: z.string().min(1, "Obligatorio").max(160, "Máximo 160 caracteres"),
  description: z.string().max(1000, "Máximo 1000 caracteres").nullable().optional(),
  base_price: priceField,
  currency: z.enum(SUPPORTED_CURRENCIES).default("PEN"),
  duration_min: z
    .number()
    .int()
    .min(1, "Mínimo 1 minuto")
    .max(24 * 60, "Máximo 1440 minutos")
    .nullable()
    .optional(),
  requires_appointment: z.boolean().default(true),
  is_package: z.boolean().default(false),
  min_hours_to_cancel: z
    .number()
    .int()
    .min(0)
    .max(24 * 7, "Máximo 168 horas")
    .nullable()
    .optional(),
});

// Cross-field rule, mirrors the backend ProductCreate model_validator: a
// bookable product with a cancellation deadline needs a duration.
function refineCancelRules<
  T extends {
    requires_appointment?: boolean;
    duration_min?: number | null;
    min_hours_to_cancel?: number | null;
  },
>(data: T, ctx: z.RefinementCtx): void {
  if (
    data.requires_appointment !== false &&
    (data.min_hours_to_cancel ?? null) !== null &&
    (data.duration_min ?? null) === null
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["duration_min"],
      message:
        "La duración es obligatoria cuando el producto es agendable y tiene plazo de cancelación.",
    });
  }
}

export const productCreateSchema = productBase
  .extend({
    service_id: z.string().min(1, "Elige un servicio"),
    code: codeField,
  })
  .superRefine(refineCancelRules);

export const productUpdateSchema = productBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineCancelRules);

export type ProductCreateInput = z.infer<typeof productCreateSchema>;
export type ProductUpdateInput = z.infer<typeof productUpdateSchema>;
