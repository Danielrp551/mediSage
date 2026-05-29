import { z } from "zod";

import { CODE_SLUG_REGEX } from "./vertical.schema"; // reuse the 3–40 char slug regex

/** ISO 3166-1 alpha-2, two uppercase letters. */
export const COUNTRY_REGEX = /^[A-Z]{2}$/;
/** Decimal-as-string for lat/long; up to 6 decimal places. */
export const LATLONG_REGEX = /^-?\d{1,3}(\.\d{1,6})?$/;

const codeField = z
  .string()
  .min(3, "Mínimo 3 caracteres")
  .max(40, "Máximo 40 caracteres")
  .regex(
    CODE_SLUG_REGEX,
    "Slug en minúsculas: letras, dígitos, '_'. Empieza con letra, termina con letra o dígito.",
  );

const latitudeField = z
  .string()
  .regex(LATLONG_REGEX, "Latitud como -12.046374")
  .refine((s) => Math.abs(parseFloat(s)) <= 90, "La latitud va de -90 a 90")
  .nullable()
  .optional();

const longitudeField = z
  .string()
  .regex(LATLONG_REGEX, "Longitud como -77.042793")
  .refine((s) => Math.abs(parseFloat(s)) <= 180, "La longitud va de -180 a 180")
  .nullable()
  .optional();

const branchBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  address_line: z.string().min(1, "Obligatorio").max(255, "Máximo 255 caracteres"),
  district: z.string().max(120).nullable().optional(),
  city: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  region: z.string().max(120).nullable().optional(),
  country: z.string().regex(COUNTRY_REGEX, "Código ISO de 2 letras (ej. PE)").default("PE"),
  postal_code: z.string().max(20).nullable().optional(),
  latitude: latitudeField,
  longitude: longitudeField,
  phone: z.string().max(40).nullable().optional(),
  email: z.string().email("Correo inválido").max(255).nullable().optional().or(z.literal("")),
  // Validated against the curated IANA list; free-form fallback allowed but the
  // picker only offers the curated set (TIMEZONE_OPTIONS).
  timezone: z.string().min(1, "Obligatorio").max(60).default("America/Lima"),
});

export const branchCreateSchema = branchBase.extend({
  code: codeField,
});

export const branchUpdateSchema = branchBase.partial().extend({ active: z.boolean().optional() });

export type BranchCreateInput = z.infer<typeof branchCreateSchema>;
export type BranchUpdateInput = z.infer<typeof branchUpdateSchema>;
