/**
 * Catalog module wire types. Mirror of the Pydantic schemas in
 * `backend/app/modules/catalog/schemas/`.
 *
 * Phase 1 ships Vertical, phase 2 adds Service; Product types land in
 * phase 3 — keep this file the single source of truth so the
 * `import type` graph stays flat.
 */

import type { UserAuditInfo } from "./audit.types";

// ── Vertical ─────────────────────────────────────────

export interface VerticalItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  color: string | null;
  icon: string | null;
  display_order: number;
  active: boolean;
  services_count: number;
  products_count: number;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detail currently has no extra relations vs Item — kept as alias so
// future widening (e.g. eager-loading services) is a non-breaking change.
export type VerticalDetail = VerticalItem;

export interface VerticalOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  icon: string | null;
}

export interface VerticalCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  icon?: string | null;
  display_order?: number;
}

export interface VerticalUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  icon?: string | null;
  display_order?: number;
  active?: boolean;
}

// ── Service ──────────────────────────────────────────

export interface ServiceItem {
  id: string;
  vertical_id: string;
  vertical_name: string; // denormalized — avoids a join in the table
  code: string;
  name: string;
  description: string | null;
  display_order: number;
  active: boolean;
  products_count: number;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface ServiceDetail extends ServiceItem {
  vertical: VerticalOption;
}

export interface ServiceOption {
  id: string;
  vertical_id: string;
  code: string;
  name: string;
}

export interface ServiceCreatePayload {
  vertical_id: string;
  code: string;
  name: string;
  description?: string | null;
  display_order?: number;
}

export interface ServiceUpdatePayload {
  name?: string;
  description?: string | null;
  display_order?: number;
  active?: boolean;
}
