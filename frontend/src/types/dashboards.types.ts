/**
 * Espejo TS de los Pydantic schemas del módulo `dashboards` (#10, OE3) — ver
 * `docs/modules/dashboards/{README,backend,ui,frontend}.md` + ADR-015 + `design.md`.
 * Importable desde server actions y client components.
 *
 * AUTORIDAD DE SHAPE: el contrato de runtime es `backend.md` (los Pydantic que serializan el
 * JSON); `frontend.md` es el molde de naming/precisión. Convenciones de contrato (design.md §7):
 *   - Las TASAS (`conversion_rate`, `rate_from_prev`, `show_rate`, …) son FRACCIÓN 0–1 (`number`);
 *     el front formatea a `%`. Los CONTEOS son `number` enteros.
 *   - Los MONTOS `Numeric` (`bot_cost_usd`) viajan como `string` (convención del repo).
 *   - `last_refreshed_at`/fechas de serie son ISO; el render local lo maneja el front.
 *
 * Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún y el módulo backend NO está
 * montado (sus endpoints dan 404 hasta F1). Las pantallas llegan por fase: panel (F2), reportes (F3).
 *
 * El embudo se cuenta cross-módulo por `person_id`; los estados (lead/cita) son catálogo
 * CONFIGURABLE (ADR-008) → el panel resuelve `code`/`color` desde `DashboardMeta`, NO hardcodea.
 */

// ── Filtro común de los endpoints de agregación ──────────────────
// Fechas como "YYYY-MM-DD" (date). El backend valida date_to >= date_from y rango <= 366 días.
export interface DashboardFilter {
  date_from: string; // ISO date (YYYY-MM-DD)
  date_to: string; // ISO date (YYYY-MM-DD)
  branch_id?: string | null; // filtro de sede (exacto de la etapa "cita" en adelante)
  source?: string | null; // AppointmentSource: "bot" | "advisor" | "admin" | "import" | "api"
  campaign_id?: string | null; // segmentación por campaña (lead.source_campaign_id)
}

// ── Embudo de conversión (6 etapas) ──────────────────────────────
export interface FunnelStage {
  key: string; // identificador de etapa: conversations | leads | contacted | appointments | confirmed | customers
  label: string; // etiqueta ES visible
  count: number;
  rate_from_prev: number | null; // fracción 0–1 vs la etapa previa (null en la 1ª)
  color: string | null; // hex (del catálogo cuando aplica)
}

export interface FunnelSummary {
  stages: FunnelStage[];
  conversion_rate: number; // KPI HU26: leads→CITA_AGENDADA / leads captados (fracción 0–1)
  total_leads: number;
  total_appointments: number;
  total_customers: number;
  chatbot_share: number; // conversations_bot / total conversaciones (fracción 0–1; aporte del bot)
}

// ── Evolución de leads (línea) ───────────────────────────────────
// Una serie por estado de lead (o nuevos/ganados/perdidos). `values` keyed por `series.key`.
export interface SeriesDef {
  key: string; // = lead_status_code (o agregado)
  label: string;
  color: string | null;
}

export interface TimeSeriesPoint {
  date: string; // ISO date (bucket diario)
  values: Record<string, number>; // { [series.key]: count }
}

export interface TimeSeries {
  series: SeriesDef[];
  points: TimeSeriesPoint[];
}

// ── Distribución de citas (donut) ────────────────────────────────
export interface DistributionBucket {
  code: string; // appointment_status code
  label: string;
  color: string | null; // del catálogo appointment_status.color
  count: number;
}

export interface DistributionSummary {
  buckets: DistributionBucket[];
  total: number;
}

// ── KPIs escalares (tarjetas) + chatbot ──────────────────────────
export interface KpiSummary {
  // tasas (fracción 0–1)
  conversion_rate: number;
  lead_to_appt_rate: number;
  confirmation_rate: number;
  show_rate: number;
  no_show_rate: number;
  customer_rate: number;
  // conteos
  total_conversations: number;
  conversations_bot: number;
  total_leads: number;
  total_appointments: number;
  total_confirmed: number;
  total_attended: number;
  total_customers: number;
  bot_turns: number;
  // monto (string por Numeric)
  bot_cost_usd: string;
}

// ── Meta del panel (catálogos para selects/colores + frescura del rollup) ──
export interface StatusOption {
  code: string;
  name: string;
  color: string | null;
  display_order: number;
}

export interface BranchOption {
  id: string;
  name: string;
}

export interface DashboardMeta {
  last_refreshed_at: string | null; // de dashboard_refresh_state → badge "Actualizado hace N min"
  lead_statuses: StatusOption[];
  appointment_statuses: StatusOption[];
  branches: BranchOption[];
  sources: string[]; // valores de AppointmentSource
}

// ── Reportes (F3) ────────────────────────────────────────────────
export type ReportFormat = "pdf" | "excel";

export interface ReportRequest extends DashboardFilter {
  format: ReportFormat;
  sections: string[]; // "kpis" | "funnel" | "distribution" | "evolution"
}

// ── Refresco del rollup (target del Cloud Scheduler; el front no lo llama) ──
export interface RefreshResult {
  refreshed_at: string;
  window_days: number;
  rows_written: number;
  status: string; // "ok" | "error"
}
