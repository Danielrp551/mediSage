"use client";

import {
  Button,
  Dropdown,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  Option,
  Spinner,
  Tab,
  TabList,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { computeAvailability, fetchAppointmentsInRange } from "@/actions/appointment.actions";
import { fetchExternalEvents } from "@/actions/calendar.actions";
import { usePermissions } from "@/hooks/usePermissions";
import { CALENDAR, WEEKDAY_LABELS, minutesToTime } from "@/lib/constants/calendar";
import { appTokens } from "@/lib/theme/brand";
import {
  addDays,
  localDateIsoOf,
  localMinutesOf,
  startOfDay,
  startOfWeek,
  toIsoDate,
} from "@/lib/utils/calendarWeek";
import type { ProductOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import type { AppointmentStatusOption, AvailabilitySlot } from "@/types/scheduling.types";
import type { DoctorOption } from "@/types/staff.types";

import { AppointmentDetailDrawer } from "../../citas/_components/AppointmentDetailDrawer";
import {
  CalendarGrid,
  type CalendarColumn,
  type CalendarEvent,
} from "../../_components/CalendarGrid";
import { PeriodNavigator } from "../../_components/PeriodNavigator";
import { QuickBookDrawer } from "../../_components/QuickBookDrawer";

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
  filter: { minWidth: "220px" },
  spacer: { flex: 1 },
  // Estado vacío / spinner ocupando el lugar de la grilla.
  placeholder: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    border: `1px dashed ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    backgroundColor: appTokens.chromeBg,
    color: appTokens.chromeTextMuted,
    textAlign: "center",
  },
  centerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: tokens.spacingVerticalXXXL,
  },
  // Leyenda del overlay (cita medisage / evento externo / hueco libre).
  legend: {
    display: "flex",
    gap: tokens.spacingHorizontalL,
    flexWrap: "wrap",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  legendItem: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalXS },
  swatch: {
    width: "14px",
    height: "14px",
    borderRadius: tokens.borderRadiusSmall,
    flexShrink: 0,
  },
  swatchAppt: { backgroundColor: tokens.colorBrandBackground },
  swatchExternal: {
    backgroundColor: tokens.colorNeutralBackground3,
    backgroundImage: `repeating-linear-gradient(45deg, ${tokens.colorNeutralStroke2}, ${tokens.colorNeutralStroke2} 1px, transparent 1px, transparent 5px)`,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  swatchFree: {
    border: `1px dashed ${tokens.colorBrandStroke1}`,
    backgroundColor: tokens.colorBrandBackground2,
  },
});

interface Props {
  doctors: DoctorOption[];
  products: ProductOption[];
  branches: BranchOption[];
  statuses: AppointmentStatusOption[];
}

type ViewMode = "week" | "day";

// Formato del rango semanal: "2–8 jun 2026" (mismo estilo que la grilla de staff). Si el
// rango cruza de mes o año, se muestran ambos lados ("28 may – 3 jun 2026").
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

// Formato del día: "lun 2 jun 2026".
function formatDayLabel(day: Date): string {
  return new Intl.DateTimeFormat("es-PE", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(day);
}

export function CalendarClient({ doctors, products, branches, statuses }: Props) {
  const styles = useStyles();

  const [view, setView] = useState<ViewMode>("week");
  // CLIENT-ONLY: anchor/todayIso/nowMin nacen null y se setean en efecto para no
  // desfasar el día en SSR (el server corre en UTC). La grilla se posiciona con
  // localMinutesOf/localDateIsoOf (TZ-safe) sobre los datos del fetch client-side.
  const [anchor, setAnchor] = useState<Date | null>(null);
  const [todayIso, setTodayIso] = useState<string | null>(null);
  const [nowMin, setNowMin] = useState<number | null>(null);

  // Filtros del modo semana (por doctor) y día (por estado).
  const [doctorId, setDoctorId] = useState<string | null>(null);
  const [productId, setProductId] = useState<string | null>(null);
  const [statusId, setStatusId] = useState<string | null>(null);
  // Overlay de eventos externos (F2): la lectura es POR SEDE. Solo visible/consultado con el
  // permiso fino del overlay (lo tienen DOCTOR/ASESOR/ADMIN).
  const { hasPermission } = usePermissions();
  const canSeeExternal = hasPermission("CALENDAR_EXTERNAL_EVENTS_READ");
  const [branchId, setBranchId] = useState<string | null>(null);

  // Drawers.
  const [detailId, setDetailId] = useState<string | null>(null);
  const [quickBook, setQuickBook] = useState<{
    slot: AvailabilitySlot;
    productId: string;
    productName: string;
  } | null>(null);

  useEffect(() => {
    const now = new Date();
    setAnchor(now);
    setTodayIso(toIsoDate(now));
    setNowMin(now.getHours() * 60 + now.getMinutes());
  }, []);

  // La línea de "ahora" avanza: recalcula nowMin cada minuto (sin esto quedaría congelada
  // en la hora de montaje).
  useEffect(() => {
    const id = setInterval(() => {
      const now = new Date();
      setNowMin(now.getHours() * 60 + now.getMinutes());
    }, 60000);
    return () => clearInterval(id);
  }, []);

  // ── Rangos derivados del anchor (memo seguro: si anchor es null, valores nulos) ──
  const weekStart = useMemo(() => (anchor ? startOfWeek(anchor) : null), [anchor]);
  const day = useMemo(() => (anchor ? startOfDay(anchor) : null), [anchor]);

  // Cotas UTC del rango: toISOString() de la medianoche LOCAL → instante UTC correcto.
  const weekFromIso = weekStart ? weekStart.toISOString() : "";
  const weekToIso = weekStart ? addDays(weekStart, 7).toISOString() : "";
  const dayFromIso = day ? day.toISOString() : "";
  const dayToIso = day ? addDays(day, 1).toISOString() : "";

  // ── Modo semana: citas del doctor en la semana ──
  const weekQuery = useQuery({
    queryKey: ["sched-cal-week", weekFromIso, weekToIso, doctorId],
    queryFn: () => fetchAppointmentsInRange({ fromIso: weekFromIso, toIso: weekToIso, doctorId }),
    enabled: view === "week" && !!weekStart && !!doctorId,
  });

  // ── Modo semana: huecos libres (sólo si hay producto) ──
  const freeQuery = useQuery({
    queryKey: ["sched-cal-free", weekStart ? toIsoDate(weekStart) : "", doctorId, productId],
    queryFn: () =>
      computeAvailability({
        doctor_id: doctorId as string,
        product_id: productId as string,
        from_date: toIsoDate(weekStart as Date),
        to_date: toIsoDate(addDays(weekStart as Date, 6)),
      }),
    enabled: view === "week" && !!weekStart && !!doctorId && !!productId,
  });

  // ── Modo día: todas las citas (filtrables por estado) ──
  const dayQuery = useQuery({
    queryKey: ["sched-cal-day", dayFromIso, dayToIso, statusId],
    queryFn: () => fetchAppointmentsInRange({ fromIso: dayFromIso, toIso: dayToIso, statusId }),
    enabled: view === "day" && !!day,
  });

  // ── Overlay informativo (F2): eventos externos de la sede en la semana (best-effort) ──
  // Comparte las MISMAS cotas UTC que las citas (weekFromIso/weekToIso). Solo en modo semana,
  // con sede elegida y permiso del overlay. NUNCA rompe la grilla (el backend es best-effort:
  // una conexión caída viaja en sources_health, sin 5xx).
  const externalQuery = useQuery({
    queryKey: ["sched-cal-external", weekFromIso, weekToIso, branchId],
    queryFn: () =>
      fetchExternalEvents({ branchId: branchId as string, from: weekFromIso, to: weekToIso }),
    // Requiere doctor: el grid (donde se pintan los eventos) sólo aparece con doctor elegido →
    // sin él, no consultamos (evita un fetch desperdiciado y legend/aviso sin grilla debajo).
    enabled: view === "week" && !!weekStart && !!doctorId && !!branchId && canSeeExternal,
  });

  // ── Columnas + eventos del modo semana ──
  const weekColumns = useMemo<CalendarColumn[]>(() => {
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

  // Mapa eventId → slot para recuperar el hueco en el click handler.
  const freeSlotsById = useMemo(() => {
    const map = new Map<string, AvailabilitySlot>();
    if (view === "week" && productId) {
      for (const slot of freeQuery.data?.slots ?? []) {
        map.set(`free-${slot.starts_at}-${slot.office_id}`, slot);
      }
    }
    return map;
  }, [view, productId, freeQuery.data]);

  const weekEvents = useMemo<CalendarEvent[]>(() => {
    const out: CalendarEvent[] = [];
    for (const appt of weekQuery.data ?? []) {
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
    // Huecos libres SOLO cuando hay producto elegido.
    if (productId) {
      for (const slot of freeQuery.data?.slots ?? []) {
        const startMin = localMinutesOf(slot.starts_at);
        out.push({
          id: `free-${slot.starts_at}-${slot.office_id}`,
          columnKey: localDateIsoOf(slot.starts_at),
          startMin,
          endMin: localMinutesOf(slot.ends_at),
          title: "Libre",
          subtitle: `${minutesToTime(startMin)} · ${slot.office_name}`,
          kind: "free",
        });
      }
    }
    return out;
  }, [weekQuery.data, freeQuery.data, productId]);

  // Eventos externos → CalendarEvent kind "external" (mismos helpers TZ que las citas: hora
  // local del navegador). Los all-day se OMITEN del MVP (no tienen hora de pared útil como
  // bloque horario; banda en cabecera = refinamiento diferido).
  const externalEvents = useMemo<CalendarEvent[]>(() => {
    const out: CalendarEvent[] = [];
    for (const ev of externalQuery.data?.events ?? []) {
      if (ev.all_day) continue;
      const startMin = localMinutesOf(ev.starts_at);
      // Si el evento cruza la medianoche local (termina otro día), localMinutesOf(ends_at)
      // "wrapea" (< startMin) y la grilla lo descartaría → recortarlo al fin del día (la grilla
      // lo clipa a la ventana 07:00–21:00) para que NO desaparezca.
      const endRaw = localMinutesOf(ev.ends_at);
      const sameDay = localDateIsoOf(ev.ends_at) === localDateIsoOf(ev.starts_at);
      out.push({
        id: `ext-${ev.source_id}-${ev.external_id}`,
        columnKey: localDateIsoOf(ev.starts_at),
        startMin,
        endMin: sameDay && endRaw > startMin ? endRaw : 24 * 60,
        title: ev.title,
        subtitle: minutesToTime(startMin),
        kind: "external",
        ariaLabel: `Evento externo: ${ev.title} · ${minutesToTime(startMin)}`,
      });
    }
    return out;
  }, [externalQuery.data]);

  // ── Columnas + eventos del modo día (columnas = doctores con ≥1 cita VISIBLE ese día) ──
  // Sólo las citas dentro de la ventana de la grilla (07:00–21:00): un doctor con citas
  // únicamente fuera de hora no debe aparecer como columna vacía (la grilla recorta esos
  // eventos). Limitación conocida (igual que la grilla de staff): citas fuera de la ventana
  // no se ven; las horas de clínica caen dentro.
  const visibleDayAppts = useMemo(() => {
    const startMin = CALENDAR.START_HOUR * 60;
    const endMin = CALENDAR.END_HOUR * 60;
    return (dayQuery.data ?? []).filter((appt) => {
      const s = localMinutesOf(appt.scheduled_for);
      return s < endMin && s + appt.duration_min > startMin;
    });
  }, [dayQuery.data]);

  const dayColumns = useMemo<CalendarColumn[]>(() => {
    if (!day) return [];
    const byDoctor = new Map<string, string>();
    for (const appt of visibleDayAppts) {
      if (!byDoctor.has(appt.doctor_id)) byDoctor.set(appt.doctor_id, appt.doctor_name);
    }
    const isToday = toIsoDate(day) === todayIso;
    return [...byDoctor.entries()]
      .map(([id, name]) => ({ key: id, label: name, isToday }))
      .sort((a, b) => a.label.localeCompare(b.label, "es"));
  }, [visibleDayAppts, day, todayIso]);

  const dayEvents = useMemo<CalendarEvent[]>(() => {
    const out: CalendarEvent[] = [];
    for (const appt of visibleDayAppts) {
      const startMin = localMinutesOf(appt.scheduled_for);
      out.push({
        id: appt.id,
        columnKey: appt.doctor_id,
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
  }, [visibleDayAppts]);

  // En semana, los eventos externos se concatenan a las citas/huecos (capa aditiva). Memoizado
  // y ANTES del early-return de abajo (Rules of Hooks); evita invalidar el layout interno de
  // CalendarGrid en cada render. No depende de weekStart/day (solo de los memos ya computados).
  const events = useMemo<CalendarEvent[]>(
    () => (view === "week" ? [...weekEvents, ...externalEvents] : dayEvents),
    [view, weekEvents, externalEvents, dayEvents],
  );

  // ── Click sobre un evento: cita → detalle; hueco → reserva rápida ──
  const handleEventClick = (event: CalendarEvent) => {
    if (event.kind === "external") return; // capa informativa: no abre detalle ni reserva
    if (event.kind === "appointment") {
      setDetailId(event.id);
      return;
    }
    const slot = freeSlotsById.get(event.id);
    if (slot && productId) {
      setQuickBook({
        slot,
        productId,
        productName: products.find((p) => p.id === productId)?.name ?? "",
      });
    }
  };

  // ── Navegación del período (en hora local) ──
  const goPrev = () => {
    if (!anchor) return;
    setAnchor(addDays(anchor, view === "week" ? -7 : -1));
  };
  const goNext = () => {
    if (!anchor) return;
    setAnchor(addDays(anchor, view === "week" ? 7 : 1));
  };
  const goToday = () => setAnchor(new Date());

  // Spinner mientras no hay anchor (evita el hydration mismatch de TZ).
  if (!anchor || !weekStart || !day) {
    return (
      <div className={styles.root}>
        <header className={styles.header}>
          <h1 className={styles.title}>Calendario</h1>
        </header>
        <div className={styles.centerRow}>
          <Spinner label="Cargando calendario…" />
        </div>
      </div>
    );
  }

  // ── Datos del modo activo para los estados loading/error/grilla ──
  const activeQuery = view === "week" ? weekQuery : dayQuery;
  const periodLabel = view === "week" ? formatWeekRange(weekStart) : formatDayLabel(day);
  const columns = view === "week" ? weekColumns : dayColumns;

  // Línea de "ahora": sólo si el día de hoy es una columna visible.
  const nowIndicator =
    nowMin !== null && todayIso && columns.some((c) => c.key === todayIso)
      ? { columnKey: todayIso, min: nowMin }
      : null;

  const needsDoctor = view === "week" && !doctorId;
  const selectedDoctorName = doctors.find((d) => d.id === doctorId)?.full_name ?? "";
  const selectedProductName = products.find((p) => p.id === productId)?.name ?? "";
  const selectedStatusName = statuses.find((s) => s.id === statusId)?.name ?? "";
  const selectedBranchName = branches.find((b) => b.id === branchId)?.name ?? "";
  // Overlay activo (semana + sede + permiso): controla legend, aviso de salud y la query.
  // Requiere doctor también: la legend/aviso sólo cuando el grid (con los eventos) está en pantalla.
  const overlayActive = view === "week" && canSeeExternal && !!doctorId && !!branchId;
  // El marcador CANÓNICO de fallo es `error` (None = OK), no `status`: un fallo de lectura
  // (CALENDAR_READ_FAILED / provider 5xx) deja status="connected" + error=code → hay que mirar
  // `error` o el aviso nunca saldría para el modo de fallo más común (rompería la mitad UI de §23).
  const externalHealthWarn =
    overlayActive &&
    (externalQuery.data?.sources_health ?? []).some(
      (h) => h.error != null || h.status !== "connected",
    );

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Calendario</h1>
        <p className={styles.subtitle}>
          Vista semanal por doctor o vista diaria con todos los doctores.
        </p>
      </header>

      <TabList selectedValue={view} onTabSelect={(_, d) => setView(d.value as ViewMode)}>
        <Tab value="week">Semana</Tab>
        <Tab value="day">Día</Tab>
      </TabList>

      <div className={styles.toolbar}>
        {view === "week" ? (
          <>
            <Dropdown
              className={styles.filter}
              placeholder="Seleccionar doctor"
              value={selectedDoctorName}
              selectedOptions={doctorId ? [doctorId] : []}
              onOptionSelect={(_, d) => setDoctorId(d.optionValue || null)}
            >
              {doctors.map((dc) => (
                <Option key={dc.id} value={dc.id}>
                  {dc.full_name}
                </Option>
              ))}
            </Dropdown>
            <Dropdown
              className={styles.filter}
              placeholder="Mostrar huecos libres de…"
              value={selectedProductName}
              selectedOptions={productId ? [productId] : []}
              onOptionSelect={(_, d) => setProductId(d.optionValue || null)}
            >
              <Option value="">Sin huecos libres</Option>
              {products.map((p) => (
                <Option key={p.id} value={p.id}>
                  {p.name}
                </Option>
              ))}
            </Dropdown>
            {canSeeExternal ? (
              <Dropdown
                className={styles.filter}
                placeholder="Calendarios externos: sede…"
                value={selectedBranchName}
                selectedOptions={branchId ? [branchId] : []}
                onOptionSelect={(_, d) => setBranchId(d.optionValue || null)}
              >
                <Option value="">Sin calendarios externos</Option>
                {branches.map((b) => (
                  <Option key={b.id} value={b.id}>
                    {b.name}
                  </Option>
                ))}
              </Dropdown>
            ) : null}
          </>
        ) : (
          <Dropdown
            className={styles.filter}
            placeholder="Todos los estados"
            value={selectedStatusName}
            selectedOptions={statusId ? [statusId] : []}
            onOptionSelect={(_, d) => setStatusId(d.optionValue || null)}
          >
            <Option value="">Todos los estados</Option>
            {statuses.map((s) => (
              <Option key={s.id} value={s.id}>
                {s.name}
              </Option>
            ))}
          </Dropdown>
        )}
        <span className={styles.spacer} />
        <PeriodNavigator
          label={periodLabel}
          prevLabel={view === "week" ? "Semana anterior" : "Día anterior"}
          nextLabel={view === "week" ? "Semana siguiente" : "Día siguiente"}
          onPrev={goPrev}
          onNext={goNext}
          onToday={goToday}
        />
      </div>

      {overlayActive ? (
        <div className={styles.legend}>
          <span className={styles.legendItem}>
            <span className={mergeClasses(styles.swatch, styles.swatchAppt)} /> Cita medisage
          </span>
          <span className={styles.legendItem}>
            <span className={mergeClasses(styles.swatch, styles.swatchExternal)} /> Evento externo
          </span>
          <span className={styles.legendItem}>
            <span className={mergeClasses(styles.swatch, styles.swatchFree)} /> Horario libre
          </span>
        </div>
      ) : null}

      {externalHealthWarn ? (
        <MessageBar intent="warning">
          <MessageBarBody>
            Algunos calendarios externos no se pudieron leer. Revisa la conexión en Calendarios
            externos.
          </MessageBarBody>
          <MessageBarActions
            containerAction={
              <Button
                appearance="transparent"
                size="small"
                onClick={() => void externalQuery.refetch()}
              >
                Reintentar
              </Button>
            }
          />
        </MessageBar>
      ) : null}

      {needsDoctor ? (
        <div className={styles.placeholder}>Elegí un doctor para ver su semana.</div>
      ) : activeQuery.isError ? (
        <MessageBar intent="error">
          <MessageBarBody>
            No se pudieron cargar las citas. Intenta de nuevo más tarde.
          </MessageBarBody>
        </MessageBar>
      ) : activeQuery.isPending ? (
        <div className={styles.centerRow}>
          <Spinner label="Cargando citas…" />
        </div>
      ) : columns.length === 0 ? (
        <div className={styles.placeholder}>
          {view === "day" ? "No hay citas este día." : "No hay citas esta semana."}
        </div>
      ) : (
        <CalendarGrid
          columns={columns}
          events={events}
          onEventClick={handleEventClick}
          nowIndicator={nowIndicator}
        />
      )}

      {detailId ? (
        <AppointmentDetailDrawer
          appointmentId={detailId}
          onClose={() => setDetailId(null)}
          onChanged={() => {
            void weekQuery.refetch();
            void dayQuery.refetch();
            // El cambio puede liberar/ocupar un slot → refrescar también los huecos libres.
            void freeQuery.refetch();
          }}
          doctors={doctors}
          branches={branches}
          products={products}
        />
      ) : null}

      {quickBook ? (
        <QuickBookDrawer
          slot={quickBook.slot}
          productId={quickBook.productId}
          productName={quickBook.productName}
          onClose={() => setQuickBook(null)}
          onBooked={() => {
            setQuickBook(null);
            void weekQuery.refetch();
            void freeQuery.refetch();
          }}
        />
      ) : null}
    </div>
  );
}
