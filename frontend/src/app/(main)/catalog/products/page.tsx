import { listProducts } from "@/actions/product.actions";
import { listActiveServices } from "@/actions/service.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import type { QueryRequest } from "@/types/query.types";

import { ProductsClient } from "./_components/ProductsClient";

export const metadata = { title: "Productos" };

interface PageProps {
  searchParams: Promise<{ vertical_id?: string; service_id?: string }>;
}

export default async function ProductsPage({ searchParams }: PageProps) {
  await requirePermission("MENU-CATALOG");
  const { vertical_id, service_id } = await searchParams;

  // A service filter is the most specific; otherwise fall back to the vertical
  // (products carry a denormalized vertical_id so this filters server-side).
  const filters: QueryRequest["filters"] = service_id
    ? {
        filters: [
          {
            operator: "AND",
            conditions: [{ field: "service_id", operator: "eq", value: service_id }],
          },
        ],
      }
    : vertical_id
      ? {
          filters: [
            {
              operator: "AND",
              conditions: [{ field: "vertical_id", operator: "eq", value: vertical_id }],
            },
          ],
        }
      : null;

  const [initialData, verticals, services] = await Promise.all([
    listProducts({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "name", sort_order: "asc" },
      filters,
    }),
    listActiveVerticals(),
    listActiveServices(vertical_id),
  ]);

  return <ProductsClient initialData={initialData} verticals={verticals} services={services} />;
}
