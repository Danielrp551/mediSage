"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  applyPromotionSchema,
  computePriceRequestSchema,
  eligibilityRequestSchema,
} from "@/lib/schemas/promotion-usage.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  ComputePriceResponse,
  PromotionEligibility,
  PromotionUsageDetail,
  PromotionUsageItem,
} from "@/types/marketing.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const PROMOTIONS_TAG = "marketing:promotions";
const USAGES_TAG = "marketing:promotion-usages";

// ── Reporte de usos (read-only) ─────────────────────────────────────────────
export async function listPromotionUsages(
  query: QueryRequest,
): Promise<ApiPaginated<PromotionUsageItem>> {
  return backendClient.post<ApiPaginated<PromotionUsageItem>>(
    ENDPOINTS.PROMOTION_USAGES.LIST,
    query,
    { tags: [USAGES_TAG] },
  );
}

// ── Validación / precio (lecturas on-the-fly; sin tags → cache "no-store") ───
// Validan con `.parse` (el caller — wizard de citas F4 / panel de verificación — pre-valida;
// un request inválido es un bug, no input de usuario suelto). NO se consumen desde la UI de
// usos (read-only); se documentan para scheduling F4 / el bot.

export async function eligibleFor(input: unknown): Promise<PromotionEligibility[]> {
  const parsed = eligibilityRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<PromotionEligibility[]>>(
    ENDPOINTS.PROMOTIONS.ELIGIBLE_FOR,
    parsed,
  );
  return res.data;
}

export async function validatePromotion(
  promotionId: string,
  input: unknown, // { product_id, person_id }
): Promise<PromotionEligibility> {
  const parsed = eligibilityRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<PromotionEligibility>>(
    ENDPOINTS.PROMOTIONS.VALIDATE(promotionId),
    parsed,
  );
  return res.data;
}

export async function computePrice(input: unknown): Promise<ComputePriceResponse> {
  const parsed = computePriceRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<ComputePriceResponse>>(
    ENDPOINTS.PROMOTION_USAGES.COMPUTE_PRICE,
    parsed,
  );
  return res.data;
}

// ── Aplicación (POST; crea PromotionUsage) ──────────────────────────────────
// En el MVP NO la llama la UI de marketing (usos = read-only); scheduling F4 la dispara vía
// apply_promotion_id en el body de POST /appointments (atómico en el backend). Documentada
// para un eventual panel de aplicación manual.
export async function applyPromotion(
  input: unknown,
): Promise<MutationResult<ApiSingle<PromotionUsageDetail>>> {
  const parsed = applyPromotionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PromotionUsageDetail>>(
      ENDPOINTS.PROMOTION_USAGES.APPLY,
      parsed.data,
    );
    revalidateTag(USAGES_TAG, "max"); // el reporte + usage-summary
    revalidateTag(PROMOTIONS_TAG, "max"); // total_uses de la promo
    return { ok: true, data };
  } catch (e) {
    // 400 PROMOTION_NOT_ACTIVE/EXPIRED/PRODUCT_NOT_COVERED/LIMIT_REACHED/PERSON_LIMIT_REACHED;
    // 409 PROMOTION_ALREADY_APPLIED; 404 PROMOTION/PRODUCT/PERSON_NOT_FOUND.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
