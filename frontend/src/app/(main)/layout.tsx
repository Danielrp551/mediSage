import { MainShell } from "./_shell/MainShell";
import { requireAuth } from "@/lib/auth/session";

// Rutas (main) requieren auth (cookies) y datos del backend por usuario —
// no se pueden pre-renderizar en build time.
export const dynamic = "force-dynamic";

export default async function MainLayout({ children }: { children: React.ReactNode }) {
  await requireAuth();
  return <MainShell>{children}</MainShell>;
}
