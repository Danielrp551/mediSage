"use client";

import { makeStyles, tokens } from "@fluentui/react-components";
import { ChatRegular } from "@fluentui/react-icons";
import { parseAsString, useQueryState } from "nuqs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getRealtimeToken,
  listConversations,
  listMyConversations,
} from "@/actions/conversation.actions";
import { CONVERSATIONS_POLL_MS, INBOX_FILTER_PRESETS } from "@/lib/constants/conversations";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { ChannelAccountOption, ConversationListItem } from "@/types/conversations.types";

import { ConversationList } from "./ConversationList";
import { ConversationThread } from "./ConversationThread";

const useStyles = makeStyles({
  shell: {
    display: "grid",
    gridTemplateColumns: "360px 1fr",
    height: "calc(100vh - 96px)", // alto del shell (descontando TopBar + padding del layout)
    minHeight: "480px",
    border: `1px solid ${appTokens.chromeBorder}`,
    borderRadius: tokens.borderRadiusMedium,
    overflow: "hidden",
    backgroundColor: appTokens.contentBg,
  },
  threadPane: { minWidth: 0, display: "flex", flexDirection: "column" },
  placeholder: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    backgroundColor: appTokens.pageBg,
    padding: tokens.spacingHorizontalXXL,
  },
  placeholderIcon: { fontSize: "44px", opacity: 0.6 },
});

interface Props {
  scope: "all" | "mine";
  initialData: ApiPaginated<ConversationListItem> | null;
  initialQueryParams: string;
  channelAccounts: ChannelAccountOption[];
  initialStatus: string;
  initialSelectedId: string | null;
  pageSize: number;
}

// El valor del param `status` en la URL del inbox. "all" es un SENTINEL client-only
// (el backend solo acepta open/closed) → en buildQueryParams "all" NO se emite, así
// "Todas" significa "sin filtro de estado". Default de landing = "open".
// Deriva el preset activo a partir del estado + flag "sin asignar" de la URL.
function derivePreset(status: string, unassigned: boolean, scope: "all" | "mine"): string {
  if (status === "closed") return "closed";
  if (status === "all") return "all";
  if (status === "open" && unassigned && scope === "all") return "unassigned";
  return "open";
}

/**
 * Inbox de 2 paneles (pieza bespoke más pesada del módulo, análoga al timeline de
 * crm). Orquesta: lista (izquierda, POLLING silencioso pausable) + hilo (derecha,
 * REAL-TIME Firestore). Compartido por `bandeja` (scope="all") y, en F3,
 * `mis-conversaciones` (scope="mine"). F2 = SOLO LECTURA (sin composer/handoff).
 */
