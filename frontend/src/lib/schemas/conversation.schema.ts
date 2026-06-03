import { z } from "zod";

/**
 * Schemas Zod de las mutaciones del inbox (F3). Defensa en profundidad: aunque el
 * backend valida y rechaza (UNSUPPORTED_CONTENT_TYPE / INVALID_ASSIGNEE / etc.), el
 * action vuelve a validar acá para dar feedback en español antes de salir a la red.
 *
 * MVP: el composer solo emite texto (`content_type: "text"`); el release solo
 * libera a `unassigned` (release a `advisor` → INVALID_ASSIGNEE en el backend; para
 * asignar a un asesor se usa "tomar"). Take/Close/Reopen no llevan body más allá del
 * `reason?` opcional.
 */

// Enviar outbound. MVP: solo texto. Límite 4096 (límite práctico de WhatsApp text).
export const sendMessageSchema = z.object({
  content: z.string().min(1, "Escribe un mensaje").max(4096, "Máximo 4096 caracteres"),
  content_type: z.literal("text").optional(),
});

// Liberar la conversación. En el MVP la UI solo libera a `unassigned`.
export const releaseConversationSchema = z.object({
  to_assignee_type: z.enum(["unassigned"]),
  reason: z.string().max(255, "Máximo 255 caracteres").optional().nullable(),
});

// Tomar la conversación (assignee = actor). `reason?` opcional (queda en el log).
export const takeConversationSchema = z.object({
  reason: z.string().max(255, "Máximo 255 caracteres").optional().nullable(),
});

export type SendMessageInput = z.infer<typeof sendMessageSchema>;
export type ReleaseConversationInput = z.infer<typeof releaseConversationSchema>;
export type TakeConversationInput = z.infer<typeof takeConversationSchema>;
