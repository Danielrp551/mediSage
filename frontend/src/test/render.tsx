/**
 * Helpers de render para React Testing Library.
 *  - `renderWithFluent`: envuelve en el FluentProvider con el tema de marca (componentes sueltos).
 *  - `renderWithProviders`: ademas monta QueryClientProvider y AuthProvider, como la app real,
 *    para probar componentes que usan TanStack Query y el contexto de permisos (RBAC).
 */
import type { ReactElement, ReactNode } from "react";

import { FluentProvider } from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";

import { appTheme } from "@/lib/theme/brand";
import { AuthProvider } from "@/providers/AuthProvider";
import type { AuthenticatedUser } from "@/types/auth.types";

function Providers({ children }: { children: ReactNode }) {
  return <FluentProvider theme={appTheme}>{children}</FluentProvider>;
}

export function renderWithFluent(ui: ReactElement): RenderResult {
  return render(ui, { wrapper: Providers });
}

function buildUser(permissions: string[]): AuthenticatedUser {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    email: "admin@example.com",
    full_name: "Admin User",
    first_name: "Admin",
    last_name: "User",
    second_last_name: null,
    active: true,
    roles: ["ADMIN"],
    permissions,
  };
}

export function renderWithProviders(
  ui: ReactElement,
  opts: { permissions?: string[] } = {},
): RenderResult {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = buildUser(opts.permissions ?? []);

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <FluentProvider theme={appTheme}>
        <QueryClientProvider client={queryClient}>
          <AuthProvider initialUser={user}>{children}</AuthProvider>
        </QueryClientProvider>
      </FluentProvider>
    );
  }

  return render(ui, { wrapper: Wrapper });
}
