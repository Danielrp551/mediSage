"use server";

/**
 * Server Actions del inbox de `conversations`.
 *
 * El browser NUNCA habla directo con el backend ni con Firestore para escribir:
 * - Las lecturas del inbox (`listConversations` / `listMyConversations` / `getConversation`)
 *   pasan por el backend client server-side (JWT en cookie httpOnly).
 * - `getRealtimeToken` minta un Firebase Custom Token (server-side, con el JWT) que
 *   el cliente usa con `signInWithCustomToken` para abrir listeners READ-ONLY de Firestore.
 * - `listMessages` es el FALLBACK server-side del hilo (lee Firestore vía Admin SDK);
 *   el path PRIMARIO es el cliente Firestore real-time (`onSnapshot` — ver useThreadMessages).
 *
 * Las MUTACIONES (F3) — enviar / tomar / liberar / cerrar / reabrir / marcar-leída —
 * viven al final del archivo: validan con Zod (defensa en profundidad), llaman al
 * backend client y revalidan los tags del listado + del hilo tras el éxito.
 */

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  releaseConversationSchema,
  sendMessageSchema,
  takeConversationSchema,
} from "@/lib/schemas/conversation.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  ConversationDetail,
  ConversationListItem,
  MessageItem,
} from "@/types/conversations.types";
import type { QueryRequest } from "@/types/query.types";

import type { MutationResult } from "./user.actions";

const LIST_TAG = "conversations:list";
const threadTag = (id: string) => `conversations:thread:${id}`;

// Shape del token de Firebase que devuelve el backend. `firebase_config` viene
// null → el cliente usa sus envs NEXT_PUBLIC_FIREBASE_* (ver lib/firebase/client.ts).
export interface RealtimeToken {
  token: string;
  firebase_config: null;
}

/**
 * Minta el Custom Token de Firebase (server-side, con el JWT del asesor). El
 * cliente lo usa una sola vez por sesión de inbox para `signInWithCustomToken`.
 * NO se taggea ni se cachea — es una credencial efímera. Si falla, el hilo cae
 * al fallback server-side (`listMessages`) sin real-time.
 */
