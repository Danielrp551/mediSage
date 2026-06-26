"use client";

import {
  Button,
  Input,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { AddRegular, DismissRegular } from "@fluentui/react-icons";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { listOfficeHours, replaceOfficeHours } from "@/actions/office-hours.actions";
import { usePermissions } from "@/hooks/usePermissions";
import { WEEKDAY_LABELS } from "@/lib/constants/timezones";
import { TIME_HHMM_REGEX } from "@/lib/schemas/office-hours.schema";
import { appTokens } from "@/lib/theme/brand";
import type {
  OfficeOperatingHoursReplacePayload,
  OfficeOperatingHoursRow,
} from "@/types/clinic.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    maxWidth: "640px",
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  dayRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalM,
    paddingTop: tokens.spacingVerticalS,
    paddingBottom: tokens.spacingVerticalS,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  dayLabel: {
    width: "84px",
    flexShrink: 0,
    paddingTop: tokens.spacingVerticalXS,
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  blocksCol: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
    flex: 1,
    minWidth: 0,
  },
  blockRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  timeInput: { width: "120px" },
  sep: { color: appTokens.chromeTextMuted },
  blockError: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorPaletteRedForeground1,
  },
  noBlocks: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    paddingTop: tokens.spacingVerticalXS,
  },
  addBtn: { alignSelf: "flex-start" },
  loadingRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
  },
});

interface Props {
  officeId: string;
  branchTimezone: string;
}

interface EditBlock {
  key: number;
  day_of_week: number;
  opens_at: string; // "HH:MM"
  closes_at: string; // "HH:MM"
}

const DAYS = [0, 1, 2, 3, 4, 5, 6];

function blockInvalid(b: EditBlock): boolean {
  return (
    !TIME_HHMM_REGEX.test(b.opens_at) ||
    !TIME_HHMM_REGEX.test(b.closes_at) ||
    b.closes_at <= b.opens_at
  );
}

