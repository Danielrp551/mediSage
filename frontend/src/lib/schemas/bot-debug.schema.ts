import { z } from "zod";

/**
 * Zod del panel de Depuración del módulo `bots` (F3a) — compartidos por el
 * componente (cliente) y el Server Action (server), drift imposible (regla del
 * template). Mensajes visibles en español; `path`/nombres de campo en inglés.
 *
 * Las dos únicas mutaciones de la pantalla (todo lo demás es read-only):
 * - `resetBotState`: reinicia el `ConversationBotState` (la traza se conserva).
 * - `dispatchBotTurnManual`: dispara un turno del bot — en F3a es SÍNCRONO (el
 *   backend corre el turno inline y devuelve el estado resultante).
 */

// Reset del estado del bot. `reason` opcional (auditoría del por qué). El cid va
// por path, no en el body.
export const resetBotStateSchema = z.object({
  reason: z.string().max(255, "Máximo 255 caracteres").nullable().optional().or(z.literal("")),
});

// Dispatch manual del turno (debug). `conversation_id` requerido; `input_message_id`
// opcional (mid Firestore del inbound a procesar; null = el motor toma el último).
export const dispatchManualSchema = z.object({
  conversation_id: z.string().min(1, "Obligatorio").max(36, "Identificador inválido"),
  input_message_id: z.string().min(1).nullable().optional(),
});

export type ResetBotStateInput = z.infer<typeof resetBotStateSchema>;
export type DispatchManualInput = z.infer<typeof dispatchManualSchema>;
