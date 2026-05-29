import { listActiveBranches } from "@/actions/branch.actions";
import { listOffices } from "@/actions/office.actions";
import { requirePermission } from "@/lib/auth/session";
import type { QueryRequest } from "@/types/query.types";

import { OfficesClient } from "./_components/OfficesClient";

export const metadata = { title: "Consultorios" };

interface PageProps {
  searchParams: Promise<{ branch_id?: string }>;
}

export default async function OfficesPage({ searchParams }: PageProps) {
  await requirePermission("MENU-CLINIC");
  const { branch_id } = await searchParams;

  const filters: QueryRequest["filters"] = branch_id
    ? {
        filters: [
          {
            operator: "AND",
            conditions: [{ field: "branch_id", operator: "eq", value: branch_id }],
          },
        ],
      }
    : null;

  const [initialData, branches] = await Promise.all([
    listOffices({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "name", sort_order: "asc" },
      filters,
    }),
    listActiveBranches(),
  ]);

  return <OfficesClient initialData={initialData} branches={branches} />;
}
