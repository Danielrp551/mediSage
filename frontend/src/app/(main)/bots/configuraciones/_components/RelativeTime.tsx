"use client";

import { useEffect, useState } from "react";

import { formatRelative } from "@/lib/utils/date";

/**
 * Renderiza un tiempo relativo ("hace 2 días") SOLO tras el mount — `formatRelative`
 * usa `new Date()` (ahora), que en SSR corre en UTC y desfasaría la frontera del día
 * en Lima (UTC-5), produciendo un hydration mismatch. Antes del mount muestra un
 * placeholder estable ("—") idéntico en server y cliente.
 */
export function RelativeTime({ iso }: { iso: string | null | undefined }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return <>{mounted ? formatRelative(iso) : "—"}</>;
}
