"use client";

import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Button,
  Card,
  Divider,
  MessageBar,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowResetRegular, BotRegular, PlayRegular } from "@fluentui/react-icons";
import { useState } from "react";

import { dispatchBotTurnManual, resetBotState } from "@/actions/bot-debug.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { usePermissions } from "@/hooks/usePermissions";
import { appTokens } from "@/lib/theme/brand";
import type { ConversationBotStateDetail } from "@/types/bots.types";

import { RelativeTime } from "../../configuraciones/_components/RelativeTime";

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    padding: tokens.spacingVerticalL,
  },
  heading: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  fields: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  field: { display: "flex", flexDirection: "column", gap: "2px" },
  label: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
  value: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    wordBreak: "break-word",
  },
  slots: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  slotRow: {
    display: "flex",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
  },
  slotKey: { color: appTokens.chromeTextMuted, fontWeight: tokens.fontWeightSemibold },
  slotVal: { color: appTokens.chromeText, wordBreak: "break-word" },
  pre: {
    margin: 0,
    padding: tokens.spacingVerticalXS,
    backgroundColor: tokens.colorNeutralBackground3,
    borderRadius: tokens.borderRadiusSmall,
    fontFamily: appTokens.fontMono,
    fontSize: tokens.fontSizeBase200,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    maxHeight: "240px",
    overflow: "auto",
  },
  muted: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  actions: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXL} ${tokens.spacingHorizontalM}`,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
  },
  emptyIcon: { fontSize: "32px", opacity: 0.7 },
});

interface Props {
  cid: string;
  /** Estado cargado | null (sin estado, 404) | undefined (cargando). */
  state: ConversationBotStateDetail | null | undefined;
  /** Error de carga del estado (5xx) — distinto del 404 "sin estado". */
  loadError: string | null;
  /** Bumpea el refetch del shell (estado + timeline) tras una mutación. */
  onMutated: () => void;
}

// Render plano de slots: clave→valor si son escalares; `<pre>` si hay anidados.
function isFlat(slots: Record<string, unknown>): boolean {
  return Object.values(slots).every(
    (v) => v === null || ["string", "number", "boolean"].includes(typeof v),
  );
}

/**
 * Panel izquierdo de la Depuración — `ConversationBotState` read-only + las dos
 * acciones de admin gated:
 *  - "Reiniciar estado" (BOT_STATE_WRITE) → borra intención/slots/turnos (la
 *    traza se conserva).
 *  - "Disparar turno (debug)" (BOT_ENGINE_INVOKE) → SÍNCRONO: corre el turno
 *    inline; al volver, el shell refetchea state + timeline INMEDIATAMENTE.
 * El 404 BOT_STATE_NOT_FOUND se muestra como empty (no error).
 */
export function BotStateCard({ cid, state, loadError, onMutated }: Props) {
  const styles = useStyles();
  const { hasAnyPermission } = usePermissions();
  const canReset = hasAnyPermission(["BOT_STATE_WRITE"]);
  const canDispatch = hasAnyPermission(["BOT_ENGINE_INVOKE"]);

  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmDispatch, setConfirmDispatch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionOk, setActionOk] = useState<string | null>(null);

  const doReset = async () => {
    setBusy(true);
    setActionError(null);
    setActionOk(null);
    const result = await resetBotState(cid, {});
    setBusy(false);
    if (result.ok) {
      setConfirmReset(false);
      setActionOk("Estado reiniciado.");
      onMutated();
    } else {
      setActionError(result.error ?? "No se pudo reiniciar el estado.");
    }
  };

  const doDispatch = async () => {
    setBusy(true);
    setActionError(null);
    setActionOk(null);
    const result = await dispatchBotTurnManual({ conversation_id: cid });
    setBusy(false);
    if (result.ok) {
      setConfirmDispatch(false);
      setActionOk("Turno ejecutado.");
      onMutated();
    } else {
      setActionError(result.error ?? "No se pudo disparar el turno.");
    }
  };

  // Error de carga (5xx) — tiene prioridad sobre el loading (narrowing limpio).
  if (loadError) {
    return (
      <Card className={styles.card}>
        <h2 className={styles.heading}>Estado del bot</h2>
        <MessageBar intent="error">
          <MessageBarBody>{loadError}</MessageBarBody>
        </MessageBar>
      </Card>
    );
  }

  // Loading.
  if (state === undefined) {
    return (
      <Card className={styles.card}>
        <h2 className={styles.heading}>Estado del bot</h2>
        <Skeleton>
          <SkeletonItem shape="rectangle" size={16} />
          <SkeletonItem shape="rectangle" size={16} style={{ marginTop: 8 }} />
          <SkeletonItem shape="rectangle" size={16} style={{ marginTop: 8 }} />
          <SkeletonItem shape="rectangle" size={64} style={{ marginTop: 8 }} />
        </Skeleton>
      </Card>
    );
  }

  // Empty — sin estado de bot (404 BOT_STATE_NOT_FOUND).
  if (state === null) {
    return (
      <Card className={styles.card}>
        <h2 className={styles.heading}>Estado del bot</h2>
        <div className={styles.empty}>
          <BotRegular className={styles.emptyIcon} />
          <span>
            Esta conversación no tiene estado de bot. No ha sido atendida por un bot todavía.
          </span>
        </div>
      </Card>
    );
  }

  const slots = state.collected_slots ?? {};
  const slotKeys = Object.keys(slots);
  const versionLabel =
    state.version_number !== null
      ? `v${state.version_number}${state.bot_configuration_code ? ` · ${state.bot_configuration_code}` : ""}`
      : "—";

  return (
    <Card className={styles.card}>
      <h2 className={styles.heading}>Estado del bot</h2>

      {actionError ? (
        <MessageBar intent="error">
          <MessageBarBody>{actionError}</MessageBarBody>
        </MessageBar>
      ) : null}
      {actionOk ? (
        <MessageBar intent="success">
          <MessageBarBody>{actionOk}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.fields}>
        <div className={styles.field}>
          <span className={styles.label}>Intención</span>
          <span className={styles.value}>{state.current_intent ?? "—"}</span>
        </div>
        <div className={styles.field}>
          <span className={styles.label}>Turnos</span>
          <span className={styles.value}>{state.turn_count}</span>
        </div>
        <div className={styles.field}>
          <Tooltip
            content="Versión con la que arrancó esta conversación; activar otra versión no migra las conversaciones en curso."
            relationship="label"
            withArrow
          >
            <span className={styles.label} style={{ cursor: "help" }}>
              Versión ⓘ
            </span>
          </Tooltip>
          <span className={styles.value}>{versionLabel}</span>
        </div>
        <div className={styles.field}>
          <span className={styles.label}>Último turno</span>
          <span className={styles.value}>
            <RelativeTime iso={state.last_bot_turn_at} />
          </span>
        </div>
        <div className={styles.field}>
          <span className={styles.label}>Último nodo</span>
          <span className={styles.value}>{state.last_node ?? "—"}</span>
        </div>
      </div>

      <Divider />

      <div className={styles.field}>
        <span className={styles.label}>Datos capturados (slots)</span>
        {slotKeys.length === 0 ? (
          <span className={styles.muted}>Sin datos capturados todavía.</span>
        ) : isFlat(slots) ? (
          <div className={styles.slots}>
            {slotKeys.map((k) => (
              <div key={k} className={styles.slotRow}>
                <span className={styles.slotKey}>{k}:</span>
                <span className={styles.slotVal}>{String(slots[k])}</span>
              </div>
            ))}
          </div>
        ) : (
          <Accordion collapsible defaultOpenItems={["slots"]}>
            <AccordionItem value="slots">
              <AccordionHeader size="small">Ver datos capturados</AccordionHeader>
              <AccordionPanel>
                <pre className={styles.pre}>{JSON.stringify(slots, null, 2)}</pre>
              </AccordionPanel>
            </AccordionItem>
          </Accordion>
        )}
      </div>

      {canReset || canDispatch ? (
        <>
          <Divider />
          <div className={styles.actions}>
            {canReset ? (
              <Button
                appearance="subtle"
                icon={<ArrowResetRegular />}
                disabled={busy}
                onClick={() => {
                  setActionError(null);
                  setActionOk(null);
                  setConfirmReset(true);
                }}
              >
                Reiniciar estado
              </Button>
            ) : null}
            {canDispatch ? (
              <Button
                appearance="subtle"
                icon={<PlayRegular />}
                disabled={busy}
                onClick={() => {
                  setActionError(null);
                  setActionOk(null);
                  setConfirmDispatch(true);
                }}
              >
                Disparar turno (debug)
              </Button>
            ) : null}
          </div>
        </>
      ) : null}

      <ConfirmDialog
        open={confirmReset}
        title="¿Reiniciar estado?"
        description="¿Reiniciar el estado del bot para esta conversación? Se borrarán la intención, los datos capturados y el contador de turnos. La traza de eventos se conserva."
        confirmText={busy ? "Reiniciando…" : "Reiniciar"}
        cancelText="Cancelar"
        destructive
        onConfirm={() => void doReset()}
        onCancel={() => {
          if (!busy) setConfirmReset(false);
        }}
      />

      <ConfirmDialog
        open={confirmDispatch}
        title="¿Disparar turno?"
        description="¿Disparar un turno del bot manualmente? El bot procesará el último mensaje del hilo y podría responder al contacto."
        confirmText={busy ? "Ejecutando…" : "Disparar turno"}
        cancelText="Cancelar"
        onConfirm={() => void doDispatch()}
        onCancel={() => {
          if (!busy) setConfirmDispatch(false);
        }}
      />
    </Card>
  );
}
