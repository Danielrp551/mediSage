import { z } from "zod";

import { CODE_SLUG_60_REGEX } from "./vertical.schema";

/**
 * Service slug. Same shape as the vertical slug but up to 60 chars, mirroring
 * the backend's `CODE_PATTERN` (`{1,58}`). Stable and non-editable post-create.
 */
const codeField = z
  .string()
  .min(3, "Mínimo 3 caracteres")
  .max(60, "Máximo 60 caracteres")
  .regex(
    CODE_SLUG_60_REGEX,
    "Slug en minúsculas: letras, dígitos, '_'. Empieza con letra, termina con letra o dígito.",
  );

const serviceBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  display_order: z.number().int().min(0).max(9999).default(0),
});

export const serviceCreateSchema = serviceBase.extend({
  vertical_id: z.string().min(1, "Elige una vertical"),
  code: codeField,
});

export const serviceUpdateSchema = serviceBase.partial().extend({ active: z.boolean().optional() });

export type ServiceCreateInput = z.infer<typeof serviceCreateSchema>;
export type ServiceUpdateInput = z.infer<typeof serviceUpdateSchema>;
