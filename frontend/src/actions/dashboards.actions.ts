"use server";

/**
 * Server Actions del módulo `dashboards` (#10, OE3 — ver `docs/modules/dashboards/`).
 *
 * Naturaleza: **100% lectura/agregación** (read-only). Los reads leen el rollup
 * materializado (`dashboard_daily_metric`) vía los endpoints `/dashboards/*` y devuelven
 * el `.data` del `SingleResponse` (molde `marketing.getPromotionUsageSummary`). NO hay
 * `revalidateTag` de mutación: el módulo no muta ni una fila de negocio. El frescor del
 * panel lo dan el `refetchInterval` de React Query (≈ intervalo del rollup) + el job del
 * backend (Cloud Scheduler → `/internal/refresh`, shared-secret, que el front NUNCA llama).
 *
 * El `tag` `dashboards` existe sólo para deduplicar/cachear el fetch de Next dentro de un
 * render (en Next 16 el fetch no se cachea por defecto sin `revalidate` → cada refetch
 * de React Query pega al backend fresco; el tag es inerte hasta que algo lo invalide, y
 * nada lo invalida desde el front).
 *
 * Los reads NO capturan el error: al ser consumidos por React Query desde el cliente,
 * un throw se vuelve `query.isError` → el widget muestra su propio MessageBar aislado
 * (un widget caído no rompe el panel — lección §23). `generateReport` (F3) sí capturará
 * el error (es un gesto del usuario → MutationResult).
 */

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import type { ApiSingle } from "@/types/api.types";
import type {
  DashboardFilter,
  DashboardMeta,
  DistributionSummary,
  FunnelSummary,
  KpiSummary,
  TimeSeries,
} from "@/types/dashboards.types";

const DASHBOARDS_TAG = "dashboards";

// ── Embudo de conversión (6 etapas) — POST + DashboardFilter ──────────────────
export async function getFunnel(filter: DashboardFilter): Promise<FunnelSummary> {
  const res = await backendClient.post<ApiSingle<FunnelSummary>>(
    ENDPOINTS.DASHBOARDS.FUNNEL,
    filter,
    { tags: [DASHBOARDS_TAG] },
  );
  return res.data;
}

// ── Evolución de leads (serie por día) — POST + DashboardFilter ───────────────
export async function getLeadsEvolution(filter: DashboardFilter): Promise<TimeSeries> {
  const res = await backendClient.post<ApiSingle<TimeSeries>>(
    ENDPOINTS.DASHBOARDS.LEADS_EVOLUTION,
    filter,
    { tags: [DASHBOARDS_TAG] },
  );
  return res.data;
}

// ── Distribución de citas (donut) — POST + DashboardFilter ────────────────────
export async function getAppointmentsDistribution(
  filter: DashboardFilter,
): Promise<DistributionSummary> {
  const res = await backendClient.post<ApiSingle<DistributionSummary>>(
    ENDPOINTS.DASHBOARDS.APPOINTMENTS_DISTRIBUTION,
    filter,
    { tags: [DASHBOARDS_TAG] },
  );
  return res.data;
}

// ── KPIs escalares + chatbot — POST + DashboardFilter ─────────────────────────
export async function getSummary(filter: DashboardFilter): Promise<KpiSummary> {
  const res = await backendClient.post<ApiSingle<KpiSummary>>(
    ENDPOINTS.DASHBOARDS.SUMMARY,
    filter,
    { tags: [DASHBOARDS_TAG] },
  );
  return res.data;
}

// ── Meta del panel (catálogos + frescura) — GET (sin body) ────────────────────
// Puebla los selects (sedes/orígenes) + los colores/labels de los charts (estados de
// lead/cita, del catálogo — ADR-008) + el badge "Actualizado hace N min".
export async function getMeta(): Promise<DashboardMeta> {
  const res = await backendClient.get<ApiSingle<DashboardMeta>>(ENDPOINTS.DASHBOARDS.META, {
    tags: [DASHBOARDS_TAG],
  });
  return res.data;
}
