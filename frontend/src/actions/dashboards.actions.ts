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

import { cookies } from "next/headers";

import { serverEnv } from "@/config/env";
import { COOKIES } from "@/lib/constants/cookies";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type {
  DashboardFilter,
  DashboardMeta,
  DistributionSummary,
  FunnelSummary,
  KpiSummary,
  ReportRequest,
  TimeSeries,
} from "@/types/dashboards.types";

import type { MutationResult } from "./user.actions";

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

// ── Reporte (F3): descarga del binario PDF/Excel desde un Server Action ───────────
// GOTCHA: `backendClient` SIEMPRE hace `res.json()` → NO sirve para un binario. `generateReport`
// hace su PROPIO `fetch` server-side (leyendo la cookie httpOnly como Bearer), captura el
// ArrayBuffer y lo devuelve como base64 + filename + mime; el cliente arma un Blob y dispara la
// descarga (no se puede streamear el binario directo al navegador desde un Server Action; se
// serializa por el canal de la action). A DIFERENCIA de los reads, SÍ captura el error → devuelve
// MutationResult para que el ReportForm muestre el `detail` ES en un MessageBar
// (REPORT_FORMAT_NOT_SUPPORTED / DASHBOARD_INVALID_DATE_RANGE). SIN revalidateTag (es export, no
// muta negocio).
export async function generateReport(
  input: ReportRequest,
): Promise<MutationResult<{ filename: string; mime: string; base64: string }>> {
  try {
    const jar = await cookies();
    const token = jar.get(COOKIES.ACCESS_TOKEN)?.value;
    const res = await fetch(`${serverEnv.BACKEND_URL}${ENDPOINTS.DASHBOARDS.REPORT}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(input),
      cache: "no-store",
    });
    if (!res.ok) {
      // El backend manda el error como envelope JSON (REPORT_FORMAT_NOT_SUPPORTED 400,
      // DASHBOARD_INVALID_DATE_RANGE 400) incluso para este endpoint binario.
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        /* ignore */
      }
      throw new HttpError(res.status, body);
    }
    const mime = res.headers.get("content-type") ?? "application/octet-stream";
    // Filename del Content-Disposition (el backend lo fija: "reporte-conversion_<desde>_<hasta>.pdf").
    const cd = res.headers.get("content-disposition") ?? "";
    const filename = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? "reporte.bin";
    const buf = await res.arrayBuffer();
    const base64 = Buffer.from(buf).toString("base64");
    return { ok: true, data: { filename, mime, base64 } };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof HttpError ? e.message : "No se pudo generar el reporte.",
    };
  }
}
