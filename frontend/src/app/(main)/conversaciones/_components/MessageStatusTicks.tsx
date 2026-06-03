"use client";

import { Tooltip, makeStyles, tokens } from "@fluentui/react-components";

import { MESSAGE_STATUS_META } from "@/lib/constants/conversations";
import type { MessageExternalStatus, MessageItem } from "@/types/conversations.types";

const useStyles = makeStyles({
  ticks: {
    display: "inline-flex",
    alignItems: "center",
    gap: "2px",
    fontSize: tokens.fontSizeBase200,
    lineHeight: 1,
  },
  icon: { fontSize: "14px", display: "inline-flex" },
});

/**
 * Deriva el estado visible de un mensaje OUTBOUND a partir de los timestamps y el
 * `external_status` (varchar libre del provider). Prioridad: failed > read >
 * delivered > sent > pending (optimista, antes de la confirmación de Meta).
 */
function deriveStatus(m: MessageItem): MessageExternalStatus | "pending" {
  if (m.failed_at || m.external_status === "failed") return "failed";
  if (m.read_at || m.external_status === "read") return "read";
  if (m.delivered_at || m.external_status === "delivered") return "delivered";
  if (m.external_id || m.external_status === "sent") return "sent";
  return "pending";
}

interface Props {
  message: MessageItem;
}

/**
 * "Tick" estilo WhatsApp para mensajes OUTBOUND (no aplica a inbound). Muestra el
 * glifo + color según el estado de entrega; en "failed" el tooltip lleva el
 * `failure_reason`. El botón "Reintentar" es F3 (composer) — acá es solo lectura.
 */
export function MessageStatusTicks({ message }: Props) {
  const styles = useStyles();
  const status = deriveStatus(message);
  const meta = MESSAGE_STATUS_META[status];
  const Icon = meta.icon;

  const tooltipContent =
    status === "failed" && message.failure_reason
      ? `${meta.label}: ${message.failure_reason}`
      : meta.label;

  return (
    <Tooltip content={tooltipContent} relationship="label" withArrow>
      <span className={styles.ticks} style={{ color: meta.color }} aria-label={meta.label}>
        <span className={styles.icon}>
          <Icon />
        </span>
      </span>
    </Tooltip>
  );
}
