import { listPromotions } from "@/actions/promotion.actions";
import { listActiveProducts } from "@/actions/product.actions";
import { requirePermission } from "@/lib/auth/session";

import { PromotionsClient } from "./_components/PromotionsClient";

export const metadata = { title: "Promociones" };

export default async function PromotionsPage() {
  await requirePermission("PROMOTIONS_READ");

  // Prefetch en paralelo: la primera página de promociones (sirve a la query
  // default de useTableQuery sin refetch) + el catálogo de productos activos
  // (opciones del editor M:N del PromotionDrawer).
  const [initialData, products] = await Promise.all([
    listPromotions({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "created_on", sort_order: "desc" },
      filters: null,
    }),
    listActiveProducts(),
  ]);

  return <PromotionsClient initialData={initialData} products={products} />;
}
