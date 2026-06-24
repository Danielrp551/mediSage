"use client";

/**
 * Orquestador del Panel de conversión (NO es una DataTable). Mantiene el `DashboardFilter`
 * en estado local y monta 5 `useQuery` **aislados** (uno por widget) — NO `useTableQuery`
 * (no hay paginación). El filtro es parte de cada `queryKey` → cambiarlo refetcha todo;
 * `placeholderData: keepPreviousData` mantiene lo visible (atenuado) mientras llega el dato
 * nuevo (sin flash a skeleton). `initialData` (del prefetch RSC) sólo aplica mientras el
 * filtro === el del prefetch → primer render sin round-trip (LCP/RNF-05). `staleTime` ≈
 * `refetchInterval` ≈ el intervalo del rollup (10 min) → el panel se siente "casi en tiempo
 * real" leyendo el rollup, sin recomputar. Cada widget maneja loading/sin-datos/error por su
 * cuenta (lección §23): uno caído nunca rompe el panel.
 */

import { Button, Spinner, Tooltip, makeStyles, tokens } from "@fluentui/react-components";
import { ArrowSyncRegular } from "@fluentui/react-icons";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  getAppointmentsDistribution,
  getFunnel,
  getLeadsEvolution,
  getMeta,
  getSummary,
} from "@/actions/dashboards.actions";
import { appTokens } from "@/lib/theme/brand";
import type {
  DashboardFilter,
  DashboardMeta,
  FunnelSummary,
  KpiSummary,
} from "@/types/dashboards.types";

import { AppointmentsDonut } from "./AppointmentsDonut";
import { BotMiniPanel } from "./BotMiniPanel";
import { ConversionFunnel } from "./ConversionFunnel";
import { DashboardFilters } from "./DashboardFilters";
import { FreshnessBadge } from "./FreshnessBadge";
import { KpiCards } from "./KpiCards";
import { LeadsLineChart } from "./LeadsLineChart";
import { WidgetFrame } from "./WidgetFrame";

const REFRESH_MINUTES = 10; // ≈ DASHBOARD_REFRESH_INTERVAL_MINUTES (el cron refresca el rollup)
const REFRESH_MS = REFRESH_MINUTES * 60_000;
const DASHBOARDS_QUERY_PREFIX = "dashboards:";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  headerActions: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  chartsRow: {
    display: "grid",
    gridTemplateColumns: "1fr",
    gap: tokens.spacingVerticalL,
    "@media (min-width: 1100px)": { gridTemplateColumns: "1.6fr 1fr" },
  },
});

interface InitialData {
  summary: KpiSummary;
  funnel: FunnelSummary;
  meta: DashboardMeta;
}

interface Props {
  /** Prefetch del RSC (summary+funnel+meta) para el filtro por defecto; null si el prefetch falló. */
  initialData: InitialData | null;
  initialFilter: DashboardFilter;
}

