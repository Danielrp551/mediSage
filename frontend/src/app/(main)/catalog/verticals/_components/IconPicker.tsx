"use client";

/**
 * Vertical icon picker — popover with a curated gallery from
 * `lib/constants/catalog-iconography.ts`. The component imports only the
 * exact set of icons that gallery exposes; never `import * as Icons` from
 * `@fluentui/react-icons` (would defeat tree-shaking).
 *
 * The selected value is stored as the Fluent UI icon key (e.g.
 * `Sparkle24Regular`). Adding a new option means:
 *   1. Append to `VERTICAL_ICON_OPTIONS` in catalog-iconography.ts.
 *   2. Add the matching `import` + `ICON_COMPONENTS` entry here.
 *   3. (Optional) Add it to Sidebar's ICONS map if it might be used as a
 *      nav icon — verticals icons stay in this picker for now.
 */

import {
  Button,
  Popover,
  PopoverSurface,
  PopoverTrigger,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  Beaker24Regular,
  Brain24Regular,
  Crown24Regular,
  Doctor24Regular,
  Drop24Regular,
  Eye24Regular,
  Flash24Regular,
  Glasses24Regular,
  Heart24Regular,
  HeartPulse24Regular,
  LeafOne24Regular,
  Patch24Regular,
  Person24Regular,
  PersonHeart24Regular,
  Pill24Regular,
  Sparkle24Regular,
  Star24Regular,
  Stethoscope24Regular,
  Syringe24Regular,
  Wand24Regular,
} from "@fluentui/react-icons";
import type { ReactNode } from "react";
import { useState } from "react";

import {
  VERTICAL_ICON_OPTIONS,
  type VerticalIconKey,
} from "@/lib/constants/catalog-iconography";
import { appTokens } from "@/lib/theme/brand";

const ICON_COMPONENTS: Record<VerticalIconKey, ReactNode> = {
  Sparkle24Regular: <Sparkle24Regular />,
  Heart24Regular: <Heart24Regular />,
  HeartPulse24Regular: <HeartPulse24Regular />,
  Stethoscope24Regular: <Stethoscope24Regular />,
  Doctor24Regular: <Doctor24Regular />,
  Eye24Regular: <Eye24Regular />,
  Brain24Regular: <Brain24Regular />,
  LeafOne24Regular: <LeafOne24Regular />,
  Beaker24Regular: <Beaker24Regular />,
  Pill24Regular: <Pill24Regular />,
  Syringe24Regular: <Syringe24Regular />,
  Patch24Regular: <Patch24Regular />,
  Person24Regular: <Person24Regular />,
  PersonHeart24Regular: <PersonHeart24Regular />,
  Glasses24Regular: <Glasses24Regular />,
  Drop24Regular: <Drop24Regular />,
  Star24Regular: <Star24Regular />,
  Crown24Regular: <Crown24Regular />,
  Wand24Regular: <Wand24Regular />,
  Flash24Regular: <Flash24Regular />,
};

const useStyles = makeStyles({
  trigger: {
    minWidth: "160px",
    justifyContent: "flex-start",
    gap: tokens.spacingHorizontalS,
  },
  iconWrap: {
    display: "inline-flex",
    width: "20px",
    height: "20px",
    alignItems: "center",
    justifyContent: "center",
    color: appTokens.chromeText,
  },
  triggerLabel: {
    color: appTokens.chromeText,
    fontSize: tokens.fontSizeBase300,
  },
  placeholder: { color: appTokens.chromeTextMuted },
  surface: {
    padding: tokens.spacingHorizontalS,
    maxWidth: "320px",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(6, 36px)",
    gap: tokens.spacingHorizontalXS,
  },
  galleryButton: {
    width: "36px",
    height: "36px",
    minWidth: "36px",
    padding: 0,
    borderRadius: tokens.borderRadiusMedium,
  },
  gallerySelected: {
    backgroundColor: appTokens.chromeBgActive,
    boxShadow: `0 0 0 2px ${tokens.colorBrandStroke1}`,
  },
  clearRow: {
    marginTop: tokens.spacingVerticalS,
    display: "flex",
    justifyContent: "flex-end",
  },
});

interface Props {
  value: string | null;
  onChange: (next: string | null) => void;
  disabled?: boolean;
  ariaLabel?: string;
}

function isKnownIconKey(value: string | null): value is VerticalIconKey {
  if (value === null) return false;
  return VERTICAL_ICON_OPTIONS.some((opt) => opt.key === value);
}

export function IconPicker({ value, onChange, disabled, ariaLabel }: Props) {
  const styles = useStyles();
  const [open, setOpen] = useState(false);

  const currentKey = isKnownIconKey(value) ? value : null;
  const currentLabel =
    currentKey === null
      ? null
      : VERTICAL_ICON_OPTIONS.find((opt) => opt.key === currentKey)?.label;

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
          aria-label={ariaLabel ?? "Seleccionar ícono"}
        >
          {currentKey ? (
            <span className={styles.iconWrap}>{ICON_COMPONENTS[currentKey]}</span>
          ) : null}
          <span
            className={`${styles.triggerLabel} ${currentKey ? "" : styles.placeholder}`}
          >
            {currentLabel ?? "Elegir ícono…"}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverSurface className={styles.surface}>
        <div className={styles.grid} role="listbox" aria-label="Galería de íconos">
          {VERTICAL_ICON_OPTIONS.map((opt) => {
            const isSelected = currentKey === opt.key;
            return (
              <Tooltip key={opt.key} content={opt.label} relationship="label">
                <Button
                  appearance="subtle"
                  className={`${styles.galleryButton} ${isSelected ? styles.gallerySelected : ""}`}
                  role="option"
                  aria-selected={isSelected}
                  aria-label={opt.label}
                  onClick={() => {
                    onChange(opt.key);
                    setOpen(false);
                  }}
                  icon={ICON_COMPONENTS[opt.key] as React.ReactElement}
                />
              </Tooltip>
            );
          })}
        </div>
        <div className={styles.clearRow}>
          <Button
            size="small"
            appearance="subtle"
            onClick={() => {
              onChange(null);
              setOpen(false);
            }}
          >
            Quitar ícono
          </Button>
        </div>
      </PopoverSurface>
    </Popover>
  );
}
