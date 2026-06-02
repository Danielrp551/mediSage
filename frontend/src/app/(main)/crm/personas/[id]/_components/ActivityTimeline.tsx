"use client";

import {
  Button,
  MessageBar,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { HistoryRegular } from "@fluentui/react-icons";
import { useQueryState } from "nuqs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { deleteActivity, listActivities, updateActivity } from "@/actions/lead-activity.actions";
import { ACTIVITY_FILTER_GROUPS } from "@/lib/constants/crm";
import type { LeadActivityUpdateInput } from "@/lib/schemas/lead-activity.schema";
import { appTokens } from "@/lib/theme/brand";
import { dayGroupLabel } from "@/lib/utils/date";
import type { LeadActivityItem } from "@/types/crm.types";

import { ActivityCard } from "./ActivityCard";
import { ActivityComposer } from "./ActivityComposer";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "760px",
  },
  chips: {
    display: "flex",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
  },
  dayGroup: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  dayHeader: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: appTokens.chromeTextMuted,
  },
  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalXXXL} ${tokens.spacingHorizontalL}`,
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    minHeight: "160px",
  },
  emptyIcon: { fontSize: "36px", opacity: 0.7 },
});

interface Props {
  personId: string;
  /** LEAD_ACTIVITIES_WRITE — habilita composer + editar/borrar/completar. */
  canWrite: boolean;
}

interface DayGroup {
  key: string;
  label: string;
  items: LeadActivityItem[];
}

// Mapea la key del chip → activity_type[] del filtro server-side (null = todos).
const FILTER_BY_KEY = new Map(ACTIVITY_FILTER_GROUPS.map((g) => [g.key, g.types]));

/**
 * Timeline rico del tab Actividad (F5). Compone el composer (gated `canWrite`),
 * los chips de filtro (URL state `?act_type=`, re-query server-side), y el feed
 * agrupado por día. La agrupación "Hoy"/"Ayer" y el resaltado de seguimientos
 * futuros se calculan SOLO en cliente (`mounted` + `nowMs`) — SSR en UTC
 * desfasaría la frontera del día en Lima (UTC-5).
 */
export function ActivityTimeline({ personId, canWrite }: Props) {
  const styles = useStyles();

  const [activities, setActivities] = useState<LeadActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // true sólo tras montar en cliente → habilita los cálculos con `new Date()`
  // (agrupación por día, tiempo relativo, seguimientos futuros) sin mismatch.
  const [mounted, setMounted] = useState(false);
  const [nowMs, setNowMs] = useState(0);

  const [actType, setActType] = useQueryState("act_type", { defaultValue: "all" });
  const activeChip = FILTER_BY_KEY.has(actType) ? actType : "all";

  const reqIdRef = useRef(0);

  // `silent` (refetch tras una mutación) NO toca `loading` → el feed visible se
  // mantiene mientras llega el nuevo lote (sin flash de skeleton ni desmontar las
  // cards). La carga inicial y el cambio de chip SÍ muestran skeleton.
  const load = useCallback(
    (silent = false) => {
      const reqId = ++reqIdRef.current;
      if (!silent) setLoading(true);
      setError(null);
      const types = FILTER_BY_KEY.get(activeChip) ?? null;
      void listActivities(personId, types ? { activity_type: types } : {})
        .then((res) => {
          if (reqId !== reqIdRef.current) return;
          setActivities(res.data);
          setLoading(false);
        })
        .catch(() => {
          if (reqId !== reqIdRef.current) return;
          setError("No se pudo cargar la actividad. Intenta de nuevo.");
          setLoading(false);
        });
    },
    [personId, activeChip],
  );

  // Refetch silencioso reutilizable tras crear/editar/borrar/completar (estable).
  const refresh = useCallback(() => load(true), [load]);

  useEffect(() => {
    setMounted(true);
    setNowMs(Date.now());
  }, []);

  // Re-fetch al montar y cada vez que cambia el chip (filtro server-side).
  useEffect(() => {
    load();
  }, [load]);

  // Handlers ESTABLES para no romper el React.memo de ActivityCard. Tras una
  // mutación exitosa re-fetcheamos el feed (mínimo viable; sin optimismo).
  const handleUpdate = useCallback(
    async (activityId: string, input: LeadActivityUpdateInput) => {
      const result = await updateActivity(personId, activityId, input);
      if (result.ok) refresh();
      return result;
    },
    [personId, refresh],
  );

  const handleDelete = useCallback(
    async (activityId: string) => {
      const result = await deleteActivity(personId, activityId);
      if (result.ok) refresh();
      return result;
    },
    [personId, refresh],
  );

  // Agrupación por día — recomputa sólo cuando cambian las actividades (o al
  // montar). Las actividades llegan más recientes primero (orden del backend).
  const groups = useMemo<DayGroup[]>(() => {
    if (!mounted) return [];
    const byKey = new Map<string, DayGroup>();
    for (const a of activities) {
      const d = new Date(a.created_on);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      let group = byKey.get(key);
      if (!group) {
        group = { key, label: dayGroupLabel(a.created_on), items: [] };
        byKey.set(key, group);
      }
      group.items.push(a);
    }
    return Array.from(byKey.values());
  }, [activities, mounted]);

  return (
    <div className={styles.root}>
      {canWrite ? <ActivityComposer personId={personId} onCreated={refresh} /> : null}

      <div className={styles.chips}>
        {ACTIVITY_FILTER_GROUPS.map((g) => (
          <Button
            key={g.key}
            appearance={activeChip === g.key ? "primary" : "outline"}
            shape="circular"
            size="small"
            onClick={() => void setActType(g.key)}
          >
            {g.label}
          </Button>
        ))}
      </div>

      {error ? (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.dayGroup}>
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i}>
              <SkeletonItem shape="rectangle" size={48} />
            </Skeleton>
          ))}
        </div>
      ) : activities.length === 0 ? (
        activeChip === "all" ? (
          <div className={styles.empty}>
            <HistoryRegular className={styles.emptyIcon} />
            <span>Sin actividad aún. Registra la primera nota, llamada o seguimiento.</span>
          </div>
        ) : (
          <div className={styles.empty}>
            <HistoryRegular className={styles.emptyIcon} />
            <span>No hay actividades de este tipo.</span>
            <Button appearance="secondary" size="small" onClick={() => void setActType("all")}>
              Ver todas
            </Button>
          </div>
        )
      ) : (
        groups.map((group) => (
          <div key={group.key} className={styles.dayGroup}>
            <div className={styles.dayHeader}>{group.label}</div>
            {group.items.map((a) => (
              <ActivityCard
                key={a.id}
                activity={a}
                canWrite={canWrite}
                nowMs={nowMs}
                onUpdate={handleUpdate}
                onDelete={handleDelete}
              />
            ))}
          </div>
        ))
      )}
    </div>
  );
}