export function DashboardClient({ initialData, initialFilter }: Props) {
  const styles = useStyles();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<DashboardFilter>(initialFilter);

  // `initialData` del prefetch sólo es válido mientras el filtro coincide con el del prefetch.
  const isInitialFilter = useMemo(
    () => JSON.stringify(filter) === JSON.stringify(initialFilter),
    [filter, initialFilter],
  );
  const filterKey = useMemo(() => JSON.stringify(filter), [filter]);

  const summaryQuery = useQuery({
    queryKey: [`${DASHBOARDS_QUERY_PREFIX}summary`, filterKey],
    queryFn: () => getSummary(filter),
    initialData: isInitialFilter ? (initialData?.summary ?? undefined) : undefined,
    placeholderData: keepPreviousData,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
  });

  const funnelQuery = useQuery({
    queryKey: [`${DASHBOARDS_QUERY_PREFIX}funnel`, filterKey],
    queryFn: () => getFunnel(filter),
    initialData: isInitialFilter ? (initialData?.funnel ?? undefined) : undefined,
    placeholderData: keepPreviousData,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
  });

  const distributionQuery = useQuery({
    queryKey: [`${DASHBOARDS_QUERY_PREFIX}distribution`, filterKey],
    queryFn: () => getAppointmentsDistribution(filter),
    placeholderData: keepPreviousData,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
  });

  const leadsQuery = useQuery({
    queryKey: [`${DASHBOARDS_QUERY_PREFIX}leads`, filterKey],
    queryFn: () => getLeadsEvolution(filter),
    placeholderData: keepPreviousData,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
  });

  // META es independiente del filtro (catálogos + frescura) → su queryKey NO lleva el filtro.
  const metaQuery = useQuery({
    queryKey: [`${DASHBOARDS_QUERY_PREFIX}meta`],
    queryFn: () => getMeta(),
    initialData: initialData?.meta ?? undefined,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
  });

  const anyFetching =
    summaryQuery.isFetching ||
    funnelQuery.isFetching ||
    distributionQuery.isFetching ||
    leadsQuery.isFetching ||
    metaQuery.isFetching;

  const refreshAll = () =>
    void queryClient.invalidateQueries({
      predicate: (q) =>
        typeof q.queryKey[0] === "string" &&
        (q.queryKey[0] as string).startsWith(DASHBOARDS_QUERY_PREFIX),
    });

  const funnelEmpty = !!funnelQuery.data && funnelQuery.data.stages.every((s) => s.count === 0);
  const distributionEmpty = !!distributionQuery.data && distributionQuery.data.total === 0;
  const leadsEmpty =
    !!leadsQuery.data &&
    !leadsQuery.data.points.some((p) => Object.values(p.values).some((v) => v > 0));

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Panel de conversión</h1>
        <div className={styles.headerActions}>
          <FreshnessBadge
            lastRefreshedAt={metaQuery.data?.last_refreshed_at ?? null}
            intervalMinutes={REFRESH_MINUTES}
          />
          <Tooltip content="Actualizar panel" relationship="label" withArrow>
            <Button
              appearance="subtle"
              aria-label="Actualizar panel"
              icon={anyFetching ? <Spinner size="tiny" /> : <ArrowSyncRegular />}
              onClick={refreshAll}
            />
          </Tooltip>
        </div>
      </header>

      <DashboardFilters filter={filter} meta={metaQuery.data} onChange={setFilter} />

      <KpiCards
        summary={summaryQuery.data}
        isLoading={summaryQuery.isPending}
        isRefetching={summaryQuery.isFetching && !summaryQuery.isPending}
        isError={summaryQuery.isError}
        onRetry={() => void summaryQuery.refetch()}
      />

      <WidgetFrame
        title="Embudo de conversión"
        isLoading={funnelQuery.isPending}
        isRefetching={funnelQuery.isFetching && !funnelQuery.isPending}
        isError={funnelQuery.isError}
        isEmpty={funnelEmpty}
        emptyLabel="No hay datos en el rango seleccionado"
        onRetry={() => void funnelQuery.refetch()}
        minHeight={264}
      >
        {funnelQuery.data ? <ConversionFunnel data={funnelQuery.data} /> : null}
      </WidgetFrame>

      <div className={styles.chartsRow}>
        <WidgetFrame
          title="Evolución de leads"
          isLoading={leadsQuery.isPending}
          isRefetching={leadsQuery.isFetching && !leadsQuery.isPending}
          isError={leadsQuery.isError}
          isEmpty={leadsEmpty}
          emptyLabel="No hay datos en el rango seleccionado"
          onRetry={() => void leadsQuery.refetch()}
          minHeight={280}
        >
          <LeadsLineChart data={leadsQuery.data} />
        </WidgetFrame>

        <WidgetFrame
          title="Distribución de citas"
          isLoading={distributionQuery.isPending}
          isRefetching={distributionQuery.isFetching && !distributionQuery.isPending}
          isError={distributionQuery.isError}
          isEmpty={distributionEmpty}
          emptyLabel="No hay citas en el rango seleccionado"
          onRetry={() => void distributionQuery.refetch()}
          minHeight={260}
        >
          <AppointmentsDonut data={distributionQuery.data} />
        </WidgetFrame>
      </div>

      <BotMiniPanel
        summary={summaryQuery.data}
        isLoading={summaryQuery.isPending}
        isError={summaryQuery.isError}
      />
    </div>
  );
}
