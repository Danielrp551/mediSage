import { z } from "zod";

/**
 * Schemas de validación/aplicación de promociones. Los importan tanto el form/caller
 * (cliente) como el Server Action (server) → drift imposible. En el MVP la página de usos
 * es read-only; `applyPromotion` la dispara scheduling (F4) / el bot, no un form de marketing.
 * Mensajes visibles en español.
 */

// Body de POST /promotion-usages (crea PromotionUsage). Ids como string.
export const applyPromotionSchema = z.object({
  promotion_id: z.string().min(1, "La promoción es obligatoria."),
  person_id: z.string().min(1, "La persona es obligatoria."),
  product_id: z.string().min(1, "El producto es obligatorio."),
  appointment_id: z.string().nullable().optional(),
  campaign_id: z.string().nullable().optional(),
  notes: z.string().max(500, "Máximo 500 caracteres.").nullable().optional(),
});
export type ApplyPromotionInput = z.infer<typeof applyPromotionSchema>;

// Body de POST /promotions/eligible-for y /promotions/{id}/validate.
export const eligibilityRequestSchema = z.object({
  product_id: z.string().min(1),
  person_id: z.string().min(1),
});
export type EligibilityRequestInput = z.infer<typeof eligibilityRequestSchema>;

// Body de POST /compute-price (promotion_id opcional = sin descuento).
export const computePriceRequestSchema = z.object({
  product_id: z.string().min(1),
  person_id: z.string().min(1),
  promotion_id: z.string().nullable().optional(),
});
export type ComputePriceRequestInput = z.infer<typeof computePriceRequestSchema>;
