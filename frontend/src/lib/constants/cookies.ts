/**
 * httpOnly cookie names. Lifetimes are derived from the backend's
 * `access_expires_at` / `refresh_expires_at` — never hard-coded — so a
 * cookie can never outlive the JWT it carries.
 *
 * Cookies are written by Server Actions / Route Handlers / middleware.
 * The browser never sets them.
 */

export const COOKIES = {
  ACCESS_TOKEN: "access_token",
  REFRESH_TOKEN: "refresh_token",
} as const;
