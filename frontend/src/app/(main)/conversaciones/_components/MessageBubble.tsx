"use client";

import { Button, Tooltip, makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import { ArrowClockwiseRegular, AttachRegular } from "@fluentui/react-icons";
import { memo, useCallback } from "react";

import { formatDate, formatTime } from "@/lib/utils/date";
import type { MessageItem } from "@/types/conversations.types";

import { MessageStatusTicks } from "./MessageStatusTicks";

const useStyles = makeStyles({
  // Fila contenedora — define la alineación horizontal de la burbuja.
  rowStart: { display: "flex", justifyContent: "flex-start" },
  rowEnd: { display: "flex", justifyContent: "flex-end" },
  rowCenter: { display: "flex", justifyContent: "center" },

  bubble: {
    maxWidth: "78%",
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusLarge,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    // Lista potencialmente larga — el navegador no paga layout fuera de viewport.
    contentVisibility: "auto",
    containIntrinsicSize: "auto 56px",
  },
  inbound: {
    backgroundColor: tokens.colorNeutralBackground3,
    color: tokens.colorNeutralForeground1,
    borderBottomLeftRadius: tokens.borderRadiusSmall,
  },
  outbound: {
    backgroundColor: tokens.colorBrandBackground,
    color: tokens.colorNeutralForegroundOnBrand,
    borderBottomRightRadius: tokens.borderRadiusSmall,
  },
  content: {
    fontSize: tokens.fontSizeBase300,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  metaRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    alignSelf: "flex-end",
    fontSize: tokens.fontSizeBase200,
    opacity: 0.85,
  },
  // Acción "Reintentar" bajo una burbuja outbound fallida.
  retryRow: {
    display: "flex",
    justifyContent: "flex-end",
    marginTop: tokens.spacingVerticalXXS,
  },
  retryButton: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorPaletteRedForeground1,
  },
  attachment: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontStyle: "italic",
    fontSize: tokens.fontSizeBase200,
  },
  // Notificación de sistema: chip centrado, atenuado, sin "burbuja de chat".
  systemChip: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    maxWidth: "80%",
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusCircular,
    backgroundColor: tokens.colorNeutralBackground2,
    color: tokens.colorNeutralForeground3,
    fontSize: tokens.fontSizeBase200,
    textAlign: "center",
  },
});

interface Props {
  message: MessageItem;
  // F3: reintentar un OUTBOUND fallido (envía un mensaje NUEVO con el mismo texto;
  // el fallido queda inmutable). Opcional: si no se pasa, no se muestra el botón.
  onRetry?: (message: MessageItem) => void;
}

/**
 * Burbuja tipada del hilo (memoizada). Variantes:
 * - inbound (sender_type=contact): izquierda, fondo neutral, sin estado de entrega.
 * - outbound (sender_type=advisor/bot): derecha, fondo brand, con MessageStatusTicks.
 * - system (sender_type=system / content_type=system_notification): centrada y atenuada.
 *
 * `content_type=text` → render del content. Otros (image/audio/…) → placeholder
 * "📎 Adjunto (no disponible aún)" (F4 cablea el render real). El timestamp usa
 * hora local (`formatTime`, client-only) — nunca toISOString para render.
 *
 * Para un OUTBOUND fallido (con `onRetry`) se muestra una acción "Reintentar" que
 * crea un mensaje nuevo con el mismo texto (F3).
 */
function MessageBubbleImpl({ message, onRetry }: Props) {
  const styles = useStyles();

  const isSystem =
    message.sender_type === "system" || message.content_type === "system_notification";
  const isOutbound = message.direction === "outbound";

  const handleRetry = useCallback(() => onRetry?.(message), [onRetry, message]);

  // ── Notificación de sistema (centrada) ──
  if (isSystem) {
    return (
      <div className={styles.rowCenter}>
        <Tooltip content={formatDate(message.sent_at)} relationship="label" withArrow>
          <span className={styles.systemChip}>
            {message.content ?? "Evento de la conversación"}
          </span>
        </Tooltip>
      </div>
    );
  }

  const isText = message.content_type === "text";
  // Los docs de Firestore podrían no traer `attachments` (texto-primero, MVP) →
  // guardar contra undefined.
  const attachments = message.attachments ?? [];
  const hasAttachments = attachments.length > 0;

  // Outbound de texto fallido + handler → ofrecemos "Reintentar" (mensaje nuevo).
  const isFailed = message.failed_at != null || message.external_status === "failed";
  const canRetry = isOutbound && isText && isFailed && Boolean(message.content) && Boolean(onRetry);

  return (
    <div className={isOutbound ? styles.rowEnd : styles.rowStart}>
      <div className={mergeClasses(styles.bubble, isOutbound ? styles.outbound : styles.inbound)}>
        {isText && message.content ? (
          <span className={styles.content}>{message.content}</span>
        ) : !isText ? (
          // Placeholder de adjunto/media (F4 diferida). Si además trae texto
          // (caption), se muestra.
          <>
            <span className={styles.attachment}>
              <AttachRegular />
              Adjunto (no disponible aún)
            </span>
            {message.content ? <span className={styles.content}>{message.content}</span> : null}
          </>
        ) : null}

        {/* Adjuntos modelados (texto-primero en MVP; placeholder por adjunto). */}
        {hasAttachments && isText
          ? attachments.map((a) => (
              <span key={a.id} className={styles.attachment}>
                <AttachRegular />
                Adjunto (no disponible aún)
              </span>
            ))
          : null}

        <span className={styles.metaRow}>
          <Tooltip content={formatDate(message.sent_at)} relationship="label" withArrow>
            <span>{formatTime(message.sent_at)}</span>
          </Tooltip>
          {isOutbound ? <MessageStatusTicks message={message} /> : null}
        </span>

        {canRetry ? (
          <div className={styles.retryRow}>
            <Button
              className={styles.retryButton}
              appearance="transparent"
              size="small"
              icon={<ArrowClockwiseRegular />}
              onClick={handleRetry}
            >
              Reintentar
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleImpl);
