"use client";

import { Button, makeStyles, tokens } from "@fluentui/react-components";
import { ChevronLeftRegular, ChevronRightRegular } from "@fluentui/react-icons";

import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  label: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    minWidth: "180px",
  },
});

interface Props {
  label: string; // rango ya compuesto por el cliente (ej. "2–8 jun 2026" o "lun 2 jun 2026")
  prevLabel: string; // aria-label del botón anterior
  nextLabel: string; // aria-label del botón siguiente
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
}

// Navegador genérico de período (semana o día): ‹ [rango] › + "Hoy". El cómputo del
// rango y de los saltos lo hace el cliente (en hora local).
export function PeriodNavigator({ label, prevLabel, nextLabel, onPrev, onNext, onToday }: Props) {
  const styles = useStyles();
  return (
    <div className={styles.root}>
      <Button
        appearance="subtle"
        icon={<ChevronLeftRegular />}
        aria-label={prevLabel}
        onClick={onPrev}
      />
      <span className={styles.label}>{label}</span>
      <Button
        appearance="subtle"
        icon={<ChevronRightRegular />}
        aria-label={nextLabel}
        onClick={onNext}
      />
      <Button appearance="secondary" size="small" onClick={onToday}>
        Hoy
      </Button>
    </div>
  );
}
