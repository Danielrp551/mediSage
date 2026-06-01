import { z } from "zod";

import type { ChannelType } from "@/types/crm.types";

/**
 * Zod del CRUD de `PersonContactIdentifier` (anidado bajo una persona) y de los
 * identificadores iniciales de `personCreateSchema`. El `channel_type` es un
 * enum cerrado (`ChannelType`) — espeja el enum Pydantic del backend.
 *
 * El formato del `identifier` depende del canal (phone E.164, email, chat id…).
 * El `superRefine` valida lo razonable por canal en español: es UX, no contrato
 * (el backend sólo impone el largo). El dedup contra BD (`IDENTIFIER_TAKEN`,
 * 409) NO se valida acá — el front no conoce los identificadores de otras
 * personas; se muestra como error de servidor en `MessageBar`.
 */

// E.164 laxo + email; el resto (chat ids) sólo no-vacío + largo.
const E164_REGEX = /^\+?[1-9]\d{6,14}$/;

// Tupla literal (z.enum exige tuple, no `readonly T[]`). Espeja `CHANNEL_TYPES`
// de crm.types — `satisfies` garantiza que no haya drift con el enum del backend.
const CHANNEL_TYPE_TUPLE = [
  "whatsapp",
  "telegram",
  "web",
  "phone",
  "email",
  "instagram",
  "facebook",
  "other",
] as const satisfies readonly ChannelType[];

// Campos base reutilizados por el CRUD anidado Y por personCreateSchema.identifiers.
export const identifierFields = {
  channel_type: z.enum(CHANNEL_TYPE_TUPLE, {
    errorMap: () => ({ message: "Canal no válido" }),
  }),
  identifier: z.string().min(1, "Obligatorio").max(255, "Máximo 255 caracteres"),
  is_primary: z.boolean().optional().default(false),
  verified: z.boolean().optional().default(false),
} as const;

export const contactIdentifierCreateSchema = z.object(identifierFields).superRefine((data, ctx) => {
  const v = data.identifier.trim();
  if (data.channel_type === "phone" || data.channel_type === "whatsapp") {
    if (!E164_REGEX.test(v)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifier"],
        message: "Teléfono en formato internacional (ej. +51999111222).",
      });
    }
  } else if (data.channel_type === "email") {
    if (!z.string().email().safeParse(v).success) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifier"],
        message: "Correo inválido.",
      });
    }
  }
});

// Update: todos opcionales (cambiar canal/valor/principal/verificado). El
// superRefine sólo corre cuando vienen ambos canal+valor.
export const contactIdentifierUpdateSchema = z
  .object({
    channel_type: z.enum(CHANNEL_TYPE_TUPLE).optional(),
    identifier: z.string().min(1).max(255).optional(),
    is_primary: z.boolean().optional(),
    verified: z.boolean().optional(),
  })
  .superRefine((data, ctx) => {
    if (!data.channel_type || !data.identifier) return;
    const v = data.identifier.trim();
    if (
      (data.channel_type === "phone" || data.channel_type === "whatsapp") &&
      !E164_REGEX.test(v)
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifier"],
        message: "Teléfono en formato internacional (ej. +51999111222).",
      });
    } else if (data.channel_type === "email" && !z.string().email().safeParse(v).success) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["identifier"],
        message: "Correo inválido.",
      });
    }
  });

export type ContactIdentifierCreateInput = z.infer<typeof contactIdentifierCreateSchema>;
export type ContactIdentifierUpdateInput = z.infer<typeof contactIdentifierUpdateSchema>;
