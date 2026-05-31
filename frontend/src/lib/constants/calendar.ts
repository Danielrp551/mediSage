// Constantes de la grilla semanal de disponibilidad (DoctorAvailability).
// La grilla es bespoke (Fluent UI 9 no trae calendario); estos valores controlan
// el rango horario visible, la altura de cada hora, el snap del cursor y el largo
// por defecto de un bloque al crear con un click.

export const CALENDAR = {
  // Primera hora visible (07:00 = 7) y última (21:00 = 21). El alto total de la
  // grilla es (END_HOUR - START_HOUR) * HOUR_HEIGHT_PX.
  START_HOUR: 7,
  END_HOUR: 21,
  // Alto en píxeles de una hora completa. top/height de un bloque se derivan de
  // minutos relativos a START_HOUR con la razón HOUR_HEIGHT_PX/60.
  HOUR_HEIGHT_PX: 56,
  // Granularidad del snap (al hacer click en una celda la hora se redondea a este
  // múltiplo). También se usa para sugerir el inicio del bloque.
  SNAP_MINUTES: 15,
  // Duración por defecto (en minutos) de un bloque creado con un solo click.
  DEFAULT_BLOCK_MINUTES: 60,
} as const;

// Etiquetas de día para los encabezados de columna. La semana se muestra de Lunes
// a Domingo (índice 0 = lunes), coherente con la convención Python que ya usa
// clinic (WEEKDAY_LABELS). Para una fecha concreta se compone "Lun 12".
export const WEEKDAY_LABELS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"] as const;

// "HH:MM" o "HH:MM:SS" → minutos desde medianoche (hora local de pared, sin TZ).
export function timeToMinutes(time: string): number {
  const [h = 0, m = 0] = time.split(":").map(Number);
  return h * 60 + m;
}

// minutos desde medianoche → "HH:MM" (24h). Se usa para posicionar/etiquetar en
// la grilla y para construir el valor de los <Input type="time">.
export function minutesToTime(min: number): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(min / 60))}:${pad(min % 60)}`;
}
