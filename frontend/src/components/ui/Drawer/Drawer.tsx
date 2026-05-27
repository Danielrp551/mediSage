"use client";

import {
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  OverlayDrawer,
} from "@fluentui/react-components";
import { DismissRegular } from "@fluentui/react-icons";
import type { ReactNode } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: "small" | "medium" | "large";
  children: ReactNode;
  footer?: ReactNode;
}

export function Drawer({ open, onClose, title, subtitle, size = "medium", children, footer }: DrawerProps) {
  return (
    <OverlayDrawer open={open} onOpenChange={(_, data) => !data.open && onClose()} position="end" size={size}>
      <DrawerHeader>
        <DrawerHeaderTitle
          action={
            <Button appearance="subtle" icon={<DismissRegular />} aria-label="Close" onClick={onClose} />
          }
        >
          {title}
          {subtitle ? <div style={{ fontSize: 12, color: "var(--colorNeutralForeground3)" }}>{subtitle}</div> : null}
        </DrawerHeaderTitle>
      </DrawerHeader>
      <DrawerBody>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>{children}</div>
        {footer ? (
          <div style={{ marginTop: 24, display: "flex", justifyContent: "flex-end", gap: 8 }}>{footer}</div>
        ) : null}
      </DrawerBody>
    </OverlayDrawer>
  );
}
