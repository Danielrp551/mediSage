/**
 * Clinic module wire types. Mirror of the Pydantic schemas in
 * `backend/app/modules/clinic/schemas/`.
 *
 * Phase 1 ships Branch only; Office*, OfficeOperatingHours* and OfficeClosure*
 * land in phases 2-4 — keep this file the single source of truth so the
 * `import type` graph stays flat. (Office will reuse VerticalOption from
 * catalog.types for the office↔vertical M:N.)
 */

import type { UserAuditInfo } from "./audit.types";

// ── Branch (Sede) ───────────────────────────────────────

export interface BranchItem {
  id: string;
  code: string;
  name: string;
  address_line: string;
  district: string | null;
  city: string;
  region: string | null;
  country: string; // ISO 3166-1 alpha-2, default "PE"
  postal_code: string | null;
  latitude: string | null; // backend serializes numeric(9,6) as string
  longitude: string | null;
  phone: string | null;
  email: string | null;
  timezone: string; // IANA, default "America/Lima"
  active: boolean;
  offices_count: number; // denormalized — mirrors catalog's services_count
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detail currently adds no extra relations vs Item — alias for non-breaking
// future widening (same convention as VerticalDetail).
export type BranchDetail = BranchItem;

export interface BranchOption {
  id: string;
  code: string;
  name: string;
  city: string;
  timezone: string;
}

export interface BranchCreatePayload {
  code: string;
  name: string;
  address_line: string;
  district?: string | null;
  city: string;
  region?: string | null;
  country?: string;
  postal_code?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  phone?: string | null;
  email?: string | null;
  timezone?: string;
}

export interface BranchUpdatePayload {
  name?: string;
  address_line?: string;
  district?: string | null;
  city?: string;
  region?: string | null;
  country?: string;
  postal_code?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  phone?: string | null;
  email?: string | null;
  timezone?: string;
  active?: boolean;
}
