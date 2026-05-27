"use client";

import type { ReactNode } from "react";

import { useAuth } from "@/providers/AuthProvider";

interface PermissionGuardProps {
  anyOf?: string[];
  allOf?: string[];
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * Render gating — hides UI from users who lack the listed permissions.
 * NOT a security control; backend `RequirePermission` is.
 */
export function PermissionGuard({ anyOf, allOf, fallback = null, children }: PermissionGuardProps) {
  const { hasAnyPermission, hasAllPermissions } = useAuth();
  if (anyOf && !hasAnyPermission(anyOf)) return <>{fallback}</>;
  if (allOf && !hasAllPermissions(allOf)) return <>{fallback}</>;
  return <>{children}</>;
}
