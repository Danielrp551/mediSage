import { z } from "zod";

/**
 * Document type catalogue (Peru). Adjust for your country.
 *
 * - DNI (Documento Nacional de Identidad): 8 digits.
 * - RUC (Registro Único de Contribuyentes): 11 digits, starts with
 *   10 (natural person), 15, 17, or 20 (legal entity).
 * - CE (Carné de Extranjería): 9–12 alphanumeric chars.
 *
 * `DOCUMENT_RULES` is the single source of truth — used by:
 *   - The Zod refinement here (server-friendly errors).
 *   - The Dropdown options in `UserDrawer` (`<Option value="...">`).
 *   - The dynamic hint text shown next to the document number input.
 */
export const DOCUMENT_TYPES = ["DNI", "RUC", "CE"] as const;
export type DocumentType = (typeof DOCUMENT_TYPES)[number];

export const DOCUMENT_RULES: Record<
  DocumentType,
  { regex: RegExp; hint: string; message: string }
> = {
  DNI: {
    regex: /^\d{8}$/,
    hint: "8 digits",
    message: "DNI must be exactly 8 digits.",
  },
  RUC: {
    regex: /^(10|15|17|20)\d{9}$/,
    hint: "11 digits, starts with 10, 15, 17 or 20",
    message: "RUC must be 11 digits starting with 10, 15, 17 or 20.",
  },
  CE: {
    regex: /^[A-Za-z0-9]{9,12}$/,
    hint: "9–12 alphanumeric characters",
    message: "CE must be 9–12 alphanumeric characters.",
  },
};

const documentTypeSchema = z.enum(DOCUMENT_TYPES).optional().nullable();

// Cross-field refinement: when both type AND number are provided, the
// number must match the type's format. Either field empty → no check
// (both are optional individually).
function refineDocument<
  T extends {
    document_type?: DocumentType | null;
    document_number?: string | null;
  },
>(data: T, ctx: z.RefinementCtx): void {
  const type = data.document_type;
  const number = data.document_number?.trim();
  if (!type || !number) return;
  const rule = DOCUMENT_RULES[type];
  if (!rule.regex.test(number)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["document_number"],
      message: rule.message,
    });
  }
}

const userBase = z.object({
  email: z.string().email(),
  first_name: z.string().min(1).max(80),
  last_name: z.string().min(1).max(80),
  second_last_name: z.string().max(80).optional().nullable(),
  document_type: documentTypeSchema,
  document_number: z.string().max(40).optional().nullable(),
  phone: z.string().max(40).optional().nullable(),
  role_ids: z.array(z.string()).default([]),
  permission_ids: z.array(z.string()).default([]),
  password: z.string().min(8).max(128).optional(),
});

export const userCreateSchema = userBase.superRefine(refineDocument);

export const userUpdateSchema = userBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineDocument);

export type UserCreateInput = z.infer<typeof userCreateSchema>;
export type UserUpdateInput = z.infer<typeof userUpdateSchema>;
