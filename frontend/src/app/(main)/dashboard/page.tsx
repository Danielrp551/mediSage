import { requirePermission } from "@/lib/auth/session";

export const metadata = { title: "Dashboard" };

export default async function DashboardPage() {
  const claims = await requirePermission("MENU-HOME");
  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Welcome</h1>
      <p>
        You are signed in as <strong>{claims.sub}</strong> with {claims.permissions.length}{" "}
        permission(s).
      </p>
    </div>
  );
}
