"use client";

import { Badge, tokens } from "@fluentui/react-components";

import type {
  CustomerStatusOption,
  CustomerStatusSummary,
  LeadStatusOption,
  LeadStatusSummary,
} from "@/types/crm.types";

/** Cualquier shape de estado que traiga `name` + `color` (lead o customer). */
type StatusLike =
  | LeadStatusSummary
  | LeadStatusOption
  | CustomerStatusSummary
  | CustomerStatusOption;

interface Props {
  status: StatusLike | null;
  /** Texto cuando no hay estado. Default "—". */
  fallback?: string;
}

/**
 * Calcula un color de texto legible (negro/blanco) sobre el fondo hex del
 * catálogo. Best-effort: luminancia relativa simple. Si el hex no parsea,
 * cae al foreground "on-brand" de Fluent.
 */
function readableText(hex: string | null): string {
  if (!hex) return tokens.colorNeutralForeground1;
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m?.[1]) return tokens.colorNeutralForegroundOnBrand;
  const int = parseInt(m[1], 16);
  const r = (int >> 16) & 0xff;
  const g = (int >> 8) & 0xff;
  const b = int & 0xff;
  // Luminancia perceptual (ITU-R BT.601).
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.6 ? "#1b1b1b" : "#ffffff";
}

/**
 * Badge de estado (lead/customer) compartido por tablas y tabs. Usa el `color`
 * hex del catálogo (configurable en BD) como fondo — NO `brandPalette` (no
 * tiene `accent`). El texto se contrasta best-effort.
 */
export function StatusBadge({ status, fallback = "—" }: Props) {
  if (!status) {
    return <span style={{ color: tokens.colorNeutralForeground3 }}>{fallback}</span>;
  }
  return (
    <Badge
      appearance="filled"
      style={{
        backgroundColor: status.color ?? tokens.colorNeutralBackground3,
        color: readableText(status.color),
      }}
    >
      {status.name}
    </Badge>
  );
}
