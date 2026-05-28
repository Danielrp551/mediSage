import { z } from "zod";

/**
 * Slug regex mirrors the backend's `CODE_PATTERN`:
 * lowercase letter at the start, letters/digits/underscores in the
 * middle, letter or digit at the end, 3–40 chars total. Bots and reports
 * rely on this being stable — the field is non-editable post-creation.
 */
export const CODE_SLUG_REGEX = /^[a-z][a-z0-9_]{1,38}[a-z0-9]$/;

/** Hex colour `#RRGGBB`. The colour picker writes uppercase; we accept both. */
export const HEX_COLOR_REGEX = /^#[0-9A-Fa-f]{6}$/;

const codeField = z
  .string()
  .min(3, "Mínimo 3 caracteres")
  .max(40, "Máximo 40 caracteres")
  .regex(
    CODE_SLUG_REGEX,
    "Slug en minúsculas: letras, dígitos, '_'. Empieza con letra, termina con letra o dígito.",
  );

const colorField = z
  .string()
  .regex(HEX_COLOR_REGEX, "Color hex como #RRGGBB")
  .nullable()
  .optional();

const verticalBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  color: colorField,
  icon: z.string().max(60).nullable().optional(),
  display_order: z.number().int().min(0).max(9999).default(0),
});

export const verticalCreateSchema = verticalBase.extend({
  code: codeField,
});

export const verticalUpdateSchema = verticalBase
  .partial()
  .extend({ active: z.boolean().optional() });

export type VerticalCreateInput = z.infer<typeof verticalCreateSchema>;
export type VerticalUpdateInput = z.infer<typeof verticalUpdateSchema>;
