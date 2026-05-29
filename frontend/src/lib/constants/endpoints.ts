/**
 * Single source of truth for backend paths consumed by `services/backend.client.ts`.
 */

const ADMIN = "/api/v1/admin";
const CATALOG = "/api/v1/catalog";
const CLINIC = "/api/v1/clinic";

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
  // ── Clinic module ────────────────────────────────────────
  BRANCHES: {
    LIST: `${CLINIC}/branches/list`,
    ACTIVE: `${CLINIC}/branches/active`,
    GET: (id: string) => `${CLINIC}/branches/${id}`,
    CREATE: `${CLINIC}/branches`,
    UPDATE: (id: string) => `${CLINIC}/branches/${id}`,
    DELETE: (id: string) => `${CLINIC}/branches/${id}`,
  },
  OFFICES: {
    LIST: `${CLINIC}/offices/list`,
    // ACTIVE accepts optional ?branch_id= & ?vertical_id= query params.
    ACTIVE: `${CLINIC}/offices/active`,
    GET: (id: string) => `${CLINIC}/offices/${id}`,
    CREATE: `${CLINIC}/offices`,
    UPDATE: (id: string) => `${CLINIC}/offices/${id}`,
    DELETE: (id: string) => `${CLINIC}/offices/${id}`,
    // Nested sub-resources (phases 3 & 4).
    OPERATING_HOURS: (id: string) => `${CLINIC}/offices/${id}/operating-hours`,
    CLOSURES: (id: string) => `${CLINIC}/offices/${id}/closures`,
    CLOSURE: (id: string, closureId: string) => `${CLINIC}/offices/${id}/closures/${closureId}`,
  },
} as const;
