/**
 * Curated subset of IANA timezones relevant to LatAm clinics. The Branch
 * picker offers these; the Zod schema still accepts any string ≤ 60 chars as
 * a fallback, but the UI nudges towards the curated set so the admin can't
 * type an invalid name that would break hour resolution in `scheduling`.
 */
export const TIMEZONE_OPTIONS = [
  { key: "America/Lima", label: "Lima (Perú, UTC-5)" },
  { key: "America/Bogota", label: "Bogotá (Colombia, UTC-5)" },
  { key: "America/Mexico_City", label: "Ciudad de México (UTC-6)" },
  { key: "America/Santiago", label: "Santiago (Chile, UTC-4/-3)" },
  { key: "America/Argentina/Buenos_Aires", label: "Buenos Aires (UTC-3)" },
  { key: "America/Guayaquil", label: "Guayaquil (Ecuador, UTC-5)" },
  { key: "America/La_Paz", label: "La Paz (Bolivia, UTC-4)" },
  { key: "America/Caracas", label: "Caracas (Venezuela, UTC-4)" },
  { key: "America/Asuncion", label: "Asunción (Paraguay, UTC-4/-3)" },
  { key: "America/Montevideo", label: "Montevideo (Uruguay, UTC-3)" },
] as const;

export type TimezoneKey = (typeof TIMEZONE_OPTIONS)[number]["key"];

/**
 * Localized labels for the weekly pattern. Index = Python weekday (0=Mon..6=Sun),
 * matching `OfficeOperatingHours.day_of_week`. Used by phase 3 (Horarios tab).
 * Do NOT derive these from a `Date` — `Date.getDay()` uses 0=Sunday and would
 * be off by one.
 */
export const WEEKDAY_LABELS = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
] as const;
