"use client";

import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
} from "@fluentui/react-components";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog(props: ConfirmDialogProps) {
  return (
    <Dialog open={props.open} onOpenChange={(_, data) => !data.open && props.onCancel()}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>{props.title}</DialogTitle>
          <DialogContent>{props.description}</DialogContent>
          <DialogActions>
            <Button appearance="secondary" onClick={props.onCancel}>
              {props.cancelText ?? "Cancelar"}
            </Button>
            <Button appearance={props.destructive ? "primary" : "primary"} onClick={props.onConfirm}>
              {props.confirmText ?? "Confirmar"}
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
