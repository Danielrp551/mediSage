"use server";

/**
 * Panel de Depuración del módulo `bots` (F3a) — observabilidad read-only de la
 * sesión del bot en UNA conversación, más dos mutaciones de admin.
 *
 * Reads (tag `bots:debug:${cid}` → se invalidan juntos tras una mutación):
 * - `getBotState`: el `ConversationBotState`. **El 404 `BOT_STATE_NOT_FOUND` NO
 *   es un error de UI** — es un empty legítimo ("esta conversación nunca la
 *   atendió un bot") → se mapea a `{ ok: false, notFound: true }` para que el
 *   componente lo pinte como empty, no como MessageBar de error.
 * - `listBotEvents` / `listBotToolCalls`: la traza (listas crudas en `.data`,
 *   NO paginadas; vacías si no hay).
 *
 * Mutaciones (MutationResult + `revalidateTag(bots:debug:${cid}, "max")`):
 * - `resetBotState`: reinicia el estado (la traza de eventos se conserva).
 * - `dispatchBotTurnManual`: dispara un turno. En F3a es **SÍNCRONO** — el
 *   backend corre el turno inline y devuelve el estado resultante; el componente
 *   refetchea state + events + tool-calls inmediatamente tras el éxito.
 */

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { dispatchManualSchema, resetBotStateSchema } from "@/lib/schemas/bot-debug.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { BotEventItem, BotToolCallItem, ConversationBotStateDetail } from "@/types/bots.types";

import type { MutationResult } from "./user.actions";

const debugTag = (cid: string) => `bots:debug:${cid}`;

/** Resultado de leer el estado: ok | sin estado (404) | error. */
export type BotStateResult =
  | { ok: true; data: ConversationBotStateDetail }
  | { ok: false; notFound: true }
  | { ok: false; notFound?: false; error: string };

export async function getBotState(cid: string): Promise<BotStateResult> {
  try {
    const res = await backendClient.get<ApiSingle<ConversationBotStateDetail>>(
      ENDPOINTS.BOT_TRACE.STATE(cid),
      { tags: [debugTag(cid)] },
    );
    return { ok: true, data: res.data };
  } catch (e) {
    // 404 BOT_STATE_NOT_FOUND = empty legítimo (no error). Cualquier otro 404
    // (p. ej. conversación inexistente) también se trata como "sin estado".
    if (e instanceof HttpError && e.status === 404) {
      return { ok: false, notFound: true };
    }
    return {
      ok: false,
      error: e instanceof HttpError ? e.message : "No se pudo cargar el estado del bot.",
    };
  }
}

export async function listBotEvents(cid: string): Promise<ApiSingle<BotEventItem[]>> {
  return backendClient.get<ApiSingle<BotEventItem[]>>(ENDPOINTS.BOT_TRACE.EVENTS(cid), {
    tags: [debugTag(cid)],
  });
}

export async function listBotToolCalls(cid: string): Promise<ApiSingle<BotToolCallItem[]>> {
  return backendClient.get<ApiSingle<BotToolCallItem[]>>(ENDPOINTS.BOT_TRACE.TOOL_CALLS(cid), {
    tags: [debugTag(cid)],
  });
}

export async function resetBotState(
  cid: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<ConversationBotStateDetail>>> {
  const parsed = resetBotStateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<ConversationBotStateDetail>>(
      ENDPOINTS.BOT_TRACE.STATE_RESET(cid),
      parsed.data,
    );
    revalidateTag(debugTag(cid), "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function dispatchBotTurnManual(
  input: unknown,
): Promise<MutationResult<ApiSingle<ConversationBotStateDetail>>> {
  const parsed = dispatchManualSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    // SÍNCRONO: el backend corre el turno inline y devuelve el estado resultante.
    const data = await backendClient.post<ApiSingle<ConversationBotStateDetail>>(
      ENDPOINTS.BOT_ENGINE.DISPATCH_MANUAL,
      parsed.data,
    );
    revalidateTag(debugTag(parsed.data.conversation_id), "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
