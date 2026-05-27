import { z } from "zod";

export const permissionCreateSchema = z.object({
  code: z
    .string()
    .min(2)
    .max(80)
    .regex(/^[A-Z0-9_\-]+$/, "Use uppercase letters, digits, `_` or `-`"),
  name: z.string().min(2).max(120),
  description: z.string().max(255).default(""),
  module: z.string().min(2).max(60),
});

export const permissionUpdateSchema = permissionCreateSchema.partial().extend({
  active: z.boolean().optional(),
});

export type PermissionCreateInput = z.infer<typeof permissionCreateSchema>;
export type PermissionUpdateInput = z.infer<typeof permissionUpdateSchema>;
