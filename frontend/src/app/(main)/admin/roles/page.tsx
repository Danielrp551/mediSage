import { listRoles } from "@/actions/role.actions";
import { listActivePermissions } from "@/actions/permission.actions";
import { requirePermission } from "@/lib/auth/session";
import { RolesClient } from "./_components/RolesClient";

export const metadata = { title: "Roles" }; // identifier and label coincide en español

export default async function RolesPage() {
  await requirePermission("MENU-ADMIN-ROLES");
  const [initial, permissions] = await Promise.all([
    listRoles({ pagination: { skip: 0, limit: 10 } }),
    listActivePermissions(),
  ]);
  return <RolesClient initialData={initial} permissions={permissions} />;
}
