"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  channelAccountCreateSchema,
  channelAccountUpdateSchema,
} from "@/lib/schemas/channel-account.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  ChannelAccountDetail,
  ChannelAccountItem,
  ChannelAccountOption,
} from "@/types/conversations.types";
import type { QueryRequest } from "@/types/query.types";

import type { MutationResult } from "./user.actions";

const CHANNEL_ACCOUNTS_TAG = "conversations:channel-accounts";

export async function listChannelAccounts(
  query: QueryRequest,
): Promise<ApiPaginated<ChannelAccountItem>> {
  return backendClient.post<ApiPaginated<ChannelAccountItem>>(
    ENDPOINTS.CHANNEL_ACCOUNTS.LIST,
    query,
    { tags: [CHANNEL_ACCOUNTS_TAG] },
  );
}

// Lista CRUDA (sin envelope SingleResponse/PaginatedResponse) — alimenta el
// dropdown de canal del inbox (F2). Mismo patrón que listActiveVerticals.
export async function listActiveChannelAccounts(): Promise<ChannelAccountOption[]> {
  return backendClient.get<ChannelAccountOption[]>(ENDPOINTS.CHANNEL_ACCOUNTS.ACTIVE, {
    tags: [CHANNEL_ACCOUNTS_TAG],
  });
}

export async function getChannelAccount(
  id: string,
): Promise<ApiSingle<ChannelAccountDetail>> {
  return backendClient.get<ApiSingle<ChannelAccountDetail>>(
    ENDPOINTS.CHANNEL_ACCOUNTS.GET(id),
    { tags: [CHANNEL_ACCOUNTS_TAG] },
  );
}

export async function createChannelAccount(
  input: unknown,
): Promise<MutationResult<ApiSingle<ChannelAccountDetail>>> {
  const parsed = channelAccountCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<ChannelAccountDetail>>(
      ENDPOINTS.CHANNEL_ACCOUNTS.CREATE,
      parsed.data,
    );
    revalidateTag(CHANNEL_ACCOUNTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateChannelAccount(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<ChannelAccountDetail>>> {
  const parsed = channelAccountUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<ChannelAccountDetail>>(
      ENDPOINTS.CHANNEL_ACCOUNTS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(CHANNEL_ACCOUNTS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteChannelAccount(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CHANNEL_ACCOUNTS.DELETE(id));
    revalidateTag(CHANNEL_ACCOUNTS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
