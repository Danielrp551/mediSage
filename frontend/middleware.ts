/**
 * Edge middleware — gates protected routes AND refreshes the access
 * token transparently before any RSC renders.
 *
 * Order of checks for a protected path:
 *   1. Access cookie present and not within `EXPIRY_SKEW_SECONDS` of
 *      `exp` → continue.
 *   2. Otherwise, refresh cookie present → POST `/auth/refresh` against
 *      the backend. On 200, rewrite both cookies and continue. On 4xx,
 *      clear cookies and redirect to `/login`.
 *   3. No refresh cookie → redirect to `/login`.
 *
 * Doing this here (instead of in `backend.client.ts`) avoids the
 * Next.js 16 limitation: `cookies().set()` only works inside Server
 * Actions / route handlers, not Server Components. Middleware writes
 * cookies on the response object directly, which is always allowed.
 */

import { decodeJwt } from "jose";
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/api/auth"];
const ACCESS_COOKIE = "access_token";
const REFRESH_COOKIE = "refresh_token";
const EXPIRY_SKEW_SECONDS = 30;

interface TokenPair {
  access_token: string;
  refresh_token: string;
  access_expires_at: string;
  refresh_expires_at: string;
}

interface RefreshResponse {
  success: true;
  tokens: TokenPair;
}

function isPublic(pathname: string): boolean {
  return pathname === "/" || PUBLIC_PATHS.some((p) => pathname.startsWith(p));
}

function isFresh(token: string): boolean {
  try {
    const { exp } = decodeJwt(token);
    if (typeof exp !== "number") return false;
    return exp - Math.floor(Date.now() / 1000) > EXPIRY_SKEW_SECONDS;
  } catch {
    return false;
  }
}

function resolveSecure(): boolean {
  // Mirror `src/config/env.ts:resolveCookieSecure` — kept inline so the
  // edge bundle doesn't drag in the server-only module.
  const raw = process.env.AUTH_COOKIE_SECURE;
  if (raw === "true") return true;
  if (raw === "false") return false;
  return process.env.NODE_ENV === "production";
}

function cookieAttrs(maxAgeMs: number) {
  return {
    httpOnly: true,
    secure: resolveSecure(),
    sameSite: "lax" as const,
    path: "/",
    domain: process.env.AUTH_COOKIE_DOMAIN || undefined,
    maxAge: Math.max(1, Math.floor(maxAgeMs / 1000)),
  };
}

function applyTokens(res: NextResponse, tokens: TokenPair): void {
  const now = Date.now();
  res.cookies.set(
    ACCESS_COOKIE,
    tokens.access_token,
    cookieAttrs(new Date(tokens.access_expires_at).getTime() - now),
  );
  res.cookies.set(
    REFRESH_COOKIE,
    tokens.refresh_token,
    cookieAttrs(new Date(tokens.refresh_expires_at).getTime() - now),
  );
}

async function refreshAtEdge(refreshToken: string): Promise<TokenPair | null> {
  const backendUrl = process.env.BACKEND_URL;
  if (!backendUrl) return null;

  try {
    const res = await fetch(`${backendUrl}/api/v1/admin/auth/refresh`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as RefreshResponse;
    return body.tokens;
  } catch {
    return null;
  }
}

function redirectToLogin(req: NextRequest): NextResponse {
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("redirect", req.nextUrl.pathname + req.nextUrl.search);
  const res = NextResponse.redirect(url);
  res.cookies.delete(ACCESS_COOKIE);
  res.cookies.delete(REFRESH_COOKIE);
  return res;
}

export async function middleware(req: NextRequest) {
  if (isPublic(req.nextUrl.pathname)) return NextResponse.next();

  const access = req.cookies.get(ACCESS_COOKIE)?.value;
  if (access && isFresh(access)) {
    return NextResponse.next();
  }

  const refresh = req.cookies.get(REFRESH_COOKIE)?.value;
  if (!refresh) return redirectToLogin(req);

  const tokens = await refreshAtEdge(refresh);
  if (!tokens) return redirectToLogin(req);

  const res = NextResponse.next();
  applyTokens(res, tokens);
  return res;
}

export const config = {
  // Skip Next internals and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
