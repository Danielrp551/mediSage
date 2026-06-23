"use client";

import { makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import { useMemo } from "react";

import { CALENDAR, minutesToTime } from "@/lib/constants/calendar";
import { layoutOverlaps } from "@/lib/utils/calendarWeek";
import { appTokens, brandPalette } from "@/lib/theme/brand";

const TIME_COL_WIDTH = "56px";
const HEADER_HEIGHT = "52px";
const COL_MIN_WIDTH = "120px";
const TODAY_TINT = "rgba(27, 122, 143, 0.06)";

// Una columna de la grilla: un día (modo semana) o un doctor (modo día·todos).
export interface CalendarColumn {
  key: string;
  label: string; // línea 1 del encabezado (ej. "Lun" o el nombre del doctor)
  sublabel?: string; // línea 2 (ej. "12" día del mes)
  isToday?: boolean;
  isWeekend?: boolean;
}

// Un evento posicionable: una cita o un hueco libre. startMin/endMin son minutos LOCALES
// desde medianoche (los calcula el cliente desde scheduled_for/starts_at, ver calendarWeek).
export interface CalendarEvent {
  id: string;
  columnKey: string;
  startMin: number;
  endMin: number;
  title: string;
  subtitle?: string;
  color?: string | null; // color del estado (cita); ignorado en huecos libres y externos
  kind: "appointment" | "free" | "external";
  // Etiqueta accesible completa (incluye el estado en las citas, que el badge de color no
  // transmite a lectores de pantalla). Si falta, se compone una básica con title+subtitle.
  ariaLabel?: string;
}

interface Props {
  columns: CalendarColumn[];
  events: CalendarEvent[];
  onEventClick: (event: CalendarEvent) => void;
  // Línea de "ahora" (minutos locales) en la columna indicada; lo calcula el cliente
  // client-only para no desfasar en SSR.
  nowIndicator?: { columnKey: string; min: number } | null;
}

const useStyles = makeStyles({
  scroll: { overflowX: "auto" },
  root: {
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    overflow: "hidden",
    backgroundColor: appTokens.chromeBg,
    boxShadow: tokens.shadow4,
  },
  header: {
    display: "grid",
    backgroundColor: appTokens.tableHeaderBg,
    borderBottom: `1px solid ${appTokens.tableBorder}`,
  },
  headerCorner: { height: HEADER_HEIGHT },
  headerCell: {
    height: HEADER_HEIGHT,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: "2px",
    borderLeft: `1px solid ${appTokens.tableBorder}`,
    paddingLeft: tokens.spacingHorizontalXS,
    paddingRight: tokens.spacingHorizontalXS,
    minWidth: 0,
  },
  headerLabel: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    color: appTokens.chromeTextMuted,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: "100%",
  },
  headerWeekendLabel: { color: tokens.colorPaletteRedForeground1 },
  headerLabelToday: { color: brandPalette.primary },
  headerSub: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    lineHeight: "1",
  },
  headerSubToday: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: "26px",
    height: "26px",
    paddingLeft: "4px",
    paddingRight: "4px",
    borderRadius: tokens.borderRadiusCircular,
    backgroundColor: brandPalette.primary,
    color: tokens.colorNeutralForegroundOnBrand,
  },
  body: { display: "grid" },
  timeCol: {
    display: "flex",
    flexDirection: "column",
    backgroundColor: appTokens.tableHeaderBg,
  },
  timeLabel: {
    position: "relative",
    top: "-7px",
    fontSize: tokens.fontSizeBase100,
    color: appTokens.chromeTextMuted,
    textAlign: "right",
    paddingRight: tokens.spacingHorizontalS,
    fontVariantNumeric: "tabular-nums",
  },
  col: {
    position: "relative",
    borderLeft: `1px solid ${appTokens.tableBorder}`,
    minWidth: 0,
  },
  colWeekend: { backgroundColor: appTokens.tableRowStripe },
  colToday: { backgroundColor: TODAY_TINT },
  hourCell: {
    boxSizing: "border-box",
    borderTop: `1px solid ${tokens.colorNeutralStroke3}`,
  },
  event: {
    position: "absolute",
    boxSizing: "border-box",
    borderRadius: tokens.borderRadiusSmall,
    padding: `2px ${tokens.spacingHorizontalXS}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    gap: "1px",
    textAlign: "left",
    cursor: "pointer",
    minHeight: 0,
    border: "none",
    transitionProperty: "filter, background-color",
    transitionDuration: tokens.durationFaster,
    ":hover": { filter: "brightness(0.95)" },
  },
  // Cita: fondo lleno (color del estado), texto sobre marca.
  eventAppointment: { color: tokens.colorNeutralForegroundOnBrand },
  // Hueco libre: contorno punteado de marca, fondo tenue.
  eventFree: {
    border: `1px dashed ${tokens.colorBrandStroke1}`,
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground1,
    ":hover": { backgroundColor: tokens.colorBrandBackground2Hover },
  },
  // Evento externo (overlay informativo, F2): capa visualmente DISTINTA — rayado diagonal
  // tenue neutral (ni color de estado ni marca) → se lee como "ajeno". NO clicable para reservar.
  eventExternal: {
    backgroundColor: tokens.colorNeutralBackground3,
    backgroundImage: `repeating-linear-gradient(45deg, ${tokens.colorNeutralStroke2}, ${tokens.colorNeutralStroke2} 1px, transparent 1px, transparent 7px)`,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    color: tokens.colorNeutralForeground2,
    cursor: "default",
    ":hover": { filter: "none" },
  },
  eventTitle: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  eventSub: {
    fontSize: tokens.fontSizeBase100,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    opacity: 0.9,
  },
  nowLine: {
    position: "absolute",
    left: 0,
    right: 0,
    height: "2px",
    backgroundColor: brandPalette.primary,
    zIndex: 1,
    pointerEvents: "none",
  },
  nowDot: {
    position: "absolute",
    left: "-3px",
    top: "-3px",
    width: "8px",
    height: "8px",
    borderRadius: tokens.borderRadiusCircular,
    backgroundColor: brandPalette.primary,
  },
});

export function CalendarGrid({ columns, events, onEventClick, nowIndicator }: Props) {
  const styles = useStyles();

  const startMin = CALENDAR.START_HOUR * 60;
  const endMin = CALENDAR.END_HOUR * 60;
  const pxPerMin = CALENDAR.HOUR_HEIGHT_PX / 60;
  const bodyHeight = (endMin - startMin) * pxPerMin;

  const hours = useMemo(() => {
    const out: number[] = [];
    for (let h = CALENDAR.START_HOUR; h < CALENDAR.END_HOUR; h++) out.push(h);
    return out;
  }, []);

  // Eventos agrupados por columna y con carriles (lanes) de solapamiento ya asignados.
  const positionedByColumn = useMemo(() => {
    const byCol = new Map<string, CalendarEvent[]>();
    for (const ev of events) {
      const arr = byCol.get(ev.columnKey);
      if (arr) arr.push(ev);
      else byCol.set(ev.columnKey, [ev]);
    }
    const out = new Map<
      string,
      { event: CalendarEvent; top: number; height: number; lane: number; lanes: number }[]
    >();
    for (const [key, list] of byCol) {
      const laid = layoutOverlaps(list);
      const positioned = laid
        .map(({ event, lane, lanes }) => {
          const visTop = Math.max(event.startMin, startMin);
          const visBottom = Math.min(event.endMin, endMin);
          if (visBottom <= visTop) return null;
          return {
            event,
            top: (visTop - startMin) * pxPerMin,
            height: (visBottom - visTop) * pxPerMin,
            lane,
            lanes,
          };
        })
        .filter((x): x is NonNullable<typeof x> => x !== null);
      out.set(key, positioned);
    }
    return out;
  }, [events, startMin, endMin, pxPerMin]);

  const gridTemplate = `${TIME_COL_WIDTH} repeat(${columns.length}, minmax(${COL_MIN_WIDTH}, 1fr))`;

  return (
    <div className={styles.scroll}>
      <div className={styles.root}>
        <div className={styles.header} style={{ gridTemplateColumns: gridTemplate }}>
          <div className={styles.headerCorner} />
          {columns.map((col) => (
            <div key={col.key} className={styles.headerCell} title={col.label}>
              <span
                className={mergeClasses(
                  styles.headerLabel,
                  col.isWeekend && styles.headerWeekendLabel,
                  col.isToday && styles.headerLabelToday,
                )}
              >
                {col.label}
              </span>
              {col.sublabel ? (
                <span
                  className={mergeClasses(styles.headerSub, col.isToday && styles.headerSubToday)}
                >
                  {col.sublabel}
                </span>
              ) : null}
            </div>
          ))}
        </div>

        <div className={styles.body} style={{ gridTemplateColumns: gridTemplate }}>
          <div className={styles.timeCol}>
            {hours.map((h) => (
              <div key={h} style={{ height: CALENDAR.HOUR_HEIGHT_PX }}>
                <div className={styles.timeLabel}>{minutesToTime(h * 60)}</div>
              </div>
            ))}
          </div>

          {columns.map((col) => {
            const positioned = positionedByColumn.get(col.key) ?? [];
            const showNow =
              nowIndicator &&
              nowIndicator.columnKey === col.key &&
              nowIndicator.min >= startMin &&
              nowIndicator.min <= endMin;
            return (
              <div
                key={col.key}
                className={mergeClasses(
                  styles.col,
                  col.isWeekend && styles.colWeekend,
                  col.isToday && styles.colToday,
                )}
                style={{ height: bodyHeight }}
              >
                {hours.map((h) => (
                  <div
                    key={h}
                    className={styles.hourCell}
                    style={{ height: CALENDAR.HOUR_HEIGHT_PX }}
                  />
                ))}

                {showNow ? (
                  <div
                    className={styles.nowLine}
                    style={{ top: (nowIndicator.min - startMin) * pxPerMin }}
                  >
                    <span className={styles.nowDot} />
                  </div>
                ) : null}

                {positioned.map(({ event, top, height, lane, lanes }) => {
                  const widthPct = 100 / lanes;
                  const isFree = event.kind === "free";
                  const isExternal = event.kind === "external";
                  const kindClass = isFree
                    ? styles.eventFree
                    : isExternal
                      ? styles.eventExternal
                      : styles.eventAppointment;
                  return (
                    <button
                      key={event.id}
                      type="button"
                      className={mergeClasses(styles.event, kindClass)}
                      style={{
                        top,
                        height,
                        left: `calc(${lane * widthPct}% + 2px)`,
                        width: `calc(${widthPct}% - 4px)`,
                        // Color del estado SOLO en citas (huecos y externos llevan estilo de clase).
                        ...(event.kind === "appointment"
                          ? { backgroundColor: event.color ?? tokens.colorNeutralBackground3 }
                          : {}),
                      }}
                      aria-label={
                        event.ariaLabel ??
                        (isFree
                          ? `Reservar ${event.subtitle ?? ""} ${event.title}`.trim()
                          : `${event.title} ${event.subtitle ?? ""}`.trim())
                      }
                      // Externo = informativo: NO abre reserva/detalle (la capa no es accionable).
                      onClick={() => {
                        if (!isExternal) onEventClick(event);
                      }}
                    >
                      <span className={styles.eventTitle}>{event.title}</span>
                      {event.subtitle ? (
                        <span className={styles.eventSub}>{event.subtitle}</span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
