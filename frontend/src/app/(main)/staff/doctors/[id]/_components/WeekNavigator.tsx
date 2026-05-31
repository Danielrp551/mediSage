"use client";

import { Button, makeStyles, tokens } from "@fluentui/react-components";
import { ChevronLeftRegular, ChevronRightRegular } from "@fluentui/react-icons";
import { useMemo } from "react";

import { appTokens } from "@/lib/theme/brand";

import { addDays } from "./week";

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  range: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    minWidth: "180px",
  },
});

const dayMonth = new Intl.DateTimeFormat("es-PE", { day: "numeric", month: "short" });
const dayMonthYear = new Intl.DateTimeFormat("es-PE", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

// Compone "2–8 jun 2026" (o "29 may – 4 jun 2026" si cruza de mes) a partir del
// lunes de la semana visible. Se trabaja en hora local; no usa los bloques.
function formatRange(weekStart: Date): string {
  const weekEnd = addDays(weekStart, 6);
  const sameMonth =
    weekStart.getMonth() === weekEnd.getMonth() &&
    weekStart.getFullYear() === weekEnd.getFullYear();
  if (sameMonth) {
    // "2–8 jun 2026": día del lunes + rango del domingo con mes/año.
    return `${weekStart.getDate()}–${dayMonthYear.format(weekEnd)}`;
  }
  return `${dayMonth.format(weekStart)} – ${dayMonthYear.format(weekEnd)}`;
}

interface Props {
  weekStart: Date;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}

export function WeekNavigator({ weekStart, onPrev, onNext, onToday }: Props) {
  const styles = useStyles();
  const range = useMemo(() => formatRange(weekStart), [weekStart]);

  return (
    <div className={styles.root}>
      <Button
        appearance="subtle"
        icon={<ChevronLeftRegular />}
        aria-label="Semana anterior"
        onClick={onPrev}
      />
      <span className={styles.range}>{range}</span>
      <Button
        appearance="subtle"
        icon={<ChevronRightRegular />}
        aria-label="Semana siguiente"
        onClick={onNext}
      />
      <Button appearance="secondary" size="small" onClick={onToday}>
        Hoy
      </Button>
    </div>
  );
}
