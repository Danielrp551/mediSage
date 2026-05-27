import "./globals.css";
import type { Metadata } from "next";
import { JetBrains_Mono, Manrope } from "next/font/google";

import { AppProviders } from "@/providers/AppProviders";
import { backendClient } from "@/services/backend.client";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import { getAccessToken } from "@/lib/auth/session";
import type { AuthenticatedUser } from "@/types/auth.types";

/**
 * App-wide typography. Single source of truth — to swap fonts:
 *   1. Change the imports below (any `next/font/google` family).
 *   2. The CSS variables propagate via `globals.css` body default AND
 *      via `appTheme.fontFamilyBase` so Fluent UI components inherit
 *      automatically. No component files to edit.
 */
const fontBody = Manrope({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

const fontMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Medisage", template: "%s · Medisage" },
  description: "Medisage admin console — Next.js + FastAPI",
};

async function loadCurrentUser(): Promise<AuthenticatedUser | null> {
  if (!(await getAccessToken())) return null;
  try {
    return await backendClient.get<AuthenticatedUser>(ENDPOINTS.AUTH.ME);
  } catch {
    return null;
  }
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const user = await loadCurrentUser();
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${fontBody.variable} ${fontMono.variable}`}
    >
      <body>
        <AppProviders initialUser={user}>{children}</AppProviders>
      </body>
    </html>
  );
}
