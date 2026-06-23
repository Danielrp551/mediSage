"use client";

import { useEffect, useState } from "react";

import { formatRelative } from "@/lib/utils/date";

/**
 * Renderiza un tiempo relativo ("hace 3 min") SOLO tras el mount — `formatRelative` usa
 * `new Date()` (ahora), que en SSR corre en UTC y desfasaría la frontera del día en Lima
 * (UTC-5), produciendo un hydration mismatch. Antes del mount muestra "—" (estable en server
 * y cliente). Molde directo del `RelativeTime` de bots. (Lección operativa §5: cualquier
 * `now()` que afecte el render = client-only.)
 */
export function RelativeTime({ iso }: { iso: string | null | undefined }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return <>{mounted ? formatRelative(iso) : "—"}</>;
}
