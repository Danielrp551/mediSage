"use client";

import {
  Button,
  Divider,
  Input,
  MessageBar,
  MessageBarBody,
  Switch,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createCustomerStatus, updateCustomerStatus } from "@/actions/customer-status.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { usePermissions } from "@/hooks/usePermissions";
import {
  customerStatusCreateSchema,
  type CustomerStatusCreateInput,
} from "@/lib/schemas/customer-status.schema";
import { appTokens } from "@/lib/theme/brand";
import type { CustomerStatusItem } from "@/types/crm.types";

import { StatusMatrixEditor } from "../../estados-lead/_components/StatusMatrixEditor";

const useStyles = makeStyles({
  body: {
    paddingTop: tokens.spacingVerticalS,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  twoCol: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: tokens.spacingHorizontalM,
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    marginTop: tokens.spacingVerticalXXS,
  },
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  colorRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  swatch: {
    display: "inline-block",
    width: "28px",
    height: "28px",
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${appTokens.chromeBorder}`,
    flexShrink: 0,
  },
  swatchEmpty: { border: `1px dashed ${appTokens.chromeBorder}`, background: "transparent" },
});

interface Props {
  mode: "create" | "edit";
  // En edición el cliente pasa la fila completa (el listado ya la tiene en memoria).
  status: CustomerStatusItem | null;
  onClose: () => void;
}

type FormValues = CustomerStatusCreateInput & { active?: boolean };

export function CustomerStatusDrawer({ mode, status, onClose }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("CUSTOMER_STATUSES_WRITE");

  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const isEdit = mode === "edit";
  const statusId = status?.id ?? null;

  const form = useForm<FormValues>({
    resolver: zodResolver(customerStatusCreateSchema),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      color: "",
      is_initial: false,
      is_final: false,
      display_order: 0,
      active: true,
    },
  });

  useEffect(() => {
    if (!status) return;
    form.reset({
      code: status.code,
      name: status.name,
      description: status.description ?? "",
      color: status.color ?? "",
      is_initial: status.is_initial,
      is_final: status.is_final,
      display_order: status.display_order,
      active: status.active,
    });
  }, [status, form]);

  const isInitial = form.watch("is_initial");
  const isFinal = form.watch("is_final");
  const color = form.watch("color");

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result =
        statusId !== null
          ? await updateCustomerStatus(statusId, values)
          : await createCustomerStatus(values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
    });
  });

  return (
    <Drawer
      open
      onClose={onClose}
      title={isEdit ? "Editar estado de cliente" : "Nuevo estado de cliente"}
      subtitle={form.watch("code") || undefined}
      size="medium"
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button
            appearance="primary"
            disabled={pending || !canWrite}
            onClick={() => void onSubmit()}
          >
            {pending ? "Guardando…" : isEdit ? "Guardar cambios" : "Crear estado"}
          </Button>
        </>
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.body}>
        <FormField
          label="Código"
          required
          error={form.formState.errors.code?.message}
          hint="Mayúsculas, sin espacios (ej. ACTIVO). No se puede cambiar después."
        >
          <Controller
            control={form.control}
            name="code"
            render={({ field }) => (
              <Input {...field} disabled={!canWrite || isEdit} placeholder="ej. ACTIVO" />
            )}
          />
        </FormField>

        <FormField label="Nombre" required error={form.formState.errors.name?.message}>
          <Controller
            control={form.control}
            name="name"
            render={({ field }) => (
              <Input {...field} disabled={!canWrite} placeholder="ej. Cliente activo" />
            )}
          />
        </FormField>

        <FormField label="Descripción" error={form.formState.errors.description?.message}>
          <Controller
            control={form.control}
            name="description"
            render={({ field }) => (
              <Input
                {...field}
                value={field.value ?? ""}
                disabled={!canWrite}
                placeholder="Breve descripción del estado…"
              />
            )}
          />
        </FormField>

        <div className={styles.twoCol}>
          <FormField label="Color" error={form.formState.errors.color?.message} hint="Hex #RRGGBB">
            <Controller
              control={form.control}
              name="color"
              render={({ field }) => (
                <div className={styles.colorRow}>
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    disabled={!canWrite}
                    placeholder="#22C55E"
                  />
                  <span
                    className={`${styles.swatch} ${color ? "" : styles.swatchEmpty}`}
                    style={color ? { backgroundColor: color } : undefined}
                    aria-label={color ?? "sin color"}
                  />
                </div>
              )}
            />
          </FormField>
          <FormField
            label="Orden"
            error={form.formState.errors.display_order?.message}
            hint="Menor = aparece primero"
          >
            <Controller
              control={form.control}
              name="display_order"
              render={({ field }) => (
                <Input
                  type="number"
                  value={String(field.value ?? 0)}
                  onChange={(_, d) => field.onChange(Number(d.value || 0))}
                  disabled={!canWrite}
                  min={0}
                  max={9999}
                />
              )}
            />
          </FormField>
        </div>

        <FormField label="Estado inicial" hint="Solo uno puede serlo en el catálogo.">
          <Controller
            control={form.control}
            name="is_initial"
            render={({ field }) => (
              <div className={styles.switchRow}>
                <Switch
                  checked={field.value ?? false}
                  onChange={(_, d) => field.onChange(d.checked)}
                  disabled={!canWrite}
                />
                <span>{field.value ? "Sí" : "No"}</span>
              </div>
            )}
          />
        </FormField>
        {isInitial ? (
          <p className={styles.hint}>Ya hay un estado inicial; el sistema rechazará un segundo.</p>
        ) : null}

        <FormField label="Estado final (terminal)">
          <Controller
            control={form.control}
            name="is_final"
            render={({ field }) => (
              <div className={styles.switchRow}>
                <Switch
                  checked={field.value ?? false}
                  onChange={(_, d) => field.onChange(d.checked)}
                  disabled={!canWrite}
                />
                <span>{field.value ? "Sí" : "No"}</span>
              </div>
            )}
          />
        </FormField>

        {isEdit && statusId ? (
          <>
            <Divider />
            <StatusMatrixEditor
              statusId={statusId}
              kind="customer"
              isFinal={isFinal ?? false}
              canWrite={canWrite}
            />
          </>
        ) : (
          <>
            <Divider />
            <p className={styles.hint}>
              Las transiciones permitidas se configuran después de crear el estado: vuelve a abrirlo
              en modo edición.
            </p>
          </>
        )}
      </div>
    </Drawer>
  );
}
