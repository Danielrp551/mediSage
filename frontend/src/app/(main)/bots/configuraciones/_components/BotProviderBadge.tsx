"use client";

import { Badge } from "@fluentui/react-components";

import { BOT_PROVIDER_META } from "@/lib/constants/bots";
import type { BotProvider } from "@/types/bots.types";

/**
 * Badge del proveedor del motor (OpenAI / Claude / …) con color por provider.
 * Usa el `color` hex del catálogo de presentación (`BOT_PROVIDER_META`) — NO
 * `brandPalette.accent` (no existe). Si `withModel` trae un modelo, lo muestra
 * al lado en texto tenue ("OpenAI · gpt-4.1-mini").
 */
export function BotProviderBadge({
  provider,
  model,
}: {
  provider: BotProvider;
  model?: string | null;
}) {
  const meta = BOT_PROVIDER_META[provider];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <Badge appearance="tint" style={{ color: meta.color, borderColor: meta.color }}>
        {meta.label}
      </Badge>
      {model ? (
        <span style={{ fontSize: 12, color: "var(--colorNeutralForeground3)" }}>· {model}</span>
      ) : null}
    </span>
  );
}
