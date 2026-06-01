"use client";

import {
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useEffect, useMemo, useState, useTransition } from "react";

import {
  getCustomerTransitions,
  listActiveCustomerStatuses,
  setCustomerTransitions,
} from "@/actions/customer-status.actions";
import {
  getLeadTransitions,
  listActiveLeadStatuses,
  setLeadTransitions,
} from "@/actions/lead-status.actions";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  label: {
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  loading: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    padding: tokens.spacingVerticalM,
  },
  footer: {
    display: "flex",
    justifyContent: "flex-end",
  },
});

interface Props {
  statusId: string;
  kind: "lead" | "customer";
  isFinal?: boolean;
  /** Sin permiso `_WRITE` el multiselect es de solo lectura. */
  canWrite?: boolean;
}

/**
 * Editor de las aristas de salida de un estado (matriz de transiciones, ADR-008).
 * Carga las transiciones actuales (`getXTransitions`) → preselecciona los destinos,
 * y todos los estados activos del catálogo (menos el propio) como opciones. Al
 * guardar hace `setXTransitions(statusId, { to_ids })` que REEMPLAZA las aristas.
 */
export function StatusMatrixEditor({ statusId, kind, isFinal = false, canWrite = true }: Props) {
  const styles = useStyles();
  const [pending, startTransition] = useTransition();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [options, setOptions] = useState<{ id: string; primary: string; secondary?: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    const loadActive = kind === "lead" ? listActiveLeadStatuses() : listActiveCustomerStatuses();
    const loadTransitions =
      kind === "lead" ? getLeadTransitions(statusId) : getCustomerTransitions(statusId);
    void Promise.all([loadActive, loadTransitions])
      .then(([active, transitions]) => {
        if (cancelled) return;
        // Excluir el estado propio (no transiciona a sí mismo).
        setOptions(
          active
            .filter((s) => s.id !== statusId)
            .map((s) => ({ id: s.id, primary: s.name, secondary: s.code })),
        );
        setSelected(transitions.to.map((o) => o.id));
      })
      .catch(() => {
        if (!cancelled) setLoadError("No se pudieron cargar las transiciones.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [statusId, kind]);

  const disabled = isFinal || !canWrite;

  const handleToggle = (id: string) => {
    setSavedOk(false);
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSave = () => {
    setSaveError(null);
    setSavedOk(false);
    startTransition(async () => {
      const result =
        kind === "lead"
          ? await setLeadTransitions(statusId, { to_ids: selected })
          : await setCustomerTransitions(statusId, { to_ids: selected });
      if (!result.ok) {
        setSaveError(result.error ?? "No se pudieron guardar las transiciones.");
        return;
      }
      setSavedOk(true);
    });
  };

  const selectedForDisplay = useMemo(
    // Un estado final no tiene aristas de salida; mostrar vacío.
    () => (isFinal ? [] : selected),
    [isFinal, selected],
  );

  return (
    <div className={styles.root}>
      <span className={styles.label}>Transiciones permitidas hacia…</span>

      {isFinal ? (
        <p className={styles.hint}>Estado final: sin transiciones de salida.</p>
      ) : (
        <p className={styles.hint}>
          Desde este estado {kind === "lead" ? "un lead" : "un cliente"} podrá pasar a los estados
          marcados.
        </p>
      )}

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
          <MessageBarBody>Transiciones guardadas.</MessageBarBody>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.loading}>
          <Spinner size="tiny" />
          <span className={styles.hint}>Cargando transiciones…</span>
        </div>
      ) : (
        <>
          <SearchableOptionList
            options={options}
            selected={selectedForDisplay}
            disabled={disabled}
            onToggle={handleToggle}
            searchPlaceholder="Buscar estados…"
            emptyMessage="No hay otros estados activos en el catálogo."
          />
          {!disabled ? (
            <div className={styles.footer}>
              <Button appearance="secondary" disabled={pending} onClick={handleSave}>
                {pending ? "Guardando…" : "Guardar transiciones"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
