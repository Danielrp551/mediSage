import { tokens } from "@fluentui/react-components";

import type { BotEventType, BotProvider, BotType, ToolCallStatus } from "@/types/bots.types";

/**
 * Metadata de presentación del módulo `bots`. Label en español + color (token
 * Fluent — NO `brandPalette.accent`, que no existe). Cubre F1 (tipos/proveedores),
 * F2 (tools) y F3a (eventos del bot + estados de tool-call en la depuración).
 */

// ── Tipo de bot (badge en la tabla de configuraciones + dropdown del drawer) ──
export const BOT_TYPE_META: Record<
  BotType,
  { label: string; color: "brand" | "success" | "informative" | "subtle" }
> = {
  preventa: { label: "Preventa", color: "brand" },
  postventa: { label: "Postventa", color: "success" },
  general: { label: "General", color: "informative" },
  custom: { label: "Personalizado", color: "subtle" },
};

// ── Proveedor del motor (badge + dropdown del editor de versiones) ──
// `supported` = se puede elegir en el MVP. Los no soportados se muestran
// deshabilitados con "(próximamente)".
export const BOT_PROVIDER_META: Record<
  BotProvider,
  { label: string; supported: boolean; color: string }
> = {
  openai: { label: "OpenAI", supported: true, color: tokens.colorPaletteGreenForeground2 },
  claude: {
    label: "Claude (Anthropic)",
    supported: true,
    color: tokens.colorPalettePurpleForeground2,
  },
  vertex_ai: { label: "Vertex AI", supported: false, color: tokens.colorNeutralForeground3 },
  azure_openai: {
    label: "Azure OpenAI",
    supported: false,
    color: tokens.colorNeutralForeground3,
  },
  external_webhook: {
    label: "Webhook externo",
    supported: false,
    color: tokens.colorNeutralForeground3,
  },
};

// Presets de modelo por provider (el campo es texto libre; estos son sugerencias
// para el placeholder). Default global = gpt-4.1-mini (spec §0.2).
export const PROVIDER_MODEL_PLACEHOLDER: Record<BotProvider, string> = {
  openai: "gpt-4.1-mini",
  claude: "claude-sonnet-4-5",
  vertex_ai: "—",
  azure_openai: "—",
  external_webhook: "—",
};

// ── Tipo de evento del bot (timeline de depuración F3a) ──
// glifo + label ES + color (token Fluent). El `glyph` es un carácter (no ícono
// Fluent) para mantener la tarjeta liviana; se acompaña de `aria-label`/tooltip
// (accesibilidad: el estado NO se comunica solo por color/glifo — ui.md §A11y).
export const BOT_EVENT_TYPE_META: Record<
  BotEventType,
  { label: string; glyph: string; color: string }
> = {
  turn_started: {
    label: "Turno iniciado",
    glyph: "◔",
    color: tokens.colorNeutralForeground3,
  },
  turn_completed: {
    label: "Turno completado",
    glyph: "●",
    color: tokens.colorPaletteGreenForeground1,
  },
  turn_failed: {
    label: "Turno fallido",
    glyph: "⚠",
    color: tokens.colorPaletteRedForeground1,
  },
  tool_dispatched: {
    label: "Herramienta invocada",
    glyph: "🔧",
    color: tokens.colorPaletteBlueForeground2,
  },
  handoff_triggered: {
    label: "Handoff disparado",
    glyph: "→",
    color: tokens.colorPaletteYellowForeground1,
  },
};

// ── Estado de una llamada a herramienta (BotToolCall, timeline F3a) ──
// glifo + label ES + color del badge (semántico de Fluent `Badge color`).
export const TOOL_CALL_STATUS_META: Record<
  ToolCallStatus,
  { label: string; glyph: string; color: "informative" | "success" | "danger" | "warning" }
> = {
  pending: { label: "Pendiente", glyph: "🕓", color: "informative" },
  success: { label: "Éxito", glyph: "✓", color: "success" },
  error: { label: "Error", glyph: "✕", color: "danger" },
  timeout: { label: "Tiempo agotado", glyph: "⏱", color: "danger" },
};
