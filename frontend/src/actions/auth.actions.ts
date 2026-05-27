"use server";

import { redirect } from "next/navigation";

import { backendClient } from "@/services/backend.client";
import { clearSession, getRefreshToken, writeSession } from "@/lib/auth/session";
import { loginSchema } from "@/lib/schemas/auth.schema";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import { HttpError } from "@/types/api.types";
import type { LoginResponseBody } from "@/types/auth.types";

interface ActionState {
  ok: boolean;
  error?: string;
  fieldErrors?: Record<string, string[]>;
}

export async function loginAction(_prev: ActionState | null, formData: FormData): Promise<ActionState> {
  const parsed = loginSchema.safeParse({
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }

  try {
    const body = await backendClient.post<LoginResponseBody>(
      ENDPOINTS.AUTH.LOGIN,
      parsed.data,
      { anonymous: true },
    );
    await writeSession(body.tokens, body.user);
  } catch (e) {
    if (e instanceof HttpError) {
      return { ok: false, error: e.message };
    }
    return { ok: false, error: "Unexpected error" };
  }

  // outside try/catch — redirect throws by design
  const redirectTo = (formData.get("redirect") as string) || "/dashboard";
  redirect(redirectTo);
}

export async function logoutAction(): Promise<void> {
  const refresh = await getRefreshToken();
  if (refresh) {
    // Fire-and-forget — even if the server can't reach the backend, kill the local session.
    try {
      await backendClient.post(ENDPOINTS.AUTH.LOGOUT, { refresh_token: refresh });
    } catch {
      /* ignore */
    }
  }
  await clearSession();
  redirect("/login");
}
