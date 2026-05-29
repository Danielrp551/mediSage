"use client";

import {
  Badge,
  Button,
  Divider,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
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

import { createService, getService, updateService } from "@/actions/service.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { serviceCreateSchema, type ServiceCreateInput } from "@/lib/schemas/service.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ServiceDetail, VerticalOption } from "@/types/catalog.types";

const useStyles = makeStyles({
  tabPanel: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
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
  serviceId: string | null;
  verticals: VerticalOption[];
  /** Pre-selects the vertical in create mode (from the active list filter). */
  defaultVerticalId?: string | null;
  onClose: () => void;
}

type TabId = "details" | "audit";

export function ServiceDrawer({ mode, serviceId, verticals, defaultVerticalId, onClose }: Props) {
  const styles = useStyles();
  const [service, setService] = useState<ServiceDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const hasAudit = mode !== "create";

  const form = useForm<ServiceCreateInput & { active?: boolean }>({
    resolver: zodResolver(serviceCreateSchema),
    defaultValues: {
      vertical_id: defaultVerticalId ?? "",
      code: "",
      name: "",
      description: "",
      display_order: 0,
      active: true,
    },
  });

  useEffect(() => {
    if (!serviceId) return;
    let cancelled = false;
    void getService(serviceId).then((res) => {
      if (cancelled) return;
      setService(res.data);
      form.reset({
        vertical_id: res.data.vertical_id,
        code: res.data.code,
        name: res.data.name,
        description: res.data.description ?? "",
        display_order: res.data.display_order,
        active: res.data.active,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [serviceId, form]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      // Update strips `vertical_id`/`code` (immutable) via its Zod schema;
      // Create takes the whole payload. Send the full form either way.
      const result = serviceId
        ? await updateService(serviceId, values)
        : await createService(values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
    });
  });

  const title =
    mode === "create"
      ? "Nuevo servicio"
      : mode === "edit"
        ? "Editar servicio"
        : "Detalle de servicio";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={service?.code ?? form.watch("code") ?? undefined}
      size="medium"
      footer={
        readOnly ? (
          <Button onClick={onClose}>Cerrar</Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
              {pending
                ? mode === "create"
                  ? "Creando…"
                  : "Guardando…"
                : mode === "create"
                  ? "Crear servicio"
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
            label="Vertical"
            required
            error={form.formState.errors.vertical_id?.message}
            hint={isEdit ? "La vertical no se puede cambiar tras crear el servicio." : undefined}
          >
            <Controller
              control={form.control}
              name="vertical_id"
              render={({ field }) => {
                const selectedName =
                  verticals.find((v) => v.id === field.value)?.name ?? service?.vertical.name ?? "";
                return (
                  <Dropdown
                    value={selectedName}
                    selectedOptions={field.value ? [field.value] : []}
                    disabled={readOnly || isEdit}
                    placeholder="Selecciona una vertical…"
                    onOptionSelect={(_, d) => field.onChange(d.optionValue ?? "")}
                  >
                    {verticals.map((v) => (
                      <Option key={v.id} value={v.id}>
                        {v.name}
                      </Option>
                    ))}
                  </Dropdown>
                );
              }}
            />
          </FormField>

          <FormField
            label="Código"
            required
            error={form.formState.errors.code?.message}
            hint="Slug en minúsculas, estable. Único dentro de la vertical."
          >
            <Controller
              control={form.control}
              name="code"
              render={({ field }) => (
                <Input
                  {...field}
                  disabled={readOnly || isEdit}
                  placeholder="ej. limpieza_profunda"
                />
              )}
            />
          </FormField>

          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. Limpieza profunda" />
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
                  placeholder="Describe brevemente este servicio…"
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
                    <span>{field.value ? "Activo" : "Deshabilitado"}</span>
                  </div>
                )}
              />
            </FormField>
          ) : null}
        </div>
      ) : (
        <AuditTab service={service} styles={styles} />
      )}
    </Drawer>
  );
}

type Styles = ReturnType<typeof useStyles>;

function AuditTab({ service, styles }: { service: ServiceDetail | null; styles: Styles }) {
  if (!service) {
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
            <Badge appearance="filled" color={service.active ? "success" : "informative"}>
              {service.active ? "Activo" : "Deshabilitado"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Vertical</div>
          <div className={styles.auditValue}>{service.vertical.name}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID del servicio</div>
          <div className={styles.auditValue}>
            <code>{service.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creado el</div>
          <div className={styles.auditValue}>{formatDate(service.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creado por</div>
          <div className={styles.auditValue}>{service.created_by_user?.full_name ?? "—"}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado el</div>
          <div className={styles.auditValue}>{formatDate(service.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado por</div>
          <div className={styles.auditValue}>{service.updated_by_user?.full_name ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}
