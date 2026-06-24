import { getMeta } from "@/actions/dashboards.actions";
import { requirePermission } from "@/lib/auth/session";

import { ReportForm } from "./_components/ReportForm";

export const metadata = { title: "Reportes" };

export default async function ReportsPage() {
  // `/dashboard/reportes` NO es la landing → `requirePermission` redirige a /dashboard si falta el
  // permiso (sin loop). ADMIN y ASESOR tienen REPORTS_EXPORT; el DOCTOR no (y no ve el item de nav).
  await requirePermission("REPORTS_EXPORT");
  // Prefetch de la meta solo para poblar el select de sede (sin datos del panel: el reporte se
  // genera server-side al pedirlo).
  const meta = await getMeta();
  return <ReportForm branches={meta.branches} />;
}
