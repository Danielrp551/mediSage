import { listVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { VerticalsClient } from "./_components/VerticalsClient";

export const metadata = { title: "Verticales" };

export default async function VerticalsPage() {
  await requirePermission("MENU-CATALOG");

  const initialData = await listVerticals({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "display_order", sort_order: "asc" },
  });

  return <VerticalsClient initialData={initialData} />;
}
