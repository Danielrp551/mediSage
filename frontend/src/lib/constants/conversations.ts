/**
 * Constantes de presentación del módulo `conversations`: ícono Fluent + label en
 * español + color (token Fluent semántico — NO `brandPalette.accent`, que no
 * existe). El `CHANNEL_TYPE_META` se REUSA de crm (`lib/constants/crm.ts`); no se
 * duplica.
 *
 * Verificados los íconos en la versión instalada de `@fluentui/react-icons`:
 * Checkmark/CheckmarkCircle/ErrorCircle/Clock/Bot/Person/PersonQuestionMark/Chat
 * existen todos. El "✓✓" de entregado/leído se compone con `CheckmarkCircleRegular`
 * (un solo glifo redondeado; no hay un doble-tick dedicado en esta versión).
 */

import { tokens } from "@fluentui/react-components";
import {
  BotRegular,
  CheckmarkCircleRegular,
  CheckmarkRegular,
  ClockRegular,
  ErrorCircleRegular,
  PersonQuestionMarkRegular,
  PersonRegular,
} from "@fluentui/react-icons";
import type { FC } from "react";

import type {
  AssigneeType,
  ConversationStatus,
  MessageExternalStatus,
  SenderType,
} from "@/types/conversations.types";

// Reuse del CHANNEL_TYPE_META de crm (ícono + label ES por canal). NO duplicar.
export { CHANNEL_TYPE_META } from "@/lib/constants/crm";

// ── Estado de mensaje (outbound) ─────────────────────────
// El "tick" estilo WhatsApp: 🕓 en tránsito (optimista, antes de la confirmación
// de Meta), ✓ enviado, ✓✓ entregado, ✓✓ azul leído, ⚠ fallido. Color con tokens
// semánticos (NO brandPalette.accent).
export const MESSAGE_STATUS_META: Record<
  MessageExternalStatus | "pending",
  { label: string; icon: FC; color: string }
> = {
  pending: { label: "Enviando…", icon: ClockRegular, color: tokens.colorNeutralForeground3 },
  sent: { label: "Enviado", icon: CheckmarkRegular, color: tokens.colorNeutralForeground3 },
  delivered: {
    label: "Entregado",
    icon: CheckmarkCircleRegular,
    color: tokens.colorNeutralForeground3,
  },
  read: {
    label: "Leído",
    icon: CheckmarkCircleRegular,
    color: tokens.colorPaletteBlueForeground2,
  },
  failed: {
    label: "Falló el envío",
    icon: ErrorCircleRegular,
    color: tokens.colorPaletteRedForeground1,
  },
};

// ── Tipo de sender (alineación de la burbuja + etiqueta del autor) ──
export const SENDER_TYPE_META: Record<
  SenderType,
  { label: string; align: "start" | "end" | "center" }
> = {
  contact: { label: "Contacto", align: "start" }, // inbound izquierda
  advisor: { label: "Asesor", align: "end" }, // outbound derecha
  bot: { label: "Bot", align: "end" }, // outbound derecha (no aplica en MVP)
  system: { label: "Sistema", align: "center" }, // notificación centrada y atenuada
};

// ── Tipo de assignee (badge del header del hilo + filtro) ──
export const ASSIGNEE_TYPE_META: Record<AssigneeType, { label: string; icon: FC; color: string }> =
  {
    advisor: {
      label: "Asignado a",
      icon: PersonRegular,
      color: tokens.colorPaletteGreenForeground2,
    },
    bot: { label: "Atiende el bot", icon: BotRegular, color: tokens.colorPaletteBlueForeground2 },
    unassigned: {
      label: "Sin asignar",
      icon: PersonQuestionMarkRegular,
      color: tokens.colorNeutralForeground3,
    },
  };

// ── Estado de la conversación (badge) ────────────────────
export const CONVERSATION_STATUS_META: Record<
  ConversationStatus,
  { label: string; color: string }
> = {
  open: { label: "Abierta", color: tokens.colorPaletteGreenForeground2 },
  closed: { label: "Cerrada", color: tokens.colorNeutralForeground3 },
};

// ── Presets de filtro del inbox (panel izquierdo) ────────
// Cada preset = combinación de filtros sobre columnas REALES (lección cd10c78:
// nunca filtrar por denormalizados). "Todas" = sin filtro de estado. El toggle
// "Sin asignar" se traduce con el flag `unassigned` (query param dedicado del
// backend, NO un FilterCondition). En scope="mine" estos presets se acotan a
// Estado (las conversaciones ya están asignadas al actor server-side).
export const INBOX_FILTER_PRESETS: {
  key: string;
  label: string;
  status?: ConversationStatus;
  unassigned?: boolean;
}[] = [
  { key: "open", label: "Abiertas", status: "open" },
  { key: "unassigned", label: "Sin asignar", status: "open", unassigned: true },
  { key: "closed", label: "Cerradas", status: "closed" },
  { key: "all", label: "Todas" },
];

// Intervalo de polling del LISTADO (panel izquierdo). El HILO no se poléa
// (real-time Firestore). ~10s (spec §1).
export const CONVERSATIONS_POLL_MS = 10_000;
