import { getFunnel, getMeta, getSummary } from "@/actions/dashboards.actions";
import { requireAuth } from "@/lib/auth/session";

import { DashboardClient } from "./_components/DashboardClient";
import { WelcomeFallback } from "./_components/WelcomeFallback";
import { getDefaultDashboardFilter } from "./_components/filterPresets";

export const metadata = { title: "Panel de conversión" };

export default async function DashboardPage() {
  // `/dashboard` es la landing tras login. Re-gateo F2: el panel requiere DASHBOARD_VIEW, pero
  // NO usamos requirePermission (redirige a /dashboard → loop). Leemos los claims y ramificamos:
  // con el permiso → el panel; sin él (ej. DOCTOR) → welcome mínimo (sin redirect).
  const claims = await requireAuth();
  if (!claims.permissions.includes("DASHBOARD_VIEW")) {
    return <WelcomeFallback permissions={claims.permissions} />;
  }

  // Filtro por defecto (últimos 30 días) calculado server-side → se pasa como `initialFilter`;
  // el cliente lo usa verbatim → en el primer render `filter === initialFilter` y el prefetch
  // aplica como `initialData` sin round-trip (LCP/RNF-05). Prefetch del above-the-fold:
  // summary (KPI cards) + funnel (embudo) + meta (catálogos/frescura). La línea y el donut los
  // pide el cliente (no bloquean el primer render).
  const filter = getDefaultDashboardFilter();
  let initialData: Awaited<ReturnType<typeof prefetch>> | null = null;
  try {
    initialData = await prefetch(filter);
  } catch {
    // Si el prefetch falla (backend caído), NO se rompe la página: el cliente carga client-side
    // y cada widget muestra su propio estado de error/reintento (aislamiento §23).
    initialData = null;
  }

  return <DashboardClient initialData={initialData} initialFilter={filter} />;
}

async function prefetch(filter: ReturnType<typeof getDefaultDashboardFilter>) {
  const [summary, funnel, meta] = await Promise.all([
    getSummary(filter),
    getFunnel(filter),
    getMeta(),
  ]);
  return { summary, funnel, meta };
}
