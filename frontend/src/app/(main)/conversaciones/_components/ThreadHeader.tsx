"use client";

import {
  Avatar,
  Badge,
  Button,
  Popover,
  PopoverSurface,
  PopoverTrigger,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { HistoryRegular } from "@fluentui/react-icons";

import {
  ASSIGNEE_TYPE_META,
  CHANNEL_TYPE_META,
  CONVERSATION_STATUS_META,
} from "@/lib/constants/conversations";
import { appTokens } from "@/lib/theme/brand";
import { formatDate, formatRelative } from "@/lib/utils/date";
import type { ConversationDetail } from "@/types/conversations.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    padding: tokens.spacingVerticalM,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.contentBg,
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
  },
  identity: { display: "flex", flexDirection: "column", gap: "2px", flex: 1, minWidth: 0 },
  name: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  subtitle: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  badges: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS, flexShrink: 0 },
  channelIcon: { display: "inline-flex", fontSize: "14px" },
  historySurface: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    maxWidth: "360px",
    maxHeight: "320px",
    overflowY: "auto",
  },
  historyTitle: {
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  historyItem: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    paddingBottom: tokens.spacingVerticalXS,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  historyMain: { color: appTokens.chromeText, fontWeight: tokens.fontWeightRegular },
  empty: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
});

interface Props {
  detail: ConversationDetail;
}

/**
 * Cabecera del hilo (sticky): contacto + canal + estado + asignación + un popover
 * con el historial de handoff (`assignment_history`, read-only). SIN controles de
 * tomar/liberar/cerrar/reabrir — eso es F3.
 */
export function ThreadHeader({ detail }: Props) {
  const styles = useStyles();

  const personName = detail.person?.full_name ?? "Contacto desconocido";
  const channelMeta = CHANNEL_TYPE_META[detail.channel_account.channel_type];
  const ChannelIcon = channelMeta.icon;
  const identifier =
    detail.person?.primary_identifier?.identifier ?? detail.channel_account.external_identifier;

  const statusMeta = CONVERSATION_STATUS_META[detail.status];
  const assigneeMeta = ASSIGNEE_TYPE_META[detail.assignee_type];

  const assignmentLabel =
    detail.assignee_type === "advisor"
      ? `Asignado a ${detail.assignee_user?.full_name ?? "—"}`
      : assigneeMeta.label;

  // Historial vigente primero (ordenado por started_at desc).
  const history = [...detail.assignment_history].sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );

  return (
    <div className={styles.root}>
      <div className={styles.topRow}>
        <Avatar name={personName} size={36} color="colorful" />
        <div className={styles.identity}>
          <span className={styles.name}>{personName}</span>
          <span className={styles.subtitle}>
            <span className={styles.channelIcon}>
              <ChannelIcon />
            </span>
            {channelMeta.label} · {identifier}
          </span>
        </div>
        <div className={styles.badges}>
          <Badge
            appearance="filled"
            style={{
              backgroundColor: statusMeta.color,
              color: tokens.colorNeutralForegroundOnBrand,
            }}
          >
            {statusMeta.label}
          </Badge>
          <Popover withArrow positioning="below-end">
            <PopoverTrigger disableButtonEnhancement>
              <Button appearance="subtle" size="small" icon={<HistoryRegular />}>
                Historial
              </Button>
            </PopoverTrigger>
            <PopoverSurface>
              <div className={styles.historySurface}>
                <span className={styles.historyTitle}>Historial de asignación</span>
                {history.length === 0 ? (
                  <span className={styles.empty}>Sin registros de asignación.</span>
                ) : (
                  history.map((log) => {
                    const to =
                      log.to_assignee_type === "advisor"
                        ? (log.to_assignee_user?.full_name ?? "Asesor")
                        : ASSIGNEE_TYPE_META[log.to_assignee_type].label;
                    const from =
                      log.from_assignee_type === null
                        ? null
                        : log.from_assignee_type === "advisor"
                          ? (log.from_assignee_user?.full_name ?? "Asesor")
                          : ASSIGNEE_TYPE_META[log.from_assignee_type].label;
                    const actor = log.by_actor_user?.full_name ?? "Sistema";
                    return (
                      <div key={log.id} className={styles.historyItem}>
                        <span className={styles.historyMain}>{from ? `${from} → ${to}` : to}</span>
                        <span>
                          {actor} · {formatRelative(log.started_at)}
                          {log.ended_at ? "" : " · vigente"}
                        </span>
                        {log.reason ? <span>Motivo: {log.reason}</span> : null}
                      </div>
                    );
                  })
                )}
              </div>
            </PopoverSurface>
          </Popover>
        </div>
      </div>
      <div className={styles.subtitle}>
        <Avatar
          name={detail.assignee_user?.full_name ?? assigneeMeta.label}
          size={20}
          color={detail.assignee_type === "advisor" ? "colorful" : "neutral"}
        />
        <span style={{ color: assigneeMeta.color }}>{assignmentLabel}</span>
        {detail.unread_count > 0 ? (
          <Badge appearance="tint" color="informative">
            {detail.unread_count} sin leer
          </Badge>
        ) : null}
      </div>
      <span className={styles.empty}>
        Abierta {formatDate(detail.opened_at)}
        {detail.closed_at ? ` · cerrada ${formatDate(detail.closed_at)}` : ""}
      </span>
    </div>
  );
}
