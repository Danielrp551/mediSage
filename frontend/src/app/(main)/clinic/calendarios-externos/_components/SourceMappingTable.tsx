"use client";

import {
  Badge,
  Button,
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  Switch,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useEffect, useMemo, useState, useTransition } from "react";

import { replaceSources } from "@/actions/calendar.actions";
import { appTokens } from "@/lib/theme/brand";
import type { BranchOption } from "@/types/clinic.types";
import type { CalendarSourceItem, ExternalCalendarOption } from "@/types/calendar.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  table: {
    display: "flex",
    flexDirection: "column",
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    borderRadius: tokens.borderRadiusMedium,
    overflow: "hidden",
  },
  headerRow: {
    display: "grid",
    gridTemplateColumns: "1fr 200px 110px",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    backgroundColor: tokens.colorNeutralBackground2,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeTextMuted,
    textTransform: "uppercase",
    letterSpacing: "0.03em",
  },
  row: {
    display: "grid",
    gridTemplateColumns: "1fr 200px 110px",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  calCell: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    minWidth: 0,
  },
  calName: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  footer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  empty: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    padding: tokens.spacingVerticalS,
  },
});

// Sentinels del Dropdown de sede. Distintos de cualquier id de sede real (uuid).
const NONE = "__none__"; // "(no mapear)" → el calendario no genera source
const ALL = "__all__"; // "Todas las sedes" → mapped con branch_id = null

interface Row {
  external_calendar_id: string;
  external_calendar_name: string;
  primary: boolean;
  mapped: boolean;
  branch_id: string | null;
  is_enabled: boolean;
}

// Cruza la lista LIVE de calendarios con los sources ya guardados: cada calendario aparece
// una vez con su mapeo actual (o sin mapear). Un source cuyo calendario ya NO está en la lista
// live (borrado del proveedor) se agrega igual como fila "huérfana" para no desmapearlo en
// silencio al guardar.
function buildRows(calendars: ExternalCalendarOption[], sources: CalendarSourceItem[]): Row[] {
  const rows: Row[] = calendars.map((cal) => {
    const src = sources.find((s) => s.external_calendar_id === cal.id);
    return {
      external_calendar_id: cal.id,
      external_calendar_name: cal.name,
      primary: cal.primary,
      mapped: src !== undefined,
      branch_id: src ? src.branch_id : null,
      is_enabled: src ? src.is_enabled : false,
    };
  });
  const seen = new Set(calendars.map((c) => c.id));
  for (const s of sources) {
    if (!seen.has(s.external_calendar_id)) {
      rows.push({
        external_calendar_id: s.external_calendar_id,
        external_calendar_name: s.external_calendar_name,
        primary: false,
        mapped: true,
        branch_id: s.branch_id,
        is_enabled: s.is_enabled,
      });
    }
  }
  return rows;
}

function rowKey(rows: Row[]): string {
  return JSON.stringify(
    rows.map((r) => [r.external_calendar_id, r.mapped, r.branch_id, r.is_enabled]),
  );
}

interface Props {
  connectionId: string;
  /** Lista LIVE del proveedor (sólo cuando hay WRITE); read-only deriva de los sources. */
  calendars: ExternalCalendarOption[];
  /** Sources ya guardados (de getConnection → Detail.sources). */
  existingSources: CalendarSourceItem[];
  branches: BranchOption[];
  /** Sin CALENDAR_CONNECTIONS_WRITE: dropdowns/switch deshabilitados, sin "Guardar mapeo". */
  readOnly: boolean;
  /** Aviso al padre tras guardar — refresca el sources_count del header (no re-fetchea el
   *  detalle: la tabla se auto-actualiza del response del PUT). */
  onSaved: () => void;
}

/**
 * Tabla de mapeo calendario→sede con bulk save (molde `OfficeOperatingHoursTab`): se edita en
 * estado local y se persiste con un solo "Guardar mapeo" (`PUT .../sources`, replace atómico).
 * El Dropdown de sede tiene 3 estados: "(no mapear)" (sin source), "Todas las sedes"
 * (branch_id null) y una sede concreta. Sólo las filas mapeadas entran al payload.
 */
