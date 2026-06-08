"use client";

import {
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

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

/** Opción mínima que el editor necesita de cada estado del catálogo. */
export interface MatrixOption {
  id: string;
  name: string;
  code: string;
}

interface Props {
  /** Id del estado cuya matriz de salida se edita. Doble función: key de recarga
   * del effect + auto-exclusión de las opciones (un estado no transiciona a sí mismo). */
  statusId: string;
  /** Sujeto del dominio para el copy ("un lead" | "un cliente" | "una cita"). */
  subjectLabel: string;
  /** Un estado final no tiene aristas de salida → editor deshabilitado/oculto. */
  isFinal?: boolean;
  /** Sin permiso `_WRITE` el multiselect es de solo lectura. */
  canWrite?: boolean;
  /** Carga todos los estados activos del catálogo (incl. el propio; el editor lo excluye). */
  fetchOptions: () => Promise<ReadonlyArray<MatrixOption>>;
  /** Carga los ids de los destinos actualmente permitidos desde `statusId`. */
  fetchSelectedIds: () => Promise<ReadonlyArray<string>>;
  /** Reemplaza el set de aristas de salida por `toIds`. */
  onSave: (toIds: string[]) => Promise<{ ok: boolean; error?: string }>;
}

/**
 * Editor genérico de las aristas de salida de un estado (matriz de transiciones,
 * ADR-008). Agnóstico de módulo: recibe por props las funciones que cargan/guardan
 * (inyección de dependencias) → ningún módulo importa las actions de otro. Lo usan
 * crm (lead/customer, vía un adaptador) y scheduling (cita, directo).
 *
 * Carga las transiciones actuales (`fetchSelectedIds`) → preselecciona los destinos,
 * y todos los estados activos (menos el propio) como opciones (`fetchOptions`). Al
 * guardar hace `onSave(toIds)` que REEMPLAZA las aristas.
 */
export function TransitionMatrixEditor({
  statusId,
  subjectLabel,
  isFinal = false,
  canWrite = true,
  fetchOptions,
  fetchSelectedIds,
  onSave,
}: Props) {
  const styles = useStyles();
  const [pending, startTransition] = useTransition();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [options, setOptions] = useState<{ id: string; primary: string; secondary?: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  // use-latest: las funciones inyectadas se recrean en cada render del padre; las
  // guardamos en refs para que el effect dependa SOLO de `statusId` (sin re-disparos).
  const fetchOptionsRef = useRef(fetchOptions);
  const fetchSelectedIdsRef = useRef(fetchSelectedIds);
  const onSaveRef = useRef(onSave);
  fetchOptionsRef.current = fetchOptions;
  fetchSelectedIdsRef.current = fetchSelectedIds;
  onSaveRef.current = onSave;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void Promise.all([fetchOptionsRef.current(), fetchSelectedIdsRef.current()])
      .then(([active, selectedIds]) => {
        if (cancelled) return;
        // Excluir el estado propio (no transiciona a sí mismo).
        setOptions(
          active
            .filter((s) => s.id !== statusId)
            .map((s) => ({ id: s.id, primary: s.name, secondary: s.code })),
        );
        setSelected([...selectedIds]);
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
  }, [statusId]);

  const disabled = isFinal || !canWrite;

  const handleToggle = (id: string) => {
    setSavedOk(false);
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSave = () => {
    setSaveError(null);
    setSavedOk(false);
    startTransition(async () => {
      const result = await onSaveRef.current(selected);
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
          Desde este estado {subjectLabel} podrá pasar a los estados marcados.
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
