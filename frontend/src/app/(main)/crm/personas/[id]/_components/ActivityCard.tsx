"use client";

import {
  Avatar,
  Badge,
  Button,
  Card,
  Dropdown,
  Option,
  Textarea,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { CheckmarkCircleRegular, DeleteRegular, EditRegular } from "@fluentui/react-icons";
import { memo, useState } from "react";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import {
  ACTIVITY_OUTCOME_LABELS,
  ACTIVITY_TYPE_META,
  REMINDER_CHANNEL_LABELS,
} from "@/lib/constants/crm";
import { appTokens } from "@/lib/theme/brand";
import { formatDate, formatRelative, nowLocalISO } from "@/lib/utils/date";
import type { ActivityOutcome, LeadActivityItem } from "@/types/crm.types";
import type { LeadActivityUpdateInput } from "@/lib/schemas/lead-activity.schema";

import type { MutationResult } from "@/actions/user.actions";
import type { ApiSingle } from "@/types/api.types";

// Tipos que el asesor edita/borra desde la tarjeta (los de sistema son read-only).
const EDITABLE_TYPES = new Set<LeadActivityItem["activity_type"]>([
  "NOTE",
  "CALL_ATTEMPT",
  "FOLLOW_UP_SCHEDULED",
  "FOLLOW_UP_COMPLETED",
]);

const OUTCOME_VALUES = Object.keys(ACTIVITY_OUTCOME_LABELS) as ActivityOutcome[];

// Color del chip de outcome por resultado (tokens Fluent, NO brandPalette.accent).
const OUTCOME_COLOR: Record<ActivityOutcome, "success" | "warning" | "danger" | "informative"> = {
  successful: "success",
  interested: "success",
  no_answer: "warning",
  busy: "warning",
  wrong_number: "danger",
  not_interested: "danger",
};

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalM,
    padding: tokens.spacingVerticalM,
    // Lista potencialmente larga — el navegador no paga layout fuera de viewport.
    contentVisibility: "auto",
    containIntrinsicSize: "auto 80px",
  },
  cardFuture: {
    borderLeft: `3px solid ${tokens.colorPaletteMarigoldBorderActive}`,
  },
  cardIcon: {
    display: "inline-flex",
    fontSize: "20px",
    flexShrink: 0,
    marginTop: "2px",
  },
  cardMain: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    flex: 1,
    minWidth: 0,
  },
  cardTopRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
  },
  cardTitle: {
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  cardMeta: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    flexShrink: 0,
  },
  cardContent: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    wordBreak: "break-word",
    whiteSpace: "pre-wrap",
  },
  cardExtras: {
    display: "flex",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
    alignItems: "center",
    marginTop: tokens.spacingVerticalXXS,
  },
  scheduleLine: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
  },
  rowActions: { display: "flex", gap: tokens.spacingHorizontalXXS, flexShrink: 0 },
  editForm: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  editActions: { display: "flex", gap: tokens.spacingHorizontalXS, justifyContent: "flex-end" },
});

export interface ActivityCardProps {
  activity: LeadActivityItem;
  canWrite: boolean;
  /** Instante actual (ms) calculado client-only por el padre (TZ-safe). */
  nowMs: number;
  /** Handlers ESTABLES (useCallback en el padre) para no romper el React.memo. */
  onUpdate: (
    activityId: string,
    input: LeadActivityUpdateInput,
  ) => Promise<MutationResult<ApiSingle<LeadActivityItem>>>;
  onDelete: (activityId: string) => Promise<MutationResult<null>>;
}

/**
 * Tarjeta tipada del timeline (memoizada). Pinta ícono+color por tipo, actor,
 * timestamp relativo (client-only), contenido y extras por tipo. Para los tipos
 * del asesor (NOTE/CALL_ATTEMPT/FOLLOW_UP_*) y con `canWrite`: editar inline,
 * eliminar (confirm) y "Marcar completado" (seguimiento pendiente).
 */
