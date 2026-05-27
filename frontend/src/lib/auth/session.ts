/**
 * Server-only session helpers. The browser never sees the tokens —
 * they live in httpOnly cookies and only Server Components / Server
 * Actions / route handlers can read or write them.
 *
 * Cookie lifetimes are derived from the backend's `expires_at` fields
 * (not hard-coded), so the cookie cannot outlive the JWT inside it.
 */

import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { decodeAccess } from "@/lib/auth/jwt";
import { COOKIES } from "@/lib/constants/cookies";
import { serverEnv } from "@/config/env";
import type { AuthenticatedUser, TokenPair } from "@/types/auth.types";

export interface SessionClaims {
  sub: string;
  exp: number;
  type: "access";
  roles: string[];
  permissions: string[];
}

export async function getAccessToken(): Promise<string | null> {
  return (await cookies()).get(COOKIES.ACCESS_TOKEN)?.value ?? null;
}

export async function getRefreshToken(): Promise<string | null> {
  return (await cookies()).get(COOKIES.REFRESH_TOKEN)?.value ?? null;
}

export async function getSessionClaims(): Promise<SessionClaims | null> {
  const token = await getAccessToken();
  if (!token) return null;
  try {
    return decodeAccess(token) as SessionClaims;
  } catch {
    return null;
  }
}

/** Use in Server Components / Server Actions that need an authenticated user. */
export async function requireAuth(): Promise<SessionClaims> {
  const claims = await getSessionClaims();
  if (!claims) redirect("/login");
  return claims;
}

export async function requirePermission(...codes: string[]): Promise<SessionClaims> {
  const claims = await requireAuth();
  const granted = new Set(claims.permissions);
  if (!codes.every((c) => granted.has(c))) redirect("/dashboard");
  return claims;
}

/** Seconds remaining from now until `iso`, clamped to >= 1. */
function maxAgeUntil(iso: string): number {
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(1, Math.floor(ms / 1000));
}

/** Cookie options shared by both tokens. Lifetime is per-call. */
function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: serverEnv.AUTH_COOKIE_SECURE,
    sameSite: "lax" as const,
    path: "/",
    domain: serverEnv.AUTH_COOKIE_DOMAIN || undefined,
    maxAge,
  };
}

export async function writeSession(tokens: TokenPair, _user: AuthenticatedUser): Promise<void> {
  const jar = await cookies();
  jar.set(
    COOKIES.ACCESS_TOKEN,
    tokens.access_token,
    cookieOptions(maxAgeUntil(tokens.access_expires_at)),
  );
  jar.set(
    COOKIES.REFRESH_TOKEN,
    tokens.refresh_token,
    cookieOptions(maxAgeUntil(tokens.refresh_expires_at)),
  );
}

export async function clearSession(): Promise<void> {
  const jar = await cookies();
  jar.delete(COOKIES.ACCESS_TOKEN);
  jar.delete(COOKIES.REFRESH_TOKEN);
}
