import { z } from "zod";

/**
 * Zod del catálogo de herramientas (`bots` F2) — compartido por el form (cliente)
 * y el Server Action (server), drift imposible (regla del template). Mensajes
 * visibles en español; `path`/nombres de campo en inglés. Largos espejan los
 * `Field(...)` de los Pydantic schemas del backend (`bot_tool.py`).
 *
 * Lo que Zod NO puede validar (queda como error de servidor en español, se muestra
 * en el MessageBar + inline del drawer): `BOT_TOOL_CODE_TAKEN` (409, UNIQUE parcial
 * `code WHERE deleted_at IS NULL` — el front no conoce las otras tools).
 */

/**
 * `parameters_schema` (JSON Schema): el form lo edita como TEXTAREA crudo (string),
 * pero el backend lo recibe como OBJETO. El MISMO schema lo corre el resolver de
 * react-hook-form (string→objeto al enviar) Y el Server Action (re-valida defensa
 * en profundidad → recibe el objeto YA transformado).
 *
 * ⚠ IDEMPOTENTE a propósito (lección F1 de versiones): sin la rama `z.record`, la
 * 2ª pasada (action, sobre el objeto ya transformado) fallaría con "Expected string,
 * received object" y NINGUNA herramienta podría crearse desde la UI. La rama string
 * parsea el textarea; la rama record acepta el objeto en la 2ª pasada. Vacío = {}.
 */
const parametersSchemaField = z.union([
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
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Esquema de parámetros: JSON inválido.",
        });
        return z.NEVER;
      }
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Esquema de parámetros: JSON inválido.",
        });
        return z.NEVER;
      }
      return parsed as Record<string, unknown>;
    }),
]);

const botToolBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().min(1, "Obligatorio").max(4000, "Máximo 4000 caracteres"),
  // Textarea de JSON Schema crudo → objeto (idempotente). Vacío = {}.
  parameters_schema: parametersSchemaField,
  target_service: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  requires_confirmation: z.boolean().optional(),
});

export const botToolCreateSchema = botToolBase.extend({
  // Slug: minúsculas, números y guion bajo (espeja la UNIQUE parcial + convención de code).
  code: z
    .string()
    .min(1, "Obligatorio")
    .max(60, "Máximo 60 caracteres")
    .regex(/^[a-z0-9_]+$/, "Solo minúsculas, números y guion bajo"),
});

export const botToolUpdateSchema = botToolBase.extend({
  active: z.boolean().optional(),
  // `code` es inmutable en la UI (slug estable) → no se incluye en el update.
});

export type BotToolCreateInput = z.infer<typeof botToolCreateSchema>;
export type BotToolUpdateInput = z.infer<typeof botToolUpdateSchema>;

// ── M:N tools del bot (bulk replace) ─────────────────────

export const configurationToolsSchema = z.object({
  tool_ids: z.array(z.string()).default([]),
});

export type ConfigurationToolsInput = z.infer<typeof configurationToolsSchema>;
