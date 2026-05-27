"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

interface LayoutContextValue {
  isSidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

const LayoutContext = createContext<LayoutContextValue | null>(null);

interface LayoutProviderProps {
  children: ReactNode;
  /** Initial state — default expanded. */
  defaultCollapsed?: boolean;
}

export function LayoutProvider({ children, defaultCollapsed = false }: LayoutProviderProps) {
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(defaultCollapsed);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((v) => !v);
  }, []);

  const value = useMemo<LayoutContextValue>(
    () => ({ isSidebarCollapsed, toggleSidebar, setSidebarCollapsed }),
    [isSidebarCollapsed, toggleSidebar],
  );

  return <LayoutContext.Provider value={value}>{children}</LayoutContext.Provider>;
}

export function useLayout(): LayoutContextValue {
  const ctx = useContext(LayoutContext);
  if (!ctx) throw new Error("useLayout must be used within <LayoutProvider>");
  return ctx;
}
