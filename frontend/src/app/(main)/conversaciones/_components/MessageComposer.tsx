"use client";

import {
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { DismissRegular, SendRegular } from "@fluentui/react-icons";
import { useCallback, useRef, useState, useTransition, type KeyboardEvent } from "react";

import { sendMessage } from "@/actions/conversation.actions";
import { appTokens } from "@/lib/theme/brand";
import type { MessageItem } from "@/types/conversations.types";

const MAX_LENGTH = 4096;
// Mostramos el contador solo cuando el texto se acerca al tope (ruido mínimo).
const COUNTER_THRESHOLD = 3800;

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    padding: tokens.spacingVerticalM,
    borderTop: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.contentBg,
  },
  row: {
    display: "flex",
    alignItems: "flex-end",
    gap: tokens.spacingHorizontalS,
  },
  textarea: {
    flex: 1,
    minWidth: 0,
  },
  // Altura cómoda con scroll si el texto crece (sin auto-resize complejo: máx ~6 filas).
  textareaInner: {
    maxHeight: "140px",
  },
  footerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: "16px",
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  counter: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  counterNearLimit: {
    color: tokens.colorPaletteRedForeground1,
  },
  failedHint: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorPaletteRedForeground1,
  },
});

interface Props {
  conversationId: string;
  onSent?: (msg: MessageItem) => void;
}

/**
 * Composer de texto del hilo (F3). Enter envía; Shift+Enter inserta salto de línea.
 * Validación en español en el action (Zod). El backend SIEMPRE responde 200: si el
 * envío a Meta falló, el `MessageItem` viene con `external_status:"failed"` → NO es
 * un error de la action; mostramos un hint sutil y dejamos que la burbuja muestre el
 * tick de error. Solo el `ok:false` (HttpError real) abre un MessageBar de error.
 */
export function MessageComposer({ conversationId, onSent }: Props) {
  const styles = useStyles();

  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [failedHint, setFailedHint] = useState(false);
  const [isPending, startTransition] = useTransition();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const trimmed = value.trim();
  const canSend = trimmed.length > 0 && trimmed.length <= MAX_LENGTH && !isPending;

  const handleSend = useCallback(() => {
    const content = value.trim();
    if (!content || isPending) return;
    setError(null);
    setFailedHint(false);
    startTransition(async () => {
      const res = await sendMessage(conversationId, { content });
      if (!res.ok) {
        // HttpError real (403/400/…): el mensaje NO se persistió.
        setError(res.error ?? res.fieldErrors?.content?.[0] ?? "No se pudo enviar el mensaje.");
        return;
      }
      // 200: el mensaje quedó persistido. Limpiamos el composer y notificamos.
      setValue("");
      if (res.data) {
        // El backend devuelve 200 aunque Meta haya rechazado el envío → hint sutil.
        if (res.data.external_status === "failed" || res.data.failed_at) {
          setFailedHint(true);
        }
        onSent?.(res.data);
      }
      // Devolvemos el foco al textarea para seguir escribiendo.
      textareaRef.current?.focus();
    });
  }, [value, isPending, conversationId, onSent]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Enter envía; Shift+Enter = nueva línea. No interferir con IME (composición).
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const showCounter = value.length >= COUNTER_THRESHOLD;
  const overLimit = value.length > MAX_LENGTH;

  return (
    <div className={styles.root}>
      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
          <MessageBarActions
            containerAction={
              <Button
                appearance="transparent"
                icon={<DismissRegular />}
                aria-label="Descartar error"
                onClick={() => setError(null)}
              />
            }
          />
        </MessageBar>
      ) : null}

      <div className={styles.row}>
        <Textarea
          ref={textareaRef}
          className={styles.textarea}
          textarea={{ className: styles.textareaInner }}
          value={value}
          onChange={(_, d) => {
            setValue(d.value);
            if (failedHint) setFailedHint(false);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Escribe un mensaje…"
          resize="vertical"
          rows={2}
          disabled={isPending}
        />
        <Button
          appearance="primary"
          icon={<SendRegular />}
          onClick={handleSend}
          disabled={!canSend}
        >
          {isPending ? "Enviando…" : "Enviar"}
        </Button>
      </div>

      <div className={styles.footerRow}>
        {failedHint ? (
          <span className={styles.failedHint}>El mensaje no se pudo entregar, reintenta.</span>
        ) : (
          <span className={styles.hint}>Enter para enviar · Shift + Enter para nueva línea</span>
        )}
        {showCounter ? (
          <span
            className={overLimit ? `${styles.counter} ${styles.counterNearLimit}` : styles.counter}
          >
            {value.length} / {MAX_LENGTH}
          </span>
        ) : null}
      </div>
    </div>
  );
}
