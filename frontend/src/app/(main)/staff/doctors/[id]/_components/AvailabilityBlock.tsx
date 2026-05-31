"use client";

import { makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import { memo } from "react";

import type { DoctorAvailabilityItem } from "@/types/staff.types";

const useStyles = makeStyles({
  block: {
    position: "absolute",
    left: "2px",
    right: "2px",
    boxSizing: "border-box",
    borderRadius: tokens.borderRadiusSmall,
    padding: `2px ${tokens.spacingHorizontalXS}`,
    overflow: "hidden",
    border: `1px solid ${tokens.colorBrandStroke1}`,
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorNeutralForeground1,
    display: "flex",
    flexDirection: "column",
    gap: "1px",
    textAlign: "left",
    cursor: "default",
    minHeight: 0,
  },
  clickable: {
    cursor: "pointer",
    ":hover": { backgroundColor: tokens.colorBrandBackground2Hover },
  },
  selected: {
    outline: `2px solid ${tokens.colorBrandStroke1}`,
    outlineOffset: "-1px",
  },
  time: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  office: {
    fontSize: tokens.fontSizeBase100,
    color: tokens.colorNeutralForeground3,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
});

interface Props {
  block: DoctorAvailabilityItem;
  top: number;
  height: number;
  canWrite: boolean;
  selected: boolean;
  onSelect: (block: DoctorAvailabilityItem) => void;
}

// Un bloque pintado en la grilla. Muestra el rango horario + consultorio. Click →
// selecciona (abre el editor/borrado) cuando canWrite.
// TODO (F2.2 drag): los bordes (resize) y el cuerpo (mover de día/hora) serán
// arrastrables; aquí sólo hay click-para-seleccionar.
function AvailabilityBlockBase({ block, top, height, canWrite, selected, onSelect }: Props) {
  const styles = useStyles();
  const opens = block.opens_at.slice(0, 5);
  const closes = block.closes_at.slice(0, 5);
  const label = `${opens}–${closes} · ${block.office_code}`;

  const className = mergeClasses(
    styles.block,
    canWrite && styles.clickable,
    selected && styles.selected,
  );

  const content = (
    <>
      <span className={styles.time}>
        {opens}–{closes}
      </span>
      <span className={styles.office}>
        {block.office_code} · {block.office_name}
      </span>
    </>
  );

  if (!canWrite) {
    return (
      <div className={className} style={{ top, height }} aria-label={label}>
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      className={className}
      style={{ top, height }}
      aria-label={`Editar bloque ${label}`}
      onClick={() => onSelect(block)}
    >
      {content}
    </button>
  );
}

export const AvailabilityBlock = memo(AvailabilityBlockBase);
