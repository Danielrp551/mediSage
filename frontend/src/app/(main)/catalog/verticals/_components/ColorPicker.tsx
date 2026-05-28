"use client";

/**
 * Vertical colour picker — popover with a curated palette + a manual hex
 * input. The curated palette is the single source of truth in
 * `lib/constants/catalog-iconography.ts`.
 *
 * Stores values uppercase `#RRGGBB`. The Zod schema accepts both cases
 * (HEX_COLOR_REGEX is case-insensitive), but we normalise to upper here
 * for visual consistency with what the backend returns.
 */

import {
  Button,
  Input,
  Popover,
  PopoverSurface,
  PopoverTrigger,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useState } from "react";

import { VERTICAL_COLOR_PALETTE } from "@/lib/constants/catalog-iconography";
import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  trigger: {
    minWidth: "130px",
    justifyContent: "flex-start",
    gap: tokens.spacingHorizontalS,
  },
  swatch: {
    display: "inline-block",
    width: "14px",
    height: "14px",
    borderRadius: tokens.borderRadiusCircular,
    border: `1px solid ${appTokens.chromeBorder}`,
  },
  swatchEmpty: {
    background: "transparent",
    border: `1px dashed ${appTokens.chromeBorder}`,
  },
  swatchSelected: {
    boxShadow: `0 0 0 2px ${tokens.colorBrandStroke1}`,
  },
  surface: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingHorizontalS,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(6, 28px)",
    gap: tokens.spacingHorizontalXS,
  },
  paletteButton: {
    width: "28px",
    height: "28px",
    borderRadius: tokens.borderRadiusCircular,
    border: `1px solid ${appTokens.chromeBorder}`,
    cursor: "pointer",
    padding: 0,
    transition: "transform 80ms ease",
    "&:hover": { transform: "scale(1.08)" },
  },
  hexInput: { marginTop: tokens.spacingVerticalXS },
});

interface Props {
  value: string | null;
  onChange: (next: string | null) => void;
  disabled?: boolean;
  ariaLabel?: string;
}

export function ColorPicker({ value, onChange, disabled, ariaLabel }: Props) {
  const styles = useStyles();
  const [open, setOpen] = useState(false);

  const handlePaletteSelect = (hex: string) => {
    onChange(hex.toUpperCase());
    setOpen(false);
  };

  const handleHexInput = (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) {
      onChange(null);
      return;
    }
    onChange(trimmed.toUpperCase());
  };

  return (
    <Popover
      open={open}
      onOpenChange={(_, data) => !disabled && setOpen(data.open)}
      positioning="below-start"
    >
      <PopoverTrigger disableButtonEnhancement>
        <Button
          className={styles.trigger}
          disabled={disabled}
          aria-label={ariaLabel ?? "Seleccionar color"}
        >
          <span
            className={`${styles.swatch} ${value ? "" : styles.swatchEmpty}`}
            style={value ? { background: value } : undefined}
          />
          <span>{value ?? "Elegir…"}</span>
        </Button>
      </PopoverTrigger>
      <PopoverSurface className={styles.surface}>
        <div className={styles.grid} role="listbox" aria-label="Paleta de colores">
          {VERTICAL_COLOR_PALETTE.map((hex) => {
            const isSelected = value?.toUpperCase() === hex.toUpperCase();
            return (
              <button
                key={hex}
                type="button"
                role="option"
                aria-selected={isSelected}
                aria-label={hex}
                className={`${styles.paletteButton} ${isSelected ? styles.swatchSelected : ""}`}
                style={{ background: hex }}
                onClick={() => handlePaletteSelect(hex)}
              />
            );
          })}
        </div>
        <Input
          className={styles.hexInput}
          size="small"
          placeholder="#RRGGBB"
          value={value ?? ""}
          onChange={(_, data) => handleHexInput(data.value)}
          aria-label="Color hex"
        />
      </PopoverSurface>
    </Popover>
  );
}
