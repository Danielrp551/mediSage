"use client";

import {
  Badge,
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  CalendarRegular,
  CheckmarkCircleRegular,
  CheckmarkRegular,
  DismissCircleRegular,
  EditRegular,
  PersonArrowRightRegular,
  PlayRegular,
} from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useTransition } from "react";

import {
  attendAppointment,
  cancelAppointment,
  checkInAppointment,
  confirmAppointment,
  getAppointment,
  noShowAppointment,
  startAppointment,
} from "@/actions/appointment.actions";
import { getAppointmentTransitions } from "@/actions/appointment-status.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ProductOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import { APPOINTMENT_SOURCES, type AppointmentStatusOption } from "@/types/scheduling.types";
import type { DoctorOption } from "@/types/staff.types";

import { EditAppointmentDrawer } from "./EditAppointmentDrawer";
import { RescheduleDrawer } from "./RescheduleDrawer";

// Etiquetas en español del origen de la cita (el code viaja en inglés).
const SOURCE_LABELS: Record<(typeof APPOINTMENT_SOURCES)[number], string> = {
  bot: "Bot",
  advisor: "Asesor",
  admin: "Administrador",
  import: "Importación",
  api: "API",
};

// Etiquetas en español de los campos del change_log (field_name viaja en inglés).
const CHANGE_FIELD_LABELS: Record<string, string> = {
  doctor_id: "Doctor",
  office_id: "Consultorio",
  product_id: "Producto",
  notes: "Notas",
};

const useStyles = makeStyles({
  loading: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    padding: tokens.spacingVerticalL,
    color: appTokens.chromeTextMuted,
  },
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  // Bloque de cabecera: estado + fecha/hora + duración + origen.
  headerBlock: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    padding: tokens.spacingVerticalM,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.chromeBg,
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  headerWhen: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  headerMeta: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  // Filas etiqueta/valor.
  fields: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gap: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    alignItems: "baseline",
  },
  fieldLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  fieldValue: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  sectionTitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  // Sección de acciones del ciclo de vida.
  actions: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  actionRow: { display: "flex", gap: tokens.spacingHorizontalS, flexWrap: "wrap" },
  cancelBox: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.chromeBg,
  },
  // Timeline de estados / cambios.
  timeline: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  timelineItem: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    paddingLeft: tokens.spacingHorizontalM,
    borderLeft: `2px solid ${appTokens.chromeBorder}`,
  },
  timelineTransition: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
  },
  timelineMeta: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  timelineReason: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeText },
  timelineChange: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
  },
  arrow: { color: appTokens.chromeTextMuted },
});

interface Props {
  appointmentId: string;
  onClose: () => void;
  onChanged?: () => void;
  doctors: DoctorOption[];
  branches: BranchOption[];
  products: ProductOption[];
}

// Badge de estado con el color denormalizado (mismo patrón establecido: único
// estilo inline permitido = backgroundColor dinámico).
function StatusBadge({ status }: { status: AppointmentStatusOption }) {
  return (
    <Badge
      appearance="filled"
      style={{
        backgroundColor: status.color ?? tokens.colorNeutralBackground3,
        color: tokens.colorNeutralForegroundOnBrand,
      }}
    >
      {status.name}
    </Badge>
  );
}

