import { listActiveRoles } from "@/actions/role.actions";
import { listActivePermissions } from "@/actions/permission.actions";
import { listUsers } from "@/actions/user.actions";
import { requirePermission } from "@/lib/auth/session";
import { UsersClient } from "./_components/UsersClient";

export const metadata = { title: "Users" };

export default async function UsersPage() {
  await requirePermission("MENU-ADMIN-USERS");

  // Pre-fetch on the server — pages render with data already on screen.
  const [initial, roles, permissions] = await Promise.all([
    listUsers({ pagination: { skip: 0, limit: 10 } }),
    listActiveRoles(),
    listActivePermissions(),
  ]);

  return (
    <UsersClient
      initialData={initial}
      roles={roles}
      permissions={permissions}
    />
  );
}
