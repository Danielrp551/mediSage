/**
 * Centralised, typed env access. Anything not prefixed with `NEXT_PUBLIC_`
 * is server-only and throws if read on the client.
 */

import "server-only";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

/**
 * Secure cookies on by default in production builds (Vercel / `next start`).
 * Local `next dev` over plain HTTP keeps Secure off so the browser actually
 * accepts the cookie. Explicit `AUTH_COOKIE_SECURE=true|false` overrides.
 */
function resolveCookieSecure(): boolean {
  const raw = process.env.AUTH_COOKIE_SECURE;
  if (raw === "true") return true;
  if (raw === "false") return false;
  return process.env.NODE_ENV === "production";
}

export const serverEnv = {
  BACKEND_URL: required("BACKEND_URL"),
  AUTH_COOKIE_DOMAIN: process.env.AUTH_COOKIE_DOMAIN ?? "",
  AUTH_COOKIE_SECURE: resolveCookieSecure(),
} as const;

export const publicEnv = {
  APP_URL: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
} as const;
