"use client";

/**
 * Superficie de un widget del panel con su header y manejo de estados **aislados**
 * (lección §23): loading (skeleton), error (MessageBar + reintentar), sin-datos
 * (mensaje), refetching (atenúa lo visible + spinner). Un widget caído nunca rompe
 * el panel — sólo este recuadro cambia de estado. NO hay spinner global.
 */

import {
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  SkeletonItem,
  Spinner,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import { DataBarVerticalRegular } from "@fluentui/react-icons";
import type { ReactNode } from "react";

import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  surface: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalL,
    backgroundColor: appTokens.contentBg,
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    boxShadow: tokens.shadow2,
    minWidth: 0, // permite que el contenido (charts) encoja dentro de un flex/grid
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.01em",
  },
  body: { position: "relative", minWidth: 0 },
  bodyDim: {
    opacity: 0.55,
    pointerEvents: "none",
    transition: "opacity 150ms ease",
  },
  refetchSpinner: {
    position: "absolute",
    top: 0,
    right: 0,
    zIndex: 1,
  },
  center: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    gap: tokens.spacingVerticalS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase300,
  },
});

interface WidgetFrameProps {
  title: string;
  /** Slot a la derecha del título (badge, valor destacado, etc.). */
  headerRight?: ReactNode;
  /** Primera carga sin datos previos → skeleton. */
  isLoading: boolean;
  /** Re-fetch con datos visibles → atenúa + spinner (no vacía el widget). */
  isRefetching: boolean;
  isError: boolean;
  /** El backend devolvió 0 (rollup vacío en el rango) → estado sin-datos, NO error. */
  isEmpty: boolean;
  emptyLabel: string;
  onRetry: () => void;
  /** Alto reservado para skeleton / estados centrados (evita CLS al hidratar charts). */
  minHeight: number;
  children: ReactNode;
}

export function WidgetFrame({
  title,
  headerRight,
  isLoading,
  isRefetching,
  isError,
  isEmpty,
  emptyLabel,
  onRetry,
  minHeight,
  children,
}: WidgetFrameProps) {
  const styles = useStyles();

  return (
    <section className={styles.surface}>
      <div className={styles.header}>
        <h2 className={styles.title}>{title}</h2>
        {headerRight ?? null}
      </div>

      {isError ? (
        <MessageBar intent="error">
          <MessageBarBody>No se pudo cargar {title.toLowerCase()}.</MessageBarBody>
          <MessageBarActions
            containerAction={
              <Button appearance="transparent" size="small" onClick={onRetry}>
                Reintentar
              </Button>
            }
          />
        </MessageBar>
      ) : isLoading ? (
        <SkeletonItem style={{ height: minHeight }} />
      ) : isEmpty ? (
        <div className={styles.center} style={{ minHeight }}>
          <DataBarVerticalRegular fontSize={28} />
          <span>{emptyLabel}</span>
        </div>
      ) : (
        <div className={styles.body}>
          {isRefetching ? (
            <span className={styles.refetchSpinner}>
              <Spinner size="tiny" aria-label="Actualizando" />
            </span>
          ) : null}
          <div className={mergeClasses(isRefetching && styles.bodyDim)}>{children}</div>
        </div>
      )}
    </section>
  );
}
