"use client";

import {
  Badge,
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { AddRegular, EyeRegular } from "@fluentui/react-icons";
import { useCallback, useEffect, useState, useTransition } from "react";

import { activateBotVersion, getBotVersion, listBotVersions } from "@/actions/bots.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { usePermissions } from "@/hooks/usePermissions";
import { appTokens } from "@/lib/theme/brand";
import type {
  BotConfigurationVersionDetail,
  BotConfigurationVersionItem,
} from "@/types/bots.types";

import { BotProviderBadge } from "./BotProviderBadge";
import { BotVersionDrawer, type VersionFormValues } from "./BotVersionDrawer";
import { RelativeTime } from "./RelativeTime";

const useStyles = makeStyles({
  root: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  heading: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusMedium,
    overflow: "hidden",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    padding: tokens.spacingVerticalM,
    borderBottom: `1px solid ${appTokens.tableBorder}`,
  },
  rowLast: { borderBottom: "none" },
  rowMain: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    flex: 1,
    minWidth: 0,
  },
  rowTop: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  versionLabel: { fontWeight: tokens.fontWeightSemibold, color: appTokens.chromeText },
  meta: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  notes: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  actions: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalXS },
  empty: {
    padding: tokens.spacingVerticalXXL,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase300,
  },
  loading: { display: "flex", justifyContent: "center", padding: tokens.spacingVerticalXXL },
});

interface Props {
  configId: string;
  currentVersionId: string | null;
  readOnly: boolean;
  /** Tras activar una versión: el padre recarga el detalle + router.refresh(). */
  onVersionActivated: () => void;
  /** Tras crear una versión: el padre recarga el detalle (version_count, etc.). */
  onVersionsChanged: () => void;
}

type SubDialog =
  | { kind: "create"; seed?: VersionFormValues | null }
  | { kind: "view"; version: BotConfigurationVersionDetail }
  | null;

export function BotVersionsTab({
  configId,
  currentVersionId,
  readOnly,
  onVersionActivated,
  onVersionsChanged,
}: Props) {
  const styles = useStyles();
  const { hasAnyPermission } = usePermissions();
  const canWrite = !readOnly && hasAnyPermission(["BOT_CONFIGURATION_VERSIONS_WRITE"]);

  const [versions, setVersions] = useState<BotConfigurationVersionItem[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [subDialog, setSubDialog] = useState<SubDialog>(null);
  const [activateTarget, setActivateTarget] = useState<BotConfigurationVersionItem | null>(null);
  const [activateError, setActivateError] = useState<string | null>(null);
  const [activatePending, startActivate] = useTransition();

  const refetch = useCallback(() => {
    setListError(null);
    void listBotVersions(configId)
      .then((res) => setVersions(res.data))
      .catch(() => setListError("No se pudieron cargar las versiones."));
  }, [configId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const handleView = (v: BotConfigurationVersionItem) => {
    void getBotVersion(configId, v.id).then((res) =>
      setSubDialog({ kind: "view", version: res.data }),
    );
  };

  const handleConfirmActivate = () => {
    if (!activateTarget) return;
    setActivateError(null);
    startActivate(async () => {
      const result = await activateBotVersion(configId, activateTarget.id);
      if (!result.ok) {
        setActivateError(result.error ?? "No se pudo activar la versión.");
        return;
      }
      setActivateTarget(null);
      refetch();
      onVersionActivated();
    });
  };

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <h3 className={styles.heading}>Versiones</h3>
        {canWrite ? (
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setSubDialog({ kind: "create" })}
          >
            Nueva versión
          </Button>
        ) : null}
      </div>

      {listError ? (
        <MessageBar intent="error">
          <MessageBarBody>{listError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {versions === null ? (
        <div className={styles.loading}>
          <Spinner size="small" label="Cargando versiones…" />
        </div>
      ) : versions.length === 0 ? (
        <div className={styles.empty}>
          Este bot no tiene versiones todavía. Crea la primera versión con su prompt para poder
          activarla.
        </div>
      ) : (
        <div className={styles.list}>
          {versions.map((v, idx) => {
            const isCurrent = v.id === currentVersionId;
            return (
              <div
                key={v.id}
                className={`${styles.row} ${idx === versions.length - 1 ? styles.rowLast : ""}`}
              >
                <div className={styles.rowMain}>
                  <div className={styles.rowTop}>
                    <span className={styles.versionLabel}>v{v.version}</span>
                    {isCurrent ? (
                      <Badge appearance="filled" color="brand">
                        VIGENTE
                      </Badge>
                    ) : null}
                    <Badge appearance="tint" color={v.is_active ? "success" : "informative"}>
                      {v.is_active ? "Activa" : "Inactiva"}
                    </Badge>
                    <BotProviderBadge provider={v.provider} model={v.model_name} />
                  </div>
                  <span className={styles.meta}>
                    <RelativeTime iso={v.created_on} />
                    {v.notes ? <span className={styles.notes}> · {v.notes}</span> : null}
                  </span>
                </div>
                <div className={styles.actions}>
                  <Button
                    appearance="subtle"
                    icon={<EyeRegular />}
                    aria-label={`Ver versión v${v.version}`}
                    onClick={() => handleView(v)}
                  >
                    Ver
                  </Button>
                  {canWrite && !isCurrent && v.is_active ? (
                    <Button
                      appearance="secondary"
                      onClick={() => {
                        setActivateError(null);
                        setActivateTarget(v);
                      }}
                    >
                      Activar
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {subDialog?.kind === "create" ? (
        <BotVersionDrawer
          mode="create"
          configId={configId}
          seed={subDialog.seed ?? null}
          onClose={() => setSubDialog(null)}
          onCreated={() => {
            refetch();
            onVersionsChanged();
          }}
        />
      ) : null}

      {subDialog?.kind === "view" ? (
        <BotVersionDrawer
          mode="view"
          configId={configId}
          version={subDialog.version}
          onClose={() => setSubDialog(null)}
          onCreated={() => {
            refetch();
            onVersionsChanged();
          }}
          onCloneToNew={canWrite ? (seed) => setSubDialog({ kind: "create", seed }) : undefined}
        />
      ) : null}

      <ConfirmDialog
        open={activateTarget !== null}
        title="¿Activar versión?"
        description={
          activateError
            ? activateError
            : activateTarget
              ? `¿Activar la versión v${activateTarget.version}? Las conversaciones nuevas usarán este prompt.`
              : ""
        }
        confirmText={activatePending ? "Activando…" : "Activar"}
        cancelText="Cancelar"
        onConfirm={handleConfirmActivate}
        onCancel={() => {
          if (!activatePending) {
            setActivateTarget(null);
            setActivateError(null);
          }
        }}
      />
    </div>
  );
}
