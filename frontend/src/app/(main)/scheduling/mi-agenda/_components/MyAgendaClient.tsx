"use client";

import {
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { fetchMyAppointmentsInRange } from "@/actions/appointment.actions";
import { WEEKDAY_LABELS, minutesToTime } from "@/lib/constants/calendar";
import { appTokens } from "@/lib/theme/brand";
import {
  addDays,
  localDateIsoOf,
  localMinutesOf,
  startOfWeek,
  toIsoDate,
} from "@/lib/utils/calendarWeek";

import { AppointmentDetailDrawer } from "../../citas/_components/AppointmentDetailDrawer";
import {
  CalendarGrid,
  type CalendarColumn,
  type CalendarEvent,
} from "../../_components/CalendarGrid";
import { PeriodNavigator } from "../../_components/PeriodNavigator";

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
  toolbar: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  spacer: { flex: 1 },
  centerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: tokens.spacingVerticalXXXL,
  },
});

// Formato del rango semanal: "2–8 jun 2026" (mismo molde que el calendario general).
function formatWeekRange(weekStart: Date): string {
  const weekEnd = addDays(weekStart, 6);
  const dayMonth = new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short" });
  const dayOnly = new Intl.DateTimeFormat("es-PE", { day: "numeric" });
  const sameMonth =
    weekStart.getMonth() === weekEnd.getMonth() &&
    weekStart.getFullYear() === weekEnd.getFullYear();
  const left = sameMonth ? dayOnly.format(weekStart) : dayMonth.format(weekStart);
  const right = dayMonth.format(weekEnd);
  return `${left}–${right} ${weekEnd.getFullYear()}`;
}

// Mi agenda: la semana de citas del doctor logueado (sin selector de doctor, sin modo
// día, sin huecos libres). El backend FUERZA doctor_id = doctor del token (anti-IDOR).
export function MyAgendaClient() {
  const styles = useStyles();

  // CLIENT-ONLY (TZ-safe): anchor/todayIso/nowMin nacen null + efecto, para no
  // desfasar el día en SSR (el server corre en UTC).
  const [anchor, setAnchor] = useState<Date | null>(null);
  const [todayIso, setTodayIso] = useState<string | null>(null);
  const [nowMin, setNowMin] = useState<number | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  useEffect(() => {
    const now = new Date();
    setAnchor(now);
    setTodayIso(toIsoDate(now));
    setNowMin(now.getHours() * 60 + now.getMinutes());
  }, []);

  // La línea de "ahora" avanza: recalcula nowMin cada minuto.
  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date();
      setNowMin(now.getHours() * 60 + now.getMinutes());
    }, 60000);
    return () => clearInterval(id);
  }, []);

  const weekStart = useMemo(() => (anchor ? startOfWeek(anchor) : null), [anchor]);
  const fromIso = weekStart ? weekStart.toISOString() : "";
  const toIso = weekStart ? addDays(weekStart, 7).toISOString() : "";

  const query = useQuery({
    queryKey: ["sched-myagenda", fromIso, toIso],
    queryFn: () => fetchMyAppointmentsInRange({ fromIso, toIso }),
    enabled: !!weekStart,
  });

  const columns = useMemo<CalendarColumn[]>(() => {
    if (!weekStart) return [];
    return Array.from({ length: 7 }, (_, i) => {
      const date = addDays(weekStart, i);
      const key = toIsoDate(date);
      return {
        key,
        // i ∈ [0,6] y WEEKDAY_LABELS tiene 7 entradas → siempre definido.
        label: WEEKDAY_LABELS[i]!,
        sublabel: String(date.getDate()),
        isToday: key === todayIso,
        isWeekend: i >= 5,
      };
    });
  }, [weekStart, todayIso]);

  const events = useMemo<CalendarEvent[]>(() => {
    const out: CalendarEvent[] = [];
    for (const appt of query.data ?? []) {
      const startMin = localMinutesOf(appt.scheduled_for);
      out.push({
        id: appt.id,
        columnKey: localDateIsoOf(appt.scheduled_for),
        startMin,
        endMin: startMin + appt.duration_min,
        title: appt.person_name,
        subtitle: minutesToTime(startMin),
        color: appt.status.color,
        kind: "appointment",
        ariaLabel: `${appt.person_name} · ${minutesToTime(startMin)} · ${appt.status.name}`,
      });
    }
    return out;
  }, [query.data]);

  if (!anchor || !weekStart) {
    return (
      <div className={styles.root}>
        <header className={styles.header}>
          <h1 className={styles.title}>Mi agenda</h1>
        </header>
        <div className={styles.centerRow}>
          <Spinner label="Cargando agenda…" />
        </div>
      </div>
    );
  }

  const nowIndicator =
    nowMin !== null && todayIso && columns.some((c) => c.key === todayIso)
      ? { columnKey: todayIso, min: nowMin }
      : null;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Mi agenda</h1>
        <p className={styles.subtitle}>Tus citas de la semana.</p>
      </header>

      <div className={styles.toolbar}>
        <span className={styles.spacer} />
        <PeriodNavigator
          label={formatWeekRange(weekStart)}
          prevLabel="Semana anterior"
          nextLabel="Semana siguiente"
          onPrev={() => setAnchor(addDays(anchor, -7))}
          onNext={() => setAnchor(addDays(anchor, 7))}
          onToday={() => setAnchor(new Date())}
        />
      </div>

      {query.isError ? (
        <MessageBar intent="error">
          <MessageBarBody>
            No se pudieron cargar tus citas. Intenta de nuevo más tarde.
          </MessageBarBody>
        </MessageBar>
      ) : query.isPending ? (
        <div className={styles.centerRow}>
          <Spinner label="Cargando citas…" />
        </div>
      ) : (
        <CalendarGrid
          columns={columns}
          events={events}
          onEventClick={(event) => setDetailId(event.id)}
          nowIndicator={nowIndicator}
        />
      )}

      {detailId ? (
        <AppointmentDetailDrawer
          appointmentId={detailId}
          onClose={() => setDetailId(null)}
          onChanged={() => void query.refetch()}
          doctors={[]}
          branches={[]}
          products={[]}
        />
      ) : null}
    </div>
  );
}