export function SourceMappingTable({
  connectionId,
  calendars,
  existingSources,
  branches,
  readOnly,
  onSaved,
}: Props) {
  const styles = useStyles();

  // Firma estable de los inputs → rebuild de las filas sólo cuando su CONTENIDO cambia (carga
  // inicial / Reintentar recarga calendars / otra conexión), NO en cada render. Tras un
  // guardado la tabla se auto-actualiza del response (no via props), así que esto no dispara.
  const inputsKey = useMemo(
    () =>
      JSON.stringify([
        calendars.map((c) => [c.id, c.name, c.primary]),
        existingSources.map((s) => [s.external_calendar_id, s.branch_id, s.is_enabled]),
      ]),
    [calendars, existingSources],
  );

  // `baseline` = el último estado PERSISTIDO (para isDirty). Es estado, no derivado: tras un
  // guardado se reconstruye del response (mantiene el "Mapeo guardado" sin remontar). El effect
  // lo re-sincroniza sólo cuando los inputs CAMBIAN de contenido (carga inicial / Reintentar /
  // otra conexión), no en cada render.
  const [baseline, setBaseline] = useState<Row[]>(() => buildRows(calendars, existingSources));
  const [rows, setRows] = useState<Row[]>(baseline);
  const [serverError, setServerError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [saving, startSave] = useTransition();

  useEffect(() => {
    const b = buildRows(calendars, existingSources);
    setBaseline(b);
    setRows(b);
    setJustSaved(false);
    setServerError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputsKey]);

  const isDirty = useMemo(() => rowKey(rows) !== rowKey(baseline), [rows, baseline]);

  const setBranch = (idx: number, value: string) => {
    setJustSaved(false);
    setRows((prev) =>
      prev.map((r, i) => {
        if (i !== idx) return r;
        if (value === NONE) return { ...r, mapped: false, branch_id: null, is_enabled: false };
        // Al mapear una fila antes SIN mapear, habilitarla por defecto (= default true de
        // CalendarSourceCreate.is_enabled del backend/Zod; mapear = habilitar). Si la fila ya
        // estaba mapeada (re-mapeo), preservar su flag (puede estar "mapeada pero pausada").
        const is_enabled = r.mapped ? r.is_enabled : true;
        if (value === ALL) return { ...r, mapped: true, branch_id: null, is_enabled };
        return { ...r, mapped: true, branch_id: value, is_enabled };
      }),
    );
  };

  const setEnabled = (idx: number, checked: boolean) => {
    setJustSaved(false);
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, is_enabled: checked } : r)));
  };

  const onSave = () => {
    setServerError(null);
    setJustSaved(false);
    const sources = rows
      .filter((r) => r.mapped)
      .map((r) => ({
        external_calendar_id: r.external_calendar_id,
        external_calendar_name: r.external_calendar_name,
        branch_id: r.branch_id,
        is_enabled: r.is_enabled,
      }));
    startSave(async () => {
      const res = await replaceSources(connectionId, { sources });
      if (!res.ok || !res.data) {
        setServerError(res.error ?? "No se pudo guardar el mapeo.");
        return;
      }
      // Reconstruye baseline+rows del set persistido (response) → isDirty vuelve a false y el
      // "Mapeo guardado" persiste (sin remontar). Mantiene la lista LIVE de calendarios.
      const fresh = buildRows(calendars, res.data.data.sources);
      setBaseline(fresh);
      setRows(fresh);
      setJustSaved(true);
      onSaved(); // refresca el sources_count del header de la card (router.refresh)
    });
  };

  const dropdownValue = (r: Row): string => {
    if (!r.mapped) return NONE;
    if (r.branch_id === null) return ALL;
    return r.branch_id;
  };

  const dropdownText = (r: Row): string => {
    if (!r.mapped) return "(no mapear)";
    if (r.branch_id === null) return "Todas las sedes";
    return branches.find((b) => b.id === r.branch_id)?.name ?? "(sede desconocida)";
  };

  if (rows.length === 0) {
    return <div className={styles.empty}>Esta cuenta no tiene calendarios para mapear.</div>;
  }

  return (
    <div className={styles.root}>
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}
      {justSaved ? (
        <MessageBar intent="success">
          <MessageBarBody>Mapeo guardado.</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.table}>
        <div className={styles.headerRow}>
          <span>Calendario</span>
          <span>Sede</span>
          <span>Habilitado</span>
        </div>
        {rows.map((r, idx) => (
          <div key={r.external_calendar_id} className={styles.row}>
            <div className={styles.calCell}>
              <Tooltip content={r.external_calendar_name} relationship="label" withArrow>
                <span className={styles.calName}>{r.external_calendar_name}</span>
              </Tooltip>
              {r.primary ? <Badge appearance="tint">⭐ prim.</Badge> : null}
            </div>
            <Dropdown
              value={dropdownText(r)}
              selectedOptions={[dropdownValue(r)]}
              disabled={readOnly}
              onOptionSelect={(_, data) => {
                if (data.optionValue) setBranch(idx, data.optionValue);
              }}
            >
              <Option value={NONE} text="(no mapear)">
                (no mapear)
              </Option>
              <Option value={ALL} text="Todas las sedes">
                Todas las sedes
              </Option>
              {branches.map((b) => (
                <Option key={b.id} value={b.id} text={b.name}>
                  {b.name}
                </Option>
              ))}
            </Dropdown>
            <Switch
              checked={r.is_enabled}
              disabled={readOnly || !r.mapped}
              onChange={(_, d) => setEnabled(idx, d.checked)}
            />
          </div>
        ))}
      </div>

      <div className={styles.footer}>
        <span className={styles.hint}>
          Las horas de los eventos se interpretan en la zona de la sede mapeada.
        </span>
        {!readOnly ? (
          <Button appearance="primary" disabled={saving || !isDirty} onClick={onSave}>
            {saving ? "Guardando…" : "Guardar mapeo"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
