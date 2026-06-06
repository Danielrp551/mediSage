"use client";

import { Button, Input, Link, makeStyles, tokens } from "@fluentui/react-components";
import { BugRegular, OpenRegular } from "@fluentui/react-icons";
import { useQueryState } from "nuqs";
import { useCallback, useEffect, useRef, useState } from "react";

import { getBotState } from "@/actions/bot-debug.actions";
import { usePermissions } from "@/hooks/usePermissions";
import { appTokens } from "@/lib/theme/brand";
import type { ConversationBotStateDetail } from "@/types/bots.types";

import { BotEventTimeline } from "./BotEventTimeline";
import { BotStateCard } from "./BotStateCard";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  header: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: 0, fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
  contextRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
  },
  link: { display: "inline-flex", alignItems: "center", gap: tokens.spacingHorizontalXXS },
  selector: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    alignItems: "flex-end",
    flexWrap: "wrap",
    maxWidth: "640px",
  },
  selectorField: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    flex: 1,
    minWidth: "320px",
  },
  selectorLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  emptySelect: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalM,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
  },
  emptyIcon: { fontSize: "40px", opacity: 0.6 },
  panels: {
    display: "grid",
    gridTemplateColumns: "340px 1fr",
    gap: tokens.spacingHorizontalL,
    alignItems: "start",
    "@media (max-width: 900px)": {
      gridTemplateColumns: "1fr",
    },
  },
});

interface Props {
  initialConv: string | null;
}

/**
 * Shell de la pantalla de Depuración (F3a). Maneja el `?conv=` (URL state via
 * nuqs), el selector cuando no hay conversación, el fetch del estado del bot, y
 * el refetch coordinado de estado + timeline tras una mutación.
 *
 * El dispatch-manual es SÍNCRONO: cuando una acción muta (reset / dispatch), el
 * shell refetchea el estado y bumpea el `reloadToken` del timeline → ambos
 * paneles se actualizan INMEDIATAMENTE (sin polling).
 */
export function BotDebugShell({ initialConv }: Props) {
  const styles = useStyles();
  const { hasAnyPermission } = usePermissions();
  const canSeeConversation = hasAnyPermission(["CONVERSATIONS_READ", "MY_CONVERSATIONS_READ"]);

  const [conv, setConv] = useQueryState("conv", { defaultValue: initialConv ?? "" });
  const activeConv = conv?.trim() ? conv.trim() : null;

  // Borrador del input del selector (no toca la URL hasta "Depurar").
  const [draft, setDraft] = useState("");

  // Estado del bot: undefined = cargando; null = sin estado (404); objeto = ok.
  const [state, setState] = useState<ConversationBotStateDetail | null | undefined>(undefined);
  const [stateError, setStateError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const reqIdRef = useRef(0);

  const loadState = useCallback((cid: string) => {
    const reqId = ++reqIdRef.current;
    setState(undefined);
    setStateError(null);
    void getBotState(cid)
      .then((res) => {
        if (reqId !== reqIdRef.current) return;
        if (res.ok) {
          setState(res.data);
        } else if (res.notFound) {
          setState(null);
        } else {
          setState(undefined);
          setStateError(res.error);
        }
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setState(undefined);
        setStateError("No se pudo cargar la depuración.");
      });
  }, []);

  useEffect(() => {
    if (activeConv) loadState(activeConv);
  }, [activeConv, loadState]);

  // Tras reset/dispatch (síncrono): refetch del estado + bump del timeline.
  const handleMutated = useCallback(() => {
    if (activeConv) loadState(activeConv);
    setReloadToken((t) => t + 1);
  }, [activeConv, loadState]);

  // ── Sin conversación: selector + empty state ──
  if (!activeConv) {
    return (
      <div className={styles.root}>
        <header className={styles.header}>
          <h1 className={styles.title}>Depuración del bot</h1>
          <p className={styles.subtitle}>
            Inspecciona el estado y la traza de turnos del bot en una conversación.
          </p>
        </header>

        <div className={styles.selector}>
          <div className={styles.selectorField}>
            <label className={styles.selectorLabel} htmlFor="conv-input">
              Identificador de la conversación
            </label>
            <Input
              id="conv-input"
              placeholder="Pega un conversation_id…"
              value={draft}
              onChange={(_, d) => setDraft(d.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && draft.trim()) void setConv(draft.trim());
              }}
            />
          </div>
          <Button
            appearance="primary"
            disabled={!draft.trim()}
            onClick={() => void setConv(draft.trim())}
          >
            Depurar
          </Button>
        </div>

        <div className={styles.emptySelect}>
          <BugRegular className={styles.emptyIcon} />
          <span>Selecciona una conversación para depurar su bot.</span>
        </div>
      </div>
    );
  }

  // ── Con conversación: header + 2 paneles ──
  const botLine =
    state && state.bot_configuration_code
      ? `Conversación atendida por: ${state.bot_configuration_code}${
          state.version_number !== null ? ` · v${state.version_number}` : ""
        }`
      : null;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Depuración del bot</h1>
        {botLine ? <p className={styles.subtitle}>{botLine}</p> : null}
        <div className={styles.contextRow}>
          <span style={{ fontFamily: appTokens.fontMono, fontSize: tokens.fontSizeBase200 }}>
            {activeConv}
          </span>
          {canSeeConversation ? (
            <Link
              className={styles.link}
              href={`/conversaciones/bandeja?conv=${encodeURIComponent(activeConv)}`}
            >
              Ver conversación <OpenRegular />
            </Link>
          ) : null}
          <Button
            appearance="subtle"
            size="small"
            onClick={() => {
              void setConv("");
              setDraft("");
            }}
          >
            Cambiar conversación
          </Button>
        </div>
      </header>

      <div className={styles.panels}>
        <BotStateCard
          cid={activeConv}
          state={state}
          loadError={stateError}
          onMutated={handleMutated}
        />
        <BotEventTimeline cid={activeConv} reloadToken={reloadToken} />
      </div>
    </div>
  );
}
