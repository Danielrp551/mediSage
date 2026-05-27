import type { UserAuditInfo } from "./audit.types";
import type { PermissionOption } from "./permission.types";
import type { RoleOption } from "./role.types";

export interface UserItem {
  id: string;
  email: string;
  full_name: string;
  first_name: string;
  last_name: string;
  second_last_name: string | null;
  document_type: string | null;
  document_number: string | null;
  phone: string | null;
  active: boolean;
  roles_count: number;
  permissions_count: number;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  created_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
  updated_on: string;
}

export interface UserDetail extends UserItem {
  roles: RoleOption[];
  permissions: PermissionOption[];
}

export interface UserCreatePayload {
  email: string;
  first_name: string;
  last_name: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  phone?: string | null;
  role_ids: string[];
  permission_ids: string[];
  password?: string;
}

export interface UserUpdatePayload {
  email?: string;
  first_name?: string;
  last_name?: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  phone?: string | null;
  active?: boolean;
  role_ids?: string[];
  permission_ids?: string[];
}

export interface UserCreatedResponse {
  success: true;
  data: UserDetail;
  generated_password: string | null;
}

// Marca explícita de módulo (type-only file under isolatedModules).
export {};
