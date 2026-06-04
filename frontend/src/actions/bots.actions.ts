"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  botConfigurationCreateSchema,
  botConfigurationUpdateSchema,
  botVersionSchema,
} from "@/lib/schemas/bots.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  BotConfigurationDetail,
  BotConfigurationItem,
  BotConfigurationOption,
  BotConfigurationVersionDetail,
  BotConfigurationVersionItem,
} from "@/types/bots.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const CONFIGS_TAG = "bots:configurations";

// ── BotConfiguration ─────────────────────────────────────

export async function listBotConfigurations(
  query: QueryRequest,
): Promise<ApiPaginated<BotConfigurationItem>> {
  return backendClient.post<ApiPaginated<BotConfigurationItem>>(
    ENDPOINTS.BOT_CONFIGURATIONS.LIST,
    query,
    { tags: [CONFIGS_TAG] },
  );
}

export async function listActiveBotConfigurations(): Promise<BotConfigurationOption[]> {
  return backendClient.get<BotConfigurationOption[]>(ENDPOINTS.BOT_CONFIGURATIONS.ACTIVE, {
    tags: [CONFIGS_TAG],
  });
}

export async function getBotConfiguration(id: string): Promise<ApiSingle<BotConfigurationDetail>> {
  return backendClient.get<ApiSingle<BotConfigurationDetail>>(
    ENDPOINTS.BOT_CONFIGURATIONS.GET(id),
    { tags: [CONFIGS_TAG] },
  );
}

export async function createBotConfiguration(
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  const parsed = botConfigurationCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.CREATE,
      parsed.data,
    );
    revalidateTag(CONFIGS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateBotConfiguration(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  const parsed = botConfigurationUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(CONFIGS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteBotConfiguration(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.BOT_CONFIGURATIONS.DELETE(id));
    revalidateTag(CONFIGS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── BotConfigurationVersion ──────────────────────────────

export async function listBotVersions(
  configId: string,
): Promise<ApiSingle<BotConfigurationVersionItem[]>> {
  return backendClient.get<ApiSingle<BotConfigurationVersionItem[]>>(
    ENDPOINTS.BOT_CONFIGURATIONS.VERSIONS_LIST(configId),
    { tags: [CONFIGS_TAG] },
  );
}

export async function getBotVersion(
  configId: string,
  vid: string,
): Promise<ApiSingle<BotConfigurationVersionDetail>> {
  return backendClient.get<ApiSingle<BotConfigurationVersionDetail>>(
    ENDPOINTS.BOT_CONFIGURATIONS.VERSION_GET(configId, vid),
    { tags: [CONFIGS_TAG] },
  );
}

export async function createBotVersion(
  configId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationVersionDetail>>> {
  const parsed = botVersionSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<BotConfigurationVersionDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.VERSION_CREATE(configId),
      parsed.data,
    );
    revalidateTag(CONFIGS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function activateBotVersion(
  configId: string,
  vid: string,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.ACTIVATE_VERSION(configId, vid),
      {},
    );
    revalidateTag(CONFIGS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
