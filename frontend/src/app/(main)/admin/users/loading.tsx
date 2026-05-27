"use client";

// Fluent UI 9 es 100% client (usa React Context). En Next.js 16 con Turbopack,
// un loading.tsx sin "use client" se evalúa en el runtime RSC donde
// createContext no existe — crashea con `d.createContext is not a function`
// y rompe la ruta entera en SSR (no solo el loading). Mantener este "use client".
import { Spinner } from "@fluentui/react-components";

export default function Loading() {
  return (
    <div style={{ padding: 48, textAlign: "center" }}>
      <Spinner label="Loading users…" />
    </div>
  );
}
