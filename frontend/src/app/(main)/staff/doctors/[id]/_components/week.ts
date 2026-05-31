// Helpers de fecha LOCAL para la grilla semanal. Todo se calcula en hora local de
// pared: las fechas de los bloques son "YYYY-MM-DD" sin TZ y NUNCA pasan por
// new Date(date) (eso interpretaría UTC y desfasaría la medianoche). Se parsean
// como `${date}T00:00:00` (local). Estos helpers son específicos de staff y por eso
// viven aquí, no en lib/utils/date.ts (genérico del template).

// Lunes (00:00 local) de la semana que contiene `date`. getDay(): 0=domingo..6=sábado;
// lo convertimos a 0=lunes restando los días correspondientes.
export function startOfWeek(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const day = d.getDay(); // 0=dom..6=sáb
  const diff = (day + 6) % 7; // cuántos días retroceder hasta el lunes
  d.setDate(d.getDate() - diff);
  return d;
}

// Suma `n` días devolviendo un nuevo Date local a medianoche.
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

// ¿Es `value` (Date local) el mismo día calendario que `other`?
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