export function InboxShell({
  scope,
  initialData,
  initialQueryParams,
  channelAccounts,
  initialStatus,
  initialSelectedId,
  pageSize,
}: Props) {
  const styles = useStyles();

  // ── URL state (deep-linkable) ──
  const [selectedId, setSelectedId] = useQueryState(
    "c",
    parseAsString.withDefault(initialSelectedId ?? ""),
  );
  const [statusFilter, setStatusFilter] = useQueryState(
    "status",
    parseAsString.withDefault(initialStatus),
  );
  const [channelFilter, setChannelFilter] = useQueryState("channel_account_id", parseAsString);
  const [unassignedFilter, setUnassignedFilter] = useQueryState("unassigned", parseAsString);

  // Búsqueda CLIENT-SIDE (no va al server ni a la URL).
  const [search, setSearch] = useState("");

  const unassigned = unassignedFilter === "true";
  const activePreset = derivePreset(statusFilter, unassigned, scope);

  // ── Datos de la lista (seed con el prefetch RSC; polling propio) ──
  const [items, setItems] = useState<ConversationListItem[]>(initialData?.data.items ?? []);
  const [loading, setLoading] = useState(initialData === null);
  const [error, setError] = useState<string | null>(
    initialData === null ? "No se pudo cargar la bandeja. Reintentando…" : null,
  );
  const [paused, setPaused] = useState(false);
  const [lastRefreshAt, setLastRefreshAt] = useState<number | null>(
    initialData ? Date.now() : null,
  );
  const [tick, setTick] = useState(0); // re-render del label "hace Ns"

  // Token Firebase para los listeners real-time del hilo. Se pide UNA vez al
  // montar (idempotente server-side). Si falla → el hilo cae a fallback.
  const [realtimeToken, setRealtimeToken] = useState<string | null>(null);

  const reqIdRef = useRef(0);
  const inFlightRef = useRef(false);

  // Construye el query string de filtros (columnas REALES) para la URL del listado.
  // "all" es sentinel client-only → NO se emite (el backend solo acepta open/closed).
  const buildQueryParams = useCallback((): string => {
    const params = new URLSearchParams();
    if (statusFilter === "open" || statusFilter === "closed") {
      params.set("status", statusFilter);
    }
    if (channelFilter) params.set("channel_account_id", channelFilter);
    if (scope === "all" && unassigned) params.set("unassigned", "true");
    return params.toString();
  }, [statusFilter, channelFilter, unassigned, scope]);

  const fetcher = scope === "mine" ? listMyConversations : listConversations;

  // Carga de la lista. `silent` (polling / refetch) NO toca el skeleton — evita
  // flash; solo la primera carga y el cambio de filtro muestran skeleton.
  const load = useCallback(
    (silent: boolean) => {
      if (inFlightRef.current) return; // sin polling concurrente: omitir, no encolar
      const reqId = ++reqIdRef.current;
      inFlightRef.current = true;
      if (!silent) setLoading(true);
      void fetcher(
        {
          pagination: { skip: 0, limit: pageSize },
          sorting: { sort_by: "last_message_at", sort_order: "desc" },
          filters: null,
        },
        buildQueryParams(),
      )
        .then((res) => {
          if (reqId !== reqIdRef.current) return;
          setItems(res.data.items);
          setError(null);
          setLoading(false);
          setLastRefreshAt(Date.now());
        })
        .catch(() => {
          if (reqId !== reqIdRef.current) return;
          // En refetch silencioso no se descarta lo visible; solo se marca el error.
          if (!silent) setLoading(false);
          setError("No se pudo cargar la bandeja. Reintentando…");
        })
        .finally(() => {
          if (reqId === reqIdRef.current) inFlightRef.current = false;
        });
    },
    [fetcher, pageSize, buildQueryParams],
  );

  // Refetch (no silencioso) al cambiar de filtro. Se omite la primera vez si el
  // request default coincide con el prefetch RSC (evita doble fetch + flash).
  const isInitialMount = useRef(true);
  useEffect(() => {
    const currentParams = buildQueryParams();
    if (isInitialMount.current) {
      isInitialMount.current = false;
      // El prefetch del RSC ya trae estos filtros → no refetchear si coinciden.
      if (currentParams === initialQueryParams && initialData !== null) return;
    }
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, channelFilter, unassignedFilter]);

  // Polling silencioso (~10s), pausable y pausado en pestaña oculta.
  useEffect(() => {
    if (paused) return;
    const id = setInterval(() => {
      if (document.visibilityState === "hidden") return; // no golpear el backend en background
      load(true);
    }, CONVERSATIONS_POLL_MS);
    return () => clearInterval(id);
  }, [paused, load]);

  // Tick para refrescar el label "hace Ns" (client-only).
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // Mintar el Custom Token al montar (una sola vez).
  useEffect(() => {
    let cancelled = false;
    void getRealtimeToken().then((res) => {
      if (cancelled) return;
      if (res.ok && res.data) setRealtimeToken(res.data.token);
      // si !res.ok: realtimeToken queda null → el hilo usa el fallback server-side.
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Handlers (estables, para no romper el React.memo de las filas) ──
  const handleSelect = useCallback(
    (id: string) => {
      void setSelectedId(id);
    },
    [setSelectedId],
  );

  const handlePresetChange = useCallback(
    (key: string) => {
      const preset = INBOX_FILTER_PRESETS.find((p) => p.key === key);
      // El preset "all" usa el sentinel "all" (no se emite al backend); el resto
      // fija open/closed. NO se pasa null (el parser lo resetearía al default "open").
      void setStatusFilter(preset?.status ?? "all");
      void setUnassignedFilter(preset?.unassigned ? "true" : null);
    },
    [setStatusFilter, setUnassignedFilter],
  );

  const handleChannelChange = useCallback(
    (id: string | null) => {
      void setChannelFilter(id && id.length > 0 ? id : null);
    },
    [setChannelFilter],
  );

  const lastRefreshLabel = useMemo(() => {
    void tick; // recomputa cada segundo
    if (!lastRefreshAt) return "";
    const secs = Math.max(0, Math.round((Date.now() - lastRefreshAt) / 1000));
    if (paused) return "actualización pausada";
    if (secs < 5) return "actualizado ahora";
    return `actualizado hace ${secs}s`;
  }, [lastRefreshAt, tick, paused]);

  const activeSelectedId = selectedId && selectedId.length > 0 ? selectedId : null;

  return (
    <div className={styles.shell}>
      <ConversationList
        scope={scope}
        items={items}
        loading={loading}
        error={loading ? null : error}
        selectedId={activeSelectedId}
        onSelect={handleSelect}
        activePreset={activePreset}
        onPresetChange={handlePresetChange}
        channelAccounts={channelAccounts}
        channelFilter={channelFilter}
        onChannelChange={handleChannelChange}
        search={search}
        onSearchChange={setSearch}
        paused={paused}
        onTogglePause={() => setPaused((p) => !p)}
        onRefresh={() => load(false)}
        lastRefreshLabel={lastRefreshLabel}
      />

      <div className={styles.threadPane}>
        {activeSelectedId ? (
          <ConversationThread
            key={activeSelectedId}
            conversationId={activeSelectedId}
            realtimeToken={realtimeToken}
          />
        ) : (
          <div className={styles.placeholder}>
            <ChatRegular className={styles.placeholderIcon} />
            <span>Selecciona una conversación</span>
            <span>Elige una conversación de la izquierda para ver el hilo.</span>
          </div>
        )}
      </div>
    </div>
  );
}
