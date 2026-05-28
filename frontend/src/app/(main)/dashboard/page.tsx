import { requirePermission } from "@/lib/auth/session";

export const metadata = { title: "Inicio" };

export default async function DashboardPage() {
  const claims = await requirePermission("MENU-HOME");
  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Bienvenido</h1>
      <p>
        Has iniciado sesión como <strong>{claims.sub}</strong> con{" "}
        {claims.permissions.length} permiso(s).
      </p>
    </div>
  );
}
