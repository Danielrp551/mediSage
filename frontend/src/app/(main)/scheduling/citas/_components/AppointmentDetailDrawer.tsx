"use client";

import {
  Badge,
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";

import { getAppointment } from "@/actions/appointment.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import { APPOINTMENT_SOURCES, type AppointmentStatusOption } from "@/types/scheduling.types";

// Etiquetas en español del origen de la cita (el code viaja en inglés).
const SOURCE_LABELS: Record<(typeof APPOINTMENT_SOURCES)[number], string> = {
  bot: "Bot",
  advisor: "Asesor",
  admin: "Administrador",
  import: "Importación",
  api: "API",
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
  // Timeline de estados.
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
  arrow: { color: appTokens.chromeTextMuted },
});

interface Props {
  appointmentId: string;
  onClose: () => void;
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

export function AppointmentDetailDrawer({ appointmentId, onClose }: Props) {
  const styles = useStyles();

  const query = useQuery({
    queryKey: ["scheduling", "appointment", appointmentId],
    queryFn: () => getAppointment(appointmentId),
  });

  const a = query.data;

  // Timeline ordenado cronológicamente ascendente (NULL→inicial primero).
  const history = a
    ? [...a.status_history].sort((x, y) => x.changed_at.localeCompare(y.changed_at))
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
      {query.isPending ? (
        <div className={styles.loading}>
          <Spinner size="small" />
          <span>Cargando cita…</span>
        </div>
      ) : query.isError || !a ? (
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
        </div>
      )}
    </Drawer>
  );
}
