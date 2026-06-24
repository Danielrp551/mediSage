/**
 * Formateadores del panel (puros). Convención de contrato (design.md §7):
 *   - TASAS (`conversion_rate`, `show_rate`, …) viajan como FRACCIÓN 0–1 → se muestran "XX.X %".
 *   - CONTEOS son enteros → se muestran con separador de miles (es-PE).
 *   - MONTOS `Numeric` (`bot_cost_usd`) viajan como STRING → se parsean explícitamente para mostrar.
 */

const LOCALE = "es-PE";
const intFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

/** Entero con separador de miles ("1 204"). */
export function formatInt(n: number): string {
  return intFmt.format(n);
}

/** Fracción 0–1 → "XX.X %" (1 decimal). Acota a [0,1] por si el backend manda ruido. */
export function formatPct(rate: number): string {
  const clamped = Math.max(0, Math.min(1, rate));
  return `${(clamped * 100).toFixed(1)} %`;
}

/** Fracción 0–1 → "XX %" (entero) — para el aporte del bot (más limpio sin decimal). */
export function formatPctInt(rate: number): string {
  const clamped = Math.max(0, Math.min(1, rate));
  return `${Math.round(clamped * 100)} %`;
}

/**
 * Igual que `formatPctInt` pero SIN cota superior. Para tasas que pueden exceder 100% de forma
 * legítima — caso del `rate_from_prev` del embudo: el backend lo computa cruzando poblaciones de
 * fuentes independientes del rollup (ej. citas/leads-engaged puede dar >1 si un lead agenda varias
 * citas, o se agenda alguien que nunca fue lead engaged). El embudo es HU26 → un >100% es señal
 * informativa real; recortarlo a "100 %" tergiversaría el dato. Sólo se acota por abajo (defensa
 * NaN/negativos). NO usar para tasas definitorialmente ≤1 (conversion_rate, chatbot_share, …).
 */
export function formatPctUncapped(rate: number): string {
  const safe = Number.isFinite(rate) ? Math.max(0, rate) : 0;
  return `${Math.round(safe * 100)} %`;
}

/**
 * Monto USD que llega como STRING (Numeric serializado) → "$ 4.12". NUNCA se opera el
 * string crudo; `Number(...)` explícito (si el backend manda number, es drift del schema).
 */
export function formatUsd(value: string): string {
  const n = Number(value);
  return `$ ${(Number.isFinite(n) ? n : 0).toFixed(2)}`;
}

/**
 * Aporte del bot = conversaciones del bot / total de conversaciones (fracción 0–1). `KpiSummary`
 * NO trae `chatbot_share` (ese campo vive en `FunnelSummary`); se deriva aquí con la MISMA fórmula
 * documentada (design §7) para las KPI cards y el mini-panel, que sólo reciben el `KpiSummary`.
 */
export function chatbotShare(s: {
  conversations_bot: number;
  total_conversations: number;
}): number {
  return s.total_conversations > 0 ? s.conversations_bot / s.total_conversations : 0;
}

const MONTHS_ES = [
  "ene",
  "feb",
  "mar",
  "abr",
  "may",
  "jun",
  "jul",
  "ago",
  "sep",
  "oct",
  "nov",
  "dic",
];

/**
 * "YYYY-MM-DD" → "01 jun". Formatea fecha-puro SIN construir un `Date` → determinista entre SSR
 * (UTC) y cliente (Lima), sin el desfase de un día en husos negativos (el eje X de la línea son
 * fechas-puro del rollup por día UTC, no instantes — no se les aplica conversión de TZ).
 */
export function formatDayMonth(iso: string): string {
  const [, m, d] = iso.split("-");
  const mi = Number(m) - 1;
  return `${d} ${MONTHS_ES[mi] ?? m}`;
}

/** Etiqueta comercial en español del `source` (value enum en inglés). */
const SOURCE_LABELS: Record<string, string> = {
  bot: "Chatbot",
  advisor: "Asesor",
  admin: "Administrador",
  import: "Importado",
  api: "API",
};

export function sourceLabel(value: string): string {
  return SOURCE_LABELS[value] ?? value;
}
