/**
 * Date helpers. The backend serialises tz-aware UTC datetimes as ISO 8601
 * with offset (e.g. `2026-05-26T10:11:12+00:00`). `new Date(iso)` parses
 * that natively; we then render in the user's locale.
 */

const LOCALE = "es-PE";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(LOCALE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(LOCALE, {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString(LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Relative time ("hace 5 min", "hace 2 h", "ayer 15:55", "12/05 09:00").
 *
 * ⚠ Usa `new Date()` (ahora) → SOLO debe llamarse en cliente (dentro de un
 * efecto / render de cliente), nunca en SSR: el servidor corre en UTC y
 * desfasaría la frontera del día en Lima (UTC-5). Para fechas futuras devuelve
 * la fecha/hora absoluta corta (los seguimientos programados van "adelante").
 */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - then.getTime();
  const diffMin = Math.round(diffMs / 60000);

  // Futuro (p. ej. un seguimiento programado): fecha/hora absoluta corta.
  if (diffMin < 0) {
    return then.toLocaleString(LOCALE, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  if (diffMin < 1) return "hace un momento";
  if (diffMin < 60) return `hace ${diffMin} min`;

  const diffHours = Math.round(diffMin / 60);
  if (diffHours < 24 && now.getDate() === then.getDate()) {
    return `hace ${diffHours} h`;
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (
    then.getDate() === yesterday.getDate() &&
    then.getMonth() === yesterday.getMonth() &&
    then.getFullYear() === yesterday.getFullYear()
  ) {
    return `ayer ${then.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" })}`;
  }

  return then.toLocaleString(LOCALE, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Etiqueta del grupo de día para el feed de actividad: "Hoy" / "Ayer" /
 * "12/05/2026". ⚠ Client-only (usa `new Date()` ahora).
 */
export function dayGroupLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = (a: Date, b: Date) =>
    a.getDate() === b.getDate() &&
    a.getMonth() === b.getMonth() &&
    a.getFullYear() === b.getFullYear();
  if (sameDay(d, now)) return "Hoy";
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(d, yesterday)) return "Ayer";
  return d.toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Returns the value for an `<input type="datetime-local">`. */
export function toLocalDatetimeInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}
