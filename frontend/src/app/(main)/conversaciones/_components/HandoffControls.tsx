"use client";

import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  ArrowResetRegular,
  DismissCircleRegular,
  DismissRegular,
  PersonAddRegular,
  PersonArrowBackRegular,
} from "@fluentui/react-icons";
import { useState, useTransition } from "react";

import {
  closeConversation,
  releaseConversation,
  reopenConversation,
  takeConversation,
} from "@/actions/conversation.actions";
import { useAuth } from "@/providers/AuthProvider";
import type { ConversationDetail } from "@/types/conversations.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  dialogField: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
  },
  dialogLabel: {
    fontSize: tokens.fontSizeBase300,
  },
});

interface Props {
  detail: ConversationDetail;
  onChanged: (detail: ConversationDetail) => void;
}

/**
 * Controles de handoff del hilo (F3): tomar / liberar / cerrar / reabrir. Cada
 * botón se muestra según el estado de la conversación, si el actor es el asignado y
 * los permisos del usuario. Liberar y cerrar piden confirmación (Dialog); liberar
 * acepta un motivo opcional. En error se muestra un MessageBar descartable (incluye
 * el mensaje del backend, p.ej. 409 CONVERSATION_ALREADY_OPEN al reabrir).
 */
export function HandoffControls({ detail, onChanged }: Props) {
  const styles = useStyles();
  const { user, hasPermission } = useAuth();

  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  // Diálogos.
  const [releaseOpen, setReleaseOpen] = useState(false);
  const [releaseReason, setReleaseReason] = useState("");
  const [closeOpen, setCloseOpen] = useState(false);

  const isOpen = detail.status === "open";
  const isClosed = detail.status === "closed";
  const isAssignee = detail.assignee_type === "advisor" && detail.assignee_user?.id === user?.id;

  // Visibilidad de cada acción (estado + asignación + permiso).
  const canTake = isOpen && !isAssignee && hasPermission("CONVERSATIONS_TAKE");
  const canRelease = isOpen && isAssignee && hasPermission("CONVERSATIONS_RELEASE");
  const canClose = isOpen && hasPermission("CONVERSATIONS_CLOSE");
  const canReopen = isClosed && hasPermission("CONVERSATIONS_TAKE");

  // Ejecuta una mutación de handoff: limpia el error, corre la action y propaga el
  // detail actualizado. `onDone` permite cerrar el diálogo asociado tras el éxito.
  const run = (
    action: () => Promise<{ ok: boolean; data?: ConversationDetail; error?: string }>,
    onDone?: () => void,
  ) => {
    setError(null);
    startTransition(async () => {
      const res = await action();
      if (res.ok && res.data) {
        onChanged(res.data);
        onDone?.();
      } else {
        setError(res.error ?? "No se pudo completar la acción.");
      }
    });
  };

  const handleTake = () => run(() => takeConversation(detail.id, {}));

  const handleReleaseConfirm = () =>
    run(
      () =>
        releaseConversation(detail.id, {
          to_assignee_type: "unassigned",
          reason: releaseReason.trim() ? releaseReason.trim() : null,
        }),
      () => {
        setReleaseOpen(false);
        setReleaseReason("");
      },
    );

  const handleCloseConfirm = () =>
    run(
      () => closeConversation(detail.id),
      () => setCloseOpen(false),
    );

  const handleReopen = () => run(() => reopenConversation(detail.id));

  // Sin ninguna acción visible: no renderizar barra (evita un contenedor vacío).
  const hasAnyAction = canTake || canRelease || canClose || canReopen;
  if (!hasAnyAction && !error) return null;

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

      {hasAnyAction ? (
        <div className={styles.actions}>
          {canTake ? (
            <Button
              appearance="primary"
              icon={<PersonAddRegular />}
              disabled={isPending}
              onClick={handleTake}
            >
              Tomar
            </Button>
          ) : null}

          {canRelease ? (
            <Button
              appearance="secondary"
              icon={<PersonArrowBackRegular />}
              disabled={isPending}
              onClick={() => {
                setReleaseReason("");
                setReleaseOpen(true);
              }}
            >
              Liberar
            </Button>
          ) : null}

          {canClose ? (
            <Button
              appearance="secondary"
              icon={<DismissCircleRegular />}
              disabled={isPending}
              onClick={() => setCloseOpen(true)}
            >
              Cerrar
            </Button>
          ) : null}

          {canReopen ? (
            <Button
              appearance="primary"
              icon={<ArrowResetRegular />}
              disabled={isPending}
              onClick={handleReopen}
            >
              Reabrir
            </Button>
          ) : null}
        </div>
      ) : null}

      {/* Diálogo: liberar (motivo opcional). */}
      <Dialog
        open={releaseOpen}
        onOpenChange={(_, d) => {
          if (!d.open && !isPending) {
            setReleaseOpen(false);
            setReleaseReason("");
          }
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>Liberar conversación</DialogTitle>
            <DialogContent>
              <div className={styles.dialogField}>
                <span className={styles.dialogLabel}>
                  La conversación quedará sin asignar y volverá a la bandeja.
                </span>
                <span className={styles.dialogLabel}>Motivo (opcional)</span>
                <Textarea
                  value={releaseReason}
                  onChange={(_, d) => setReleaseReason(d.value)}
                  rows={3}
                  placeholder="Anota por qué liberas la conversación…"
                  disabled={isPending}
                />
              </div>
            </DialogContent>
            <DialogActions>
              <Button
                appearance="secondary"
                disabled={isPending}
                onClick={() => {
                  setReleaseOpen(false);
                  setReleaseReason("");
                }}
              >
                Cancelar
              </Button>
              <Button appearance="primary" disabled={isPending} onClick={handleReleaseConfirm}>
                {isPending ? "Liberando…" : "Liberar"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>

      {/* Diálogo: cerrar (confirmación). */}
      <Dialog
        open={closeOpen}
        onOpenChange={(_, d) => {
          if (!d.open && !isPending) setCloseOpen(false);
        }}
      >
        <DialogSurface>
          <DialogBody>
            <DialogTitle>¿Cerrar esta conversación?</DialogTitle>
            <DialogContent>
              <span className={styles.dialogLabel}>
                Podrás reabrirla más adelante si el contacto vuelve a escribir.
              </span>
            </DialogContent>
            <DialogActions>
              <Button
                appearance="secondary"
                disabled={isPending}
                onClick={() => setCloseOpen(false)}
              >
                Cancelar
              </Button>
              <Button appearance="primary" disabled={isPending} onClick={handleCloseConfirm}>
                {isPending ? "Cerrando…" : "Cerrar conversación"}
              </Button>
            </DialogActions>
          </DialogBody>
        </DialogSurface>
      </Dialog>
    </div>
  );
}
