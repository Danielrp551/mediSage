import { listBotConfigurations } from "@/actions/bots.actions";
import { requirePermission } from "@/lib/auth/session";

import { BotConfigurationsClient } from "./_components/BotConfigurationsClient";

export const metadata = { title: "Configuraciones de bot" };

export default async function BotConfigurationsPage() {
  await requirePermission("BOT_CONFIGURATIONS_READ");

  const initialData = await listBotConfigurations({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "created_on", sort_order: "desc" },
    filters: null,
  });

  return <BotConfigurationsClient initialData={initialData} />;
}
