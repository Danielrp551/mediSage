"use client";

import {
  Badge,
  Button,
  Card,
  Divider,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  ArrowSyncRegular,
  CalendarLtrRegular,
  CheckmarkCircleRegular,
  DismissCircleRegular,
  ErrorCircleRegular,
  MailRegular,
  PlugDisconnectedRegular,
  WarningRegular,
} from "@fluentui/react-icons";
import { type ComponentType, useCallback, useEffect, useState } from "react";

import {
  disconnect,
  getConnection,
  listExternalCalendars,
  startOAuth,
} from "@/actions/calendar.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { CALENDAR_PROVIDER_META, CONNECTION_STATUS_META } from "@/lib/constants/calendar-providers";
import { appTokens } from "@/lib/theme/brand";
import type {
  CalendarConnectionDetail,
  CalendarConnectionItem,
  ConnectionStatus,
  ExternalCalendarOption,
} from "@/types/calendar.types";
import type { BranchOption } from "@/types/clinic.types";

import { RelativeTime } from "./RelativeTime";
import { SourceMappingTable } from "./SourceMappingTable";

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    padding: tokens.spacingVerticalL,
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  identity: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    minWidth: 0,
  },
  providerIcon: { fontSize: "24px", color: appTokens.chromeTextMuted, flexShrink: 0 },
  identityText: { display: "flex", flexDirection: "column", minWidth: 0 },
  email: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    wordBreak: "break-word",
  },
  providerName: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  meta: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  lostAccess: { fontSize: tokens.fontSizeBase300, color: tokens.colorPaletteRedForeground1 },
  loadingRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
  },
  footer: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
});

const HEALTH_ICON: Record<ConnectionStatus, ComponentType<{ className?: string }>> = {
  connected: CheckmarkCircleRegular,
  needs_reauth: WarningRegular,
  revoked: DismissCircleRegular,
  error: ErrorCircleRegular,
};

interface Props {
  connection: CalendarConnectionItem;
  branches: BranchOption[];
  canWrite: boolean;
  /** Re-fetch de la lista de conexiones del padre (tras desconectar). */
  onChanged: () => void;
}

/**
 * Una conexión OAuth a nivel clínica. Cabecera (ícono del proveedor + `account_email` + badge
 * de salud + "Última revisión") + el mapeo embebido (sólo si `connected`) + footer
 * Reconectar/Desconectar (gated WRITE). El mapeo carga `getConnection` (sources, READ) y, si
 * hay WRITE, `listExternalCalendars` (live, gated WRITE en el backend → un read-only NO la
 * llama: deriva las filas de los sources ya guardados).
 */
