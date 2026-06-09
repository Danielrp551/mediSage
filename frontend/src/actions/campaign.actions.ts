"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  campaignCreateSchema,
  campaignTransitionSchema,
  campaignUpdateSchema,
} from "@/lib/schemas/campaign.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { CampaignDetail, CampaignItem, CampaignOption } from "@/types/marketing.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const CAMPAIGNS_TAG = "marketing:campaigns";

export async function listCampaigns(query: QueryRequest): Promise<ApiPaginated<CampaignItem>> {
  return backendClient.post<ApiPaginated<CampaignItem>>(ENDPOINTS.CAMPAIGNS.LIST, query, {
    tags: [CAMPAIGNS_TAG],
  });
}

export async function listActiveCampaigns(): Promise<CampaignOption[]> {
  // Lista CRUDA (sin envelope) — NO se lee `.data`.
  return backendClient.get<CampaignOption[]>(ENDPOINTS.CAMPAIGNS.ACTIVE, {
    tags: [CAMPAIGNS_TAG],
  });
}

export async function getCampaign(id: string): Promise<ApiSingle<CampaignDetail>> {
  return backendClient.get<ApiSingle<CampaignDetail>>(ENDPOINTS.CAMPAIGNS.GET(id), {
    tags: [CAMPAIGNS_TAG],
  });
}

export async function createCampaign(
  input: unknown,
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.CREATE,
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 CAMPAIGN_CODE_TAKEN / 400 CAMPAIGN_INVALID_DATES / 400 TARGET_VERTICAL_NOT_FOUND.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateCampaign(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteCampaign(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CAMPAIGNS.DELETE(id));
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Transición de estado (valida la matriz §2 en el service) ──────────────
export async function transitionCampaign(
  id: string,
  input: unknown, // { to_status }
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignTransitionSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.TRANSITION(id),
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 CAMPAIGN_TRANSITION_NOT_ALLOWED (detalle en español).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
