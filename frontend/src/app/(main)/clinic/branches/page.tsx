import { listBranches } from "@/actions/branch.actions";
import { requirePermission } from "@/lib/auth/session";

import { BranchesClient } from "./_components/BranchesClient";

export const metadata = { title: "Sedes" };

export default async function BranchesPage() {
  await requirePermission("MENU-CLINIC");

  const initialData = await listBranches({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "name", sort_order: "asc" },
  });

  return <BranchesClient initialData={initialData} />;
}
