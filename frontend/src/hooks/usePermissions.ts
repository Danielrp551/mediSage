"use client";

import { useAuth } from "@/providers/AuthProvider";

export function usePermissions() {
  const { permissions, hasPermission, hasAnyPermission, hasAllPermissions } = useAuth();
  return { permissions, hasPermission, hasAnyPermission, hasAllPermissions };
}
