import { tokens } from "@fluentui/react-components";

import type { BotProvider, BotType } from "@/types/bots.types";

/**
 * Metadata de presentación del módulo `bots` (alcance F1). Label en español +
 * color (token Fluent — NO `brandPalette.accent`, que no existe). El tab Tools
 * (F2) y el panel de depuración (F3) sumarán su propia metadata.
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
