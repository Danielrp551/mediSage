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

import { createProduct, getProduct, updateProduct } from "@/actions/product.actions";
import { listActiveServices } from "@/actions/service.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import {
  SUPPORTED_CURRENCIES,
  type SupportedCurrency,
  productCreateSchema,
  type ProductCreateInput,
} from "@/lib/schemas/product.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ProductDetail, ServiceOption, VerticalOption } from "@/types/catalog.types";

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
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
});

interface Props {
  mode: "create" | "edit" | "view";
  productId: string | null;
  verticals: VerticalOption[];
  defaultVerticalId?: string | null;
  defaultServiceId?: string | null;
  onClose: () => void;
}

type TabId = "details" | "pricing" | "booking" | "audit";

function narrowCurrency(value: string): SupportedCurrency {
  return (SUPPORTED_CURRENCIES as readonly string[]).includes(value)
    ? (value as SupportedCurrency)
    : "PEN";
}

export function ProductDrawer({
  mode,
  productId,
  verticals,
  defaultVerticalId,
  defaultServiceId,
  onClose,
}: Props) {
  const styles = useStyles();
  const isCreate = mode === "create";
  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const hasAudit = mode !== "create";

  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  // Vertical is a UI helper that scopes the Service dropdown — not a form field
  // (the backend derives the product's vertical from the chosen service).
  const [selectedVerticalId, setSelectedVerticalId] = useState<string | null>(
    isCreate ? (defaultVerticalId ?? null) : null,
  );
  const [serviceOptions, setServiceOptions] = useState<ServiceOption[]>([]);

  const form = useForm<ProductCreateInput & { active?: boolean }>({
    resolver: zodResolver(productCreateSchema),
    defaultValues: {
      service_id: defaultServiceId ?? "",
      code: "",
      name: "",
      description: "",
      base_price: "",
      currency: "PEN",
      duration_min: null,
      requires_appointment: true,
      is_package: false,
      min_hours_to_cancel: null,
      active: true,
    },
  });

  // Create: keep the Service dropdown in sync with the chosen vertical.
  useEffect(() => {
    if (!isCreate) return;
    let cancelled = false;
    if (selectedVerticalId) {
      void listActiveServices(selectedVerticalId).then((opts) => {
        if (!cancelled) setServiceOptions(opts);
      });
    } else {
      setServiceOptions([]);
    }
    return () => {
      cancelled = true;
    };
  }, [isCreate, selectedVerticalId]);

  // Edit/View: hydrate the form + dropdowns from the loaded product.
  useEffect(() => {
    if (!productId) return;
    let cancelled = false;
    void getProduct(productId).then((res) => {
      if (cancelled) return;
      const p = res.data;
      setProduct(p);
      setSelectedVerticalId(p.vertical.id);
      setServiceOptions([p.service]);
      form.reset({
        service_id: p.service_id,
        code: p.code,
        name: p.name,
        description: p.description ?? "",
        base_price: p.base_price,
        currency: narrowCurrency(p.currency),
        duration_min: p.duration_min,
        requires_appointment: p.requires_appointment,
        is_package: p.is_package,
        min_hours_to_cancel: p.min_hours_to_cancel,
        active: p.active,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [productId, form]);

  const requiresAppt = form.watch("requires_appointment");
  const minHours = form.watch("min_hours_to_cancel");
  const durationMin = form.watch("duration_min");
  const showDurationWarning =
    requiresAppt !== false && (minHours ?? null) !== null && (durationMin ?? null) === null;

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const payload = { ...values } as Record<string, unknown>;
      // On edit, drop `currency` unless the user actually changed it. The form
      // coerces an out-of-enum stored currency (e.g. GBP) to PEN for display
      // via narrowCurrency; resending it would silently overwrite the real
      // value on an unrelated save. Create always keeps it.
      if (productId && !form.formState.dirtyFields.currency) {
        delete payload.currency;
      }
      const result = productId
        ? await updateProduct(productId, payload)
        : await createProduct(payload);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
    });
  });

  const handleVerticalChange = (id: string | null) => {
    setSelectedVerticalId(id);
    form.setValue("service_id", "", { shouldValidate: false });
  };

  const title =
    mode === "create"
      ? "Nuevo producto"
      : mode === "edit"
        ? "Editar producto"
        : "Detalle de producto";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={product?.code ?? form.watch("code") ?? undefined}
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
                  ? "Crear producto"
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
        <Tab value="pricing">Precio</Tab>
        <Tab value="booking">Reserva</Tab>
        {hasAudit ? <Tab value="audit">Auditoría</Tab> : null}
      </TabList>

      {tab === "details" ? (
        <div className={styles.tabPanel}>
          <FormField label="Vertical" required hint="Filtra los servicios disponibles abajo.">
            <Dropdown
              value={
                verticals.find((v) => v.id === selectedVerticalId)?.name ??
                product?.vertical.name ??
                ""
              }
              selectedOptions={selectedVerticalId ? [selectedVerticalId] : []}
              disabled={readOnly || isEdit}
              placeholder="Selecciona una vertical…"
              onOptionSelect={(_, d) => handleVerticalChange(d.optionValue || null)}
            >
              {verticals.map((v) => (
                <Option key={v.id} value={v.id}>
                  {v.name}
                </Option>
              ))}
            </Dropdown>
          </FormField>

          <FormField
            label="Servicio"
            required
            error={form.formState.errors.service_id?.message}
            hint={isEdit ? "El servicio no se puede cambiar tras crear el producto." : undefined}
          >
            <Controller
              control={form.control}
              name="service_id"
              render={({ field }) => (
                <Dropdown
                  value={
                    serviceOptions.find((s) => s.id === field.value)?.name ??
                    product?.service.name ??
                    ""
                  }
                  selectedOptions={field.value ? [field.value] : []}
                  disabled={readOnly || isEdit || !selectedVerticalId}
                  placeholder={
                    selectedVerticalId ? "Selecciona un servicio…" : "Elige una vertical primero"
                  }
                  onOptionSelect={(_, d) => field.onChange(d.optionValue ?? "")}
                >
                  {serviceOptions.map((s) => (
                    <Option key={s.id} value={s.id}>
                      {s.name}
                    </Option>
                  ))}
                </Dropdown>
              )}
            />
          </FormField>

          <FormField
            label="Código"
            required
            error={form.formState.errors.code?.message}
            hint="Slug en minúsculas, estable. Único dentro del servicio."
          >
            <Controller
              control={form.control}
              name="code"
              render={({ field }) => (
                <Input
                  {...field}
                  disabled={readOnly || isEdit}
                  placeholder="ej. hydrafacial_premium_60"
                />
              )}
            />
          </FormField>

          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input
                  {...field}
                  disabled={readOnly}
                  placeholder="ej. HydraFacial Premium 60 min"
                />
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
                  placeholder="Describe brevemente este producto…"
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
      ) : tab === "pricing" ? (
        <div className={styles.tabPanel}>
          <div className={styles.twoCol}>
            <FormField
              label="Precio base"
              required
              error={form.formState.errors.base_price?.message}
            >
              <Controller
                control={form.control}
                name="base_price"
                render={({ field }) => (
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    disabled={readOnly}
                    inputMode="decimal"
                    placeholder="ej. 350.00"
                  />
                )}
              />
            </FormField>
            <FormField label="Moneda" required error={form.formState.errors.currency?.message}>
              <Controller
                control={form.control}
                name="currency"
                render={({ field }) => (
                  <Dropdown
                    value={field.value ?? "PEN"}
                    selectedOptions={[field.value ?? "PEN"]}
                    disabled={readOnly}
                    onOptionSelect={(_, d) => field.onChange(d.optionValue ?? "PEN")}
                  >
                    {SUPPORTED_CURRENCIES.map((cur) => (
                      <Option key={cur} value={cur}>
                        {cur}
                      </Option>
                    ))}
                  </Dropdown>
                )}
              />
            </FormField>
          </div>
        </div>
      ) : tab === "booking" ? (
        <div className={styles.tabPanel}>
          <FormField label="Requiere cita">
            <Controller
              control={form.control}
              name="requires_appointment"
              render={({ field }) => (
                <div className={styles.switchRow}>
                  <Switch
                    checked={field.value ?? true}
                    onChange={(_, d) => field.onChange(d.checked)}
                    disabled={readOnly}
                  />
                  <span>{field.value ? "Agendable" : "Venta directa"}</span>
                </div>
              )}
            />
          </FormField>

          <div className={styles.twoCol}>
            <FormField
              label="Duración (min)"
              error={form.formState.errors.duration_min?.message}
              hint="Tiempo de atención para calcular los cupos."
            >
              <Controller
                control={form.control}
                name="duration_min"
                render={({ field }) => (
                  <Input
                    type="number"
                    value={field.value == null ? "" : String(field.value)}
                    onChange={(_, d) => field.onChange(d.value === "" ? null : Number(d.value))}
                    disabled={readOnly}
                    min={1}
                    max={24 * 60}
                  />
                )}
              />
            </FormField>
            <FormField
              label="Horas mín. para cancelar"
              error={form.formState.errors.min_hours_to_cancel?.message}
            >
              <Controller
                control={form.control}
                name="min_hours_to_cancel"
                render={({ field }) => (
                  <Input
                    type="number"
                    value={field.value == null ? "" : String(field.value)}
                    onChange={(_, d) => field.onChange(d.value === "" ? null : Number(d.value))}
                    disabled={readOnly}
                    min={0}
                    max={24 * 7}
                  />
                )}
              />
            </FormField>
          </div>

          <FormField label="Es paquete">
            <Controller
              control={form.control}
              name="is_package"
              render={({ field }) => (
                <div className={styles.switchRow}>
                  <Switch
                    checked={field.value ?? false}
                    onChange={(_, d) => field.onChange(d.checked)}
                    disabled={readOnly}
                  />
                  <span>{field.value ? "Sí" : "No"}</span>
                </div>
              )}
            />
          </FormField>

          {showDurationWarning ? (
            <MessageBar intent="warning">
              <MessageBarBody>
                Indica una duración: el producto es agendable y tiene plazo de cancelación.
              </MessageBarBody>
            </MessageBar>
          ) : null}
        </div>
      ) : (
        <AuditTab product={product} styles={styles} />
      )}
    </Drawer>
  );
}

type Styles = ReturnType<typeof useStyles>;

function AuditTab({ product, styles }: { product: ProductDetail | null; styles: Styles }) {
  if (!product) {
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
            <Badge appearance="filled" color={product.active ? "success" : "informative"}>
              {product.active ? "Activo" : "Deshabilitado"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Servicio · Vertical</div>
          <div className={styles.auditValue}>
            {product.service.name} · {product.vertical.name}
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID del producto</div>
          <div className={styles.auditValue}>
            <code>{product.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creado el</div>
          <div className={styles.auditValue}>{formatDate(product.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creado por</div>
          <div className={styles.auditValue}>{product.created_by_user?.full_name ?? "—"}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado el</div>
          <div className={styles.auditValue}>{formatDate(product.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado por</div>
          <div className={styles.auditValue}>{product.updated_by_user?.full_name ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}
