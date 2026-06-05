import { listBotTools } from "@/actions/bot-tools.actions";
import { requirePermission } from "@/lib/auth/session";

import { BotToolsClient } from "./_components/BotToolsClient";

export const metadata = { title: "Herramientas" };

export default async function BotToolsPage() {
  await requirePermission("BOT_TOOLS_READ");

  const initialData = await listBotTools({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "created_on", sort_order: "desc" },
    filters: null,
  });

  return <BotToolsClient initialData={initialData} />;
}
