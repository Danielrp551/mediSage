"use client";

/**
 * Badge "Actualizado hace N min" (de `DashboardMeta.last_refreshed_at`). El cálculo es
 * relativo a `new Date()` → **client-only**: nace `now=null` (placeholder neutro en SSR/primer
 * paint) y se setea en un efecto, evitando el hydration mismatch de TZ/tiempo (lección §22).
 * Re-tickea cada 60 s para que el "hace N min" avance. Si la frescura supera 3× el intervalo
 * de refresco (señal de job caído), el badge se pone en `warning` pero el panel SIGUE mostrando
 * el último rollup bueno (degrada con gracia).
 */

import { Badge, Tooltip } from "@fluentui/react-components";
import { useEffect, useState } from "react";

import { formatDate, formatRelative } from "@/lib/utils/date";

const STALE_FACTOR = 3;

interface Props {
  lastRefreshedAt: string | null;
  intervalMinutes: number;
}

export function FreshnessBadge({ lastRefreshedAt, intervalMinutes }: Props) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);

  if (now === null) {
    return (
      <Badge appearance="tint" color="informative">
        Actualizado
      </Badge>
    );
  }
  if (!lastRefreshedAt) {
    return (
      <Badge appearance="tint" color="informative">
        Aún sin actualizar
      </Badge>
    );
  }

  const ageMin = (now - new Date(lastRefreshedAt).getTime()) / 60_000;
  const stale = ageMin > intervalMinutes * STALE_FACTOR;
  const tip = stale
    ? "El panel puede estar desactualizado."
    : `Última actualización: ${formatDate(lastRefreshedAt)}`;

  return (
    <Tooltip content={tip} relationship="label" withArrow>
      <Badge appearance="tint" color={stale ? "warning" : "informative"}>
        Actualizado {formatRelative(lastRefreshedAt)}
      </Badge>
    </Tooltip>
  );
}
