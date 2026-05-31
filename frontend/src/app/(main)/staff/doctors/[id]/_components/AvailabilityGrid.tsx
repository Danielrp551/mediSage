"use client";

import { makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import { useCallback, useMemo } from "react";

import { CALENDAR, WEEKDAY_LABELS, minutesToTime, timeToMinutes } from "@/lib/constants/calendar";
import { appTokens, brandPalette } from "@/lib/theme/brand";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import { AvailabilityBlock } from "./AvailabilityBlock";
import { addDays, toIsoDate } from "./week";

const TIME_COL_WIDTH = "56px";
const HEADER_HEIGHT = "40px";

const useStyles = makeStyles({
  root: {
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusMedium,
    overflow: "hidden",
    backgroundColor: appTokens.chromeBg,
  },
  header: {
    display: "grid",
    gridTemplateColumns: `${TIME_COL_WIDTH} repeat(7, 1fr)`,
    borderBottom: `1px solid ${appTokens.tableBorder}`,
  },
  headerCell: {
    height: HEADER_HEIGHT,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    borderLeft: `1px solid ${appTokens.tableBorder}`,
  },
  headerToday: { color: brandPalette.primary, fontWeight: tokens.fontWeightSemibold },
  headerCorner: { height: HEADER_HEIGHT },
  body: {
    display: "grid",
    gridTemplateColumns: `${TIME_COL_WIDTH} repeat(7, 1fr)`,
  },
  timeCol: { display: "flex", flexDirection: "column" },
  timeLabel: {
    position: "relative",
    fontSize: tokens.fontSizeBase100,
    color: appTokens.chromeTextMuted,
    textAlign: "right",
    paddingRight: tokens.spacingHorizontalXS,
    top: "-6px",
  },
  dayCol: {
    position: "relative",
    borderLeft: `1px solid ${appTokens.tableBorder}`,
  },
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
    ":hover": { backgroundColor: tokens.colorNeutralBackground1Hover },
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

  const startMin = CALENDAR.START_HOUR * 60;
  const endMin = CALENDAR.END_HOUR * 60;
  const totalMinutes = endMin - startMin;
  const pxPerMin = CALENDAR.HOUR_HEIGHT_PX / 60;
  const bodyHeight = totalMinutes * pxPerMin;

  // Columnas de la semana (Lun..Dom). Cada una con su Date local + "YYYY-MM-DD".
  const columns = useMemo(() => {
    const today = toIsoDate(new Date());
    return WEEKDAY_LABELS.map((label, i) => {
      const date = addDays(weekStart, i);
      const iso = toIsoDate(date);
      return { label, date, iso, dayOfMonth: dayNum.format(date), isToday: iso === today };
    });
  }, [weekStart]);

  // Líneas horarias (una por hora visible).
  const hours = useMemo(() => {
    const out: number[] = [];
    for (let h = CALENDAR.START_HOUR; h < CALENDAR.END_HOUR; h++) out.push(h);
    return out;
  }, []);

  // Bloques posicionados, agrupados por fecha. Memoizado: sólo recalcula cuando
  // cambian los bloques o la ventana. top/height en px relativos a START_HOUR.
  const positionedByDate = useMemo(() => {
    const map = new Map<string, { block: DoctorAvailabilityItem; top: number; height: number }[]>();
    for (const block of Object.values(blocks)) {
      const opens = timeToMinutes(block.opens_at);
      const closes = timeToMinutes(block.closes_at);
      // Recorta a la ventana visible para que un bloque fuera de rango no rompa el layout.
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
          <div
            key={col.iso}
            className={mergeClasses(styles.headerCell, col.isToday && styles.headerToday)}
          >
            <span>{col.label}</span>
            <span>{col.dayOfMonth}</span>
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
            <div key={col.iso} className={styles.dayCol} style={{ height: bodyHeight }}>
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
