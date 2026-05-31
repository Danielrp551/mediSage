"use client";

import { makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import { useCallback, useEffect, useMemo, useState } from "react";

import { CALENDAR, WEEKDAY_LABELS, minutesToTime, timeToMinutes } from "@/lib/constants/calendar";
import { appTokens, brandPalette } from "@/lib/theme/brand";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import { AvailabilityBlock } from "./AvailabilityBlock";
import { addDays, toIsoDate } from "./week";

const TIME_COL_WIDTH = "60px";
const HEADER_HEIGHT = "52px";
// Tinte muy tenue de marca para la columna de "hoy" (sobre fondo blanco).
const TODAY_TINT = "rgba(27, 122, 143, 0.06)";

const useStyles = makeStyles({
  root: {
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    overflow: "hidden",
    backgroundColor: appTokens.chromeBg,
    boxShadow: tokens.shadow4,
  },
  header: {
    display: "grid",
    gridTemplateColumns: `${TIME_COL_WIDTH} repeat(7, minmax(0, 1fr))`,
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
  },
  headerWeekday: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    color: appTokens.chromeTextMuted,
  },
  headerDay: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    lineHeight: "1",
  },
  headerWeekendLabel: { color: tokens.colorPaletteRedForeground1 },
  // "Hoy": el número del día va en un círculo de marca.
  headerDayToday: {
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
  headerWeekdayToday: { color: brandPalette.primary },
  body: {
    display: "grid",
    gridTemplateColumns: `${TIME_COL_WIDTH} repeat(7, minmax(0, 1fr))`,
  },
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
  dayCol: {
    position: "relative",
    borderLeft: `1px solid ${appTokens.tableBorder}`,
  },
  dayColWeekend: { backgroundColor: appTokens.tableRowStripe },
  dayColToday: { backgroundColor: TODAY_TINT },
  hourCell: {
    boxSizing: "border-box",
    borderTop: `1px solid ${tokens.colorNeutralStroke3}`,
    margin: 0,
    padding: 0,
    width: "100%",
    background: "transparent",
    display: "block",
  },
  hourCellClickable: {
    cursor: "pointer",
    transitionProperty: "background-color",
    transitionDuration: tokens.durationFaster,
    ":hover": { backgroundColor: tokens.colorBrandBackground2Hover },
  },
});

interface Props {
  weekStart: Date;
  blocks: Record<string, DoctorAvailabilityItem>;
  canWrite: boolean;
  selectedBlockId: string | null;
  onCreateAt: (dateIso: string, hhmm: string) => void;
  onSelectBlock: (block: DoctorAvailabilityItem) => void;
}

const dayNum = new Intl.DateTimeFormat("es-PE", { day: "numeric" });

export function AvailabilityGrid({
  weekStart,
  blocks,
  canWrite,
  selectedBlockId,
  onCreateAt,
  onSelectBlock,
}: Props) {
  const styles = useStyles();

  // "Hoy" se calcula SOLO en cliente tras montar: `new Date()` en SSR corre en la
  // TZ del servidor (UTC), que de noche en Lima (UTC-5) ya está en el día siguiente
  // → resaltaría el día equivocado. Con el guard de montaje, en SSR no se resalta
  // nada (sin hydration mismatch) y en cliente se usa la fecha local real.
  const [todayIso, setTodayIso] = useState<string | null>(null);
  useEffect(() => {
    setTodayIso(toIsoDate(new Date()));
  }, []);

  const startMin = CALENDAR.START_HOUR * 60;
  const endMin = CALENDAR.END_HOUR * 60;
  const pxPerMin = CALENDAR.HOUR_HEIGHT_PX / 60;
  const bodyHeight = (endMin - startMin) * pxPerMin;

  // Columnas de la semana (Lun..Dom). Cada una con su Date local + "YYYY-MM-DD".
  const columns = useMemo(() => {
    return WEEKDAY_LABELS.map((label, i) => {
      const date = addDays(weekStart, i);
      const iso = toIsoDate(date);
      return {
        label,
        iso,
        dayOfMonth: dayNum.format(date),
        isToday: iso === todayIso,
        isWeekend: i >= 5, // Sáb (5), Dom (6)
      };
    });
  }, [weekStart, todayIso]);

  // Líneas horarias (una por hora visible).
  const hours = useMemo(() => {
    const out: number[] = [];
    for (let h = CALENDAR.START_HOUR; h < CALENDAR.END_HOUR; h++) out.push(h);
    return out;
  }, []);

  // Bloques posicionados, agrupados por fecha. top/height en px relativos a START_HOUR.
  const positionedByDate = useMemo(() => {
    const map = new Map<string, { block: DoctorAvailabilityItem; top: number; height: number }[]>();
    for (const block of Object.values(blocks)) {
      const opens = timeToMinutes(block.opens_at);
      const closes = timeToMinutes(block.closes_at);
      const visTop = Math.max(opens, startMin);
      const visBottom = Math.min(closes, endMin);
      if (visBottom <= visTop) continue;
      const top = (visTop - startMin) * pxPerMin;
      const height = (visBottom - visTop) * pxPerMin;
      const arr = map.get(block.date) ?? [];
      arr.push({ block, top, height });
      map.set(block.date, arr);
    }
    return map;
  }, [blocks, startMin, endMin, pxPerMin]);

  const handleCellClick = useCallback(
    (dateIso: string, hour: number) => {
      if (!canWrite) return;
      onCreateAt(dateIso, minutesToTime(hour * 60));
    },
    [canWrite, onCreateAt],
  );

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <div className={styles.headerCorner} />
        {columns.map((col) => (
          <div key={col.iso} className={styles.headerCell}>
            <span
              className={mergeClasses(
                styles.headerWeekday,
                col.isWeekend && styles.headerWeekendLabel,
                col.isToday && styles.headerWeekdayToday,
              )}
            >
              {col.label}
            </span>
            <span className={mergeClasses(styles.headerDay, col.isToday && styles.headerDayToday)}>
              {col.dayOfMonth}
            </span>
          </div>
        ))}
      </div>

      <div className={styles.body}>
        <div className={styles.timeCol}>
          {hours.map((h) => (
            <div key={h} style={{ height: CALENDAR.HOUR_HEIGHT_PX }}>
              <div className={styles.timeLabel}>{minutesToTime(h * 60)}</div>
            </div>
          ))}
        </div>

        {columns.map((col) => {
          const positioned = positionedByDate.get(col.iso) ?? [];
          return (
            <div
              key={col.iso}
              className={mergeClasses(
                styles.dayCol,
                col.isWeekend && styles.dayColWeekend,
                col.isToday && styles.dayColToday,
              )}
              style={{ height: bodyHeight }}
            >
              {hours.map((h) =>
                canWrite ? (
                  <button
                    key={h}
                    type="button"
                    className={mergeClasses(styles.hourCell, styles.hourCellClickable)}
                    style={{ height: CALENDAR.HOUR_HEIGHT_PX }}
                    aria-label={`Agregar bloque ${col.label} ${col.dayOfMonth} a las ${minutesToTime(h * 60)}`}
                    onClick={() => handleCellClick(col.iso, h)}
                  />
                ) : (
                  <div
                    key={h}
                    className={styles.hourCell}
                    style={{ height: CALENDAR.HOUR_HEIGHT_PX }}
                  />
                ),
              )}
              {positioned.map(({ block, top, height }) => (
                <AvailabilityBlock
                  key={block.id}
                  block={block}
                  top={top}
                  height={height}
                  canWrite={canWrite}
                  selected={block.id === selectedBlockId}
                  onSelect={onSelectBlock}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
