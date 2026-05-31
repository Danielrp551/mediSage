import { z } from "zod";

// "HH:MM" 24h, 00:00–23:59. El form trabaja en "HH:MM"; el action serializa a
// "HH:MM:SS" antes de mandar al backend (que acepta ambos, almacena `time` sin TZ).
export const TIME_HHMM_REGEX = /^([01]\d|2[0-3]):[0-5]\d$/;
// "YYYY-MM-DD". El backend la almacena como `date` sin TZ.
export const DATE_ISO_REGEX = /^\d{4}-\d{2}-\d{2}$/;

const timeField = z.string().regex(TIME_HHMM_REGEX, "Hora como HH:MM (24h)");
const dateField = z.string().regex(DATE_ISO_REGEX, "Fecha como AAAA-MM-DD");

// Un bloque concreto. Mirror del model_validator del backend (closes>opens) y de
// los FK obligatorios (branch_id/office_id). El emparejamiento office↔branch y el
// doctor↔branch son invariantes de service (OFFICE_NOT_IN_BRANCH /
// DOCTOR_NOT_IN_BRANCH), no validables en Zod (cruzan datos): se muestran como
// error de servidor.
export const doctorAvailabilityBlockSchema = z
  .object({
    branch_id: z.string().min(1, "Elige una sede"),
    office_id: z.string().min(1, "Elige un consultorio"),
    date: dateField,
    opens_at: timeField,
    closes_at: timeField,
  })
  .superRefine((block, ctx) => {
    // Un bloque nunca cruza medianoche; si hiciera falta, se modela como dos
    // bloques en dos fechas. Espeja el CHECK ck_doctor_availability_closes_after_opens.
    if (block.closes_at <= block.opens_at) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["closes_at"],
        message: "La hora de cierre debe ser mayor que la de apertura.",
      });
    }
  });

// Alta masiva: el body del POST. Permite varios bloques (mismo doctor) repartidos
// en varias fechas. Además del closes>opens por bloque, valida NO-SOLAPAMIENTO
// entre bloques del MISMO día dentro del propio body (el backend además cruza con
// los existentes en BD). Adyacentes (next.opens == prev.closes) son válidos.
export const doctorAvailabilityBulkSchema = z
  .object({
    blocks: z.array(doctorAvailabilityBlockSchema).min(1, "Agrega al menos un bloque"),
  })
  .superRefine((data, ctx) => {
    const byDate = new Map<string, { i: number; opens: string; closes: string }[]>();
    data.blocks.forEach((b, i) => {
      const arr = byDate.get(b.date) ?? [];
      arr.push({ i, opens: b.opens_at, closes: b.closes_at });
      byDate.set(b.date, arr);
    });
    for (const group of byDate.values()) {
      group.sort((a, b) => a.opens.localeCompare(b.opens));
      for (let k = 1; k < group.length; k++) {
        const prev = group[k - 1];
        const cur = group[k];
        if (prev && cur && cur.opens < prev.closes) {
          // adyacentes (==) OK; solapados (<) error
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["blocks", cur.i, "opens_at"],
            message: "Este bloque se solapa con otro del mismo día.",
          });
        }
      }
    }
  });

// Editar un bloque: todos opcionales, pero si vienen opens_at Y closes_at se valida
// la relación. (El cross-field completo y el no-overlap con vecinos del día los hace
// el backend con los datos de BD; aquí sólo el sanity local.)
export const doctorAvailabilityUpdateSchema = z
  .object({
    branch_id: z.string().min(1).optional(),
    office_id: z.string().min(1).optional(),
    date: dateField.optional(),
    opens_at: timeField.optional(),
    closes_at: timeField.optional(),
  })
  .superRefine((b, ctx) => {
    if (b.opens_at && b.closes_at && b.closes_at <= b.opens_at) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["closes_at"],
        message: "La hora de cierre debe ser mayor que la de apertura.",
      });
    }
  });

export type DoctorAvailabilityBlockInput = z.infer<typeof doctorAvailabilityBlockSchema>;
export type DoctorAvailabilityBulkInput = z.infer<typeof doctorAvailabilityBulkSchema>;
export type DoctorAvailabilityUpdateInput = z.infer<typeof doctorAvailabilityUpdateSchema>;
