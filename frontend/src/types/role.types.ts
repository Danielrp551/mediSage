import type { UserAuditInfo } from "./audit.types";
import type { PermissionOption } from "./permission.types";

export interface RoleOption {
  id: string;
  name: string;
}

export interface RoleItem {
  id: string;
  name: string;
  description: string;
  active: boolean;
  permissions_count: number;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  created_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
  updated_on: string;
}

export interface RoleDetail extends RoleItem {
  permissions: PermissionOption[];
}

export interface RoleCreatePayload {
  name: string;
  description: string;
  permission_ids: string[];
}

export interface RoleUpdatePayload {
  name?: string;
  description?: string;
  active?: boolean;
  permission_ids?: string[];
}

// Marca explícita de módulo (type-only file under isolatedModules).
export {};
