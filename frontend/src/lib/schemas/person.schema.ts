import { z } from "zod";

import { identifierFields } from "./contact-identifier.schema";

/**
 * Zod del create/update de `Person`. El create lleva una lista OPCIONAL de
 * `identifiers` anidados (reusa `identifierFields` de contact-identifier.schema).
 * El dedup contra BD lo hace el backend (`IDENTIFIER_TAKEN`, 409); el front
 * previene el dedup DENTRO del propio body con un `superRefine` (dos identifiers
 * con el mismo (channel_type, identifier)) + máx 1 `is_primary` por canal.
 *
 * `personCreateSchema` NO crea lead automáticamente — espeja `person.create` del
 * backend (crea la Person + identifiers nested). El lead se crea aparte desde el
 * tab Lead (F3).
 */

// Documento: texto libre acotado (DNI/RUC/CE). NO se valida formato estricto en
// Zod (el backend lo acepta como varchar); sólo el largo.
const personBase = z.object({
  first_name: z.string().min(1, "Obligatorio").max(80, "Máximo 80 caracteres"),
  last_name: z.string().min(1, "Obligatorio").max(80, "Máximo 80 caracteres"),
  second_last_name: z.string().max(80, "Máximo 80 caracteres").nullable().optional(),
  document_type: z.string().max(20).nullable().optional(),
  document_number: z.string().max(40, "Máximo 40 caracteres").nullable().optional(),
  birth_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD")
    .nullable()
    .optional()
    // El <input type="date"> vacío emite "" — lo transformamos a null. El backend
    // (`birth_date: date | None`) rechaza "" con 422; sin esto, guardar cualquier
    // persona sin fecha de nacimiento (create o update) fallaría con "Validation failed".
    .or(z.literal("").transform(() => null)),
  gender: z.string().max(20, "Máximo 20 caracteres").nullable().optional(),
  address: z.string().max(255, "Máximo 255 caracteres").nullable().optional(),
  notes: z.string().max(5000, "Máximo 5000 caracteres").nullable().optional(),
});

// Identificador inicial dentro del create de Person (mismas reglas que el CRUD
// anidado, sin el superRefine por canal — el create del drawer es más laxo; el
// backend valida el dedup). `identifierFields` = el objeto Zod base reutilizado.
const personInitialIdentifierSchema = z.object(identifierFields);

export const personCreateSchema = personBase
  .extend({
    identifiers: z.array(personInitialIdentifierSchema).optional().default([]),
  })
  .superRefine((data, ctx) => {
    // Dedup dentro del propio body: dos identifiers con el mismo
    // (channel_type, identifier) serían rechazados por el backend
    // (IDENTIFIER_TAKEN). Lo prevenimos en español.
    const seen = new Map<string, number>();
    (data.identifiers ?? []).forEach((it, i) => {
      const key = `${it.channel_type}::${it.identifier.trim().toLowerCase()}`;
      if (seen.has(key)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["identifiers", i, "identifier"],
          message: "Este identificador ya está repetido en la lista.",
        });
      } else {
        seen.set(key, i);
      }
    });
    // Como máximo un is_primary por (person, channel_type) en el body.
    const primaryByChannel = new Set<string>();
    (data.identifiers ?? []).forEach((it, i) => {
      if (!it.is_primary) return;
      if (primaryByChannel.has(it.channel_type)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["identifiers", i, "is_primary"],
          message: "Sólo un identificador principal por canal.",
        });
      } else {
        primaryByChannel.add(it.channel_type);
      }
    });
  });

export const personUpdateSchema = personBase.partial().extend({
  active: z.boolean().optional(),
});

export type PersonCreateInput = z.infer<typeof personCreateSchema>;
export type PersonUpdateInput = z.infer<typeof personUpdateSchema>;
