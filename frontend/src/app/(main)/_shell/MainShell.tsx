"use client";

/**
 * Client-side shell for the protected `(main)` route group.
 *
 * Reads `LayoutProvider` to react to sidebar collapse state. Layout is
 * `topbar` row on top, then `sidebar | content` below — keeps the
 * hamburger button always visible regardless of sidebar state.
 */

import { makeStyles, tokens } from "@fluentui/react-components";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/layout/Sidebar/Sidebar";
import { TopBar } from "@/components/layout/TopBar/TopBar";
import { useLayout } from "@/providers/LayoutProvider";
import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  root: {
    display: "grid",
    gridTemplateRows: `${appTokens.topbarHeight} 1fr`,
    gridTemplateColumns: `${appTokens.sidebarWidth} 1fr`,
    gridTemplateAreas: `
      "topbar topbar"
      "sidebar content"
    `,
    height: "100vh",
    backgroundColor: appTokens.pageBg,
    transition: `grid-template-columns ${appTokens.shellAnimationMs} ease`,
  },
  rootCollapsed: {
    gridTemplateColumns: `${appTokens.sidebarWidthCollapsed} 1fr`,
  },
  topbar: { gridArea: "topbar" },
  sidebar: {
    gridArea: "sidebar",
    overflow: "hidden", // hide overflow when collapsing
  },
  content: {
    gridArea: "content",
    overflow: "auto",
    padding: tokens.spacingVerticalXL,
    backgroundColor: appTokens.pageBg,
  },
});

interface MainShellProps {
  children: ReactNode;
}

export function MainShell({ children }: MainShellProps) {
  const styles = useStyles();
  const { isSidebarCollapsed } = useLayout();

  return (
    <div className={`${styles.root} ${isSidebarCollapsed ? styles.rootCollapsed : ""}`}>
      <div className={styles.topbar}>
        <TopBar />
      </div>
      <div className={styles.sidebar}>
        <Sidebar />
      </div>
      <main className={styles.content}>{children}</main>
    </div>
  );
}
