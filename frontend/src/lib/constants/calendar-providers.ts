/**
 * Constantes de presentación del módulo `calendar` (#9): metadata de proveedor (label +
 * etiqueta del botón "Conectar X"), metadata de salud de la conexión (label ES + intent del
 * Badge Fluent) y la traducción al español de los `?calendar_error=CODE` que el callback
 * público del backend deja en la URL al volver de un OAuth fallido.
 *
 * Los ÍCONOS NO viven aquí (este es un `.ts`, no puede hospedar JSX): cada componente
 * resuelve el ícono Fluent del proveedor con un map local (sólo 2 proveedores). El color de
 * los badges sale de tokens semánticos Fluent (intent → `<Badge color>`), nunca de un hex ni
 * de `brandPalette` (que no tiene `accent` — lección operativa transversal).
 */

import type { CalendarProvider, ConnectionStatus } from "@/types/calendar.types";

// Proveedor → etiquetas en español. `microsoft` se muestra como "Outlook" (el usuario lo
// conoce así), aunque el `provider` del contrato es "microsoft". `caldav` (futuro, B4) no se
// lista → no aparece un botón "Conectar" para él hasta que se seedee.
export const CALENDAR_PROVIDER_META: Record<
  CalendarProvider,
  { label: string; connectLabel: string }
> = {
  google: { label: "Google", connectLabel: "Conectar Google" },
  microsoft: { label: "Outlook", connectLabel: "Conectar Outlook" },
};

// Salud → label ES + intent del Badge Fluent. connected = verde; needs_reauth = ámbar
// (CTA "Reconectar"); revoked/error = rojo. "Conexión" es femenino → "Conectada"/"Revocada".
export const CONNECTION_STATUS_META: Record<
  ConnectionStatus,
  { label: string; intent: "success" | "warning" | "danger" }
> = {
  connected: { label: "Conectada", intent: "success" },
  needs_reauth: { label: "Reconectar", intent: "warning" },
  revoked: { label: "Revocada", intent: "danger" },
  error: { label: "Error", intent: "danger" },
};

// El callback público del backend hace 302 a la página con `?calendar_error=CODE` cuando el
// OAuth (o una acción posterior) falla. La página traduce el code (inglés) a un mensaje en
// español para un MessageBar. Los codes espejan los del service (spec §8). Cualquier code no
// listado cae a un mensaje genérico en el componente.
export const CALENDAR_ERROR_LABELS: Record<string, string> = {
  CALENDAR_OAUTH_STATE_INVALID:
    "La sesión de conexión expiró o no es válida. Vuelve a intentar conectar.",
  CALENDAR_OAUTH_EXCHANGE_FAILED:
    "No se pudo completar la conexión con el proveedor. Inténtalo de nuevo.",
  CALENDAR_CONNECTION_ALREADY_EXISTS: "Esa cuenta ya está conectada.",
  CALENDAR_PROVIDER_NOT_SUPPORTED: "Ese proveedor no está disponible.",
  CALENDAR_TOKEN_REFRESH_FAILED: "La conexión perdió acceso. Reconéctala.",
  CALENDAR_CREDENTIALS_MISSING: "No se encontraron las credenciales de la conexión. Reconéctala.",
  CALENDAR_CONNECTION_NOT_FOUND: "La conexión ya no existe. Recarga la página.",
  CALENDAR_SOURCE_NOT_FOUND: "El calendario ya no existe en esta conexión. Recarga la página.",
  BRANCH_NOT_FOUND: "Una de las sedes seleccionadas ya no existe. Recarga e inténtalo de nuevo.",
};
