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

  // Orden por `created_on` (columna real). full_name/email NO son columnas de
  // `doctor` (se denormalizan del User) → no están en ALLOWED_FIELDS y el query
  // builder responde 400 si se ordena/filtra por ellas (whitelist estricta). La
  // búsqueda por nombre es client-side (ver DoctorsClient). El sort DEBE coincidir
  // con el defaultSort del cliente para que initialData se use sin refetch.
  // Las sedes y verticales activas pueblan los Dropdowns de filtro Y el drawer de
  // creación (multiselect). Reusan los /active de clinic y catalog.
  const [initialData, branches, verticals] = await Promise.all([
    listDoctors({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "created_on", sort_order: "desc" },
      filters,
    }),
    listActiveBranches(),
    listActiveVerticals(),
  ]);

  return <DoctorsClient initialData={initialData} branches={branches} verticals={verticals} />;
}
