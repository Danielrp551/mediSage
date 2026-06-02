"use client";

import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  Menu,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  Spinner,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowRightRegular } from "@fluentui/react-icons";
import { useEffect, useRef, useState } from "react";

import { getLeadTransitions } from "@/actions/lead-status.actions";
import { appTokens } from "@/lib/theme/brand";
import type { LeadStatusOption } from "@/types/crm.types";

import { StatusBadge } from "./StatusBadge";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  row: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS, flexWrap: "wrap" },
  label: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  loading: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  menuItemBadge: { display: "inline-flex", alignItems: "center" },
});

interface Props {
  currentStatusId: string;
  kind: "lead";
  onTransition: (toId: string, reason?: string | null) => Promise<void>;
  disabled?: boolean;
}

/**
 * Dado el estado actual, ofrece SOLO los destinos permitidos por la matriz
 * (`getLeadTransitions`). Si el estado es terminal (sin destinos) → control
 * deshabilitado con hint. Al elegir un destino, abre un diálogo con `reason?`
 * opcional → llama `onTransition`.
 */
export function TransitionControl({ currentStatusId, onTransition, disabled = false }: Props) {
  const styles = useStyles();

  const [loading, setLoading] = useState(true);
  const [targets, setTargets] = useState<LeadStatusOption[]>([]);
  const [loadError, setLoadError] = useState(false);

  const [chosen, setChosen] = useState<LeadStatusOption | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reqIdRef = useRef(0);

  useEffect(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setLoadError(false);
    void getLeadTransitions(currentStatusId)
      .then((res) => {
        if (reqId !== reqIdRef.current) return;
        setTargets(res.to);
        setLoading(false);
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setLoadError(true);
        setLoading(false);
      });
  }, [currentStatusId]);

  const handleConfirm = async () => {
    if (!chosen) return;
    setSubmitting(true);
    try {
      await onTransition(chosen.id, reason.trim() ? reason.trim() : null);
      setChosen(null);
      setReason("");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.loading}>
        <Spinner size="tiny" />
        <span className={styles.hint}>Cargando transiciones…</span>
      </div>
    );
  }

  if (loadError) {
    return <p className={styles.hint}>No se pudieron cargar las transiciones disponibles.</p>;
  }

  const noTargets = targets.length === 0;

  return (
    <div className={styles.root}>
      <div className={styles.row}>
        <span className={styles.label}>Cambiar estado a:</span>
        <Menu positioning="below-start">
          <MenuTrigger disableButtonEnhancement>
            <Button
              appearance="primary"
              icon={<ArrowRightRegular />}
              disabled={disabled || noTargets}
            >
              Selecciona…
            </Button>
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              {targets.map((t) => (
                <MenuItem
                  key={t.id}
                  onClick={() => {
                    setReason("");
                    setChosen(t);
                  }}
                >
                  <span className={styles.menuItemBadge}>
                    <StatusBadge status={t} />
                  </span>
                </MenuItem>
              ))}
            </MenuList>
          </MenuPopover>
        </Menu>
      </div>

      {noTargets ? <p className={styles.hint}>Estado final, sin transiciones.</p> : null}

      <Dialog
        open={chosen !== null}
        onOpenChange={(_, d) => {
          if (!d.open && !submitting) {
            setChosen(null);
            setReason("");
          }
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Cambiar estado del lead</DialogTitle>
            <DialogContent>
              <div className={styles.root}>
                {chosen ? (
                  <div className={styles.row}>
                    <span className={styles.label}>Nuevo estado:</span>
                    <StatusBadge status={chosen} />
                  </div>
                ) : null}
                <span className={styles.label}>Motivo (opcional)</span>
                <Textarea
                  value={reason}
                  onChange={(_, d) => setReason(d.value)}
                  rows={3}
                  placeholder="Anota por qué cambias el estado…"
                  disabled={submitting}
                />
              </div>
            </DialogContent>
            <DialogActions>
              <Button
                appearance="secondary"
                disabled={submitting}
                onClick={() => {
                  setChosen(null);
                  setReason("");
                }}
              >
                Cancelar
              </Button>
              <Button
                appearance="primary"
                disabled={submitting}
                onClick={() => void handleConfirm()}
              >
                {submitting ? "Cambiando…" : "Cambiar"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
}
