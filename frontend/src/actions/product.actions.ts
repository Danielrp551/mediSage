"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { productCreateSchema, productUpdateSchema } from "@/lib/schemas/product.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { ProductDetail, ProductItem, ProductOption } from "@/types/catalog.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

// Product is the leaf of the catalog tree — nothing denormalizes its name, so
// a product mutation only invalidates its own tag (no cross-tag needed).
const PRODUCTS_TAG = "catalog:products";

export async function listProducts(query: QueryRequest): Promise<ApiPaginated<ProductItem>> {
  return backendClient.post<ApiPaginated<ProductItem>>(ENDPOINTS.PRODUCTS.LIST, query, {
    tags: [PRODUCTS_TAG],
  });
}

export async function listActiveProducts(serviceId?: string): Promise<ProductOption[]> {
  const url = serviceId
    ? `${ENDPOINTS.PRODUCTS.ACTIVE}?service_id=${encodeURIComponent(serviceId)}`
    : ENDPOINTS.PRODUCTS.ACTIVE;
  return backendClient.get<ProductOption[]>(url, { tags: [PRODUCTS_TAG] });
}

export async function getProduct(id: string): Promise<ApiSingle<ProductDetail>> {
  return backendClient.get<ApiSingle<ProductDetail>>(ENDPOINTS.PRODUCTS.GET(id), {
    tags: [PRODUCTS_TAG],
  });
}

export async function createProduct(
  input: unknown,
): Promise<MutationResult<ApiSingle<ProductDetail>>> {
  const parsed = productCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<ProductDetail>>(
      ENDPOINTS.PRODUCTS.CREATE,
      parsed.data,
    );
    revalidateTag(PRODUCTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateProduct(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<ProductDetail>>> {
  const parsed = productUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<ProductDetail>>(
      ENDPOINTS.PRODUCTS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(PRODUCTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteProduct(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PRODUCTS.DELETE(id));
    revalidateTag(PRODUCTS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