export function AppointmentDetailDrawer({
  appointmentId,
  onClose,
  onChanged,
  doctors,
  branches,
  products,
}: Props) {
  const styles = useStyles();

  const detailQuery = useQuery({
    queryKey: ["scheduling", "appointment", appointmentId],
    queryFn: () => getAppointment(appointmentId),
  });

  const a = detailQuery.data;

  // Transiciones permitidas desde el estado actual (la matriz decide qué botón mostrar).
  const transitionsQuery = useQuery({
    queryKey: ["scheduling", "appointment-transitions", a?.status.id],
    queryFn: () => getAppointmentTransitions(a!.status.id),
    enabled: !!a,
  });

  const allowedCodes = useMemo(
    () => new Set((transitionsQuery.data?.to ?? []).map((t) => t.code)),
    [transitionsQuery.data],
  );

  // Estado de las acciones del ciclo de vida.
  const [pending, startTransition] = useTransition();
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancellationReason, setCancellationReason] = useState("");
  const [rescheduleOpen, setRescheduleOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

  // Tras una acción exitosa: refrescar el detalle (campos + timeline) y avisar al padre
  // para que refresque la tabla (el badge denormalizado cambia). Se AWAITea dentro del
  // startTransition → `pending` queda true durante el refetch (botones deshabilitados, sin
  // doble-submit). El detalle trae el nuevo status → la queryKey de transitionsQuery
  // cambia y la matriz se re-fetchea sola (no hace falta refetch explícito, que pediría la
  // key vieja).
  const refreshAfterAction = async () => {
    await detailQuery.refetch();
    onChanged?.();
  };

  // Handler genérico de un shortcut (confirm/check-in/start/attend/no-show).
  const runShortcut = (action: (id: string) => Promise<{ ok: boolean; error?: string }>) => {
    startTransition(async () => {
      const r = await action(appointmentId);
      if (!r.ok) {
        setActionError(r.error ?? "No se pudo completar la acción.");
        return;
      }
      setActionError(null);
      await refreshAfterAction();
    });
  };

  const handleCancelConfirm = () => {
    startTransition(async () => {
      const r = await cancelAppointment(appointmentId, {
        cancellation_reason: cancellationReason,
      });
      if (!r.ok) {
        setActionError(r.error ?? "No se pudo cancelar la cita.");
        return;
      }
      setCancelOpen(false);
      setCancellationReason("");
      setActionError(null);
      await refreshAfterAction();
    });
  };

  // Timeline de estados ordenado cronológicamente ascendente (NULL→inicial primero).
  const history = a
    ? [...a.status_history].sort((x, y) => x.changed_at.localeCompare(y.changed_at))
    : [];
  // Historial de cambios (change_log) ordenado igual.
  const changeLog = a
    ? [...a.change_log].sort((x, y) => x.changed_at.localeCompare(y.changed_at))
    : [];

  return (
    <Drawer
      open
      onClose={onClose}
      title="Detalle de la cita"
      subtitle={a ? a.person_name : undefined}
      size="medium"
      footer={
        <Button appearance="secondary" onClick={onClose}>
          Cerrar
        </Button>
      }
    >
      {detailQuery.isPending ? (
        <div className={styles.loading}>
          <Spinner size="small" />
          <span>Cargando cita…</span>
        </div>
      ) : detailQuery.isError || !a ? (
        <MessageBar intent="error">
          <MessageBarBody>No se pudo cargar la cita.</MessageBarBody>
        </MessageBar>
      ) : (
        <div className={styles.panel}>
          <div className={styles.headerBlock}>
            <div className={styles.headerRow}>
              <StatusBadge status={a.status} />
              <span className={styles.headerWhen}>{formatDate(a.scheduled_for)}</span>
            </div>
            <span className={styles.headerMeta}>
              {a.duration_min} min · Origen: {SOURCE_LABELS[a.source] ?? a.source}
            </span>
          </div>

          <div className={styles.fields}>
            <span className={styles.fieldLabel}>Paciente</span>
            <span className={styles.fieldValue}>{a.person_name}</span>
            <span className={styles.fieldLabel}>Doctor</span>
            <span className={styles.fieldValue}>{a.doctor_name}</span>
            <span className={styles.fieldLabel}>Producto</span>
            <span className={styles.fieldValue}>{a.product_name}</span>
            <span className={styles.fieldLabel}>Consultorio</span>
            <span className={styles.fieldValue}>
              {a.office_name} · {a.branch_name}
            </span>
            <span className={styles.fieldLabel}>Notas</span>
            <span className={styles.fieldValue}>{a.notes ?? "—"}</span>
          </div>

          {/* Confirmación / atención / cancelación (Detail-only). */}
          {a.confirmed_at || a.attended_at || a.cancelled_at ? (
            <div className={styles.fields}>
              {a.confirmed_at ? (
                <>
                  <span className={styles.fieldLabel}>Confirmada el</span>
                  <span className={styles.fieldValue}>{formatDate(a.confirmed_at)}</span>
                </>
              ) : null}
              {a.attended_at ? (
                <>
                  <span className={styles.fieldLabel}>Atendida el</span>
                  <span className={styles.fieldValue}>{formatDate(a.attended_at)}</span>
                </>
              ) : null}
              {a.cancelled_at ? (
                <>
                  <span className={styles.fieldLabel}>Cancelada el</span>
                  <span className={styles.fieldValue}>{formatDate(a.cancelled_at)}</span>
                  <span className={styles.fieldLabel}>Motivo de cancelación</span>
                  <span className={styles.fieldValue}>{a.cancellation_reason ?? "—"}</span>
                </>
              ) : null}
            </div>
          ) : null}

          {/* ── Acciones del ciclo de vida ── La matriz decide qué botón mostrar. ── */}
          <div className={styles.actions}>
            <h3 className={styles.sectionTitle}>Acciones</h3>

            {actionError ? (
              <MessageBar intent="error">
                <MessageBarBody>{actionError}</MessageBarBody>
              </MessageBar>
            ) : null}

            {/* Si falla la carga de la matriz, las acciones quedarían vacías sin explicación. */}
            {transitionsQuery.isError ? (
              <MessageBar intent="error">
                <MessageBarBody>No se pudieron cargar las acciones disponibles.</MessageBarBody>
              </MessageBar>
            ) : null}

            {cancelOpen ? (
              // Sub-flujo de cancelación inline.
              <div className={styles.cancelBox}>
                <FormField label="Motivo de cancelación (opcional)">
                  <Textarea
                    value={cancellationReason}
                    onChange={(_, d) => setCancellationReason(d.value)}
                    rows={3}
                    placeholder="Anota por qué cancelas la cita…"
                    disabled={pending}
                  />
                </FormField>
                <div className={styles.actionRow}>
                  <Button
                    appearance="primary"
                    icon={<DismissCircleRegular />}
                    onClick={handleCancelConfirm}
                    disabled={pending}
                  >
                    {pending ? "Cancelando…" : "Confirmar cancelación"}
                  </Button>
                  <Button
                    appearance="secondary"
                    onClick={() => {
                      setCancelOpen(false);
                      setCancellationReason("");
                    }}
                    disabled={pending}
                  >
                    Volver
                  </Button>
                </div>
              </div>
            ) : (
              <div className={styles.actionRow}>
                {allowedCodes.has("CONFIRMED") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_TRANSITION"]}>
                    <Button
                      appearance="secondary"
                      icon={<CheckmarkRegular />}
                      onClick={() => runShortcut(confirmAppointment)}
                      disabled={pending}
                    >
                      Confirmar
                    </Button>
                  </PermissionGuard>
                ) : null}
                {allowedCodes.has("CHECKED_IN") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_TRANSITION"]}>
                    <Button
                      appearance="secondary"
                      icon={<PersonArrowRightRegular />}
                      onClick={() => runShortcut(checkInAppointment)}
                      disabled={pending}
                    >
                      Registrar llegada
                    </Button>
                  </PermissionGuard>
                ) : null}
                {allowedCodes.has("IN_PROGRESS") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_TRANSITION"]}>
                    <Button
                      appearance="secondary"
                      icon={<PlayRegular />}
                      onClick={() => runShortcut(startAppointment)}
                      disabled={pending}
                    >
                      Iniciar
                    </Button>
                  </PermissionGuard>
                ) : null}
                {allowedCodes.has("ATTENDED") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_TRANSITION"]}>
                    <Button
                      appearance="secondary"
                      icon={<CheckmarkCircleRegular />}
                      onClick={() => runShortcut(attendAppointment)}
                      disabled={pending}
                    >
                      Atender
                    </Button>
                  </PermissionGuard>
                ) : null}
                {allowedCodes.has("NO_SHOW") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_TRANSITION"]}>
                    <Button
                      appearance="secondary"
                      icon={<DismissCircleRegular />}
                      onClick={() => runShortcut(noShowAppointment)}
                      disabled={pending}
                    >
                      No asistió
                    </Button>
                  </PermissionGuard>
                ) : null}
                {allowedCodes.has("CANCELLED") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_CANCEL"]}>
                    <Button
                      appearance="secondary"
                      icon={<DismissCircleRegular />}
                      onClick={() => {
                        setActionError(null);
                        setCancelOpen(true);
                      }}
                      disabled={pending}
                    >
                      Cancelar
                    </Button>
                  </PermissionGuard>
                ) : null}
                {allowedCodes.has("RESCHEDULED") ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_RESCHEDULE"]}>
                    <Button
                      appearance="secondary"
                      icon={<CalendarRegular />}
                      onClick={() => setRescheduleOpen(true)}
                      disabled={pending}
                    >
                      Reagendar
                    </Button>
                  </PermissionGuard>
                ) : null}
                {!a.status.is_final ? (
                  <PermissionGuard anyOf={["APPOINTMENTS_UPDATE"]}>
                    <Button
                      appearance="secondary"
                      icon={<EditRegular />}
                      onClick={() => setEditOpen(true)}
                      disabled={pending}
                    >
                      Editar
                    </Button>
                  </PermissionGuard>
                ) : null}
              </div>
            )}
          </div>

          <div>
            <h3 className={styles.sectionTitle}>Historial de estado</h3>
            {history.length === 0 ? (
              <p className={styles.timelineMeta}>Sin cambios de estado registrados.</p>
            ) : (
              <div className={styles.timeline} style={{ marginTop: tokens.spacingVerticalS }}>
                {history.map((h) => (
                  <div key={h.id} className={styles.timelineItem}>
                    <div className={styles.timelineTransition}>
                      {h.from_status ? (
                        <StatusBadge status={h.from_status} />
                      ) : (
                        <span className={styles.timelineMeta}>(inicial)</span>
                      )}
                      <span className={styles.arrow}>→</span>
                      <StatusBadge status={h.to_status} />
                    </div>
                    <span className={styles.timelineMeta}>
                      {formatDate(h.changed_at)} · {h.changed_by_user?.full_name ?? "Sistema"}
                    </span>
                    {h.reason ? <span className={styles.timelineReason}>{h.reason}</span> : null}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Historial de cambios (change_log) — columnas no-estado editadas. */}
          <div>
            <h3 className={styles.sectionTitle}>Historial de cambios</h3>
            {changeLog.length === 0 ? (
              <p className={styles.timelineMeta}>Sin cambios registrados.</p>
            ) : (
              <div className={styles.timeline} style={{ marginTop: tokens.spacingVerticalS }}>
                {changeLog.map((c) => (
                  <div key={c.id} className={styles.timelineItem}>
                    <div className={styles.timelineChange}>
                      <strong>{CHANGE_FIELD_LABELS[c.field_name] ?? c.field_name}</strong>
                      <span className={styles.timelineMeta}>{c.previous_value ?? "—"}</span>
                      <span className={styles.arrow}>→</span>
                      <span>{c.new_value ?? "—"}</span>
                    </div>
                    <span className={styles.timelineMeta}>
                      {formatDate(c.changed_at)} · {c.changed_by_user?.full_name ?? "Sistema"}
                    </span>
                    {c.reason ? <span className={styles.timelineReason}>{c.reason}</span> : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reagendar: crea una NUEVA cita + marca esta RESCHEDULED → cerramos el detalle. */}
      {rescheduleOpen && a ? (
        <RescheduleDrawer
          appointment={a}
          doctors={doctors}
          branches={branches}
          onClose={() => setRescheduleOpen(false)}
          onRescheduled={() => {
            setRescheduleOpen(false);
            onChanged?.();
            onClose();
          }}
        />
      ) : null}

      {/* Editar: NO cambia el estado → mantenemos el detalle abierto y lo refrescamos. */}
      {editOpen && a ? (
        <EditAppointmentDrawer
          appointment={a}
          doctors={doctors}
          products={products}
          onClose={() => setEditOpen(false)}
          onUpdated={() => {
            setEditOpen(false);
            void detailQuery.refetch();
            onChanged?.();
          }}
        />
      ) : null}
    </Drawer>
  );
}
