/**
 * Zod del composer del timeline (F5). El `superRefine` valida POR tipo qué campos
 * son obligatorios. El composer sólo emite los 4 tipos que el asesor crea (los de
 * sistema los emite el backend). Mensajes en español.
 *
 * ⚠ El backend (Pydantic ActivityCreate) SOLO impone dos invariantes: el tipo ∈
 * ADVISOR_ACTIVITY_TYPES y `scheduled_for` requerido para FOLLOW_UP_SCHEDULED. Las
 * reglas `content` (NOTE) y `outcome` (CALL_ATTEMPT) de abajo son validación de
 * CLIENTE (UX más estricta que el contrato del server, dirección segura) — NO existen
 * en el Pydantic; no asumir que el server las rechaza.
 *
 * `scheduled_for`/`completed_at` viajan como ISO 8601 con offset (el composer los
 * serializa client-only desde un `datetime-local` → no se construyen en SSR).
 */

import { z } from "zod";

import type { ActivityOutcome } from "@/types/crm.types";

const ACTIVITY_OUTCOMES = [
  "successful",
  "no_answer",
  "busy",
  "wrong_number",
  "not_interested",
  "interested",
] as const satisfies readonly ActivityOutcome[];

// Tipos que el asesor puede emitir desde el composer (los demás los emite el sistema).
export const COMPOSER_ACTIVITY_TYPES = [
  "NOTE",
  "CALL_ATTEMPT",
  "FOLLOW_UP_SCHEDULED",
  "FOLLOW_UP_COMPLETED",
] as const;

export const leadActivityCreateSchema = z
  .object({
    activity_type: z.enum(COMPOSER_ACTIVITY_TYPES),
    content: z.string().max(5000, "Máximo 5000 caracteres").nullable().optional(),
    scheduled_for: z
      .string()
      .datetime({ offset: true, message: "Fecha y hora inválidas." })
      .nullable()
      .optional(),
    completed_at: z
      .string()
      .datetime({ offset: true, message: "Fecha y hora inválidas." })
      .nullable()
      .optional(),
    outcome: z.enum(ACTIVITY_OUTCOMES).nullable().optional(),
    payload: z.record(z.unknown()).nullable().optional(),
  })
  .superRefine((data, ctx) => {
    switch (data.activity_type) {
      case "NOTE":
        if (!data.content || !data.content.trim()) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["content"],
            message: "Escribe el contenido de la nota.",
          });
        }
        break;
      case "CALL_ATTEMPT":
        if (!data.outcome) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["outcome"],
            message: "Indica el resultado de la llamada.",
          });
        }
        break;
      case "FOLLOW_UP_SCHEDULED":
        if (!data.scheduled_for) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["scheduled_for"],
            message: "Elige la fecha y hora del seguimiento.",
          });
        }
        break;
      case "FOLLOW_UP_COMPLETED":
        // `completed_at` se default-ea a "ahora" en el composer si viene vacío.
        break;
    }
  });

// Editar: SOLO content/outcome/completed_at/scheduled_for (el backend rechaza el
// resto). Sin discriminación por tipo (no se cambia el tipo al editar).
export const leadActivityUpdateSchema = z.object({
  content: z.string().max(5000, "Máximo 5000 caracteres").nullable().optional(),
  outcome: z.enum(ACTIVITY_OUTCOMES).nullable().optional(),
  completed_at: z
    .string()
    .datetime({ offset: true, message: "Fecha y hora inválidas." })
    .nullable()
    .optional(),
  scheduled_for: z
    .string()
    .datetime({ offset: true, message: "Fecha y hora inválidas." })
    .nullable()
    .optional(),
});

export type LeadActivityCreateInput = z.infer<typeof leadActivityCreateSchema>;
export type LeadActivityUpdateInput = z.infer<typeof leadActivityUpdateSchema>;
