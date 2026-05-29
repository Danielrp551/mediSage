"use client";

import { makeStyles, mergeClasses, tokens } from "@fluentui/react-components";
import {
  AppsListRegular,
  BoxRegular,
  BriefcaseRegular,
  BuildingMultipleRegular,
  BuildingRegular,
  ChevronRightRegular,
  ConferenceRoomRegular,
  HomeRegular,
  LockClosedRegular,
  PeopleRegular,
  SettingsRegular,
  ShieldRegular,
  TagRegular,
} from "@fluentui/react-icons";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState, type ReactElement } from "react";

import { NAV_ITEMS, type NavItem } from "@/lib/constants/navigation";
import { appTokens } from "@/lib/theme/brand";
import { useAuth } from "@/providers/AuthProvider";
import { useLayout } from "@/providers/LayoutProvider";

const ICONS: Record<string, ReactElement> = {
  HomeRegular: <HomeRegular />,
  SettingsRegular: <SettingsRegular />,
  PeopleRegular: <PeopleRegular />,
  ShieldRegular: <ShieldRegular />,
  LockClosedRegular: <LockClosedRegular />,
  // Catalog module
  AppsListRegular: <AppsListRegular />,
  TagRegular: <TagRegular />,
  BriefcaseRegular: <BriefcaseRegular />,
  BoxRegular: <BoxRegular />,
  // Clinic module
  BuildingMultipleRegular: <BuildingMultipleRegular />,
  BuildingRegular: <BuildingRegular />,
  ConferenceRoomRegular: <ConferenceRoomRegular />,
};

const useStyles = makeStyles({
  root: {
    width: appTokens.sidebarWidth,
    height: "100%",
    backgroundColor: appTokens.chromeBg,
    borderRight: `1px solid ${appTokens.chromeBorder}`,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    transition: `transform ${appTokens.shellAnimationMs} ease, opacity ${appTokens.shellAnimationMs} ease`,
  },
  rootCollapsed: {
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
  },
  brand: {
    padding: `${tokens.spacingVerticalL} ${tokens.spacingHorizontalL}`,
    borderBottom: `1px solid ${appTokens.chromeBorder}`,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  brandTitle: {
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.01em",
  },
  brandSubtitle: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  nav: {
    flex: 1,
    overflowY: "auto",
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalS}`,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  group: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  groupHeader: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeTextMuted,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    cursor: "pointer",
    userSelect: "none",
    borderRadius: tokens.borderRadiusMedium,
    "&:hover": { backgroundColor: appTokens.chromeBgHover },
  },
  groupChevron: {
    marginLeft: "auto",
    transition: `transform ${appTokens.shellAnimationMs} ease`,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
  },
  groupChevronOpen: { transform: "rotate(90deg)" },
  groupItems: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    paddingLeft: tokens.spacingHorizontalS,
  },
  item: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    padding: `${tokens.spacingVerticalSNudge} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusMedium,
    color: appTokens.chromeText,
    textDecoration: "none",
    fontSize: tokens.fontSizeBase300,
    transition: "background-color 120ms ease, color 120ms ease",
    position: "relative",
    "&:hover": { backgroundColor: appTokens.chromeBgHover },
  },
  itemActive: {
    backgroundColor: appTokens.chromeBgActive,
    color: tokens.colorBrandForeground1,
    fontWeight: tokens.fontWeightSemibold,
    "&::before": {
      content: '""',
      position: "absolute",
      left: 0,
      top: "6px",
      bottom: "6px",
      width: "3px",
      borderRadius: "0 2px 2px 0",
      backgroundColor: tokens.colorBrandBackground,
    },
  },
  itemIcon: {
    fontSize: "20px",
    display: "inline-flex",
    color: "currentColor",
  },
});

function filterByPermissions(items: NavItem[], hasAny: (codes: string[]) => boolean): NavItem[] {
  return items
    .map((item) => {
      const children = item.children ? filterByPermissions(item.children, hasAny) : undefined;
      const allowed = !item.permissions || hasAny(item.permissions);
      if (!allowed && !(children && children.length)) return null;
      return { ...item, children } as NavItem;
    })
    .filter((x): x is NavItem => x !== null);
}

export function Sidebar() {
  const styles = useStyles();
  const { hasAnyPermission } = useAuth();
  const { isSidebarCollapsed } = useLayout();
  const pathname = usePathname();

  const items = useMemo(() => filterByPermissions(NAV_ITEMS, hasAnyPermission), [hasAnyPermission]);

  return (
    <aside
      className={mergeClasses(styles.root, isSidebarCollapsed && styles.rootCollapsed)}
      aria-label="Navegación principal"
    >
      <div className={styles.brand}>
        <span className={styles.brandTitle}>Medisage</span>
        <span className={styles.brandSubtitle}>Consola admin</span>
      </div>

      <nav className={styles.nav} aria-label="Navegación principal">
        {items.map((item) =>
          item.children && item.children.length > 0 ? (
            <NavGroup key={item.key} item={item} pathname={pathname} styles={styles} />
          ) : (
            <NavLeaf key={item.key} item={item} pathname={pathname} styles={styles} />
          ),
        )}
      </nav>
    </aside>
  );
}

interface NavStyles {
  group: string;
  groupHeader: string;
  groupChevron: string;
  groupChevronOpen: string;
  groupItems: string;
  item: string;
  itemActive: string;
  itemIcon: string;
}

function NavGroup({
  item,
  pathname,
  styles,
}: {
  item: NavItem;
  pathname: string;
  styles: NavStyles;
}) {
  // A group is expanded by default when any child is active.
  const isAnyChildActive = item.children?.some((c) => c.url && pathname.startsWith(c.url)) ?? false;
  const [open, setOpen] = useState(isAnyChildActive);

  return (
    <div className={styles.group}>
      <div
        className={styles.groupHeader}
        role="button"
        tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
        aria-expanded={open}
      >
        {item.label}
        <ChevronRightRegular
          className={mergeClasses(styles.groupChevron, open && styles.groupChevronOpen)}
        />
      </div>
      {open ? (
        <div className={styles.groupItems}>
          {item.children!.map((child) => (
            <NavLeaf key={child.key} item={child} pathname={pathname} styles={styles} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function NavLeaf({
  item,
  pathname,
  styles,
}: {
  item: NavItem;
  pathname: string;
  styles: NavStyles;
}) {
  const icon = ICONS[item.icon];
  const isActive = item.url ? pathname.startsWith(item.url) : false;
  const href = item.url ?? "#";

  return (
    <Link
      href={href}
      className={mergeClasses(styles.item, isActive && styles.itemActive)}
      aria-current={isActive ? "page" : undefined}
    >
      {icon ? <span className={styles.itemIcon}>{icon}</span> : null}
      <span>{item.label}</span>
    </Link>
  );
}
