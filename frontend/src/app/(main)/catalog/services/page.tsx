import { listActiveVerticals } from "@/actions/vertical.actions";
import { listServices } from "@/actions/service.actions";
import { requirePermission } from "@/lib/auth/session";
import type { QueryRequest } from "@/types/query.types";

import { ServicesClient } from "./_components/ServicesClient";

export const metadata = { title: "Servicios" };

interface PageProps {
  searchParams: Promise<{ vertical_id?: string }>;
}

export default async function ServicesPage({ searchParams }: PageProps) {
  await requirePermission("MENU-CATALOG");
  const { vertical_id } = await searchParams;

  const filters: QueryRequest["filters"] = vertical_id
    ? {
        filters: [
          {
            operator: "AND",
            conditions: [{ field: "vertical_id", operator: "eq", value: vertical_id }],
          },
        ],
      }
    : null;

  const [initialData, verticals] = await Promise.all([
    listServices({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "display_order", sort_order: "asc" },
      filters,
    }),
    listActiveVerticals(),
  ]);

  return <ServicesClient initialData={initialData} verticals={verticals} />;
}
