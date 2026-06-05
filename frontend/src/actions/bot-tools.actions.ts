"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  botToolCreateSchema,
  botToolUpdateSchema,
  configurationToolsSchema,
} from "@/lib/schemas/bot-tools.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  BotConfigurationDetail,
  BotToolDetail,
  BotToolItem,
  BotToolOption,
} from "@/types/bots.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const TOOLS_TAG = "bots:tools";
const CONFIGS_TAG = "bots:configurations";

// ── BotTool (catálogo) ───────────────────────────────────

export async function listBotTools(query: QueryRequest): Promise<ApiPaginated<BotToolItem>> {
  return backendClient.post<ApiPaginated<BotToolItem>>(ENDPOINTS.BOT_TOOLS.LIST, query, {
    tags: [TOOLS_TAG],
  });
}

// Lista CRUDA (sin envelope) — candidatas del multiselect M:N por bot.
export async function listActiveBotTools(): Promise<BotToolOption[]> {
  return backendClient.get<BotToolOption[]>(ENDPOINTS.BOT_TOOLS.ACTIVE, { tags: [TOOLS_TAG] });
}

export async function getBotTool(id: string): Promise<ApiSingle<BotToolDetail>> {
  return backendClient.get<ApiSingle<BotToolDetail>>(ENDPOINTS.BOT_TOOLS.GET(id), {
    tags: [TOOLS_TAG],
  });
}

export async function createBotTool(
  input: unknown,
): Promise<MutationResult<ApiSingle<BotToolDetail>>> {
  const parsed = botToolCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<BotToolDetail>>(
      ENDPOINTS.BOT_TOOLS.CREATE,
      parsed.data,
    );
    revalidateTag(TOOLS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateBotTool(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotToolDetail>>> {
  const parsed = botToolUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<BotToolDetail>>(
      ENDPOINTS.BOT_TOOLS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(TOOLS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteBotTool(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.BOT_TOOLS.DELETE(id));
    revalidateTag(TOOLS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── M:N tools del bot (editor del tab Herramientas) ──────

// Set actual de tools asignadas a un bot (vivas). SingleResponse[list[BotToolOption]].
export async function getConfigurationTools(configId: string): Promise<ApiSingle<BotToolOption[]>> {
  return backendClient.get<ApiSingle<BotToolOption[]>>(
    ENDPOINTS.BOT_CONFIGURATIONS.TOOLS_LIST(configId),
    { tags: [CONFIGS_TAG] },
  );
}

// Reemplaza (bulk) el set M:N completo de tools del bot.
export async function setConfigurationTools(
  configId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BotConfigurationDetail>>> {
  const parsed = configurationToolsSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<BotConfigurationDetail>>(
      ENDPOINTS.BOT_CONFIGURATIONS.TOOLS_UPDATE(configId),
      parsed.data,
    );
    revalidateTag(CONFIGS_TAG, "max"); // el detalle del bot embebe tool_ids
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
