"use client";

/**
 * Welcome mínimo para usuarios SIN `DASHBOARD_VIEW` (ej. DOCTOR). `/dashboard` es la landing
 * tras login → NO se redirige (sería un loop); se degrada a este welcome con atajos según los
 * permisos del actor.
 *
 * ⚠ Es "use client" a propósito: importa `appTokens` (de `lib/theme/brand`, que a su vez importa
 * `@fluentui/react-components`). Si fuera Server Component, el barrel de react-components entraría
 * al grafo RSC y se evaluaría con el React restringido (sin `createContext`) → el build de App
 * Router falla al recolectar `/dashboard`. Como client component, el módulo es una referencia en
 * RSC y se evalúa con el React completo. (Mismo motivo por el que ningún Server Component del
 * template importa el design system directo.)
 */

import Link from "next/link";

import { appTokens } from "@/lib/theme/brand";

// Atajos posibles → se muestran sólo los que el actor tiene permiso de ver (mismo gating que
// el sidebar). Para el DOCTOR, su vista operativa es "Mi agenda".
const SHORTCUTS: { permission: string; label: string; href: string }[] = [
  { permission: "MY_APPOINTMENTS_READ", label: "Mi agenda", href: "/scheduling/mi-agenda" },
  { permission: "MY_DOCTOR_PROFILE_READ", label: "Mi perfil", href: "/staff/me/perfil" },
  { permission: "MY_LEADS_READ", label: "Mis leads", href: "/crm/mis-leads" },
  {
    permission: "MY_CONVERSATIONS_READ",
    label: "Mi bandeja",
    href: "/conversaciones/mis-conversaciones",
  },
];

export function WelcomeFallback({ permissions }: { permissions: string[] }) {
  const granted = new Set(permissions);
  const shortcuts = SHORTCUTS.filter((s) => granted.has(s.permission));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "12px", maxWidth: "640px" }}>
      <h1
        style={{
          margin: 0,
          fontSize: "28px",
          fontWeight: 600,
          color: appTokens.chromeText,
          letterSpacing: "-0.02em",
        }}
      >
        Bienvenido a Medisage
      </h1>
      <p style={{ margin: 0, fontSize: "15px", color: appTokens.chromeTextMuted }}>
        Usa el menú lateral para acceder a tu trabajo del día.
      </p>

      {shortcuts.length > 0 ? (
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginTop: "8px" }}>
          {shortcuts.map((s) => (
            <Link
              key={s.href}
              href={s.href}
              style={{
                padding: "10px 16px",
                borderRadius: "8px",
                border: `1px solid ${appTokens.tableBorder}`,
                backgroundColor: appTokens.contentBg,
                color: appTokens.chromeText,
                textDecoration: "none",
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              {s.label}
            </Link>
          ))}
        </div>
      ) : null}
    </div>
  );
}
