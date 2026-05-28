"use client";

import {
  Badge,
  Button,
  Divider,
  Input,
  MessageBar,
  MessageBarBody,
  Switch,
  Tab,
  TabList,
  Textarea,
  makeStyles,
  tokens,
  type SelectTabData,
  type SelectTabEvent,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createVertical, getVertical, updateVertical } from "@/actions/vertical.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import {
  verticalCreateSchema,
  type VerticalCreateInput,
} from "@/lib/schemas/vertical.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { VerticalDetail } from "@/types/catalog.types";

import { ColorPicker } from "./ColorPicker";
import { IconPicker } from "./IconPicker";

const useStyles = makeStyles({
  tabPanel: {
    paddingTop: tokens.spacingVerticalL,
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
  audit: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    fontSize: tokens.fontSizeBase200,
  },
  auditLabel: { color: appTokens.chromeTextMuted, fontSize: tokens.fontSizeBase200 },
  auditValue: { color: appTokens.chromeText, fontWeight: tokens.fontWeightMedium },
  emptyState: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    padding: tokens.spacingVerticalM,
    textAlign: "center",
  },
  switchRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
});

interface Props {
  mode: "create" | "edit" | "view";
  verticalId: string | null;
  onClose: () => void;
}

type TabId = "details" | "audit";

export function VerticalDrawer({ mode, verticalId, onClose }: Props) {
  const styles = useStyles();
  const [vertical, setVertical] = useState<VerticalDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const hasAudit = mode !== "create";

  const form = useForm<VerticalCreateInput & { active?: boolean }>({
    resolver: zodResolver(verticalCreateSchema),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      color: null,
      icon: null,
      display_order: 0,
      active: true,
    },
  });

  useEffect(() => {
    if (!verticalId) return;
    let cancelled = false;
    void getVertical(verticalId).then((res) => {
      if (cancelled) return;
      setVertical(res.data);
      form.reset({
        code: res.data.code,
        name: res.data.name,
        description: res.data.description ?? "",
        color: res.data.color,
        icon: res.data.icon,
        display_order: res.data.display_order,
        active: res.data.active,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [verticalId, form]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      // The Update schema omits `code` (immutable); for Create the value
      // is taken from the form. We send the full form payload either way
      // and let the Zod schema on the server pick what it needs.
      const result = verticalId
        ? await updateVertical(verticalId, values)
        : await createVertical(values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
    });
  });

  const title =
    mode === "create"
      ? "Nueva vertical"
      : mode === "edit"
        ? "Editar vertical"
        : "Detalle de vertical";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={vertical?.code ?? form.watch("code") ?? undefined}
      size="medium"
      footer={
        readOnly ? (
          <Button onClick={onClose}>Cerrar</Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button
              appearance="primary"
              disabled={pending}
              onClick={() => void onSubmit()}
            >
              {pending
                ? mode === "create"
                  ? "Creando…"
                  : "Guardando…"
                : mode === "create"
                  ? "Crear vertical"
                  : "Guardar cambios"}
            </Button>
          </>
        )
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <TabList
        selectedValue={tab}
        onTabSelect={(_e: SelectTabEvent, d: SelectTabData) => setTab(d.value as TabId)}
      >
        <Tab value="details">Detalles</Tab>
        {hasAudit ? <Tab value="audit">Auditoría</Tab> : null}
      </TabList>

      {tab === "details" ? (
        <div className={styles.tabPanel}>
          <FormField
            label="Código"
            required
            error={form.formState.errors.code?.message}
            hint="Slug en minúsculas, estable. Lo usan los bots para clasificar leads."
          >
            <Controller
              control={form.control}
              name="code"
              render={({ field }) => (
                <Input
                  {...field}
                  disabled={readOnly || isEdit}
                  placeholder="ej. estetica_facial"
                />
              )}
            />
          </FormField>

          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. Estética facial" />
              )}
            />
          </FormField>

          <FormField label="Descripción" error={form.formState.errors.description?.message}>
            <Controller
              control={form.control}
              name="description"
              render={({ field }) => (
                <Textarea
                  {...field}
                  value={field.value ?? ""}
                  disabled={readOnly}
                  rows={3}
                  placeholder="Describe brevemente esta vertical…"
                />
              )}
            />
          </FormField>

          <div className={styles.twoCol}>
            <FormField label="Color" hint="Hex como #FF6B6B">
              <Controller
                control={form.control}
                name="color"
                render={({ field }) => (
                  <ColorPicker
                    value={field.value ?? null}
                    onChange={(v) => field.onChange(v)}
                    disabled={readOnly}
                  />
                )}
              />
            </FormField>
            <FormField label="Orden" hint="Menor = aparece primero">
              <Controller
                control={form.control}
                name="display_order"
                render={({ field }) => (
                  <Input
                    type="number"
                    value={String(field.value ?? 0)}
                    onChange={(_, d) => field.onChange(Number(d.value || 0))}
                    disabled={readOnly}
                    min={0}
                    max={9999}
                  />
                )}
              />
            </FormField>
          </div>

          <FormField label="Ícono" hint="Elige uno de la galería">
            <Controller
              control={form.control}
              name="icon"
              render={({ field }) => (
                <IconPicker
                  value={field.value ?? null}
                  onChange={(v) => field.onChange(v)}
                  disabled={readOnly}
                />
              )}
            />
          </FormField>

          {isEdit ? (
            <FormField label="Estado">
              <Controller
                control={form.control}
                name="active"
                render={({ field }) => (
                  <div className={styles.switchRow}>
                    <Switch
                      checked={field.value ?? true}
                      onChange={(_, d) => field.onChange(d.checked)}
                      disabled={readOnly}
                    />
                    <span>{field.value ? "Activa" : "Deshabilitada"}</span>
                  </div>
                )}
              />
            </FormField>
          ) : null}
        </div>
      ) : (
        <AuditTab vertical={vertical} styles={styles} />
      )}
    </Drawer>
  );
}

type Styles = ReturnType<typeof useStyles>;

function AuditTab({
  vertical,
  styles,
}: {
  vertical: VerticalDetail | null;
  styles: Styles;
}) {
  if (!vertical) {
    return (
      <div className={styles.tabPanel}>
        <p className={styles.emptyState}>Cargando…</p>
      </div>
    );
  }
  return (
    <div className={styles.tabPanel}>
      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Estado</div>
          <div className={styles.auditValue}>
            <Badge appearance="filled" color={vertical.active ? "success" : "informative"}>
              {vertical.active ? "Activa" : "Deshabilitada"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID de la vertical</div>
          <div className={styles.auditValue}>
            <code>{vertical.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creada el</div>
          <div className={styles.auditValue}>{formatDate(vertical.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creada por</div>
          <div className={styles.auditValue}>
            {vertical.created_by_user?.full_name ?? "—"}
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada el</div>
          <div className={styles.auditValue}>{formatDate(vertical.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada por</div>
          <div className={styles.auditValue}>
            {vertical.updated_by_user?.full_name ?? "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
