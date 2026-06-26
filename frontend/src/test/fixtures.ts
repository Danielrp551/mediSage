/**
 * Datos de prueba (fixtures) para el modulo de Dashboards. Espejan los schemas Pydantic del
 * backend (`dashboards.types.ts`). Conteos pequenos (menores a mil) para evitar dependencia del
 * agrupador de miles del locale entre maquinas.
 */
import type {
  DistributionSummary,
  FunnelSummary,
  KpiSummary,
  TimeSeries,
} from "@/types/dashboards.types";

export function makeFunnelSummary(): FunnelSummary {
  return {
    stages: [
      { key: "conversations", label: "Conversaciones", count: 200, rate_from_prev: null, color: null },
      { key: "leads", label: "Leads", count: 120, rate_from_prev: 0.6, color: null },
      { key: "appointments", label: "Citas agendadas", count: 30, rate_from_prev: 0.25, color: null },
    ],
    conversion_rate: 0.25,
    total_leads: 120,
    total_appointments: 30,
    total_customers: 12,
    chatbot_share: 0.7,
  };
}

export function makeKpiSummary(overrides: Partial<KpiSummary> = {}): KpiSummary {
  return {
    conversion_rate: 0.42,
    lead_to_appt_rate: 0.5,
    confirmation_rate: 0.8,
    show_rate: 0.9,
    no_show_rate: 0.1,
    customer_rate: 0.3,
    total_conversations: 200,
    conversations_bot: 140,
    total_leads: 120,
    total_appointments: 30,
    total_confirmed: 24,
    total_attended: 20,
    total_customers: 12,
    bot_turns: 540,
    bot_cost_usd: "4.12",
    ...overrides,
  };
}

export function makeDistributionSummary(): DistributionSummary {
  return {
    buckets: [
      { code: "confirmed", label: "Confirmadas", color: null, count: 6 },
      { code: "cancelled", label: "Canceladas", color: null, count: 4 },
    ],
    total: 10,
  };
}

export function makeTimeSeries(): TimeSeries {
  return {
    series: [
      { key: "nuevos", label: "Nuevos", color: null },
      { key: "ganados", label: "Ganados", color: null },
    ],
    points: [
      { date: "2026-06-01", values: { nuevos: 5, ganados: 2 } },
      { date: "2026-06-02", values: { nuevos: 8, ganados: 3 } },
      { date: "2026-06-03", values: { nuevos: 6, ganados: 4 } },
    ],
  };
}
