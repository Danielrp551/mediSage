/**
 * Helpers de fecha LOCAL + posicionamiento para el calendario de citas (scheduling F4).
 *
 * Dos mundos de tiempo conviven:
 *  - La GRILLA se dibuja en hora local de pared (columnas = días/​doctores, eje = horas).
 *    Las fechas de columna son "YYYY-MM-DD" locales y NUNCA se parsean con new Date(iso)
 *    (eso interpretaría UTC y desfasaría la medianoche).
 *  - Las CITAS llegan como `scheduled_for` = instante UTC ISO 8601 con offset. Para ubicarlas
 *    en la grilla se convierten a hora local de pared con `localMinutesOf` / `localDateIsoOf`
 *    (usan `new Date(iso)`, que SÍ es correcto para un instante con offset: da la hora local
 *    del navegador). Por eso el cálculo de posición debe correr en CLIENTE (los datos llegan
 *    por fetch client-side → sin desfase SSR).
 *
 * Espeja los helpers de la grilla de staff (week.ts) sin acoplarse a ese módulo.
 */

// ── Semana / día (hora local) ───────────────────────────────────────────────

// Lunes (00:00 local) de la semana que contiene `date`. getDay(): 0=domingo..6=sábado.
export function startOfWeek(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = d.getDay();
  const diff = (day + 6) % 7; // días a retroceder hasta el lunes
  d.setDate(d.getDate() - diff);
  return d;
}

// Medianoche local del día que contiene `date`.
export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

// Suma `n` días devolviendo un Date local a medianoche.
export function addDays(date: Date, n: number): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  d.setDate(d.getDate() + n);
  return d;
}

// Date local → "YYYY-MM-DD" (sin pasar por toISOString, que convertiría a UTC).
export function toIsoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// "YYYY-MM-DD" → Date local a medianoche (parsea como local, no UTC).
export function parseIsoDate(value: string): Date {
  return new Date(`${value}T00:00:00`);
}

// ¿Mismo día calendario?
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

// ── Instante UTC → hora/fecha LOCAL de pared (para ubicar citas en la grilla) ─

// `scheduled_for` (instante UTC ISO con offset) → minutos desde medianoche LOCAL.
export function localMinutesOf(iso: string): number {
  const d = new Date(iso);
  return d.getHours() * 60 + d.getMinutes();
}

// `scheduled_for` (instante UTC ISO con offset) → "YYYY-MM-DD" del día LOCAL.
export function localDateIsoOf(iso: string): string {
  return toIsoDate(new Date(iso));
}

// ── Layout de solapamientos dentro de una columna ───────────────────────────
// Reparte eventos que se solapan en carriles (lanes) lado a lado: cada evento recibe
// su `lane` (0-based) y la cantidad total de `lanes` de su clúster de solapamiento, para
// pintarlo con left=lane/lanes y width=1/lanes. Eventos que no se solapan quedan a ancho
// completo (lanes=1).
export interface LaidOut<T> {
  event: T;
  lane: number;
  lanes: number;
}

export function layoutOverlaps<T extends { startMin: number; endMin: number }>(
  events: T[],
): LaidOut<T>[] {
  const sorted = [...events].sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin);
  const result: LaidOut<T>[] = [];
  let cluster: { event: T; lane: number }[] = [];
  let clusterEnd = -Infinity;

  const flush = () => {
    const lanes = cluster.reduce((m, c) => Math.max(m, c.lane + 1), 0);
    for (const c of cluster) result.push({ event: c.event, lane: c.lane, lanes });
    cluster = [];
  };

  for (const ev of sorted) {
    // Si este evento empieza tras el fin de TODO el clúster activo, ese clúster cierra.
    if (cluster.length && ev.startMin >= clusterEnd) flush();
    // Carriles ocupados por eventos del clúster que siguen vivos al inicio de este evento.
    const used = new Set(cluster.filter((c) => c.event.endMin > ev.startMin).map((c) => c.lane));
    let lane = 0;
    while (used.has(lane)) lane++;
    cluster.push({ event: ev, lane });
    clusterEnd = Math.max(clusterEnd, ev.endMin);
  }
  if (cluster.length) flush();
  return result;
}
