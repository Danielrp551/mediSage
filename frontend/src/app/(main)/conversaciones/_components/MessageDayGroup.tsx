"use client";

import { makeStyles, tokens } from "@fluentui/react-components";

import { appTokens } from "@/lib/theme/brand";
import type { MessageItem } from "@/types/conversations.types";

import { MessageBubble } from "./MessageBubble";

const useStyles = makeStyles({
  group: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  separatorRow: {
    display: "flex",
    justifyContent: "center",
    margin: `${tokens.spacingVerticalS} 0`,
  },
  separator: {
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusCircular,
    backgroundColor: tokens.colorNeutralBackground2,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    textTransform: "capitalize",
  },
});

export interface DayGroupData {
  key: string;
  label: string;
  items: MessageItem[];
}

interface Props {
  group: DayGroupData;
}

/**
 * Una sección del hilo: separador de día ("Hoy"/"Ayer"/"12 may 2026") + las
 * burbujas de ese día. La etiqueta del día se calcula client-only en el padre
 * (`ConversationThread`) — el SSR en UTC desfasaría la frontera del día en Lima
 * (UTC-5). Las burbujas van ascendentes por `sent_at` (lo más nuevo abajo, orden
 * natural de chat).
 */
export function MessageDayGroup({ group }: Props) {
  const styles = useStyles();
  return (
    <div className={styles.group}>
      <div className={styles.separatorRow}>
        <span className={styles.separator}>{group.label}</span>
      </div>
      {group.items.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
