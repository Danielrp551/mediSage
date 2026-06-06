"use client";

import {
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { DocumentSearchRegular } from "@fluentui/react-icons";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listBotEvents, listBotToolCalls } from "@/actions/bot-debug.actions";
import { appTokens } from "@/lib/theme/brand";
import { dayGroupLabel } from "@/lib/utils/date";
import type { BotEventItem, BotToolCallItem } from "@/types/bots.types";

import { BotEventCard } from "./BotEventCard";
import { BotToolCallCard } from "./BotToolCallCard";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  refreshing: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  dayGroup: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  dayHeader: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: appTokens.chromeTextMuted,
  },
  orphanHeader: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeTextMuted,
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    minHeight: "160px",
  },
  emptyIcon: { fontSize: "36px", opacity: 0.7 },
});

interface Props {
  cid: string;
  /** Bump por el padre para forzar un refetch silencioso (tras reset/dispatch). */
  reloadToken: number;
}

interface DayGroup {
  key: string;
  label: string;
  items: BotEventItem[];
}

/**
 * Timeline de turnos (`BotEvent`) + llamadas a herramienta (`BotToolCall`)
 * anidadas. Feed cronológico DESCENDENTE (lo más nuevo arriba) agrupado por día
 * — el cálculo "Hoy"/"Ayer" es **client-only** (`mounted` + `dayGroupLabel`):
 * SSR corre en UTC y desfasaría la frontera del día en Lima (UTC-5).
 *
 * El merge events+tool-calls (anidar por `bot_event_id`) y la agrupación por día
 * van en `useMemo`; las cards son `React.memo` → el refetch tras un debug no
 * re-renderiza todo. El primer fetch muestra skeleton; los refetch por
 * `reloadToken` son silenciosos (no desmontan el feed visible).
 */
function BotEventTimelineImpl({ cid, reloadToken }: Props) {
  const styles = useStyles();

  const [events, setEvents] = useState<BotEventItem[]>([]);
  const [toolCalls, setToolCalls] = useState<BotToolCallItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Client-only para los cálculos con `new Date()` (agrupación por día) sin mismatch.
  const [mounted, setMounted] = useState(false);
  const [nowMs, setNowMs] = useState(0);
  useEffect(() => {
    setMounted(true);
    setNowMs(Date.now());
  }, []);

  const reqIdRef = useRef(0);

  const load = useCallback(
    (silent: boolean) => {
      const reqId = ++reqIdRef.current;
      if (silent) setRefreshing(true);
      else setLoading(true);
      setError(null);
      // allSettled: un fallo de tool-calls (p.ej. un rol con BOT_EVENTS_READ pero sin
      // BOT_TOOL_CALLS_READ → 403) NO debe tumbar el render de los turnos que sí puede ver.
      void Promise.allSettled([listBotEvents(cid), listBotToolCalls(cid)]).then(
        ([evRes, tcRes]) => {
          if (reqId !== reqIdRef.current) return;
          if (evRes.status !== "fulfilled") {
            setError("No se pudo cargar la depuración.");
            setLoading(false);
            setRefreshing(false);
            return;
          }
          setEvents(evRes.value.data);
          setToolCalls(tcRes.status === "fulfilled" ? tcRes.value.data : []);
          setLoading(false);
          setRefreshing(false);
          setNowMs(Date.now());
        },
      );
    },
    [cid],
  );

  // Carga inicial + recarga al cambiar de conversación.
  useEffect(() => {
    load(false);
  }, [load]);

  // Refetch silencioso cuando el padre bumpea el token (reset/dispatch). El
  // token arranca en 0 → ignoramos esa primera corrida (la cubre `load(false)`).
  const firstTokenRef = useRef(reloadToken);
  useEffect(() => {
    if (reloadToken === firstTokenRef.current) return;
    load(true);
  }, [reloadToken, load]);

  // Tool-calls indexadas por bot_event_id (una sola pasada, no por render).
  const callsByEvent = useMemo(() => {
    const map = new Map<string, BotToolCallItem[]>();
    const orphans: BotToolCallItem[] = [];
    for (const tc of toolCalls) {
      if (tc.bot_event_id) {
        const arr = map.get(tc.bot_event_id);
        if (arr) arr.push(tc);
        else map.set(tc.bot_event_id, [tc]);
      } else {
        orphans.push(tc);
      }
    }
    return { map, orphans };
  }, [toolCalls]);

  // Agrupación por día — DESCENDENTE (lo más nuevo arriba). Client-only.
  const groups = useMemo<DayGroup[]>(() => {
    if (!mounted) return [];
    const sorted = [...events].sort(
      (a, b) => new Date(b.created_on).getTime() - new Date(a.created_on).getTime(),
    );
    const byKey = new Map<string, DayGroup>();
    for (const ev of sorted) {
      const d = new Date(ev.created_on);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      let group = byKey.get(key);
      if (!group) {
        group = { key, label: dayGroupLabel(ev.created_on), items: [] };
        byKey.set(key, group);
      }
      group.items.push(ev);
    }
    return Array.from(byKey.values());
  }, [events, mounted]);

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>Timeline de turnos</h2>
        {refreshing ? (
          <span className={styles.refreshing}>
            <Spinner size="tiny" /> Actualizando…
          </span>
        ) : null}
      </div>

      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
          <MessageBarActions>
            <Button size="small" onClick={() => load(false)}>
              Reintentar
            </Button>
          </MessageBarActions>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.dayGroup}>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i}>
              <SkeletonItem shape="rectangle" size={48} />
            </Skeleton>
          ))}
        </div>
      ) : events.length === 0 && !error ? (
        <div className={styles.empty}>
          <DocumentSearchRegular className={styles.emptyIcon} />
          <span>Sin turnos registrados todavía.</span>
        </div>
      ) : (
        <>
          {groups.map((group) => (
            <div key={group.key} className={styles.dayGroup}>
              <div className={styles.dayHeader}>{group.label}</div>
              {group.items.map((ev) => (
                <BotEventCard
                  key={ev.id}
                  event={ev}
                  toolCalls={callsByEvent.map.get(ev.id) ?? []}
                  nowMs={nowMs}
                />
              ))}
            </div>
          ))}

          {callsByEvent.orphans.length > 0 ? (
            <div className={styles.dayGroup}>
              <div className={styles.orphanHeader}>Sin turno asociado</div>
              {callsByEvent.orphans.map((tc) => (
                <BotToolCallCard key={`orphan-${tc.id}`} toolCall={tc} />
              ))}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export const BotEventTimeline = memo(BotEventTimelineImpl);
