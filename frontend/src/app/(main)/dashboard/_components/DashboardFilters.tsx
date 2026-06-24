"use client";

/**
 * Filtros del panel: Rango (presets + personalizado) · Sede · Origen. Sincroniza el
 * `DashboardFilter` hacia arriba vía `onChange` → cambiar un filtro refetcha todos los widgets
 * (el filtro es parte de la `queryKey`). Validación client-side espejo del backend
 * (`date_to >= date_from`, rango ≤ 366 días → DASHBOARD_INVALID_DATE_RANGE): si el rango es
 * inválido NO se propaga (los widgets conservan el último filtro válido).
 *
 * Caveat de sede (design §4): el filtro de sede sólo aplica de "Citas" en adelante (sólo
 * `appointment` tiene `branch_id`); las etapas previas (conversaciones/leads) son a nivel
 * clínica → una nota suave lo explica cuando Sede ≠ "Todas".
 *
 * Fechas-puro: el `<input type="date">` nativo entrega "YYYY-MM-DD" directo (sin TZ) → encaja
 * con el contrato del rollup (día UTC) sin conversiones.
 */

import {
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useState } from "react";

import { appTokens } from "@/lib/theme/brand";
import type { DashboardFilter, DashboardMeta } from "@/types/dashboards.types";

import { RANGE_PRESETS, rangeDays, resolveRange, type RangePresetKey } from "./filterPresets";
import { sourceLabel } from "./format";

const MAX_RANGE_DAYS = 366;

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  toolbar: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  rangeFilter: { minWidth: "180px" },
  filter: { minWidth: "170px" },
  customDates: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  dateField: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalXS },
  dateLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  dateInput: {
    fontFamily: tokens.fontFamilyBase,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    padding: `${tokens.spacingVerticalXS} ${tokens.spacingHorizontalSNudge}`,
    border: `1px solid ${tokens.colorNeutralStroke1}`,
    borderRadius: tokens.borderRadiusMedium,
    backgroundColor: appTokens.contentBg,
  },
});

const ALL_BRANCHES = "__all__"; // value sentinela del Option "Todas" (no choca con un id real)
const ALL_SOURCES = "__all__";

interface Props {
  filter: DashboardFilter;
  meta: DashboardMeta | undefined;
  onChange: (next: DashboardFilter) => void;
}

export function DashboardFilters({ filter, meta, onChange }: Props) {
  const styles = useStyles();
  const [presetKey, setPresetKey] = useState<RangePresetKey>("last30");
  const [rangeError, setRangeError] = useState<string | null>(null);

  const branches = meta?.branches ?? [];
  const sources = meta?.sources ?? [];

  const presetLabel = RANGE_PRESETS.find((p) => p.key === presetKey)?.label ?? "Últimos 30 días";
  const selectedBranchName = filter.branch_id
    ? (branches.find((b) => b.id === filter.branch_id)?.name ?? "Sede")
    : "Todas";
  const selectedSourceLabel = filter.source ? sourceLabel(filter.source) : "Todos";

  function applyRange(from: string, to: string) {
    if (to < from) {
      setRangeError("La fecha final no puede ser anterior a la inicial.");
      return;
    }
    if (rangeDays(from, to) > MAX_RANGE_DAYS) {
      setRangeError("El rango no puede superar un año.");
      return;
    }
    setRangeError(null);
    onChange({ ...filter, date_from: from, date_to: to });
  }

  function handlePreset(key: RangePresetKey) {
    setPresetKey(key);
    if (key === "custom") return; // muestra los inputs; no cambia el filtro hasta editar
    setRangeError(null);
    const r = resolveRange(key);
    onChange({ ...filter, date_from: r.date_from, date_to: r.date_to });
  }

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <Dropdown
          className={styles.rangeFilter}
          aria-label="Rango de fechas"
          value={presetLabel}
          selectedOptions={[presetKey]}
          onOptionSelect={(_, d) => handlePreset(d.optionValue as RangePresetKey)}
        >
          {RANGE_PRESETS.map((p) => (
            <Option key={p.key} value={p.key}>
              {p.label}
            </Option>
          ))}
        </Dropdown>

        <Dropdown
          className={styles.filter}
          aria-label="Sede"
          value={selectedBranchName}
          selectedOptions={[filter.branch_id ?? ALL_BRANCHES]}
          onOptionSelect={(_, d) =>
            onChange({
              ...filter,
              branch_id: d.optionValue === ALL_BRANCHES ? null : (d.optionValue ?? null),
            })
          }
        >
          <Option value={ALL_BRANCHES}>Todas</Option>
          {branches.map((b) => (
            <Option key={b.id} value={b.id}>
              {b.name}
            </Option>
          ))}
        </Dropdown>

        <Dropdown
          className={styles.filter}
          aria-label="Origen"
          value={selectedSourceLabel}
          selectedOptions={[filter.source ?? ALL_SOURCES]}
          onOptionSelect={(_, d) =>
            onChange({
              ...filter,
              source: d.optionValue === ALL_SOURCES ? null : (d.optionValue ?? null),
            })
          }
        >
          <Option value={ALL_SOURCES}>Todos</Option>
          {sources.map((s) => (
            <Option key={s} value={s}>
              {sourceLabel(s)}
            </Option>
          ))}
        </Dropdown>
      </div>

      {presetKey === "custom" ? (
        <div className={styles.customDates}>
          <span className={styles.dateField}>
            <span className={styles.dateLabel}>Desde</span>
            <input
              type="date"
              aria-label="Fecha inicial"
              className={styles.dateInput}
              value={filter.date_from}
              max={filter.date_to}
              onChange={(e) => applyRange(e.target.value, filter.date_to)}
            />
          </span>
          <span className={styles.dateField}>
            <span className={styles.dateLabel}>Hasta</span>
            <input
              type="date"
              aria-label="Fecha final"
              className={styles.dateInput}
              value={filter.date_to}
              min={filter.date_from}
              onChange={(e) => applyRange(filter.date_from, e.target.value)}
            />
          </span>
        </div>
      ) : null}

      {rangeError ? (
        <MessageBar intent="error">
          <MessageBarBody>{rangeError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {filter.branch_id ? (
        <MessageBar intent="info">
          <MessageBarBody>
            Conversaciones y leads son a nivel clínica; el filtro de sede aplica desde
            &quot;Citas&quot; en adelante.
          </MessageBarBody>
        </MessageBar>
      ) : null}
    </div>
  );
}
