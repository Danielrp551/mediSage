"use client";

/**
 * Root client providers.
 *
 * Griffel (the CSS-in-JS engine behind Fluent UI v9) needs an explicit
 * SSR handoff in the Next.js App Router. Without this, server-rendered
 * HTML lacks the Fluent styles → during hydration the user sees a
 * flash of unstyled content AND overlays like `OverlayDrawer` /
 * `MenuPopover` render without their backdrop (the "background turns
 * white" symptom).
 *
 * We use `useServerInsertedHTML` to push Griffel's collected styles
 * into the streamed HTML head — the canonical Fluent UI + Next App
 * Router pattern.
 */

import {
  FluentProvider,
  RendererProvider,
  SSRProvider,
  createDOMRenderer,
  renderToStyleElements,
} from "@fluentui/react-components";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useServerInsertedHTML } from "next/navigation";
import { useState, type ReactNode } from "react";

import { LayoutProvider } from "./LayoutProvider";
import { AuthProvider } from "./AuthProvider";
import { appTheme } from "@/lib/theme/brand";
import type { AuthenticatedUser } from "@/types/auth.types";

interface AppProvidersProps {
  children: ReactNode;
  /** Hydrated from the Server Component layout — `null` when logged out. */
  initialUser: AuthenticatedUser | null;
}

export function AppProviders({ children, initialUser }: AppProvidersProps) {
  // Griffel DOM renderer — one per request. The hook below extracts the
  // collected CSS and injects it during streaming.
  const [renderer] = useState(() => createDOMRenderer());

  useServerInsertedHTML(() => {
    return <>{renderToStyleElements(renderer)}</>;
  });

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <RendererProvider renderer={renderer}>
      <SSRProvider>
        <FluentProvider theme={appTheme}>
          <NuqsAdapter>
            <QueryClientProvider client={queryClient}>
              <AuthProvider initialUser={initialUser}>
                <LayoutProvider>{children}</LayoutProvider>
              </AuthProvider>
            </QueryClientProvider>
          </NuqsAdapter>
        </FluentProvider>
      </SSRProvider>
    </RendererProvider>
  );
}
