import { requirePermission } from "@/lib/auth/session";

import { BotDebugShell } from "./_components/BotDebugShell";

export const metadata = { title: "Depuración del bot" };

/**
 * Pantalla `/bots/depuracion` (F3a) — observabilidad read-only de la sesión del
 * bot en una conversación. Gated `BOT_EVENTS_READ` (lectura de la traza). Lee el
 * `?conv=<conversation_id>` del query; si no hay, el shell muestra el selector.
 * El fetch del estado/traza es client-side (el shell maneja el 404 como empty).
 */
export default async function BotDebugPage({
  searchParams,
}: {
  searchParams: Promise<{ conv?: string }>;
}) {
  await requirePermission("BOT_EVENTS_READ");
  const { conv } = await searchParams;

  return <BotDebugShell initialConv={conv ?? null} />;
}
