/**
 * Isomorphic Zod schemas — used both by client-side `react-hook-form`
 * resolvers AND by Server Actions for revalidation.
 */

import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().email("Invalid email"),
  password: z.string().min(1, "Required"),
});

export type LoginInput = z.infer<typeof loginSchema>;

export const passwordChangeSchema = z
  .object({
    current_password: z.string().min(1, "Required"),
    new_password: z
      .string()
      .min(8, "Min 8 characters")
      .max(128, "Max 128 characters")
      .regex(/[A-Z]/, "Needs an uppercase letter")
      .regex(/[a-z]/, "Needs a lowercase letter")
      .regex(/[0-9]/, "Needs a digit"),
    confirm_password: z.string(),
  })
  .refine((d) => d.new_password === d.confirm_password, {
    path: ["confirm_password"],
    message: "Passwords do not match",
  });

export type PasswordChangeInput = z.infer<typeof passwordChangeSchema>;
