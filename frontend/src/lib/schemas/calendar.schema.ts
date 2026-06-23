/**
 * Zod del módulo `calendar` (#9). Lo importan tanto el form (cliente) como el Server Action
 * (server) → drift imposible (regla del template). Mensajes visibles en español; `path`/
 * nombres de campo en inglés.
 *
 * Sólo el mapeo de sources necesita Zod: el OAuth es un redirect sin form y el disconnect es
 * un DELETE sin body. Molde directo de `office-hours.schema.ts` (el bulk-replace de
 * `OfficeOperatingHours`). Espejo de `CalendarSourceCreate`/`CalendarSourcesReplace` del
 * backend (`calendar/schemas/source.py`).
 */

import { z } from "zod";

// Una fila del mapeo: un calendario externo → una sede (o "todas"). `external_calendar_id` y
// `_name` vienen de la opción elegida (list_calendars), no los teclea el usuario.
const sourceCreateSchema = z.object({
  external_calendar_id: z.string().min(1, "Calendario obligatorio"),
  external_calendar_name: z.string().min(1, "Nombre de calendario obligatorio"),
  // null/ausente = "todas las sedes" (decisión LOCKED #3). El backend valida que la sede
  // exista (404 BRANCH_NOT_FOUND); Zod sólo asegura el shape.
  branch_id: z.string().min(1).nullable().optional(),
  is_enabled: z.boolean().optional().default(true),
});

// Body del PUT bulk replace. min 0: mandar [] borra todos los mapeos de la conexión (mismo
// criterio que `officeHoursReplaceSchema` con hours: []).
export const sourcesReplaceSchema = z.object({
  sources: z.array(sourceCreateSchema),
});

export type SourceCreateInput = z.infer<typeof sourceCreateSchema>;
export type SourcesReplaceInput = z.infer<typeof sourcesReplaceSchema>;
