"use client";

import {
  Badge,
  Button,
  MessageBar,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowDownRegular } from "@fluentui/react-icons";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getConversation } from "@/actions/conversation.actions";
import { appTokens } from "@/lib/theme/brand";
import { dayGroupLabel } from "@/lib/utils/date";
import type { ConversationDetail, MessageItem } from "@/types/conversations.types";

import { MessageDayGroup, type DayGroupData } from "./MessageDayGroup";
import { ThreadHeader } from "./ThreadHeader";
import { useThreadMessages } from "./useThreadMessages";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    minWidth: 0,
    backgroundColor: appTokens.pageBg,
  },
  scroll: {
    flex: 1,
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    position: "relative",
  },
  liveBar: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalM}`,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.contentBg,
  },
  liveDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    backgroundColor: tokens.colorPaletteGreenForeground2,
    display: "inline-block",
  },
  reconnectingDot: { backgroundColor: tokens.colorPaletteMarigoldForeground2 },
  empty: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    padding: tokens.spacingHorizontalXXL,
  },
  skeletonBubble: { marginBottom: tokens.spacingVerticalM },
  newBadge: {
    position: "sticky",
    bottom: tokens.spacingVerticalM,
    alignSelf: "center",
    zIndex: 1,
  },
  closedBar: {
    padding: tokens.spacingVerticalM,
    borderTop: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.contentBg,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    textAlign: "center",
  },
});

interface Props {
  conversationId: string;
  realtimeToken: string | null;
}

/**
 * Panel derecho: el hilo de la conversación seleccionada (F2 = SOLO LECTURA). El
 * `ConversationDetail` (header/historial) se carga por server action; los mensajes
 * llegan en vivo por el listener Firestore (`useThreadMessages`). Agrupación por
 * día client-only (TZ-safe). SIN composer ni handoff (F3).
 */
export function ConversationThread({ conversationId, realtimeToken }: Props) {
  const styles = useStyles();

  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const reqIdRef = useRef(0);

  // Mensajes en vivo desde Firestore (o fallback server-side).
  const { messages, status: msgStatus } = useThreadMessages(conversationId, realtimeToken);

  // Cálculos client-only (TZ): "mounted" habilita la agrupación por día con
  // new Date() sin mismatch de hidratación.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const loadDetail = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setDetailError(null);
    void getConversation(conversationId)
      .then((res) => {
        if (reqId !== reqIdRef.current) return;
        setDetail(res.data);
        setLoading(false);
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setDetailError("No se pudo cargar la conversación. Intenta de nuevo.");
        setLoading(false);
      });
  }, [conversationId]);

  // Reset + recarga del detail al cambiar de conversación.
  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  // Orden cronológico ascendente (lo más nuevo abajo) por sent_at, y agrupación
  // por día — recomputa solo cuando cambian los mensajes (o al montar en cliente).
  const dayGroups = useMemo<DayGroupData[]>(() => {
    if (!mounted) return [];
    const list = Object.values(messages).sort(
      (a, b) => new Date(a.sent_at).getTime() - new Date(b.sent_at).getTime(),
    );
    const byKey = new Map<string, DayGroupData>();
    for (const m of list) {
      const d = new Date(m.sent_at);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      let group = byKey.get(key);
      if (!group) {
        group = { key, label: dayGroupLabel(m.sent_at), items: [] };
        byKey.set(key, group);
      }
      group.items.push(m);
    }
    return Array.from(byKey.values());
  }, [messages, mounted]);

  // ── Auto-scroll "stick to bottom" condicional ──
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const atBottomRef = useRef(true);
  const [showNewBadge, setShowNewBadge] = useState(false);
  const lastCountRef = useRef(0);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    atBottomRef.current = distance < 80;
    if (atBottomRef.current) setShowNewBadge(false);
  }, []);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    atBottomRef.current = true;
    setShowNewBadge(false);
  }, []);

  // Al llegar mensajes nuevos: si el usuario está al fondo → auto-scroll; si está
  // leyendo arriba → badge "↓ N nuevos" (no robar el scroll).
  const messageCount = useMemo(() => Object.keys(messages).length, [messages]);
  useEffect(() => {
    if (!mounted) return;
    if (messageCount > lastCountRef.current) {
      if (atBottomRef.current) {
        // Defer al próximo frame para que el layout ya tenga las burbujas nuevas.
        requestAnimationFrame(scrollToBottom);
      } else {
        setShowNewBadge(true);
      }
    }
    lastCountRef.current = messageCount;
  }, [messageCount, mounted, scrollToBottom]);

  // Al cambiar de conversación, resetear el contador y pegar al fondo.
  useEffect(() => {
    lastCountRef.current = 0;
    atBottomRef.current = true;
    setShowNewBadge(false);
  }, [conversationId]);

  if (loading && !detail) {
    return (
      <div className={styles.root}>
        <div className={styles.scroll}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className={styles.skeletonBubble}>
              <SkeletonItem
                shape="rectangle"
                size={40}
                style={{ width: "60%", alignSelf: i % 2 === 0 ? "flex-start" : "flex-end" }}
              />
            </Skeleton>
          ))}
        </div>
      </div>
    );
  }

  if (detailError) {
    return (
      <div className={styles.root}>
        <div className={styles.empty}>
          <MessageBar intent="error">
            <MessageBarBody>{detailError}</MessageBarBody>
          </MessageBar>
          <Button appearance="secondary" onClick={loadDetail}>
            Reintentar
          </Button>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  const messagesLoading = msgStatus === "loading";
  const noMessages = !messagesLoading && messageCount === 0;

  return (
    <div className={styles.root}>
      <ThreadHeader detail={detail} />

      <div className={styles.liveBar}>
        <span
          className={
            msgStatus === "error" ? `${styles.liveDot} ${styles.reconnectingDot}` : styles.liveDot
          }
        />
        {msgStatus === "live"
          ? "En vivo"
          : msgStatus === "fallback"
            ? "Sin actualización en vivo"
            : msgStatus === "error"
              ? "Reconectando…"
              : "Cargando…"}
      </div>

      <div ref={scrollRef} className={styles.scroll} onScroll={handleScroll}>
        {messagesLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className={styles.skeletonBubble}>
              <SkeletonItem
                shape="rectangle"
                size={40}
                style={{ width: "55%", alignSelf: i % 2 === 0 ? "flex-start" : "flex-end" }}
              />
            </Skeleton>
          ))
        ) : noMessages ? (
          <div className={styles.empty}>
            <span>Aún no hay mensajes en esta conversación.</span>
          </div>
        ) : (
          dayGroups.map((group) => <MessageDayGroup key={group.key} group={group} />)
        )}

        {showNewBadge ? (
          <Button
            className={styles.newBadge}
            appearance="primary"
            shape="circular"
            size="small"
            icon={<ArrowDownRegular />}
            onClick={scrollToBottom}
          >
            Mensajes nuevos
          </Button>
        ) : null}
      </div>

      {detail.status === "closed" ? (
        <div className={styles.closedBar}>
          <Badge appearance="tint" color="informative">
            Esta conversación está cerrada
          </Badge>
        </div>
      ) : null}
    </div>
  );
}