export async function getRealtimeToken(): Promise<MutationResult<RealtimeToken>> {
  try {
    const res = await backendClient.post<ApiSingle<RealtimeToken>>(
      ENDPOINTS.CONVERSATIONS_API.REALTIME_TOKEN,
      {},
    );
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Lecturas del inbox (taggeadas; el polling las re-invoca) ──

// Anexa el query string de filtros deep-link (status / channel_account_id /
// unassigned / assignee_user_id) a la URL del listado. El backend lee estos
// filtros de la URL, NO del body (el body es la paginación/sort del QueryRequest).
function withParams(path: string, queryParams?: string): string {
  return queryParams ? `${path}?${queryParams}` : path;
}

export async function listConversations(
  query: QueryRequest,
  queryParams?: string,
): Promise<ApiPaginated<ConversationListItem>> {
  return backendClient.post<ApiPaginated<ConversationListItem>>(
    withParams(ENDPOINTS.CONVERSATIONS_API.LIST, queryParams),
    query,
    { tags: [LIST_TAG] },
  );
}

export async function listMyConversations(
  query: QueryRequest,
  queryParams?: string,
): Promise<ApiPaginated<ConversationListItem>> {
  // El backend resuelve el asesor del token (assignee_user_id = actor). En "mine"
  // solo aplican los filtros de estado/canal (sin "sin asignar"/"mías").
  return backendClient.post<ApiPaginated<ConversationListItem>>(
    withParams(ENDPOINTS.ME_CONVERSATIONS.LIST, queryParams),
    query,
    { tags: [LIST_TAG] },
  );
}

export async function getConversation(id: string): Promise<ApiSingle<ConversationDetail>> {
  // Detail incluye assignment_history (para el header/handoff del hilo).
  return backendClient.get<ApiSingle<ConversationDetail>>(ENDPOINTS.CONVERSATIONS_API.GET(id), {
    tags: [threadTag(id)],
  });
}

/**
 * FALLBACK del hilo (rediseño Firestore): el path PRIMARIO de lectura del hilo es
 * el cliente Firestore real-time (`onSnapshot` — ver useThreadMessages). Esta
 * action lee Firestore vía Admin SDK server-side y se usa solo como degradación
 * (si el Web SDK no carga / el custom token falla). El backend devuelve el mismo
 * shape `MessageItem` (snake_case).
 */
export async function listMessages(
  conversationId: string,
  query: QueryRequest,
): Promise<ApiPaginated<MessageItem>> {
  return backendClient.post<ApiPaginated<MessageItem>>(
    ENDPOINTS.CONVERSATIONS_API.MESSAGES_LIST(conversationId),
    query,
    { tags: [threadTag(conversationId)] },
  );
}

// ── Mutaciones (F3): enviar / tomar / liberar / cerrar / reabrir / marcar-leída ──

// Revalida los caches del listado + del hilo tras una mutación con éxito. Next 16
// exige el 2º argumento "max" en revalidateTag.
function revalidateThread(conversationId: string): void {
  revalidateTag(LIST_TAG, "max");
  revalidateTag(threadTag(conversationId), "max");
}

/**
 * Envía un mensaje OUTBOUND (real, vía Meta Graph API en el backend). El backend
 * SIEMPRE responde 200 con el `MessageItem` persistido: si el envío a Meta falló, el
 * mensaje viene con `external_status:"failed"` (NO es un error de la action — la UI
 * pinta el estado del mensaje). Solo devolvemos `ok:false` ante un HttpError real
 * (403 NOT_CONVERSATION_ASSIGNEE, 400 CONVERSATION_NOT_OPEN/UNSUPPORTED_CONTENT_TYPE…).
 */
export async function sendMessage(
  conversationId: string,
  input: unknown,
): Promise<MutationResult<MessageItem>> {
  const parsed = sendMessageSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const res = await backendClient.post<ApiSingle<MessageItem>>(
      ENDPOINTS.CONVERSATIONS_API.SEND_MESSAGE(conversationId),
      parsed.data,
    );
    revalidateThread(conversationId);
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

/**
 * Toma la conversación (assignee = actor). `reason?` opcional queda en el log de
 * handoff. Devuelve el `ConversationDetail` actualizado para refrescar el header.
 */
export async function takeConversation(
  conversationId: string,
  input: unknown,
): Promise<MutationResult<ConversationDetail>> {
  const parsed = takeConversationSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const res = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.TAKE(conversationId),
      parsed.data,
    );
    revalidateThread(conversationId);
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

/**
 * Libera la conversación. En el MVP la UI solo libera a `unassigned` (release a
 * `advisor` → INVALID_ASSIGNEE en el backend). `reason?` opcional queda en el log.
 */
export async function releaseConversation(
  conversationId: string,
  input: unknown,
): Promise<MutationResult<ConversationDetail>> {
  const parsed = releaseConversationSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const res = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.RELEASE(conversationId),
      parsed.data,
    );
    revalidateThread(conversationId);
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

/** Cierra la conversación (soft, vía status). Sin body. */
export async function closeConversation(
  conversationId: string,
): Promise<MutationResult<ConversationDetail>> {
  try {
    const res = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.CLOSE(conversationId),
      {},
    );
    revalidateThread(conversationId);
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

/**
 * Reabre la conversación. Puede dar 409 CONVERSATION_ALREADY_OPEN si ya existe otra
 * conversación abierta para el mismo contacto en el mismo canal — el mensaje del
 * backend ("Ya hay una conversación abierta…") se propaga tal cual en `error`.
 */
export async function reopenConversation(
  conversationId: string,
): Promise<MutationResult<ConversationDetail>> {
  try {
    const res = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.REOPEN(conversationId),
      {},
    );
    revalidateThread(conversationId);
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

/** Marca la conversación como leída (resetea `unread_count`). Sin body. */
export async function markRead(
  conversationId: string,
): Promise<MutationResult<ConversationDetail>> {
  try {
    const res = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.MARK_READ(conversationId),
      {},
    );
    revalidateThread(conversationId);
    return { ok: true, data: res.data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
