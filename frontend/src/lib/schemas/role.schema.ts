import { z } from "zod";

export const roleCreateSchema = z.object({
  name: z.string().min(2).max(80),
  description: z.string().min(1).max(255),
  permission_ids: z.array(z.string()).default([]),
});

export const roleUpdateSchema = z.object({
  name: z.string().min(2).max(80).optional(),
  description: z.string().min(1).max(255).optional(),
  active: z.boolean().optional(),
  permission_ids: z.array(z.string()).optional(),
});

export type RoleCreateInput = z.infer<typeof roleCreateSchema>;
export type RoleUpdateInput = z.infer<typeof roleUpdateSchema>;