function ActivityCardImpl({ activity, canWrite, nowMs, onUpdate, onDelete }: ActivityCardProps) {
  const styles = useStyles();
  const meta = ACTIVITY_TYPE_META[activity.activity_type];
  const Icon = meta.icon;
  const actorName = activity.advisor?.full_name ?? "Sistema";

  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState(activity.content ?? "");
  const [editOutcome, setEditOutcome] = useState<ActivityOutcome | "">(activity.outcome ?? "");
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const canEdit = canWrite && EDITABLE_TYPES.has(activity.activity_type);

  // Seguimiento futuro pendiente: resaltado + acción "Marcar completado".
  const isFutureFollowUp =
    activity.activity_type === "FOLLOW_UP_SCHEDULED" &&
    !activity.completed_at &&
    !!activity.scheduled_for &&
    new Date(activity.scheduled_for).getTime() > nowMs;
  const isPendingFollowUp =
    activity.activity_type === "FOLLOW_UP_SCHEDULED" && !activity.completed_at;

  // STATUS_CHANGE emite payload {from: id, to: id} (ids, no nombres): el detalle
  // "{from} → {to}" con badges vive en el tab Historial del Lead, no acá (la tarjeta
  // de actividad muestra solo el label + actor + tiempo). No se intenta resolver ids.
  const durationMin =
    typeof activity.payload?.duration_min === "number" ? activity.payload.duration_min : null;
  const reminderChannel =
    typeof activity.payload?.reminder_channel === "string"
      ? activity.payload.reminder_channel
      : null;
  // Un seguimiento programado YA realizado (PUT completed_at) sigue siendo
  // FOLLOW_UP_SCHEDULED pero debe mostrarse como completado (paridad ui.md).
  const isCompletedFollowUp =
    activity.activity_type === "FOLLOW_UP_SCHEDULED" && !!activity.completed_at;

  const startEdit = () => {
    setEditContent(activity.content ?? "");
    setEditOutcome(activity.outcome ?? "");
    setRowError(null);
    setEditing(true);
  };

  const saveEdit = async () => {
    setSaving(true);
    setRowError(null);
    const input: LeadActivityUpdateInput = {
      content: editContent.trim() ? editContent.trim() : null,
    };
    if (activity.activity_type === "CALL_ATTEMPT" && editOutcome) input.outcome = editOutcome;
    const result = await onUpdate(activity.id, input);
    setSaving(false);
    if (result.ok) {
      setEditing(false);
    } else {
      setRowError(result.error ?? "No se pudo guardar.");
    }
  };

  const markCompleted = async () => {
    setBusy(true);
    setRowError(null);
    const result = await onUpdate(activity.id, { completed_at: nowLocalISO() });
    setBusy(false);
    if (!result.ok) setRowError(result.error ?? "No se pudo marcar como completado.");
  };

  const doDelete = async () => {
    setBusy(true);
    setRowError(null);
    const result = await onDelete(activity.id);
    setBusy(false);
    if (result.ok) {
      setConfirmDelete(false);
    } else {
      setRowError(result.error ?? "No se pudo eliminar.");
    }
  };

  return (
    <Card className={`${styles.card} ${isFutureFollowUp ? styles.cardFuture : ""}`}>
      <span className={styles.cardIcon} style={{ color: meta.color }}>
        <Icon />
      </span>
      <div className={styles.cardMain}>
        <div className={styles.cardTopRow}>
          <span className={styles.cardTitle}>{meta.label}</span>
          <span className={styles.cardMeta}>
            <Avatar size={20} name={actorName} color={activity.advisor ? "colorful" : "neutral"} />
            {actorName}
            {" · "}
            <Tooltip content={formatDate(activity.created_on)} relationship="label" withArrow>
              <span>{formatRelative(activity.created_on)}</span>
            </Tooltip>
          </span>
        </div>

        {editing ? (
          <div className={styles.editForm}>
            <Textarea
              value={editContent}
              onChange={(_, d) => setEditContent(d.value)}
              rows={2}
              disabled={saving}
              placeholder="Contenido…"
            />
            {activity.activity_type === "CALL_ATTEMPT" ? (
              <Dropdown
                value={editOutcome ? ACTIVITY_OUTCOME_LABELS[editOutcome] : ""}
                selectedOptions={editOutcome ? [editOutcome] : []}
                placeholder="Resultado…"
                disabled={saving}
                onOptionSelect={(_, data) =>
                  setEditOutcome((data.optionValue as ActivityOutcome) ?? "")
                }
              >
                {OUTCOME_VALUES.map((o) => (
                  <Option key={o} value={o}>
                    {ACTIVITY_OUTCOME_LABELS[o]}
                  </Option>
                ))}
              </Dropdown>
            ) : null}
            <div className={styles.editActions}>
              <Button
                appearance="secondary"
                size="small"
                disabled={saving}
                onClick={() => setEditing(false)}
              >
                Cancelar
              </Button>
              <Button
                appearance="primary"
                size="small"
                disabled={saving}
                onClick={() => void saveEdit()}
              >
                {saving ? "Guardando…" : "Guardar"}
              </Button>
            </div>
          </div>
        ) : (
          <>
            {activity.content ? (
              <span className={styles.cardContent}>{activity.content}</span>
            ) : null}

            {activity.scheduled_for ? (
              <span className={styles.scheduleLine}>
                Para: {formatDate(activity.scheduled_for)}
                {reminderChannel ? (
                  <>
                    {" "}
                    · Recordatorio: {REMINDER_CHANNEL_LABELS[reminderChannel] ?? reminderChannel}
                  </>
                ) : null}
                {isFutureFollowUp ? (
                  <Badge appearance="tint" color="warning">
                    Próximo
                  </Badge>
                ) : null}
              </span>
            ) : null}

            {isCompletedFollowUp && activity.completed_at ? (
              <span className={styles.scheduleLine}>
                <CheckmarkCircleRegular />
                Completado el {formatDate(activity.completed_at)}
              </span>
            ) : null}

            {activity.activity_type === "FOLLOW_UP_COMPLETED" && activity.completed_at ? (
              <span className={styles.scheduleLine}>
                Completado el {formatDate(activity.completed_at)}
              </span>
            ) : null}

            <div className={styles.cardExtras}>
              {activity.outcome ? (
                <Badge appearance="tint" color={OUTCOME_COLOR[activity.outcome]}>
                  {ACTIVITY_OUTCOME_LABELS[activity.outcome]}
                </Badge>
              ) : null}
              {durationMin !== null ? (
                <Badge appearance="outline" color="informative">
                  {durationMin} min
                </Badge>
              ) : null}
            </div>
          </>
        )}

        {rowError ? (
          <span
            className={styles.scheduleLine}
            style={{ color: tokens.colorPaletteRedForeground1 }}
          >
            {rowError}
          </span>
        ) : null}

        {canEdit && !editing ? (
          <div className={styles.cardExtras}>
            {isPendingFollowUp ? (
              <Button
                appearance="subtle"
                size="small"
                icon={<CheckmarkCircleRegular />}
                disabled={busy}
                onClick={() => void markCompleted()}
              >
                Marcar completado
              </Button>
            ) : null}
            <div className={styles.rowActions}>
              <Button
                appearance="subtle"
                size="small"
                icon={<EditRegular />}
                aria-label="Editar actividad"
                disabled={busy}
                onClick={startEdit}
              />
              <Button
                appearance="subtle"
                size="small"
                icon={<DeleteRegular />}
                aria-label="Eliminar actividad"
                disabled={busy}
                onClick={() => {
                  setRowError(null);
                  setConfirmDelete(true);
                }}
              />
            </div>
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="¿Eliminar actividad?"
        description={
          rowError
            ? rowError
            : "La actividad desaparecerá del feed. Esta acción no se puede deshacer desde la interfaz."
        }
        confirmText={busy ? "Eliminando…" : "Eliminar"}
        cancelText="Cancelar"
        destructive
        onConfirm={() => void doDelete()}
        onCancel={() => {
          if (!busy) {
            setConfirmDelete(false);
            setRowError(null);
          }
        }}
      />
    </Card>
  );
}

export const ActivityCard = memo(ActivityCardImpl);
