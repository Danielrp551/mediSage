"use client";

/**
 * Three-dot action menu for table rows.
 *
 * Standard usage in a CRUD table — collapses all per-row affordances
 * (View, Edit, Disable, etc.) into a single icon button that opens a
 * Fluent UI menu. Same pattern as KAM Digital so users navigate either
 * console without re-learning.
 *
 * Permissions are checked here so each *Client.tsx page doesn't have
 * to wrap every action in `<PermissionGuard>` — declarative array.
 */

import {
  Menu,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  Button,
  Tooltip,
} from "@fluentui/react-components";
import { MoreHorizontalRegular } from "@fluentui/react-icons";
import type { ReactElement } from "react";

import { useAuth } from "@/providers/AuthProvider";

export interface RowAction<T> {
  /** Stable key for React reconciliation. */
  key: string;
  label: string;
  // Must be `ReactElement` (not `ReactNode`) — Fluent UI `MenuItem.icon` is a
  // slot, which doesn't accept primitives like `bigint`/`string` that
  // `ReactNode` allows. A JSX element (e.g. `<EditRegular />`) is the right
  // shape.
  icon?: ReactElement;
  /** If set, the action is hidden unless the user has any of these permissions. */
  permissions?: string[];
  /** Renders with destructive styling and a confirm-friendly affordance. */
  danger?: boolean;
  /** Disabled state — keeps the row in the menu but unclickable. */
  disabled?: (item: T) => boolean;
  onSelect: (item: T) => void;
}

interface RowActionsProps<T> {
  item: T;
  actions: RowAction<T>[];
  /** Tooltip on the trigger. Default: "Actions". */
  triggerLabel?: string;
}

export function RowActions<T>({ item, actions, triggerLabel = "Actions" }: RowActionsProps<T>) {
  const { hasAnyPermission } = useAuth();

  // Filter out actions the user can't perform — if nothing left, render
  // nothing so we don't leave a useless trigger button.
  const visible = actions.filter(
    (a) => !a.permissions?.length || hasAnyPermission(a.permissions),
  );
  if (visible.length === 0) return null;

  return (
    <Menu positioning="below-start">
      <MenuTrigger disableButtonEnhancement>
        <Tooltip content={triggerLabel} relationship="label">
          <Button
            appearance="subtle"
            icon={<MoreHorizontalRegular />}
            aria-label={triggerLabel}
            size="small"
            onClick={(e) => e.stopPropagation()}
          />
        </Tooltip>
      </MenuTrigger>
      <MenuPopover>
        <MenuList>
          {visible.map((action) => (
            <MenuItem
              key={action.key}
              icon={action.icon}
              disabled={action.disabled?.(item)}
              onClick={(e) => {
                e.stopPropagation();
                action.onSelect(item);
              }}
            >
              {action.label}
            </MenuItem>
          ))}
        </MenuList>
      </MenuPopover>
    </Menu>
  );
}
