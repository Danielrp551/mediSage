import { z } from "zod";

import type { ChannelType } from "@/types/crm.types";

/**
 * CRUD de cuentas de canal (`conversations` F1). El `channel_type` es un enum
 * cerrado (`ChannelType`, reuse de crm — single source of truth); en el MVP el
 * único valor seleccionable desde el form es `whatsapp` (los otros aparecen como
 * "(próximamente)" deshabilitados), pero el schema acepta los 8 para no bloquear
 * futuros canales.
 *
 * ⚠ El SECRETO (access_token/app_secret) NUNCA se valida ni viaja en claro: el
 * form sólo captura `secret_name` (el NOMBRE del secreto en GCP Secret Manager,
 * ej. `medisage-whatsapp-estetica-qa`), nunca su valor (ADR-010). El
 * `webhook_verify_token` es editable en claro (no es secreto duro — lo envía Meta
 * en el GET de verificación del webhook y se compara). Los largos espejan los
 * `varchar(...)` del modelo (backend.md §channel_account).
 *
 * Lo que Zod NO puede validar (queda como error de servidor en español, se muestra
 * en el MessageBar del drawer): `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` (409, UNIQUE
 * parcial `(channel_type, external_identifier)`) y `CHANNEL_CREDENTIALS_MISSING`
 * (si el `secret_name` apunta a un secreto inexistente y no hay fallback env).
 */

// Tupla literal (z.enum exige tuple, no `readonly T[]`). Espeja `CHANNEL_TYPES`
// de crm.types (single source of truth) — si crm agrega un canal, agregarlo aquí.
const CHANNEL_TYPE_VALUES = [
  "whatsapp",
  "telegram",
  "web",
  "phone",
  "email",
  "instagram",
  "facebook",
  "other",
] as const satisfies readonly ChannelType[];

const channelAccountBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  external_identifier: z
    .string()
    .min(1, "Obligatorio")
    .max(255, "Máximo 255 caracteres"),
  // Nombre del secreto en Secret Manager (NO el secreto). Opcional: null/"" =
  // fallback a env en local/dev. NO es el access_token/app_secret.
  secret_name: z
    .string()
    .max(255, "Máximo 255 caracteres")
    .nullable()
    .optional()
    .or(z.literal("")),
  // Challenge de verificación de Meta (GET webhook). Editable en claro (no secreto duro).
  webhook_verify_token: z
    .string()
    .max(255, "Máximo 255 caracteres")
    .nullable()
    .optional()
    .or(z.literal("")),
  // id del número en WhatsApp Cloud API (para construir la URL /{phone_number_id}/messages).
  phone_number_id: z
    .string()
    .max(64, "Máximo 64 caracteres")
    .nullable()
    .optional()
    .or(z.literal("")),
});

export const channelAccountCreateSchema = channelAccountBase.extend({
  channel_type: z.enum(CHANNEL_TYPE_VALUES, {
    errorMap: () => ({ message: "Canal no válido" }),
  }),
});

export const channelAccountUpdateSchema = channelAccountBase.partial().extend({
  active: z.boolean().optional(),
  // channel_type NO se edita (define la cuenta; espeja el backend, que no lo
  // permite en el update — cambiar de canal = cuenta nueva). No se incluye.
});

export type ChannelAccountCreateInput = z.infer<typeof channelAccountCreateSchema>;
export type ChannelAccountUpdateInput = z.infer<typeof channelAccountUpdateSchema>;
