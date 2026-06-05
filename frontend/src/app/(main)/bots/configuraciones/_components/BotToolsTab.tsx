"use client";

import {
  Button,
  Link,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useEffect, useState, useTransition } from "react";

import {
  getConfigurationTools,
  listActiveBotTools,
  setConfigurationTools,
} from "@/actions/bot-tools.actions";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { usePermissions } from "@/hooks/usePermissions";
import { appTokens } from "@/lib/theme/brand";
import type { BotToolOption } from "@/types/bots.types";

const useStyles = makeStyles({
  root: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  heading: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  empty: {
    padding: tokens.spacingVerticalXXL,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase300,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    alignItems: "center",
  },
  loading: { display: "flex", justifyContent: "center", padding: tokens.spacingVerticalXXL },
  footer: { display: "flex", justifyContent: "flex-end" },
});

interface Props {
  configId: string;
  /** Sin permiso BOT_CONFIGURATIONS_UPDATE el multiselect es de solo lectura. */
  readOnly: boolean;
}

/**
 * Editor M:N de las herramientas que un bot puede invocar (molde StatusMatrixEditor
 * de crm). Carga las tools asignadas (`getConfigurationTools`) → preselección, y el
 * catálogo de tools activas (`listActiveBotTools`) como candidatas. Al guardar hace
 * `setConfigurationTools(configId, { tool_ids })` que REEMPLAZA el set completo (bulk).
 * Gated BOT_CONFIGURATIONS_UPDATE: la asignación es una edición del bot.
 */
export function BotToolsTab({ configId, readOnly }: Props) {
  const styles = useStyles();
  const { hasAnyPermission } = usePermissions();
  const canWrite = !readOnly && hasAnyPermission(["BOT_CONFIGURATIONS_UPDATE"]);
  const canSeeCatalog = hasAnyPermission(["BOT_TOOLS_READ"]);

  const [pending, startTransition] = useTransition();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<BotToolOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void Promise.all([listActiveBotTools(), getConfigurationTools(configId)])
      .then(([active, assigned]) => {
        if (cancelled) return;
        setCatalog(active);
        setSelected(assigned.data.map((t) => t.id));
      })
      .catch(() => {
        if (!cancelled) setLoadError("No se pudieron cargar las herramientas.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [configId]);

  const handleToggle = (id: string) => {
    setSavedOk(false);
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSave = () => {
    setSaveError(null);
    setSavedOk(false);
    startTransition(async () => {
      const result = await setConfigurationTools(configId, { tool_ids: selected });
      if (!result.ok) {
        setSaveError(result.error ?? "No se pudieron guardar las herramientas.");
        return;
      }
      setSavedOk(true);
    });
  };

  // Opciones del multiselect: `name` (con ⚠ si requires_confirmation) + `code` (mono).
  // SearchableOptionList renderiza strings; embebemos el ⚠ en el primary.
  const options = catalog.map((t) => ({
    id: t.id,
    primary: t.requires_confirmation ? `⚠ ${t.name}` : t.name,
    secondary: t.code,
  }));

  return (
    <div className={styles.root}>
      <h3 className={styles.heading}>Herramientas que este bot puede usar</h3>

      {loadError ? (
        <MessageBar intent="error">
          <MessageBarBody>{loadError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {saveError ? (
        <MessageBar intent="error">
          <MessageBarBody>{saveError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {savedOk ? (
        <MessageBar intent="success">
          <MessageBarBody>Herramientas actualizadas.</MessageBarBody>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.loading}>
          <Spinner size="small" label="Cargando herramientas…" />
        </div>
      ) : catalog.length === 0 ? (
        <div className={styles.empty}>
          <span>
            Aún no hay herramientas. Crea herramientas en la sección Herramientas para asignarlas a
            este bot.
          </span>
          {canSeeCatalog ? <Link href="/bots/tools">Ir a Herramientas</Link> : null}
        </div>
      ) : (
        <>
          <SearchableOptionList
            options={options}
            selected={selected}
            disabled={!canWrite}
            onToggle={handleToggle}
            searchPlaceholder="Buscar herramientas…"
            emptyMessage="No hay herramientas activas en el catálogo."
          />
          <p className={styles.hint}>
            El bot solo podrá invocar las herramientas marcadas. ⚠ = requiere confirmación.
          </p>
          {canWrite ? (
            <div className={styles.footer}>
              <Button appearance="secondary" disabled={pending} onClick={handleSave}>
                {pending ? "Guardando…" : "Guardar herramientas"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
