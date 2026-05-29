/**
 * Catalog module wire types. Mirror of the Pydantic schemas in
 * `backend/app/modules/catalog/schemas/`.
 *
 * Phase 1 ships Vertical, phase 2 adds Service, phase 3 adds Product —
 * the full hierarchy. Keep this file the single source of truth so the
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

// ── Product ──────────────────────────────────────────

export interface ProductItem {
  id: string;
  service_id: string;
  service_name: string; // denormalized
  vertical_id: string; // denormalized
  vertical_name: string; // denormalized
  code: string;
  name: string;
  description: string | null;
  base_price: string; // backend serializes Decimal as a string
  currency: string;
  duration_min: number | null;
  requires_appointment: boolean;
  is_package: boolean;
  min_hours_to_cancel: number | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface ProductDetail extends ProductItem {
  service: ServiceOption;
  vertical: VerticalOption;
}

export interface ProductOption {
  id: string;
  service_id: string;
  code: string;
  name: string;
  base_price: string;
  currency: string;
  duration_min: number | null;
}

export interface ProductCreatePayload {
  service_id: string;
  code: string;
  name: string;
  description?: string | null;
  base_price: string;
  currency?: string;
  duration_min?: number | null;
  requires_appointment?: boolean;
  is_package?: boolean;
  min_hours_to_cancel?: number | null;
}

export interface ProductUpdatePayload {
  name?: string;
  description?: string | null;
  base_price?: string;
  currency?: string;
  duration_min?: number | null;
  requires_appointment?: boolean;
  is_package?: boolean;
  min_hours_to_cancel?: number | null;
  active?: boolean;
}
