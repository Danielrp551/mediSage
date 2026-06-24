"use client";

/**
 * Formulario de generación de reportes (F3). Configura rango + sede + formato (PDF/Excel) +
 * secciones a incluir y dispara `generateReport` (Server Action que devuelve el binario serializado
 * → reconstruye un Blob y lo descarga client-side). NO muta negocio (sin revalidateTag).
 *
 * Validación client-side espejo del backend (rango ≤ 366 días, date_to ≥ date_from, ≥1 sección);
 * el backend re-valida (DASHBOARD_INVALID_DATE_RANGE / REPORT_FORMAT_NOT_SUPPORTED) → el error en
 * español se muestra en un MessageBar. Fechas-puro (`<input type="date">` da "YYYY-MM-DD" directo).
 * El rango por defecto se calcula en un efecto (client-only) para no desfasar el día por TZ en SSR.
 */

import {
  Button,
  Checkbox,
  Dropdown,
  Field,
  MessageBar,
  MessageBarBody,
  Option,
  Radio,
  RadioGroup,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowDownloadRegular } from "@fluentui/react-icons";
import { useEffect, useState } from "react";

import { generateReport } from "@/actions/dashboards.actions";
import { appTokens } from "@/lib/theme/brand";
import type { ReportFormat, ReportRequest } from "@/types/dashboards.types";

import {
  RANGE_PRESETS,
  rangeDays,
  resolveRange,
  type RangePresetKey,
} from "../../_components/filterPresets";

const MAX_RANGE_DAYS = 366;
const ALL_BRANCHES = "__all__";

const SECTIONS: { code: string; label: string }[] = [
  { code: "kpis", label: "KPIs" },
  { code: "funnel", label: "Embudo de conversión" },
  { code: "distribution", label: "Distribución de citas" },
  { code: "evolution", label: "Evolución de leads" },
];

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "640px",
  },
  header: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: 0, fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    padding: tokens.spacingHorizontalXL,
    backgroundColor: appTokens.contentBg,
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    boxShadow: tokens.shadow2,
  },
  rangeRow: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "flex-end",
    flexWrap: "wrap",
  },
  control: { minWidth: "180px" },
  dateInput: {
    fontFamily: tokens.fontFamilyBase,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    padding: `${tokens.spacingVerticalSNudge} ${tokens.spacingHorizontalSNudge}`,
    border: `1px solid ${tokens.colorNeutralStroke1}`,
    borderRadius: tokens.borderRadiusMedium,
    backgroundColor: appTokens.contentBg,
  },
  sections: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  actions: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalM },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
});

