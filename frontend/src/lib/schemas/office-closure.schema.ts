import { z } from "zod";

export const officeClosureCreateSchema = z
  .object({
    // <input type="datetime-local"> produces "YYYY-MM-DDTHH:MM"; the action
    // converts to ISO 8601 with offset before sending. Keep as string here.
    starts_at: z.string().min(1, "Obligatorio"),
    ends_at: z.string().min(1, "Obligatorio"),
    is_closed: z.boolean().default(true),
    reason: z.string().min(1, "Obligatorio").max(255, "Máximo 255 caracteres"),
  })
  .superRefine((data, ctx) => {
    // Mirror of the backend CHECK ends_at > starts_at.
    if (new Date(data.ends_at).getTime() <= new Date(data.starts_at).getTime()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["ends_at"],
        message: "El fin debe ser posterior al inicio.",
      });
    }
  });

export type OfficeClosureCreateInput = z.infer<typeof officeClosureCreateSchema>;
