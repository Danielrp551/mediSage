/**
 * Single source of truth for backend paths consumed by `services/backend.client.ts`.
 */

const ADMIN = "/api/v1/admin";
const CATALOG = "/api/v1/catalog";

export const ENDPOINTS = {
  AUTH: {
    LOGIN: `${ADMIN}/auth/login`,
    REFRESH: `${ADMIN}/auth/refresh`,
    LOGOUT: `${ADMIN}/auth/logout`,
    ME: `${ADMIN}/auth/me`,
  },
  USERS: {
    LIST: `${ADMIN}/users/list`,
    CREATE: `${ADMIN}/users`,
    GET: (id: string) => `${ADMIN}/users/${id}`,
    UPDATE: (id: string) => `${ADMIN}/users/${id}`,
    CHANGE_PASSWORD: `${ADMIN}/users/me/change-password`,
  },
  ROLES: {
    LIST: `${ADMIN}/roles/list`,
    ACTIVE: `${ADMIN}/roles/active`,
    GET: (id: string) => `${ADMIN}/roles/${id}`,
    CREATE: `${ADMIN}/roles`,
    UPDATE: (id: string) => `${ADMIN}/roles/${id}`,
  },
  PERMISSIONS: {
    LIST: `${ADMIN}/permissions/list`,
    ACTIVE: `${ADMIN}/permissions/active`,
    GET: (id: string) => `${ADMIN}/permissions/${id}`,
    CREATE: `${ADMIN}/permissions`,
    UPDATE: (id: string) => `${ADMIN}/permissions/${id}`,
  },
  // ── Catalog module ───────────────────────────────────────
  VERTICALS: {
    LIST: `${CATALOG}/verticals/list`,
    ACTIVE: `${CATALOG}/verticals/active`,
    GET: (id: string) => `${CATALOG}/verticals/${id}`,
    CREATE: `${CATALOG}/verticals`,
    UPDATE: (id: string) => `${CATALOG}/verticals/${id}`,
    DELETE: (id: string) => `${CATALOG}/verticals/${id}`,
  },
  SERVICES: {
    LIST: `${CATALOG}/services/list`,
    ACTIVE: `${CATALOG}/services/active`,
    GET: (id: string) => `${CATALOG}/services/${id}`,
    CREATE: `${CATALOG}/services`,
    UPDATE: (id: string) => `${CATALOG}/services/${id}`,
    DELETE: (id: string) => `${CATALOG}/services/${id}`,
  },
  PRODUCTS: {
    LIST: `${CATALOG}/products/list`,
    ACTIVE: `${CATALOG}/products/active`,
    GET: (id: string) => `${CATALOG}/products/${id}`,
    CREATE: `${CATALOG}/products`,
    UPDATE: (id: string) => `${CATALOG}/products/${id}`,
    DELETE: (id: string) => `${CATALOG}/products/${id}`,
  },
} as const;
