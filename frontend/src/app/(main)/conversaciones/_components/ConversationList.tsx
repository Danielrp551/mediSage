"use client";

import {
  Badge,
  Button,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Skeleton,
  SkeletonItem,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  ArrowSyncRegular,
  DismissRegular,
  MailInboxRegular,
  PauseRegular,
  PlayRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useMemo } from "react";

import { CHANNEL_TYPE_META, INBOX_FILTER_PRESETS } from "@/lib/constants/conversations";
import { appTokens } from "@/lib/theme/brand";
import type { ChannelAccountOption, ConversationListItem } from "@/types/conversations.types";

import { ConversationListItemRow } from "./ConversationListItemRow";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100%",
    minHeight: 0,
    borderRight: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.contentBg,
  },
  toolbar: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
  },
  presets: { display: "flex", gap: tokens.spacingHorizontalXS, flexWrap: "wrap" },
  filtersRow: { display: "flex", gap: tokens.spacingHorizontalS, alignItems: "center" },
  channelDropdown: { minWidth: "160px", flex: 1 },
  chips: { display: "flex", gap: tokens.spacingHorizontalXS, flexWrap: "wrap" },
  chip: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXXS,
  },
  list: { flex: 1, overflowY: "auto", minHeight: 0 },
  footer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalXS} ${tokens.spacingHorizontalM}`,
    borderTop: `1px solid ${appTokens.chromeBorder}`,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  footerControls: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXXS,
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingHorizontalXXL,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    minHeight: "220px",
  },
  emptyIcon: { fontSize: "40px", opacity: 0.6 },
  skeletonRow: { padding: tokens.spacingVerticalM },
});

interface Props {
  scope: "all" | "mine";
  items: ConversationListItem[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  // Filtros (URL state, gobernados por InboxShell).
  activePreset: string;
  onPresetChange: (key: string) => void;
  channelAccounts: ChannelAccountOption[];
  channelFilter: string | null;
  onChannelChange: (id: string | null) => void;
  search: string;
  onSearchChange: (value: string) => void;
  // Polling.
  paused: boolean;
  onTogglePause: () => void;
  onRefresh: () => void;
  lastRefreshLabel: string;
}

/**
 * Panel izquierdo del inbox: presets de filtro (estado/sin-asignar, columnas
 * REALES — server-side), dropdown de canal, búsqueda CLIENT-SIDE (sobre la página
 * cargada, por nombre/preview — NO server, lección cd10c78), filas memoizadas y
 * controles del polling (refrescar / pausar). En scope="mine" se acotan los
 * presets (sin "Sin asignar").
 */
export function ConversationList({
  scope,
  items,
  loading,
  error,
  selectedId,
  onSelect,
  activePreset,
  onPresetChange,
  channelAccounts,
  channelFilter,
  onChannelChange,
  search,
  onSearchChange,
  paused,
  onTogglePause,
  onRefresh,
  lastRefreshLabel,
}: Props) {
  const styles = useStyles();

  // En "mine" las conversaciones ya están asignadas al actor → ocultar "Sin asignar".
  const presets = useMemo(
    () =>
      scope === "mine"
        ? INBOX_FILTER_PRESETS.filter((p) => p.key !== "unassigned")
        : INBOX_FILTER_PRESETS,
    [scope],
  );

  // Búsqueda client-side por nombre / identificador / preview (denormalizados, NO
  // server-filterables). Se aplica sobre la página visible.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((c) => {
      const name = c.person?.full_name?.toLowerCase() ?? "";
      const ident = c.person?.primary_identifier?.identifier?.toLowerCase() ?? "";
      const preview = c.last_message_preview?.toLowerCase() ?? "";
      return name.includes(q) || ident.includes(q) || preview.includes(q);
    });
  }, [items, search]);

  const selectedChannel = channelFilter
    ? channelAccounts.find((c) => c.id === channelFilter)
    : null;

  const emptyMessage =
    activePreset === "closed"
      ? "No hay conversaciones cerradas."
      : activePreset === "unassigned"
        ? "No hay conversaciones sin asignar."
        : scope === "mine"
          ? "No tienes conversaciones asignadas todavía."
          : "Aún no hay conversaciones. Cuando un contacto escriba a uno de tus canales, aparecerá aquí.";

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <div className={styles.presets}>
          {presets.map((p) => (
            <Button
              key={p.key}
              appearance={activePreset === p.key ? "primary" : "outline"}
              shape="circular"
              size="small"
              onClick={() => onPresetChange(p.key)}
            >
              {p.label}
            </Button>
          ))}
        </div>

        <div className={styles.filtersRow}>
          <Dropdown
            className={styles.channelDropdown}
            size="small"
            placeholder="Todos los canales"
            value={selectedChannel ? selectedChannel.name : ""}
            selectedOptions={channelFilter ? [channelFilter] : []}
            onOptionSelect={(_, data) => onChannelChange(data.optionValue ?? null)}
          >
            <Option value="">Todos los canales</Option>
            {channelAccounts.map((c) => (
              <Option key={c.id} value={c.id}>
                {`${CHANNEL_TYPE_META[c.channel_type].label} · ${c.name}`}
              </Option>
            ))}
          </Dropdown>
        </div>

        <Input
          size="small"
          placeholder="Buscar nombre o contacto…"
          value={search}
          onChange={(_, d) => onSearchChange(d.value)}
          contentBefore={<SearchRegular />}
        />

        {selectedChannel ? (
          <div className={styles.chips}>
            <Badge className={styles.chip} appearance="tint" color="brand">
              Canal: {selectedChannel.name}
              <Button
                appearance="transparent"
                size="small"
                icon={<DismissRegular />}
                aria-label="Quitar filtro de canal"
                onClick={() => onChannelChange(null)}
              />
            </Badge>
          </div>
        ) : null}
      </div>

      <div className={styles.list}>
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className={styles.skeletonRow}>
              <SkeletonItem shape="rectangle" size={48} />
            </Skeleton>
          ))
        ) : error ? (
          <div className={styles.empty}>
            <MessageBar intent="error">
              <MessageBarBody>{error}</MessageBarBody>
            </MessageBar>
          </div>
        ) : filtered.length === 0 ? (
          <div className={styles.empty}>
            <MailInboxRegular className={styles.emptyIcon} />
            <span>
              {search.trim() ? "No hay resultados con la búsqueda actual." : emptyMessage}
            </span>
          </div>
        ) : (
          filtered.map((c) => (
            <ConversationListItemRow
              key={c.id}
              conversation={c}
              selected={c.id === selectedId}
              onSelect={onSelect}
            />
          ))
        )}
      </div>

      <div className={styles.footer}>
        <span>
          {filtered.length === 1 ? "1 conversación" : `${filtered.length} conversaciones`}
          {lastRefreshLabel ? ` · ${lastRefreshLabel}` : ""}
        </span>
        <span className={styles.footerControls}>
          <Button
            appearance="subtle"
            size="small"
            icon={<ArrowSyncRegular />}
            aria-label="Refrescar bandeja"
            onClick={onRefresh}
          />
          <Button
            appearance="subtle"
            size="small"
            icon={paused ? <PlayRegular /> : <PauseRegular />}
            aria-label={
              paused ? "Reanudar actualización automática" : "Pausar actualización automática"
            }
            onClick={onTogglePause}
          />
        </span>
      </div>
    </div>
  );
}
