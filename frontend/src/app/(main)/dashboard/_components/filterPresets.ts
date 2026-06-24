/**
 * Presets de rango del panel + filtro por defecto. Helpers PUROS (sin "use client"):
 * los usa tanto el RSC (`page.tsx`, server) para el prefetch como el cliente
 * (`DashboardFilters`) para resolver los presets al interactuar.
 *
 * Fechas = **fecha-puro** "YYYY-MM-DD" (el rollup es por día UTC; el backend valida
 * `date_to >= date_from` y rango ≤ 366 días). El filtro POR DEFECTO lo calcula el RSC
 * y se pasa como `initialFilter` al cliente (que NO lo recalcula) → en el primer render
 * `filter === initialFilter` y el `initialData` del prefetch aplica sin refetch (LCP).
 * Los presets que el usuario elige luego se resuelven client-side (hora local).
 */

import type { DashboardFilter } from "@/types/dashboards.types";

/** "YYYY-MM-DD" a partir de los componentes LOCALES de la fecha (sin desfase por TZ). */
export function isoDateLocal(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export type RangePresetKey = "today" | "last7" | "last30" | "thisMonth" | "custom";

export const RANGE_PRESETS: { key: RangePresetKey; label: string }[] = [
  { key: "today", label: "Hoy" },
  { key: "last7", label: "Últimos 7 días" },
  { key: "last30", label: "Últimos 30 días" },
  { key: "thisMonth", label: "Este mes" },
  { key: "custom", label: "Personalizado…" },
];

export interface DateRange {
  date_from: string;
  date_to: string;
}

/** Resuelve un preset (≠ "custom") a un rango "YYYY-MM-DD". Calcula sobre `new Date()`. */
export function resolveRange(preset: Exclude<RangePresetKey, "custom">): DateRange {
  const today = new Date();
  const to = isoDateLocal(today);
  switch (preset) {
    case "today":
      return { date_from: to, date_to: to };
    case "last7": {
      const from = new Date(today);
      from.setDate(today.getDate() - 6);
      return { date_from: isoDateLocal(from), date_to: to };
    }
    case "last30": {
      const from = new Date(today);
      from.setDate(today.getDate() - 29);
      return { date_from: isoDateLocal(from), date_to: to };
    }
    case "thisMonth": {
      const from = new Date(today.getFullYear(), today.getMonth(), 1);
      return { date_from: isoDateLocal(from), date_to: to };
    }
  }
}

/** Filtro por defecto del panel: últimos 30 días, todas las sedes, todos los orígenes. */
export function getDefaultDashboardFilter(): DashboardFilter {
  return {
    ...resolveRange("last30"),
    branch_id: null,
    source: null,
    campaign_id: null,
  };
}

/** Días entre dos fechas-puro (inclusive). Para validar el rango ≤ 366 días client-side. */
export function rangeDays(from: string, to: string): number {
  const a = new Date(`${from}T00:00:00`);
  const b = new Date(`${to}T00:00:00`);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000) + 1;
}
