import { z } from "zod";

import { DOCUMENT_RULES, DOCUMENT_TYPES, type DocumentType } from "./user.schema";

// Normaliza "" → undefined ANTES de validar, manteniendo el tipo inferido como
// `string | undefined` (sin literal "") para que `{...field} value={...}` de
// react-hook-form + Fluent compile sin TS2783 (mismo idiom que el molde admin).
const emptyToUndefined = (v: unknown) => (v === "" ? undefined : v);

/**
 * Parte "user" anidada del create de doctor. Espeja el `userCreateSchema` del
 * admin (mismas reglas de documento, mismos límites) PERO sin `role_ids` /
 * `permission_ids` — el service asigna el role DOCTOR. El `password` es opcional:
 * si falta (o vacío), el backend genera una contraseña temporal y la devuelve en
 * `generated_password`.
 *
 * Se deja como `ZodObject` plano (sin `.superRefine`) para que la inferencia de
 * `z.infer` del schema padre conserve todas las claves anidadas; el refinamiento
 * de documento vive en `doctorCreateSchema` con `path: ["user", ...]`.
 */
const doctorUserSchema = z.object({
  email: z.string().email("Correo electrónico inválido."),
  first_name: z.string().min(1, "El nombre es obligatorio.").max(80, "Máximo 80 caracteres."),
  last_name: z.string().min(1, "El apellido es obligatorio.").max(80, "Máximo 80 caracteres."),
  second_last_name: z.string().max(80, "Máximo 80 caracteres.").optional().nullable(),
  document_type: z.enum(DOCUMENT_TYPES).optional().nullable(),
  document_number: z.string().max(40, "Máximo 40 caracteres.").optional().nullable(),
  phone: z.string().max(40, "Máximo 40 caracteres.").optional().nullable(),
  // Vacío permitido (el backend genera la contraseña); si se escribe, mín. 8.
  // "" se normaliza a undefined antes de validar (no dispara el min(8)).
  password: z.preprocess(
    emptyToUndefined,
    z
      .string()
      .min(8, "La contraseña debe tener al menos 8 caracteres.")
      .max(128, "Máximo 128 caracteres.")
      .optional(),
  ),
});

// Refinamiento de documento anidado (cuando type Y number vienen, el number debe
// matchear el formato del type). Espeja `refineDocument` del admin.
function refineNestedUserDocument(
  data: { user?: { document_type?: DocumentType | null; document_number?: string | null } },
  ctx: z.RefinementCtx,
): void {
  const type = data.user?.document_type;
  const number = data.user?.document_number?.trim();
  if (!type || !number) return;
  const rule = DOCUMENT_RULES[type];
  if (!rule.regex.test(number)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["user", "document_number"],
      message: rule.message,
    });
  }
}

// ── Campos propios del Doctor ──
// CMP es texto libre acotado (Colegio Médico u homólogo); NO es un slug.
const doctorProfileBase = z.object({
  cmp_code: z.string().max(40, "Máximo 40 caracteres.").nullable().optional(),
  bio: z.string().max(5000, "Máximo 5000 caracteres.").nullable().optional(),
  photo_url: z.preprocess(
    emptyToUndefined,
    z.string().url("URL inválida.").max(500, "Máximo 500 caracteres.").nullable().optional(),
  ),
  signature_url: z.preprocess(
    emptyToUndefined,
    z.string().url("URL inválida.").max(500, "Máximo 500 caracteres.").nullable().optional(),
  ),
  slot_duration_min: z
    .number({ invalid_type_error: "Indica los minutos." })
    .int("Debe ser un número entero.")
    .min(5, "Mínimo 5 minutos.")
    .max(240, "Máximo 240 minutos.")
    .default(30),
});

export const doctorCreateSchema = doctorProfileBase
  .extend({
    user: doctorUserSchema,
    branch_ids: z.array(z.string()).min(1, "Elige al menos una sede."),
    vertical_ids: z.array(z.string()).min(1, "Elige al menos una vertical."),
  })
  .superRefine(refineNestedUserDocument);

// Update: NO incluye `user` (se gestiona en admin) ni `user_id` (inmutable).
// branch_ids/vertical_ids opcionales: presentes = full replace del M:N.
export const doctorUpdateSchema = doctorProfileBase.partial().extend({
  branch_ids: z.array(z.string()).optional(),
  vertical_ids: z.array(z.string()).optional(),
  active: z.boolean().optional(),
});

// Self-service update (perfil propio del doctor logueado, fase F3). El backend
// SOLO acepta estos campos en `PUT /me/doctor` (ignora branch_ids/vertical_ids/
// active aunque lleguen); el self NUNCA edita sus sedes/verticales/estado (eso es
// admin). Mismas reglas de validación que `doctorProfileBase` para los campos en
// común. NO toca doctorCreate/doctorUpdate.
export const doctorSelfUpdateSchema = doctorProfileBase.partial();

export type DoctorCreateInput = z.infer<typeof doctorCreateSchema>;
export type DoctorUpdateInput = z.infer<typeof doctorUpdateSchema>;
export type DoctorSelfUpdateInput = z.infer<typeof doctorSelfUpdateSchema>;
