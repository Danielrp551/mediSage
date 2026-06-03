"use client";

import { Avatar, Badge, makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import { memo, useEffect, useState } from "react";

import { CHANNEL_TYPE_META } from "@/lib/constants/conversations";
import { appTokens } from "@/lib/theme/brand";
import { formatRelative } from "@/lib/utils/date";
import type { ConversationListItem } from "@/types/conversations.types";

const useStyles = makeStyles({
  row: {
    display: "flex",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    cursor: "pointer",
    borderLeft: `3px solid transparent`,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
    // Lista potencialmente larga — el navegador no paga layout fuera de viewport.
    contentVisibility: "auto",
    containIntrinsicSize: "auto 64px",
    ":hover": { backgroundColor: appTokens.tableRowHover },
  },
  rowSelected: {
    borderLeftColor: tokens.colorBrandStroke1,
    backgroundColor: appTokens.chromeBgActive,
  },
  rowClosed: { opacity: 0.7 },
  main: { display: "flex", flexDirection: "column", gap: "2px", flex: 1, minWidth: 0 },
  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalXS,
  },
  nameWrap: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    minWidth: 0,
  },
  channelIcon: { display: "inline-flex", fontSize: "14px", color: appTokens.chromeTextMuted },
  name: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  nameUnread: { fontWeight: tokens.fontWeightSemibold },
  time: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted, flexShrink: 0 },
  bottomRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalXS,
  },
  preview: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    flex: 1,
    minWidth: 0,
  },
  assignee: {
    fontSize: tokens.fontSizeBase100,
    color: appTokens.chromeTextMuted,
    flexShrink: 0,
  },
});

export interface ConversationListItemRowProps {
  conversation: ConversationListItem;
  selected: boolean;
  /** Callback ESTABLE (useCallback en el padre) para no romper el React.memo. */
  onSelect: (id: string) => void;
}

/**
 * Fila densa del inbox (memoizada). El polling re-pinta la lista cada ~10s; el
 * React.memo evita re-renderizar las filas cuya conversación no cambió (las que
 * el polling no reemplazó conservan su referencia). Avatar + canal + nombre +
 * preview + hora relativa (client-only) + badge de no-leídos + asignación.
 */
function ConversationListItemRowImpl({
  conversation,
  selected,
  onSelect,
}: ConversationListItemRowProps) {
  const styles = useStyles();

  // La hora relativa usa new Date() (ahora) → client-only. El SSR en UTC
  // desfasaría la frontera del día en Lima (UTC-5) y daría mismatch de
  // hidratación; por eso se renderiza recién tras montar (lección TZ recurrente).
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const name = conversation.person?.full_name ?? "Contacto desconocido";
  const channelMeta = CHANNEL_TYPE_META[conversation.channel_account.channel_type];
  const ChannelIcon = channelMeta.icon;
  const hasUnread = conversation.unread_count > 0;
  const isClosed = conversation.status === "closed";

  const assigneeLabel =
    conversation.assignee_type === "advisor"
      ? (conversation.assignee_user?.full_name ?? "Asignada")
      : conversation.assignee_type === "bot"
        ? "Bot"
        : "Sin asignar";

  return (
    <div
      className={mergeClasses(
        styles.row,
        selected && styles.rowSelected,
        isClosed && styles.rowClosed,
      )}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(conversation.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(conversation.id);
        }
      }}
    >
      <Avatar name={name} size={36} color="colorful" />
      <div className={styles.main}>
        <div className={styles.topRow}>
          <span className={styles.nameWrap}>
            <span className={styles.channelIcon}>
              <ChannelIcon />
            </span>
            <span className={mergeClasses(styles.name, hasUnread && styles.nameUnread)}>
              {name}
            </span>
          </span>
          <span className={styles.time}>
            {mounted ? formatRelative(conversation.last_message_at) : ""}
          </span>
        </div>
        <div className={styles.bottomRow}>
          <span className={styles.preview}>
            {conversation.last_message_preview ?? "Sin mensajes todavía"}
          </span>
          {hasUnread ? (
            <Badge appearance="filled" color="brand" shape="circular">
              {conversation.unread_count}
            </Badge>
          ) : null}
        </div>
        <span className={styles.assignee}>{assigneeLabel}</span>
      </div>
    </div>
  );
}

export const ConversationListItemRow = memo(ConversationListItemRowImpl);
