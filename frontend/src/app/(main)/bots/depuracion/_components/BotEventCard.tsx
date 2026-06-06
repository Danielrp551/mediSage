"use client";

import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Badge,
  Card,
  MessageBar,
  MessageBarBody,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { memo } from "react";

import { BOT_EVENT_TYPE_META } from "@/lib/constants/bots";
import { appTokens } from "@/lib/theme/brand";
import { formatDate, formatRelative } from "@/lib/utils/date";
import type { BotEventItem, BotToolCallItem } from "@/types/bots.types";

import { BotToolCallCard } from "./BotToolCallCard";

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    padding: tokens.spacingVerticalM,
    // El timeline puede acumular decenas de turnos — el navegador no paga
    // layout/paint de lo que está fuera del viewport (molde Timeline de crm).
    contentVisibility: "auto",
    containIntrinsicSize: "auto 120px",
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  title: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  time: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    flexShrink: 0,
    cursor: "default",
  },
  metrics: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    fontFamily: appTokens.fontMono,
  },
  messages: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    fontSize: tokens.fontSizeBase200,
  },
  msgRow: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    minWidth: 0,
  },
  msgLabel: { color: appTokens.chromeTextMuted, flexShrink: 0 },
  msgId: {
    fontFamily: appTokens.fontMono,
    color: appTokens.chromeText,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "220px",
    cursor: "help",
  },
  toolCalls: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    marginTop: tokens.spacingVerticalXXS,
  },
  pre: {
    margin: 0,
    padding: tokens.spacingVerticalXS,
    backgroundColor: tokens.colorNeutralBackground3,
    borderRadius: tokens.borderRadiusSmall,
    fontFamily: appTokens.fontMono,
    fontSize: tokens.fontSizeBase200,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    maxHeight: "260px",
    overflow: "auto",
  },
});

export interface BotEventCardProps {
  event: BotEventItem;
  /** Tool-calls que cuelgan de este evento (match por bot_event_id == event.id). */
  toolCalls: BotToolCallItem[];
  /** Instante actual (ms) — client-only por el padre (TZ-safe). No usado para
   *  cálculo aquí salvo invalidar el memo cuando el padre refresca. */
  nowMs: number;
}

function formatCost(cost: string | null): string {
  if (cost === null) return "—";
  const n = Number(cost);
  if (Number.isNaN(n)) return cost;
  return `$${n.toFixed(4)}`;
}

function MessageIdRow({ label, id }: { label: string; id: string }) {
  const styles = useStyles();
  return (
    <span className={styles.msgRow}>
      <span className={styles.msgLabel}>{label}:</span>
      <Tooltip content={id} relationship="label" withArrow>
        <span className={styles.msgId}>{id}</span>
      </Tooltip>
    </span>
  );
}

/**
 * Tarjeta de un turno del bot (`BotEvent`), memoizada. Encabezado con glifo +
 * badge de event_type + hora relativa (client-only, via `formatRelative`),
 * métricas (tokens/latencia/costo), mids de entrada/salida (truncados con
 * tooltip), error si falló, metadata colapsada, y las tool-calls anidadas.
 */
function BotEventCardImpl({ event, toolCalls }: BotEventCardProps) {
  const styles = useStyles();
  const meta = BOT_EVENT_TYPE_META[event.event_type];
  const showMetrics =
    event.tokens_in !== null ||
    event.tokens_out !== null ||
    event.latency_ms !== null ||
    event.cost_estimated_usd !== null;

  return (
    <Card className={styles.card} aria-label={`Turno ${event.turn_number}, ${meta.label}`}>
      <div className={styles.topRow}>
        <span className={styles.title}>
          <span style={{ color: meta.color }} aria-hidden>
            {meta.glyph}
          </span>
          Turno {event.turn_number}
          <Badge appearance="tint" color="informative" aria-label={meta.label}>
            {meta.label}
          </Badge>
        </span>
        <Tooltip content={formatDate(event.created_on)} relationship="label" withArrow>
          <span className={styles.time}>{formatRelative(event.created_on)}</span>
        </Tooltip>
      </div>

      {showMetrics ? (
        <div className={styles.metrics}>
          <span>
            tokens ↑{event.tokens_in ?? "—"} ↓{event.tokens_out ?? "—"}
          </span>
          <span>{event.latency_ms !== null ? `${event.latency_ms}ms` : "—"}</span>
          <span>{formatCost(event.cost_estimated_usd)}</span>
        </div>
      ) : null}

      {event.input_message_id || event.output_message_id ? (
        <div className={styles.messages}>
          {event.input_message_id ? (
            <MessageIdRow label="Entrada" id={event.input_message_id} />
          ) : null}
          {event.output_message_id ? (
            <MessageIdRow label="Salida" id={event.output_message_id} />
          ) : null}
        </div>
      ) : null}

      {event.error ? (
        <MessageBar intent="error">
          <MessageBarBody>{event.error}</MessageBarBody>
        </MessageBar>
      ) : null}

      {event.metadata && Object.keys(event.metadata).length > 0 ? (
        <Accordion collapsible>
          <AccordionItem value="metadata">
            <AccordionHeader size="small">Ver detalle</AccordionHeader>
            <AccordionPanel>
              <pre className={styles.pre}>{JSON.stringify(event.metadata, null, 2)}</pre>
            </AccordionPanel>
          </AccordionItem>
        </Accordion>
      ) : null}

      {toolCalls.length > 0 ? (
        <div className={styles.toolCalls}>
          {toolCalls.map((tc) => (
            <BotToolCallCard key={tc.id} toolCall={tc} />
          ))}
        </div>
      ) : null}
    </Card>
  );
}

export const BotEventCard = memo(BotEventCardImpl);
