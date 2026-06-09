/**
 * Zod de Campaign — compartido por el form (cliente) y el Server Action (servidor),
 * así no hay drift. Mensajes visibles en español; `path`/campos en inglés.
 *
 * `code` es un slug minúsculas INMUTABLE (solo en el create; el update no lo incluye,
 * igual que el backend). El `superRefine` espeja la validación de fechas del service
 * (CAMPAIGN_INVALID_DATES). El `status` no se valida acá (nace `draft`, cambia por
 * /transition). La validez de la transición la impone el service (la UI solo ofrece los
 * destinos permitidos por la matriz de marketing.ts).
 */

import { z } from "zod";

// code = slug en MINÚSCULAS (patrón catalog). Inmutable post-create. min2 max40.
const CODE_SLUG_REGEX = /^[a-z][a-z0-9_]{1,38}[a-z0-9]$/;

const campaignBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD"),
  end_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD")
    .nullable()
    .optional()
    .or(z.literal("")),
  target_vertical_id: z.string().nullable().optional(), // null = transversal
});

// end_date >= start_date (comparación lexicográfica válida para YYYY-MM-DD). Solo corre
// cuando ambas fechas están presentes.
function refineCampaignDates(
  data: { start_date?: string; end_date?: string | null },
  ctx: z.RefinementCtx,
) {
  if (data.start_date && data.end_date && data.end_date !== "" && data.end_date < data.start_date) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["end_date"],
      message: "La fecha de fin no puede ser anterior a la de inicio.",
    });
  }
}

export const campaignCreateSchema = campaignBase
  .extend({
    code: z
      .string()
      .min(2, "Mínimo 2 caracteres")
      .max(40, "Máximo 40 caracteres")
      .regex(CODE_SLUG_REGEX, "Minúsculas, números y guion bajo (ej. verano_2026)"),
  })
  .superRefine(refineCampaignDates);

export const campaignUpdateSchema = campaignBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineCampaignDates);

// Body de POST /campaigns/{id}/transition (la validez de la arista la impone el service).
export const campaignTransitionSchema = z.object({
  to_status: z.enum(["draft", "active", "paused", "ended"]),
});

// Body de PUT /campaigns/{id}/promotions (reemplaza el set completo del M:N). Se cablea
// en F2 (la tabla `promotion` aún no existe).
export const campaignPromotionsReplaceSchema = z.object({
  promotion_ids: z.array(z.string()),
});

export type CampaignCreateInput = z.infer<typeof campaignCreateSchema>;
export type CampaignUpdateInput = z.infer<typeof campaignUpdateSchema>;
export type CampaignTransitionInput = z.infer<typeof campaignTransitionSchema>;
export type CampaignPromotionsReplaceInput = z.infer<typeof campaignPromotionsReplaceSchema>;
