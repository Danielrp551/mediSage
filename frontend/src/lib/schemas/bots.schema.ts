import { z } from "zod";

import { BOT_TYPES } from "@/types/bots.types";

/**
 * Zod del módulo `bots` (F1) — compartidos por el form (cliente) y el Server
 * Action (server), drift imposible (regla del template). Mensajes visibles en
 * español; `path`/nombres de campo en inglés. Largos espejan los `Field(...)`
 * de los Pydantic schemas del backend (`bot_configuration.py`,
 * `bot_configuration_version.py`).
 *
 * Lo que Zod NO puede validar (queda como error de servidor en español, se
 * muestra en el MessageBar + inline del drawer): `BOT_CONFIGURATION_CODE_TAKEN`
 * (409, UNIQUE parcial `code WHERE deleted_at IS NULL` — el front no conoce los
 * otros bots).
 */

// ── BotConfiguration (tab Datos) ─────────────────────────

const botConfigurationBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  bot_type: z.enum(BOT_TYPES as unknown as [string, ...string[]], {
    errorMap: () => ({ message: "Tipo de bot no válido" }),
  }),
  description: z
    .string()
    .max(4000, "Máximo 4000 caracteres")
    .nullable()
    .optional()
    .or(z.literal("")),
  // Guard opcional: null/vacío = sin límite. Si se setea, entero ≥ 1.
  max_turns_per_conversation: z
    .number({ invalid_type_error: "Debe ser un número" })
    .int("Debe ser un entero")
    .positive("Debe ser mayor que 0")
    .nullable()
    .optional(),
});

export const botConfigurationCreateSchema = botConfigurationBase.extend({
  // Slug: minúsculas, números y guion bajo (espeja la UNIQUE parcial + convención de code).
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(40, "Máximo 40 caracteres")
    .regex(/^[a-z0-9_]+$/, "Solo minúsculas, números y guion bajo"),
});

export const botConfigurationUpdateSchema = botConfigurationBase.partial().extend({
  active: z.boolean().optional(),
  // `code` es inmutable en la UI (slug estable) → no se incluye en el update.
});

export type BotConfigurationCreateInput = z.infer<typeof botConfigurationCreateSchema>;
export type BotConfigurationUpdateInput = z.infer<typeof botConfigurationUpdateSchema>;

// ── BotConfigurationVersion (sub-dialog Nueva versión) ───

/**
 * Parámetros del proveedor. El form pasa el textarea como STRING crudo; el backend
 * recibe `parameters: jsonb` como OBJETO. El schema lo valida/normaliza a objeto.
 *
 * ⚠ IDEMPOTENTE a propósito: el MISMO schema lo corre el resolver de react-hook-form
 * (string→objeto al enviar el form) Y el Server Action (re-valida defensa-en-profundidad).
 * Tras el resolver, el Server Action recibe el valor YA transformado (objeto) → la rama
 * `z.record` lo acepta sin re-transformar. Si en cambio recibe el string crudo (llamada
 * directa al action), la rama string lo parsea. Sin la rama `z.record`, la 2ª pasada fallaría
 * con "Expected string, received object" y NINGUNA versión podría crearse desde la UI.
 */
const parametersField = z.union([
  z.record(z.unknown()), // ya es objeto (2ª pasada tras el resolver, o llamada con objeto)
  z
    .string()
    .trim()
    .transform((raw, ctx) => {
      if (raw === "") return {} as Record<string, unknown>;
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Parámetros: JSON inválido." });
        return z.NEVER;
      }
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: "Parámetros: JSON inválido." });
        return z.NEVER;
      }
      return parsed as Record<string, unknown>;
    }),
]);

// En el MVP el form solo habilita openai/claude; el resto está deshabilitado en
// el dropdown. El schema acepta solo estos dos (no hay forma de elegir otro
// desde la UI; `external_webhook`/webhook fields son F4, fuera de alcance).
export const botVersionSchema = z.object({
  provider: z.enum(["openai", "claude"], {
    errorMap: () => ({ message: "Proveedor no válido" }),
  }),
  model_name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  system_prompt: z
    .string()
    .min(1, "El prompt no puede estar vacío")
    .max(20000, "Máximo 20000 caracteres"),
  // El form pasa el textarea de JSON crudo; el schema lo transforma a objeto (idempotente).
  parameters: parametersField,
  notes: z.string().max(4000, "Máximo 4000 caracteres").nullable().optional().or(z.literal("")),
});

export type BotVersionInput = z.infer<typeof botVersionSchema>;
