import { z } from "zod";

/** "HH:MM" 24h, 00:00–23:59. Stored as `time` (no TZ) on the backend. */
export const TIME_HHMM_REGEX = /^([01]\d|2[0-3]):[0-5]\d$/;

const timeField = z.string().regex(TIME_HHMM_REGEX, "Hora como HH:MM (24h)");

const hoursBlockSchema = z
  .object({
    // 0 = lunes … 6 = domingo (Python datetime.weekday()).
    day_of_week: z.number().int().min(0, "Día inválido").max(6, "Día inválido"),
    opens_at: timeField,
    closes_at: timeField,
  })
  .superRefine((block, ctx) => {
    // Mirror of the backend CHECK closes_at > opens_at. A block never crosses
    // midnight; if needed, model it as two blocks across two days.
    if (block.closes_at <= block.opens_at) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["closes_at"],
        message: "La hora de cierre debe ser mayor que la de apertura.",
      });
    }
  });

// Body of the bulk PUT. Multiple blocks per day are allowed (mañana + tarde).
// The array can be empty (office with no recurring pattern yet). The per-day
// no-overlap refinement mirrors the backend `OfficeOperatingHoursReplace`
// validator so an overlapping pattern is caught client-side (Spanish message)
// instead of surfacing the backend's English 422.
export const officeHoursReplaceSchema = z
  .object({ hours: z.array(hoursBlockSchema) })
  .superRefine((data, ctx) => {
    const byDay = new Map<number, { opens: string; closes: string; idx: number }[]>();
    data.hours.forEach((h, idx) => {
      const arr = byDay.get(h.day_of_week) ?? [];
      arr.push({ opens: h.opens_at, closes: h.closes_at, idx });
      byDay.set(h.day_of_week, arr);
    });
    for (const arr of byDay.values()) {
      // Sort by opening time; adjacent blocks (next.opens == prev.closes) are OK.
      const sorted = [...arr].sort((a, b) => a.opens.localeCompare(b.opens));
      for (let i = 1; i < sorted.length; i++) {
        const prev = sorted[i - 1];
        const cur = sorted[i];
        if (prev && cur && cur.opens < prev.closes) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["hours", cur.idx, "opens_at"],
            message: "Este bloque se solapa con otro del mismo día.",
          });
        }
      }
    }
  });

export type OfficeHoursBlockInput = z.infer<typeof hoursBlockSchema>;
export type OfficeHoursReplaceInput = z.infer<typeof officeHoursReplaceSchema>;
