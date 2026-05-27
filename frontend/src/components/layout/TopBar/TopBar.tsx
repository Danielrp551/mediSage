"use client";

import {
  Avatar,
  Button,
  Divider,
  Menu,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  Tooltip,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  NavigationRegular,
  PersonRegular,
  SignOutRegular,
} from "@fluentui/react-icons";
import { useTransition } from "react";

import { logoutAction } from "@/actions/auth.actions";
import { appTokens } from "@/lib/theme/brand";
import { useAuth } from "@/providers/AuthProvider";
import { useLayout } from "@/providers/LayoutProvider";

const useStyles = makeStyles({
  root: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    height: appTokens.topbarHeight,
    padding: `0 ${tokens.spacingHorizontalL}`,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.contentBg,
    position: "relative",
    zIndex: 5,
  },
  leftCluster: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
  },
  title: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.01em",
  },
  spacer: { flex: 1 },
  avatarTrigger: {
    minWidth: 0,
    padding: tokens.spacingHorizontalXS,
    borderRadius: tokens.borderRadiusCircular,
  },
  userBlock: {
    display: "flex",
    flexDirection: "column",
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    gap: tokens.spacingVerticalXXS,
    cursor: "default",
  },
  userName: {
    fontWeight: tokens.fontWeightSemibold,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
  },
  userEmail: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
});

function getInitials(user: { first_name?: string; last_name?: string } | null): string {
  if (!user) return "?";
  return ((user.first_name?.[0] ?? "") + (user.last_name?.[0] ?? "")).toUpperCase() || "?";
}

export function TopBar() {
  const styles = useStyles();
  const { user } = useAuth();
  const { isSidebarCollapsed, toggleSidebar } = useLayout();
  // Server Actions that call `redirect()` only navigate the client when
  // invoked from a form action or inside `startTransition`. A bare
  // `onClick={() => logoutAction()}` runs the action server-side but the
  // redirect is lost — that's why "Sign out" was a no-op.
  const [isSigningOut, startSignOut] = useTransition();

  return (
    <header className={styles.root}>
      <div className={styles.leftCluster}>
        <Tooltip
          content={isSidebarCollapsed ? "Show navigation" : "Hide navigation"}
          relationship="label"
        >
          <Button
            appearance="subtle"
            icon={<NavigationRegular />}
            onClick={toggleSidebar}
            aria-label={isSidebarCollapsed ? "Show navigation" : "Hide navigation"}
            aria-expanded={!isSidebarCollapsed}
          />
        </Tooltip>
        <div className={styles.title}>Medisage</div>
      </div>

      <div className={styles.spacer} />

      <Menu positioning="below-end">
        <MenuTrigger disableButtonEnhancement>
          <Button
            appearance="subtle"
            className={styles.avatarTrigger}
            aria-label="Open user menu"
          >
            <Avatar
              name={user?.full_name}
              initials={getInitials(user)}
              color="colorful"
              size={32}
            />
          </Button>
        </MenuTrigger>
        <MenuPopover>
          <div className={styles.userBlock}>
            <span className={styles.userName}>{user?.full_name ?? "—"}</span>
            <span className={styles.userEmail}>{user?.email ?? ""}</span>
          </div>
          <Divider />
          <MenuList>
            <MenuItem icon={<PersonRegular />} disabled>
              My profile
            </MenuItem>
            <MenuItem
              icon={<SignOutRegular />}
              disabled={isSigningOut}
              onClick={() => startSignOut(() => logoutAction())}
            >
              {isSigningOut ? "Signing out…" : "Sign out"}
            </MenuItem>
          </MenuList>
        </MenuPopover>
      </Menu>
    </header>
  );
}
