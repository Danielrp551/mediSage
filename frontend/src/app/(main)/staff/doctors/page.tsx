import { listActiveBranches } from "@/actions/branch.actions";
import { listDoctors } from "@/actions/doctor.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import type { QueryRequest } from "@/types/query.types";

import { DoctorsClient } from "./_components/DoctorsClient";

export const metadata = { title: "Doctores" };

interface PageProps {
  searchParams: Promise<{ branch_id?: string; vertical_id?: string }>;
}

export default async function DoctorsPage({ searchParams }: PageProps) {
  await requirePermission("MENU-STAFF");
  const { branch_id, vertical_id } = await searchParams;

  const conditions: { field: string; operator: "eq"; value: string }[] = [];
  if (branch_id) conditions.push({ field: "branch_id", operator: "eq", value: branch_id });
  if (vertical_id) conditions.push({ field: "vertical_id", operator: "eq", value: vertical_id });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  // Las sedes y verticales activas pueblan los Dropdowns de filtro Y el drawer de
  // creación (multiselect). Reusan los /active de clinic y catalog.
  const [initialData, branches, verticals] = await Promise.all([
    listDoctors({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "full_name", sort_order: "asc" },
      filters,
    }),
    listActiveBranches(),
    listActiveVerticals(),
  ]);

  return <DoctorsClient initialData={initialData} branches={branches} verticals={verticals} />;
}
