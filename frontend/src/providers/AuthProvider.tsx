"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";

import type { AuthenticatedUser } from "@/types/auth.types";

interface AuthContextValue {
  user: AuthenticatedUser | null;
  permissions: Set<string>;
  isAuthenticated: boolean;
  hasPermission: (code: string) => boolean;
  hasAnyPermission: (codes: string[]) => boolean;
  hasAllPermissions: (codes: string[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
  initialUser: AuthenticatedUser | null;
}

export function AuthProvider({ children, initialUser }: AuthProviderProps) {
  const value = useMemo<AuthContextValue>(() => {
    const permissions = new Set(initialUser?.permissions ?? []);
    return {
      user: initialUser,
      permissions,
      isAuthenticated: initialUser !== null,
      hasPermission: (code) => permissions.has(code),
      hasAnyPermission: (codes) => codes.some((c) => permissions.has(c)),
      hasAllPermissions: (codes) => codes.every((c) => permissions.has(c)),
    };
  }, [initialUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
