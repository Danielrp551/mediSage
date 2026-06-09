/**
 * Constantes de presentación del módulo marketing: label ES + color por estado de
 * campaña, la matriz de transiciones (espejo §2 del backend, para gatear los shortcuts
 * del control "Cambiar estado"), label ES por tipo de descuento, monedas soportadas y
 * un helper de formato de descuento.
 *
 * El color de los badges de estado es FIJO (token Fluent semántico por `CampaignStatus`),
 * NO del catálogo en BD: a diferencia de crm `LeadStatus`/scheduling `AppointmentStatus`
 * (color hex configurable), `CampaignStatus` es un ENUM cerrado (ADR-013).
 *
 * Solo lo importan client components (Fluent `tokens` se resuelve en el browser).
 */

import { tokens } from "@fluentui/react-components";

import type { CampaignStatus, DiscountType, PromotionOption } from "@/types/marketing.types";

// ── Estado de campaña (ENUM fijo) ─────────────────────────────────────────
export const CAMPAIGN_STATUS_META: Record<CampaignStatus, { label: string; color: string }> = {
  draft: { label: "Borrador", color: tokens.colorNeutralForeground3 },
  active: { label: "Activa", color: tokens.colorPaletteGreenForeground1 },
  paused: { label: "Pausada", color: tokens.colorPaletteMarigoldForeground2 },
  ended: { label: "Finalizada", color: tokens.colorNeutralForeground4 },
};

// Matriz de transiciones permitidas (espejo EXACTO del service §2; hardcodeada). El
// control "Cambiar estado" ofrece SOLO estos destinos → previene
// CAMPAIGN_TRANSITION_NOT_ALLOWED (400). 'ended' es terminal (sin destinos).
export const CAMPAIGN_TRANSITIONS: Record<CampaignStatus, CampaignStatus[]> = {
  draft: ["active"],
  active: ["paused", "ended"],
  paused: ["active", "ended"],
  ended: [], // terminal
};

// Verbo del botón shortcut según el estado destino (para el control "Cambiar estado").
export const CAMPAIGN_TRANSITION_VERB: Record<CampaignStatus, string> = {
  draft: "Pasar a borrador",
  active: "Activar",
  paused: "Pausar",
  ended: "Finalizar",
};

// ── Tipo de descuento (lo usan Promociones en F2) ─────────────────────────
export const DISCOUNT_TYPE_META: Record<DiscountType, { label: string }> = {
  percentage: { label: "Porcentaje" },
  fixed_amount: { label: "Monto fijo" },
};

// Monedas soportadas por la UI (ISO 4217). El backend acepta cualquier ^[A-Z]{3}$; el
// front lo acota. Lo reusa el Zod de promotion en F2 (single source).
export const SUPPORTED_CURRENCIES = ["PEN", "USD", "EUR"] as const;

// Formato de descuento para badges/columnas: "10%" o "S/ 25.00" según el tipo.
export function formatDiscount(
  p: Pick<PromotionOption, "discount_type" | "discount_value" | "currency">,
): string {
  if (p.discount_type === "percentage") return `${p.discount_value}%`;
  const symbol =
    p.currency === "PEN"
      ? "S/"
      : p.currency === "USD"
        ? "$"
        : p.currency === "EUR"
          ? "€"
          : p.currency;
  return `${symbol} ${p.discount_value}`;
}
