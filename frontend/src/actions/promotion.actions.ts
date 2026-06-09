"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  promotionCreateSchema,
  promotionProductsReplaceSchema,
  promotionUpdateSchema,
} from "@/lib/schemas/promotion.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { ProductOption } from "@/types/catalog.types";
import type { PromotionDetail, PromotionItem, PromotionOption } from "@/types/marketing.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const PROMOTIONS_TAG = "marketing:promotions";

export async function listPromotions(query: QueryRequest): Promise<ApiPaginated<PromotionItem>> {
  return backendClient.post<ApiPaginated<PromotionItem>>(ENDPOINTS.PROMOTIONS.LIST, query, {
    tags: [PROMOTIONS_TAG],
  });
}

export async function listActivePromotions(): Promise<PromotionOption[]> {
  // Lista CRUDA — la consume el editor M:N de campañas (opciones).
  return backendClient.get<PromotionOption[]>(ENDPOINTS.PROMOTIONS.ACTIVE, {
    tags: [PROMOTIONS_TAG],
  });
}

export async function getPromotion(id: string): Promise<ApiSingle<PromotionDetail>> {
  return backendClient.get<ApiSingle<PromotionDetail>>(ENDPOINTS.PROMOTIONS.GET(id), {
    tags: [PROMOTIONS_TAG],
  });
}

export async function createPromotion(
  input: unknown,
): Promise<MutationResult<ApiSingle<PromotionDetail>>> {
  const parsed = promotionCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<PromotionDetail>>(
      ENDPOINTS.PROMOTIONS.CREATE,
      parsed.data,
    );
    revalidateTag(PROMOTIONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 PROMOTION_CODE_TAKEN / 400 PROMOTION_INVALID_DISCOUNT / 400 PROMOTION_INVALID_DATES.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updatePromotion(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PromotionDetail>>> {
  const parsed = promotionUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  // Descartar el campo efímero _discount_type antes del PUT (el backend no lo acepta;
  // sólo existía para que el Zod del update valide el rango de discount_value).
  const { _discount_type, ...body } = parsed.data as Record<string, unknown>;
  void _discount_type;
  try {
    const data = await backendClient.put<ApiSingle<PromotionDetail>>(
      ENDPOINTS.PROMOTIONS.UPDATE(id),
      body,
    );
    revalidateTag(PROMOTIONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deletePromotion(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PROMOTIONS.DELETE(id));
    revalidateTag(PROMOTIONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── M:N promotion_product ──────────────────────────────────────────────────

export async function getPromotionProducts(id: string): Promise<ProductOption[]> {
  // GET enveloped SingleResponse[list[ProductOption]] → leer .data.
  const res = await backendClient.get<ApiSingle<ProductOption[]>>(
    ENDPOINTS.PROMOTIONS.PRODUCTS_LIST(id),
    { tags: [PROMOTIONS_TAG] },
  );
  return res.data;
}

export async function setPromotionProducts(
  id: string,
  input: unknown, // { product_ids: [...] } — reemplaza el set completo
): Promise<MutationResult<ApiSingle<PromotionDetail>>> {
  const parsed = promotionProductsReplaceSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<PromotionDetail>>(
      ENDPOINTS.PROMOTIONS.PRODUCTS_UPDATE(id),
      parsed.data,
    );
    revalidateTag(PROMOTIONS_TAG, "max"); // products_count + detalle
    return { ok: true, data };
  } catch (e) {
    // 404 PRODUCT_NOT_FOUND si algún product_id no existe vivo en catalog.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
