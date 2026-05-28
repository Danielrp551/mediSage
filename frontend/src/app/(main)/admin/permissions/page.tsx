import { listPermissions } from "@/actions/permission.actions";
import { requirePermission } from "@/lib/auth/session";
import { PermissionsClient } from "./_components/PermissionsClient";

export const metadata = { title: "Permisos" };

export default async function PermissionsPage() {
  await requirePermission("MENU-ADMIN-PERMISSIONS");
  const initial = await listPermissions({ pagination: { skip: 0, limit: 10 } });
  return <PermissionsClient initialData={initial} />;
}