export function OfficeHoursTab({ officeId, branchTimezone }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("OFFICE_HOURS_WRITE");

  const [blocks, setBlocks] = useState<EditBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [serverError, setServerError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);
  const [saving, startSave] = useTransition();
  const keyRef = useRef(0);

  const applyRows = (rows: OfficeOperatingHoursRow[]) => {
    // Backend serializes `time` as "HH:MM:SS"; the editor + the Zod schema use
    // "HH:MM", so normalize on load (and the <input type="time"> shows HH:MM).
    setBlocks(
      rows.map((r) => ({
        key: keyRef.current++,
        day_of_week: r.day_of_week,
        opens_at: r.opens_at.slice(0, 5),
        closes_at: r.closes_at.slice(0, 5),
      })),
    );
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void listOfficeHours(officeId)
      .then((rows) => {
        if (cancelled) return;
        applyRows(rows);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setServerError("No se pudieron cargar los horarios. Intenta de nuevo.");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [officeId]);

  const blocksByDay = useMemo(() => {
    const map = new Map<number, EditBlock[]>(DAYS.map((d) => [d, []]));
    for (const b of blocks) map.get(b.day_of_week)?.push(b);
    return map;
  }, [blocks]);

  // Same-day overlap detection — mirrors the backend no-overlap validator so
  // the user can't enable Save with an overlapping pattern (which would fail
  // with the backend's English 422). Adjacent blocks (next.opens == prev.closes)
  // are OK. Only blocks with valid times participate (invalid ones flagged apart).
  const overlapKeys = useMemo(() => {
    const bad = new Set<number>();
    const byDay = new Map<number, EditBlock[]>();
    for (const b of blocks) {
      const arr = byDay.get(b.day_of_week) ?? [];
      arr.push(b);
      byDay.set(b.day_of_week, arr);
    }
    for (const arr of byDay.values()) {
      const valid = arr
        .filter((b) => !blockInvalid(b))
        .sort((a, b) => a.opens_at.localeCompare(b.opens_at));
      for (let i = 1; i < valid.length; i++) {
        const prev = valid[i - 1];
        const cur = valid[i];
        if (prev && cur && cur.opens_at < prev.closes_at) {
          bad.add(prev.key);
          bad.add(cur.key);
        }
      }
    }
    return bad;
  }, [blocks]);

  const hasErrors = useMemo(
    () => blocks.some(blockInvalid) || overlapKeys.size > 0,
    [blocks, overlapKeys],
  );

  const addBlock = (day: number) => {
    setJustSaved(false);
    setBlocks((prev) => [
      ...prev,
      { key: keyRef.current++, day_of_week: day, opens_at: "09:00", closes_at: "18:00" },
    ]);
  };

  const removeBlock = (key: number) => {
    setJustSaved(false);
    setBlocks((prev) => prev.filter((b) => b.key !== key));
  };

  const updateBlock = (key: number, field: "opens_at" | "closes_at", value: string) => {
    setJustSaved(false);
    setBlocks((prev) => prev.map((b) => (b.key === key ? { ...b, [field]: value } : b)));
  };

  const onSave = () => {
    setServerError(null);
    setJustSaved(false);
    const payload: OfficeOperatingHoursReplacePayload = {
      hours: blocks.map((b) => ({
        day_of_week: b.day_of_week,
        opens_at: b.opens_at,
        closes_at: b.closes_at,
      })),
    };
    startSave(async () => {
      const result = await replaceOfficeHours(officeId, payload);
      if (!result.ok || !result.data) {
        setServerError(result.error ?? "No se pudieron guardar los horarios.");
        return;
      }
      applyRows(result.data.data);
      setJustSaved(true);
    });
  };

  return (
    <div className={styles.root}>
      <div className={styles.headerRow}>
        <h2 className={styles.title}>Horario semanal</h2>
        {canWrite ? (
          <Button appearance="primary" disabled={saving || hasErrors} onClick={onSave}>
            {saving ? "Guardando…" : "Guardar horarios"}
          </Button>
        ) : null}
      </div>

      <MessageBar intent="info">
        <MessageBarBody>
          Las horas se interpretan en la zona horaria de la sede ({branchTimezone}). Guardar
          reemplaza todo el horario semanal.
        </MessageBarBody>
      </MessageBar>

      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {justSaved ? (
        <MessageBar intent="success">
          <MessageBarBody>Horarios guardados.</MessageBarBody>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.loadingRow}>
          <Spinner size="tiny" />
          Cargando horarios…
        </div>
      ) : (
        DAYS.map((day) => {
          const dayBlocks = blocksByDay.get(day) ?? [];
          return (
            <div key={day} className={styles.dayRow}>
              <div className={styles.dayLabel}>{WEEKDAY_LABELS[day]}</div>
              <div className={styles.blocksCol}>
                {dayBlocks.length === 0 ? (
                  <span className={styles.noBlocks}>(sin bloques)</span>
                ) : (
                  dayBlocks.map((b) => {
                    const invalid = blockInvalid(b);
                    return (
                      <div key={b.key}>
                        <div className={styles.blockRow}>
                          <Input
                            className={styles.timeInput}
                            type="time"
                            value={b.opens_at}
                            disabled={!canWrite}
                            onChange={(_, d) => updateBlock(b.key, "opens_at", d.value)}
                          />
                          <span className={styles.sep}>–</span>
                          <Input
                            className={styles.timeInput}
                            type="time"
                            value={b.closes_at}
                            disabled={!canWrite}
                            onChange={(_, d) => updateBlock(b.key, "closes_at", d.value)}
                          />
                          {canWrite ? (
                            <Button
                              appearance="subtle"
                              size="small"
                              icon={<DismissRegular />}
                              aria-label="Quitar bloque"
                              onClick={() => removeBlock(b.key)}
                            />
                          ) : null}
                        </div>
                        {invalid ? (
                          <span className={styles.blockError}>
                            La hora de cierre debe ser mayor que la de apertura.
                          </span>
                        ) : overlapKeys.has(b.key) ? (
                          <span className={styles.blockError}>
                            Este bloque se solapa con otro del mismo día.
                          </span>
                        ) : null}
                      </div>
                    );
                  })
                )}
                {canWrite ? (
                  <Button
                    className={styles.addBtn}
                    appearance="subtle"
                    size="small"
                    icon={<AddRegular />}
                    onClick={() => addBlock(day)}
                  >
                    Agregar bloque
                  </Button>
                ) : null}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
