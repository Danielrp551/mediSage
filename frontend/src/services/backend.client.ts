/**
 * Server-only HTTP client for the FastAPI backend.
 *
 * Used by Server Components, Server Actions, and route handlers. The
 * browser bundle never imports this module — `BACKEND_URL` stays server-side.
 *
 * Token refresh is handled **proactively in `middleware.ts`** before any
 * RSC renders. This client only attaches the current access token and
 * does NOT try to refresh on 401 — doing so from a Server Component
 * would throw in Next.js 16 (`cookies()` is read-only outside actions).
 * Callers that hit 401 should let the error propagate; the next request
 * will be re-routed through middleware and refreshed there.
 */

import "server-only";

import { cookies } from "next/headers";

import { serverEnv } from "@/config/env";
import { COOKIES } from "@/lib/constants/cookies";
import { HttpError } from "@/types/api.types";

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /** RSC fetch tags for cache invalidation via `revalidateTag`. */
  tags?: string[];
  /** Skip auth (login/refresh use this). */
  anonymous?: boolean;
}

async function _request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const jar = await cookies();
  const token = opts.anonymous ? null : jar.get(COOKIES.ACCESS_TOKEN)?.value;

  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers["authorization"] = `Bearer ${token}`;

  const res = await fetch(`${serverEnv.BACKEND_URL}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    next: opts.tags ? { tags: opts.tags } : undefined,
    cache: opts.tags ? undefined : "no-store",
  });

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      /* ignore */
    }
    throw new HttpError(res.status, body);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const backendClient = {
  get: <T>(path: string, opts?: Omit<RequestOptions, "method" | "body">) =>
    _request<T>(path, { ...opts, method: "GET" }),
  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    _request<T>(path, { ...opts, method: "POST", body }),
  put: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    _request<T>(path, { ...opts, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, "method" | "body">) =>
    _request<T>(path, { ...opts, method: "PATCH", body }),
  delete: <T>(path: string, opts?: Omit<RequestOptions, "method" | "body">) =>
    _request<T>(path, { ...opts, method: "DELETE" }),
};
