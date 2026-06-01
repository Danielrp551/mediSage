/**
 * Constantes de presentación del módulo `crm`: metadata de canal (ícono Fluent +
 * label ES) y de tipo de actividad (ícono + color + label ES), labels de
 * resultado de llamada, y los grupos de filtro del timeline.
 *
 * Los colores usan tokens Fluent semánticos — NO `brandPalette.accent` (que no
 * existe). El `color` de LeadStatus/CustomerStatus viene del catálogo (hex
 * configurable en BD) y se aplica directo al badge, no desde acá.
 *
 * En F1 sólo se consume `CHANNEL_TYPE_META` (lista + tab Identificadores +
 * drawer de creación). `ACTIVITY_TYPE_META`/`ACTIVITY_OUTCOME_LABELS`/
 * `ACTIVITY_FILTER_GROUPS` se declaran ya (contrato estable) pero los consume el
 * timeline en F5.
 */

import { tokens } from "@fluentui/react-components";
import {
  ArrowSwapRegular,
  CalendarClockRegular,
  CallRegular,
  ChatRegular,
  CheckmarkCircleRegular,
  GlobeRegular,
  MailRegular,
  MegaphoneRegular,
  NoteRegular,
  PersonSwapRegular,
  PhoneRegular,
  SendRegular,
} from "@fluentui/react-icons";
import type { FC } from "react";

import type { ActivityOutcome, ActivityType, ChannelType } from "@/types/crm.types";

// ── Canales ──────────────────────────────────────────────
// Label en ES; el ícono se renderiza junto al identifier en tablas/tab.
// instagram/facebook/other no tienen ícono propio dedicado en la versión
// instalada de @fluentui/react-icons → fallback al genérico ChatRegular.
export const CHANNEL_TYPE_META: Record<ChannelType, { label: string; icon: FC }> = {
  whatsapp: { label: "WhatsApp", icon: ChatRegular },
  telegram: { label: "Telegram", icon: SendRegular },
  web: { label: "Web", icon: GlobeRegular },
  phone: { label: "Teléfono", icon: PhoneRegular },
  email: { label: "Correo", icon: MailRegular },
  instagram: { label: "Instagram", icon: ChatRegular },
  facebook: { label: "Facebook", icon: ChatRegular },
  other: { label: "Otro", icon: ChatRegular },
};

// ── Tipos de actividad (F5) ──────────────────────────────
// Ícono + color (token Fluent, NO brandPalette.accent) + label ES por tipo.
export const ACTIVITY_TYPE_META: Record<ActivityType, { label: string; icon: FC; color: string }> =
  {
    NOTE: { label: "Nota", icon: NoteRegular, color: tokens.colorNeutralForeground2 },
    CALL_ATTEMPT: {
      label: "Llamada",
      icon: CallRegular,
      color: tokens.colorPaletteBlueForeground2,
    },
    FOLLOW_UP_SCHEDULED: {
      label: "Seguimiento programado",
      icon: CalendarClockRegular,
      color: tokens.colorPaletteMarigoldForeground2,
    },
    FOLLOW_UP_COMPLETED: {
      label: "Seguimiento realizado",
      icon: CheckmarkCircleRegular,
      color: tokens.colorPaletteGreenForeground2,
    },
    STATUS_CHANGE: {
      label: "Cambio de estado",
      icon: ArrowSwapRegular,
      color: tokens.colorPalettePurpleForeground2,
    },
    REASSIGNED: {
      label: "Reasignación",
      icon: PersonSwapRegular,
      color: tokens.colorNeutralForeground3,
    },
    CAMPAIGN_ATTRIBUTION: {
      label: "Atribución de campaña",
      icon: MegaphoneRegular,
      color: tokens.colorPaletteTealForeground2,
    },
    // Cross-módulo (emisión diferida; el front debe saber pintarlos si aparecen).
    MESSAGE_SENT: {
      label: "Mensaje enviado",
      icon: SendRegular,
      color: tokens.colorNeutralForeground3,
    },
    CONVERSATION_TAKEN: {
      label: "Conversación tomada",
      icon: ChatRegular,
      color: tokens.colorNeutralForeground3,
    },
    CONVERSATION_RELEASED: {
      label: "Conversación liberada",
      icon: ChatRegular,
      color: tokens.colorNeutralForeground3,
    },
    APPOINTMENT_BOOKED: {
      label: "Cita agendada",
      icon: CalendarClockRegular,
      color: tokens.colorPaletteGreenForeground2,
    },
    APPOINTMENT_CANCELLED: {
      label: "Cita cancelada",
      icon: CalendarClockRegular,
      color: tokens.colorPaletteRedForeground2,
    },
  };

// Resultado de llamada (label ES para el chip y el select del composer).
export const ACTIVITY_OUTCOME_LABELS: Record<ActivityOutcome, string> = {
  successful: "Exitosa",
  no_answer: "Sin respuesta",
  busy: "Ocupado",
  wrong_number: "Número equivocado",
  not_interested: "No interesado",
  interested: "Interesado",
};

// Chips de filtro del timeline → agrupan varios activity_type. "Todos" = sin
// filtro. "Sistema" agrupa los tipos emitidos por crm/otros módulos.
export const ACTIVITY_FILTER_GROUPS: {
  key: string;
  label: string;
  types: ActivityType[] | null; // null = todos
}[] = [
  { key: "all", label: "Todos", types: null },
  { key: "notes", label: "Notas", types: ["NOTE"] },
  { key: "calls", label: "Llamadas", types: ["CALL_ATTEMPT"] },
  {
    key: "follow_ups",
    label: "Seguimientos",
    types: ["FOLLOW_UP_SCHEDULED", "FOLLOW_UP_COMPLETED"],
  },
  { key: "status", label: "Estado", types: ["STATUS_CHANGE"] },
  {
    key: "system",
    label: "Sistema",
    types: [
      "REASSIGNED",
      "CAMPAIGN_ATTRIBUTION",
      "MESSAGE_SENT",
      "CONVERSATION_TAKEN",
      "CONVERSATION_RELEASED",
      "APPOINTMENT_BOOKED",
      "APPOINTMENT_CANCELLED",
    ],
  },
];