export function ReportForm({ branches }: { branches: { id: string; name: string }[] }) {
  const styles = useStyles();

  const [presetKey, setPresetKey] = useState<RangePresetKey>("last30");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [branchId, setBranchId] = useState<string | null>(null);
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [checked, setChecked] = useState<Set<string>>(() => new Set(SECTIONS.map((s) => s.code)));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [rangeError, setRangeError] = useState<string | null>(null);

  // Rango por defecto (últimos 30 días) calculado client-only → sin desfase de TZ en SSR.
  useEffect(() => {
    const r = resolveRange("last30");
    setDateFrom(r.date_from);
    setDateTo(r.date_to);
  }, []);

  function validateRange(from: string, to: string): string | null {
    if (!from || !to) return null;
    if (to < from) return "La fecha final no puede ser anterior a la inicial.";
    if (rangeDays(from, to) > MAX_RANGE_DAYS) return "El rango no puede superar un año.";
    return null;
  }

  // Limpia el feedback (éxito Y error) del intento anterior cuando el usuario edita cualquier input
  // → el MessageBar siempre refleja el último intento, nunca uno obsoleto.
  function resetResult() {
    setSuccess(false);
    setError(null);
  }

  function handlePreset(key: RangePresetKey) {
    setPresetKey(key);
    resetResult();
    if (key === "custom") return;
    const r = resolveRange(key);
    setDateFrom(r.date_from);
    setDateTo(r.date_to);
    setRangeError(null);
  }

  function handleDate(which: "from" | "to", value: string) {
    const from = which === "from" ? value : dateFrom;
    const to = which === "to" ? value : dateTo;
    setDateFrom(from);
    setDateTo(to);
    setRangeError(validateRange(from, to));
    resetResult();
  }

  function toggleSection(code: string, on: boolean) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (on) next.add(code);
      else next.delete(code);
      return next;
    });
    resetResult();
  }

  const canGenerate = !pending && !!dateFrom && !!dateTo && !rangeError && checked.size > 0;

  async function handleGenerate() {
    if (!canGenerate) return;
    setPending(true);
    setError(null);
    setSuccess(false);
    const input: ReportRequest = {
      date_from: dateFrom,
      date_to: dateTo,
      branch_id: branchId,
      source: null,
      campaign_id: null,
      format,
      sections: SECTIONS.filter((s) => checked.has(s.code)).map((s) => s.code),
    };
    const res = await generateReport(input);
    setPending(false);
    if (!res.ok || !res.data) {
      setError(res.error ?? "No se pudo generar el reporte. Inténtalo de nuevo.");
      return;
    }
    // Reconstruir el Blob desde el base64 y disparar la descarga.
    const { filename, mime, base64 } = res.data;
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setSuccess(true);
  }

  const selectedBranchName = branchId
    ? (branches.find((b) => b.id === branchId)?.name ?? "Sede")
    : "Todas";
  const presetLabel = RANGE_PRESETS.find((p) => p.key === presetKey)?.label ?? "Últimos 30 días";

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Reportes</h1>
        <p className={styles.subtitle}>
          Genera un reporte histórico de conversiones y conversaciones.
        </p>
      </header>

      <div className={styles.card}>
        <Field label="Rango">
          <div className={styles.rangeRow}>
            <Dropdown
              className={styles.control}
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
            {presetKey === "custom" ? (
              <>
                <input
                  type="date"
                  aria-label="Fecha inicial"
                  className={styles.dateInput}
                  value={dateFrom}
                  max={dateTo || undefined}
                  onChange={(e) => handleDate("from", e.target.value)}
                />
                <input
                  type="date"
                  aria-label="Fecha final"
                  className={styles.dateInput}
                  value={dateTo}
                  min={dateFrom || undefined}
                  onChange={(e) => handleDate("to", e.target.value)}
                />
              </>
            ) : null}
          </div>
        </Field>

        <Field label="Sede">
          <Dropdown
            className={styles.control}
            aria-label="Sede"
            value={selectedBranchName}
            selectedOptions={[branchId ?? ALL_BRANCHES]}
            onOptionSelect={(_, d) => {
              setBranchId(d.optionValue === ALL_BRANCHES ? null : (d.optionValue ?? null));
              resetResult();
            }}
          >
            <Option value={ALL_BRANCHES}>Todas</Option>
            {branches.map((b) => (
              <Option key={b.id} value={b.id}>
                {b.name}
              </Option>
            ))}
          </Dropdown>
        </Field>

        <Field label="Formato">
          <RadioGroup
            layout="horizontal"
            value={format}
            onChange={(_, d) => {
              setFormat(d.value as ReportFormat);
              resetResult();
            }}
          >
            <Radio value="pdf" label="PDF" />
            <Radio value="excel" label="Excel" />
          </RadioGroup>
        </Field>

        <Field label="Incluir">
          <div className={styles.sections}>
            {SECTIONS.map((s) => (
              <Checkbox
                key={s.code}
                label={s.label}
                checked={checked.has(s.code)}
                onChange={(_, d) => toggleSection(s.code, d.checked === true)}
              />
            ))}
          </div>
        </Field>

        {rangeError ? (
          <MessageBar intent="error">
            <MessageBarBody>{rangeError}</MessageBarBody>
          </MessageBar>
        ) : null}

        {error ? (
          <MessageBar intent="error">
            <MessageBarBody>{error}</MessageBarBody>
          </MessageBar>
        ) : null}

        {success ? (
          <MessageBar intent="success">
            <MessageBarBody>Reporte generado.</MessageBarBody>
          </MessageBar>
        ) : null}

        <div className={styles.actions}>
          <Button
            appearance="primary"
            icon={pending ? <Spinner size="tiny" /> : <ArrowDownloadRegular />}
            disabled={!canGenerate}
            onClick={handleGenerate}
          >
            {pending ? "Generando…" : "Generar y descargar"}
          </Button>
          {checked.size === 0 ? (
            <span className={styles.hint}>Selecciona al menos una sección.</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
