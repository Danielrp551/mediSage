/**
 * Zod de Promotion — compartido por el form (cliente) y el Server Action (servidor).
 *
 * El descuento es DISCRIMINADO por discount_type, pero NO se usa z.discriminatedUnion
 * (el update aplica .partial() y omite discount_type, que es inmutable; discriminatedUnion
 * exige el discriminante presente). Patrón: base + `refineDiscount` aplicado con
 * `.superRefine()` a create Y update (mold crm `refineWonRequiresFinal`). En el update, el
 * discount_type se inyecta como `_discount_type` efímero (lo conoce el form de la fila
 * existente) sólo para el refine; el action lo descarta antes del PUT.
 *
 * ⚠ Server-safe: NO importa `marketing.ts` (que importa `tokens` de Fluent) para no
 * arrastrar la librería de cliente al grafo del Server Action → los enums van inline.
 * Mantener las monedas en sync con SUPPORTED_CURRENCIES de `lib/constants/marketing.ts`.
 */

import { z } from "zod";

// code = slug MINÚSCULAS (patrón catalog), inmutable post-create.
const CODE_SLUG_REGEX = /^[a-z][a-z0-9_]{1,38}[a-z0-9]$/;
// discount_value como monto fijo = decimal-string con ≤2 decimales (espeja Numeric(10,2)).
const DECIMAL_2_REGEX = /^\d+(\.\d{1,2})?$/;

const promotionBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  currency: z.enum(["PEN", "USD", "EUR"]).optional(), // sync con SUPPORTED_CURRENCIES (marketing.ts)
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD"),
  end_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD")
    .nullable()
    .optional()
    .or(z.literal("")),
  max_uses_total: z
    .number({ invalid_type_error: "Número entero" })
    .int("Entero")
    .min(1, "Mínimo 1")
    .nullable()
    .optional(),
  max_uses_per_person: z
    .number({ invalid_type_error: "Número entero" })
    .int("Entero")
    .min(1, "Mínimo 1")
    .nullable()
    .optional(),
  applies_to_all_products: z.boolean().optional().default(false),
  // discount_value viaja como string (Decimal). El form lo arma según discount_type.
  discount_value: z.string().min(1, "Obligatorio"),
});

// percentage → número 0<v<=100; fixed_amount → decimal-string >0 + currency obligatoria.
function refineDiscount(
  data: {
    discount_type?: "percentage" | "fixed_amount";
    discount_value?: string;
    currency?: string;
  },
  ctx: z.RefinementCtx,
) {
  if (!data.discount_value) return; // opcional en update; si ausente, no refinar
  const raw = data.discount_value.trim();
  if (data.discount_type === "percentage") {
    const n = Number(raw);
    // ≤2 decimales (espeja Numeric(10,2)/decimal_places=2 del backend): sin esto, '33.333'
    // pasa el Zod y el backend lo rechaza con un 422 de Pydantic ilegible (review F2 minor).
    if (!DECIMAL_2_REGEX.test(raw) || !Number.isFinite(n) || n <= 0 || n > 100) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["discount_value"],
        message: "El porcentaje debe ser mayor que 0, máximo 100 y con hasta 2 decimales.",
      });
    }
  } else if (data.discount_type === "fixed_amount") {
    if (!DECIMAL_2_REGEX.test(raw) || Number(raw) <= 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["discount_value"],
        message: "El monto debe ser mayor que 0 (hasta 2 decimales).",
      });
    }
    if (!data.currency) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["currency"],
        message: "Elige la moneda del descuento fijo.",
      });
    }
  }
}

export const promotionCreateSchema = promotionBase
  .extend({
    code: z
      .string()
      .min(2, "Mínimo 2 caracteres")
      .max(40, "Máximo 40 caracteres")
      .regex(CODE_SLUG_REGEX, "Minúsculas, números y guion bajo (ej. dscto_10)"),
    discount_type: z.enum(["percentage", "fixed_amount"]),
  })
  .superRefine((data, ctx) => refineDiscount(data, ctx));

// Update: discount_type INMUTABLE (no va en el body). discount_value opcional. El form
// inyecta `_discount_type` (de la fila existente) sólo para el refine; el action lo descarta.
export const promotionUpdateSchema = promotionBase
  .partial()
  .extend({
    active: z.boolean().optional(),
    _discount_type: z.enum(["percentage", "fixed_amount"]).optional(), // efímero, sólo refine
  })
  .superRefine((data, ctx) =>
    refineDiscount(
      {
        discount_type: data._discount_type,
        discount_value: data.discount_value,
        currency: data.currency,
      },
      ctx,
    ),
  );

// Body de PUT /promotions/{id}/products (reemplaza el set completo del M:N).
export const promotionProductsReplaceSchema = z.object({
  product_ids: z.array(z.string()),
});

export type PromotionCreateInput = z.infer<typeof promotionCreateSchema>;
export type PromotionUpdateInput = z.infer<typeof promotionUpdateSchema>;
export type PromotionProductsReplaceInput = z.infer<typeof promotionProductsReplaceSchema>;
