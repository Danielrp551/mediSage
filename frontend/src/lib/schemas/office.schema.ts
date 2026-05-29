import { z } from "zod";

/**
 * Office code regex mirrors the backend `CODE_PATTERN` in
 * `clinic/schemas/office.py`: 2–40 chars, letters/digits/-/_, starting and
 * ending with a letter or digit. Looser than catalog slugs on purpose so the
 * usual room identifiers ("C-03", "ESTETICA-01") are valid — do NOT reuse the
 * lowercase CODE_SLUG_REGEX here, it would reject those.
 */
export const OFFICE_CODE_REGEX = /^[A-Za-z0-9][A-Za-z0-9_-]{0,38}[A-Za-z0-9]$/;

const codeField = z
  .string()
  .min(2, "Mínimo 2 caracteres")
  .max(40, "Máximo 40 caracteres")
  .regex(
    OFFICE_CODE_REGEX,
    "2 a 40 caracteres: letras, dígitos, '-' o '_'. Empieza y termina con letra o dígito.",
  );

const officeBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  room_number: z.string().max(20).nullable().optional(),
  floor: z.string().max(20).nullable().optional(),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  // M:N apt verticals. Backend tolerates an empty list, but the create form
  // requires at least one (an office apt for nothing is useless); on update the
  // list is optional — when present it's a full replace, when omitted untouched.
  vertical_ids: z.array(z.string()).default([]),
});

export const officeCreateSchema = officeBase.extend({
  branch_id: z.string().min(1, "Elige una sede"),
  code: codeField,
  vertical_ids: z.array(z.string()).min(1, "Selecciona al menos una vertical."),
});

// On update, vertical_ids is optional: when present the backend does a full
// replace of office_vertical; when omitted the M:N is left untouched.
export const officeUpdateSchema = officeBase.partial().extend({ active: z.boolean().optional() });

export type OfficeCreateInput = z.infer<typeof officeCreateSchema>;
export type OfficeUpdateInput = z.infer<typeof officeUpdateSchema>;
