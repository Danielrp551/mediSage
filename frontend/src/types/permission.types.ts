import type { UserAuditInfo } from "./audit.types";

export interface PermissionOption {
  id: string;
  code: string;
  name: string;
  module: string;
}

export interface PermissionItem extends PermissionOption {
  description: string;
  active: boolean;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  created_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
  updated_on: string;
}

export interface PermissionCreatePayload {
  code: string;
  name: string;
  description: string;
  module: string;
}

export interface PermissionUpdatePayload {
  code?: string;
  name?: string;
  description?: string;
  module?: string;
  active?: boolean;
}

// Marca explícita de módulo (type-only file under isolatedModules).
export {};
