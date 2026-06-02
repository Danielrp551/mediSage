/**
 * Schemas Zod del ciclo de vida del lead (F3). La transición es simple
 * (`to_lead_status_id` + `reason?`); la VALIDEZ de la arista
 * (`LEAD_TRANSITION_NOT_ALLOWED`, 400) NO se valida en Zod — la conoce la matriz
 * del backend, y la UI la mitiga ofreciendo en el `TransitionControl` SOLO los
 * destinos permitidos.
 *
 * F3 = lead-only. Los schemas customer/promote llegan en F4 (sus endpoints de
 * backend aún no existen) — se omiten aquí para mantener el alcance acotado.
 */

import { z } from "zod";

export const createLeadSchema = z.object({
  source_campaign_id: z.string().max(36).nullable().optional(),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

export const leadTransitionSchema = z.object({
  to_lead_status_id: z.string().min(1, "Elige un estado destino"),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

export type CreateLeadInput = z.infer<typeof createLeadSchema>;
export type LeadTransitionInput = z.infer<typeof leadTransitionSchema>;
