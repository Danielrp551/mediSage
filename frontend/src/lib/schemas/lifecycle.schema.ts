/**
 * Schemas Zod del ciclo de vida lead + customer (F3 + F4). Las transiciones son
 * simples (`to_*_status_id` + `reason?`); la VALIDEZ de la arista
 * (`LEAD_TRANSITION_NOT_ALLOWED` / `CUSTOMER_TRANSITION_NOT_ALLOWED`, 400) NO se
 * valida en Zod — la conoce la matriz del backend, y la UI la mitiga ofreciendo
 * en el `TransitionControl` SOLO los destinos permitidos.
 *
 * El promote-to-customer (F4) sólo lleva un `reason?` opcional: el estado inicial
 * de cliente es implícito (el `is_initial` del catálogo customer).
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

export const customerTransitionSchema = z.object({
  to_customer_status_id: z.string().min(1, "Elige un estado destino"),
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

export const promoteToCustomerSchema = z.object({
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
});

export type CreateLeadInput = z.infer<typeof createLeadSchema>;
export type LeadTransitionInput = z.infer<typeof leadTransitionSchema>;
export type CustomerTransitionInput = z.infer<typeof customerTransitionSchema>;
export type PromoteToCustomerInput = z.infer<typeof promoteToCustomerSchema>;
