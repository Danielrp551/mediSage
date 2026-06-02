"use client";

import {
  Avatar,
  Badge,
  Card,
  MessageBar,
  MessageBarBody,
  Skeleton,
  SkeletonItem,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { HistoryRegular } from "@fluentui/react-icons";
import { useEffect, useMemo, useRef, useState } from "react";

import { listActivities } from "@/actions/lead-activity.actions";
import { ACTIVITY_OUTCOME_LABELS, ACTIVITY_TYPE_META } from "@/lib/constants/crm";
import { appTokens } from "@/lib/theme/brand";
import { dayGroupLabel, formatDate, formatRelative } from "@/lib/utils/date";
import type { LeadActivityItem } from "@/types/crm.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
    maxWidth: "760px",
  },
  dayGroup: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  dayHeader: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    color: appTokens.chromeTextMuted,
  },
  card: {
    display: "flex",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalM,
    padding: tokens.spacingVerticalM,
    // Lista potencialmente larga — el navegador no paga layout fuera de viewport.
    contentVisibility: "auto",
    containIntrinsicSize: "auto 80px",
  },
  cardIcon: {
    display: "inline-flex",
    fontSize: "20px",
    flexShrink: 0,
    marginTop: "2px",
  },
  cardMain: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    flex: 1,
    minWidth: 0,
  },
  cardTopRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
  },
  cardTitle: {
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  cardMeta: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    flexShrink: 0,
  },
  cardContent: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    wordBreak: "break-word",
  },
  cardExtras: {
    display: "flex",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
    marginTop: tokens.spacingVerticalXXS,
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
    minHeight: "200px",
  },
  emptyIcon: { fontSize: "36px", opacity: 0.7 },
});

interface Props {
  personId: string;
  /** Sin uso en F3 (no hay composer; el create llega en F5). */
  canWrite: boolean;
}

interface DayGroup {
  key: string;
  label: string;
  items: LeadActivityItem[];
}

/**
 * Feed read-only del timeline (F3, Iteración A). Carga `listActivities` al
 * montar y agrupa por día (Hoy/Ayer/fecha). La agrupación y los timestamps
 * relativos se calculan SOLO en cliente (montados ya) — SSR en UTC desfasaría la
 * frontera del día en Lima. SIN composer / SIN crear/editar/borrar (eso es F5).
 */
export function ActivityTimeline({ personId }: Props) {
  const styles = useStyles();

  const [activities, setActivities] = useState<LeadActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Se vuelve true sólo tras montar en cliente → habilita los cálculos con
  // `new Date()` (agrupación por día + tiempo relativo) sin mismatch de hidratación.
  const [mounted, setMounted] = useState(false);

  const reqIdRef = useRef(0);

  useEffect(() => {
    setMounted(true);
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setError(null);
    void listActivities(personId)
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
  }, [personId]);

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

  if (loading) {
    return (
      <div className={styles.root}>
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i}>
            <SkeletonItem shape="rectangle" size={48} />
          </Skeleton>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.root}>
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      </div>
    );
  }

  if (activities.length === 0) {
    return (
      <div className={styles.empty}>
        <HistoryRegular className={styles.emptyIcon} />
        <span>Aún no hay actividad.</span>
      </div>
    );
  }

  return (
    <div className={styles.root}>
      {groups.map((group) => (
        <div key={group.key} className={styles.dayGroup}>
          <div className={styles.dayHeader}>{group.label}</div>
          {group.items.map((a) => (
            <ActivityCard key={a.id} activity={a} />
          ))}
        </div>
      ))}
    </div>
  );
}

function ActivityCard({ activity }: { activity: LeadActivityItem }) {
  const styles = useStyles();
  const meta = ACTIVITY_TYPE_META[activity.activity_type];
  const Icon = meta.icon;
  const actorName = activity.advisor?.full_name ?? "Sistema";

  return (
    <Card className={styles.card}>
      <span className={styles.cardIcon} style={{ color: meta.color }}>
        <Icon />
      </span>
      <div className={styles.cardMain}>
        <div className={styles.cardTopRow}>
          <span className={styles.cardTitle}>{meta.label}</span>
          <span className={styles.cardMeta}>
            <Avatar size={20} name={actorName} color={activity.advisor ? "colorful" : "neutral"} />
            {actorName}
            {" · "}
            <Tooltip content={formatDate(activity.created_on)} relationship="label" withArrow>
              <span>{formatRelative(activity.created_on)}</span>
            </Tooltip>
          </span>
        </div>
        {activity.content ? <span className={styles.cardContent}>{activity.content}</span> : null}
        {activity.outcome ? (
          <div className={styles.cardExtras}>
            <Badge appearance="tint" color="informative">
              {ACTIVITY_OUTCOME_LABELS[activity.outcome]}
            </Badge>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
