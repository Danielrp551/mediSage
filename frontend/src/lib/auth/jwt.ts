/**
 * Edge-safe JWT decoder.
 *
 * The token came from the backend over an httpOnly cookie that the
 * browser cannot forge, so we only need to read claims — signature
 * verification stays on the backend. `jose.decodeJwt` runs in the Edge
 * runtime (no Node `Buffer`, unlike a manual base64 decode).
 */

import { decodeJwt } from "jose";

export interface AccessClaims {
  sub: string;
  type: "access";
  exp: number;
  iat: number;
  roles: string[];
  permissions: string[];
}

export function decodeAccess(token: string): AccessClaims {
  return decodeJwt(token) as unknown as AccessClaims;
}

/** Seconds until the token expires. Negative when already expired. */
export function secondsUntilExpiry(token: string, now: number = Date.now()): number {
  try {
    const { exp } = decodeJwt(token);
    if (typeof exp !== "number") return -1;
    return exp - Math.floor(now / 1000);
  } catch {
    return -1;
  }
}

/**
 * Back-compat alias for callers outside the edge runtime that just want
 * a generic decode. New code should prefer `decodeAccess`.
 */
export function jwtDecode<T>(token: string): T {
  return decodeJwt(token) as unknown as T;
}
