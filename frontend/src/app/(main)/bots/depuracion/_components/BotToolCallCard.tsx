"use client";

import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Badge,
  MessageBar,
  MessageBarBody,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { memo } from "react";

import { TOOL_CALL_STATUS_META } from "@/lib/constants/bots";
import { appTokens } from "@/lib/theme/brand";
import type { BotToolCallItem } from "@/types/bots.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    padding: tokens.spacingVerticalS,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
    backgroundColor: tokens.colorNeutralBackground2,
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  toolName: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontFamily: appTokens.fontMono,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeText,
    minWidth: 0,
    wordBreak: "break-all",
  },
  meta: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    flexShrink: 0,
  },
  jsonAccordion: {
    fontSize: tokens.fontSizeBase200,
  },
  pre: {
    margin: 0,
    padding: tokens.spacingVerticalXS,
    backgroundColor: tokens.colorNeutralBackground3,
    borderRadius: tokens.borderRadiusSmall,
    fontFamily: appTokens.fontMono,
    fontSize: tokens.fontSizeBase200,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    maxHeight: "260px",
    overflow: "auto",
  },
});

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * Span de una llamada a herramienta (`BotToolCall`), anidada bajo su turno.
 * Memoizada (la traza puede tener cientos de tool-calls; el refetch tras un
 * debug no debe re-renderizar todo). Args/result van colapsados en `<Accordion>`
 * — no se paga el `<pre>` hasta que el usuario lo abre.
 */
function BotToolCallCardImpl({ toolCall }: { toolCall: BotToolCallItem }) {
  const styles = useStyles();
  const meta = TOOL_CALL_STATUS_META[toolCall.status];
  const isError = toolCall.status === "error" || toolCall.status === "timeout";

  return (
    <div className={styles.root}>
      <div className={styles.topRow}>
        <span className={styles.toolName}>🔧 {toolCall.bot_tool_code ?? toolCall.bot_tool_id}</span>
        <span className={styles.meta}>
          <Badge appearance="tint" color={meta.color} aria-label={`Estado: ${meta.label}`}>
            {meta.glyph} {meta.label}
          </Badge>
          {toolCall.latency_ms !== null ? <span>{toolCall.latency_ms}ms</span> : null}
          {toolCall.tool_use_id ? (
            <Tooltip
              content={`tool_use_id: ${toolCall.tool_use_id}`}
              relationship="label"
              withArrow
            >
              <span style={{ cursor: "help" }}>ⓘ</span>
            </Tooltip>
          ) : null}
        </span>
      </div>

      {isError && toolCall.error_message ? (
        <MessageBar intent="error">
          <MessageBarBody>{toolCall.error_message}</MessageBarBody>
        </MessageBar>
      ) : null}

      <Accordion collapsible multiple className={styles.jsonAccordion}>
        <AccordionItem value="args">
          <AccordionHeader size="small">Ver argumentos</AccordionHeader>
          <AccordionPanel>
            <pre className={styles.pre}>{pretty(toolCall.arguments)}</pre>
          </AccordionPanel>
        </AccordionItem>
        {toolCall.result !== null ? (
          <AccordionItem value="result">
            <AccordionHeader size="small">Ver resultado</AccordionHeader>
            <AccordionPanel>
              <pre className={styles.pre}>{pretty(toolCall.result)}</pre>
            </AccordionPanel>
          </AccordionItem>
        ) : null}
      </Accordion>
    </div>
  );
}

export const BotToolCallCard = memo(BotToolCallCardImpl);