export function ConnectionCard({ connection, branches, canWrite, onChanged }: Props) {
  const styles = useStyles();
  const status = connection.status;
  const isConnected = status === "connected";

  const meta = CONNECTION_STATUS_META[status];
  const providerMeta = CALENDAR_PROVIDER_META[connection.provider];
  const ProviderIcon = connection.provider === "google" ? CalendarLtrRegular : MailRegular;
  const HealthIcon = HEALTH_ICON[status];

  const [detail, setDetail] = useState<CalendarConnectionDetail | undefined>(undefined);
  const [calendars, setCalendars] = useState<ExternalCalendarOption[] | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [calendarsError, setCalendarsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [busy, setBusy] = useState(false);

  // Carga el detalle (sources) y, si hay WRITE, la lista LIVE de calendarios del proveedor.
  const loadMapping = useCallback(() => {
    setLoadError(null);
    setDetail(undefined);
    void getConnection(connection.id)
      .then((res) => setDetail(res.data))
      .catch(() => setLoadError("No se pudo cargar la conexión. Recarga la página."));
    if (canWrite) {
      setCalendars(undefined);
      setCalendarsError(null);
      void listExternalCalendars(connection.id)
        .then(setCalendars)
        .catch(() =>
          setCalendarsError("No se pudieron cargar los calendarios. Reintenta o reconecta."),
        );
    }
  }, [connection.id, canWrite]);

  useEffect(() => {
    if (isConnected) loadMapping();
  }, [isConnected, loadMapping]);

  const onReconnect = async () => {
    setActionError(null);
    // return_to ABSOLUTO (origin + path): el callback del backend redirige crudo desde su host.
    const res = await startOAuth(
      connection.provider,
      `${window.location.origin}${window.location.pathname}`,
    );
    if (res.ok && res.data) {
      window.location.href = res.data.auth_url; // redirect del navegador al consentimiento
    } else {
      setActionError(res.error ?? "No se pudo iniciar la reconexión.");
    }
  };

  const onDisconnect = async () => {
    if (busy) return; // el botón de confirmar del ConfirmDialog no se deshabilita solo → guard
    setBusy(true);
    setActionError(null);
    const res = await disconnect(connection.id);
    setBusy(false);
    if (res.ok) {
      setConfirmDisconnect(false);
      onChanged();
    } else {
      setActionError(res.error ?? "No se pudo desconectar la cuenta.");
    }
  };

  // Filas para la tabla: live (WRITE) o derivadas de los sources guardados (read-only).
  const tableCalendars: ExternalCalendarOption[] = canWrite
    ? (calendars ?? [])
    : (detail?.sources ?? []).map((s) => ({
        id: s.external_calendar_id,
        name: s.external_calendar_name,
        primary: false,
      }));

  return (
    <Card className={styles.card}>
      <div className={styles.header}>
        <div className={styles.identity}>
          <ProviderIcon className={styles.providerIcon} />
          <div className={styles.identityText}>
            <span className={styles.email}>{connection.account_email}</span>
            <span className={styles.providerName}>
              {providerMeta.label}
              {connection.display_name && connection.display_name !== connection.account_email
                ? ` · ${connection.display_name}`
                : ""}
            </span>
          </div>
        </div>
        <Badge appearance="filled" color={meta.intent} icon={<HealthIcon />}>
          {meta.label}
        </Badge>
      </div>

      <div className={styles.meta}>
        {connection.sources_count} {connection.sources_count === 1 ? "calendario" : "calendarios"} ·{" "}
        {connection.last_checked_at ? (
          <>
            Última revisión: <RelativeTime iso={connection.last_checked_at} />
          </>
        ) : (
          "Aún sin revisar"
        )}
      </div>

      {!isConnected ? (
        <span className={styles.lostAccess}>La conexión perdió acceso. Vuelve a conectarla.</span>
      ) : null}

      {actionError ? (
        <MessageBar intent="error">
          <MessageBarBody>{actionError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {isConnected ? (
        <>
          <Divider />
          {loadError ? (
            <MessageBar intent="error">
              <MessageBarBody>{loadError}</MessageBarBody>
            </MessageBar>
          ) : detail === undefined ? (
            <div className={styles.loadingRow}>
              <Spinner size="tiny" />
              Cargando calendarios…
            </div>
          ) : canWrite && calendarsError ? (
            <>
              <MessageBar intent="warning">
                <MessageBarBody>{calendarsError}</MessageBarBody>
              </MessageBar>
              <Button appearance="secondary" onClick={loadMapping}>
                Reintentar
              </Button>
            </>
          ) : canWrite && calendars === undefined ? (
            <div className={styles.loadingRow}>
              <Spinner size="tiny" />
              Cargando calendarios…
            </div>
          ) : (
            <SourceMappingTable
              connectionId={connection.id}
              calendars={tableCalendars}
              existingSources={detail.sources}
              branches={branches}
              readOnly={!canWrite}
              // El mapeo se auto-actualiza del response; el padre sólo refresca el header
              // (sources_count) vía router.refresh — sin re-fetch del detalle (no remonta).
              onSaved={onChanged}
            />
          )}
        </>
      ) : null}

      {canWrite ? (
        <>
          <Divider />
          <div className={styles.footer}>
            <Button
              appearance="secondary"
              icon={<ArrowSyncRegular />}
              onClick={() => void onReconnect()}
            >
              Reconectar
            </Button>
            <Button
              appearance="subtle"
              icon={<PlugDisconnectedRegular />}
              disabled={busy}
              onClick={() => {
                setActionError(null);
                setConfirmDisconnect(true);
              }}
            >
              Desconectar
            </Button>
          </div>
        </>
      ) : null}

      <ConfirmDialog
        open={confirmDisconnect}
        title="¿Desconectar esta cuenta?"
        description="Se eliminará la conexión y sus calendarios mapeados. Podrás volver a conectarla más adelante."
        confirmText={busy ? "Desconectando…" : "Desconectar"}
        cancelText="Cancelar"
        destructive
        onConfirm={() => void onDisconnect()}
        onCancel={() => {
          if (!busy) setConfirmDisconnect(false);
        }}
      />
    </Card>
  );
}
