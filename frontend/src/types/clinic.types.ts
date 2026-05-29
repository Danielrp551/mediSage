/**
 * Clinic module wire types. Mirror of the Pydantic schemas in
 * `backend/app/modules/clinic/schemas/`.
 *
 * Phase 1 ships Branch; phase 2 adds Office (+ the office↔vertical M:N, which
 * reuses VerticalOption from catalog.types). OfficeOperatingHours* and
 * OfficeClosure* land in phases 3-4 — keep this file the single source of truth
 * so the `import type` graph stays flat.
 */

import type { VerticalOption } from "./catalog.types";

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

// ── Office (Consultorio) ────────────────────────────────

export interface OfficeItem {
  id: string;
  branch_id: string;
  branch_name: string; // denormalized — avoids a join in the table (mirrors vertical_name)
  code: string;
  name: string;
  room_number: string | null;
  floor: string | null;
  description: string | null;
  active: boolean;
  verticals_count: number; // denormalized — # of apt (non-deleted) verticals
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface OfficeDetail extends OfficeItem {
  branch: BranchOption;
  verticals: VerticalOption[]; // soft-deleted verticals filtered out server-side
}

export interface OfficeOption {
  id: string;
  branch_id: string;
  code: string;
  name: string;
}

export interface OfficeCreatePayload {
  branch_id: string;
  code: string;
  name: string;
  room_number?: string | null;
  floor?: string | null;
  description?: string | null;
  vertical_ids: string[]; // M:N office_vertical assignment at create time
}

export interface OfficeUpdatePayload {
  name?: string;
  room_number?: string | null;
  floor?: string | null;
  description?: string | null;
  vertical_ids?: string[]; // full replace of the M:N when present
  active?: boolean;
}
