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
  Spinner,
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

import {
  createPromotion,
  getPromotion,
  getPromotionProducts,
  setPromotionProducts,
  updatePromotion,
} from "@/actions/promotion.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { usePermissions } from "@/hooks/usePermissions";
import {
  CAMPAIGN_STATUS_META,
  DISCOUNT_TYPE_META,
  SUPPORTED_CURRENCIES,
  formatDiscount,
} from "@/lib/constants/marketing";
import { promotionCreateSchema, type PromotionCreateInput } from "@/lib/schemas/promotion.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ProductOption } from "@/types/catalog.types";
import type { CampaignStatus, DiscountType, PromotionDetail } from "@/types/marketing.types";
import { DISCOUNT_TYPES } from "@/types/marketing.types";

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
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  loading: { display: "flex", justifyContent: "center", padding: tokens.spacingVerticalXXL },
  footerRow: { display: "flex", justifyContent: "flex-end" },
  chipRow: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    alignItems: "center",
    flexWrap: "wrap",
  },
  chip: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXXS,
    padding: `${tokens.spacingVerticalXXS} ${tokens.spacingHorizontalS}`,
    backgroundColor: appTokens.chromeBgHover,
    borderRadius: tokens.borderRadiusCircular,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeText,
  },
});

interface Props {
  mode: "create" | "edit" | "view";
  promotionId: string | null;
  products: ProductOption[];
  onClose: () => void;
  onChanged?: () => void;
}

type TabId = "details" | "discount" | "limits" | "products" | "campaigns" | "audit";

type Styles = ReturnType<typeof useStyles>;

/** Form value shape: create input + `active` (edit) + `_discount_type` efímero (refine del update). */
type PromotionFormValues = PromotionCreateInput & {
  active?: boolean;
  _discount_type?: DiscountType;
};

/** Badge de estado de campaña con color FIJO del front (ADR-013). */
function CampaignStatusBadge({ status }: { status: CampaignStatus }) {
  const meta = CAMPAIGN_STATUS_META[status];
  return (
    <Badge
      appearance="filled"
      style={{ backgroundColor: meta.color, color: tokens.colorNeutralForegroundOnBrand }}
    >
      {meta.label}
    </Badge>
  );
}

export function PromotionDrawer({ mode, promotionId, products, onClose, onChanged }: Props) {
  const styles = useStyles();
  const isCreate = mode === "create";
  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const hasAudit = mode !== "create";

  const [promotion, setPromotion] = useState<PromotionDetail | null>(null);
  // En create, tras guardar exitosamente conmutamos a "edit" con el id devuelto
  // para habilitar el M:N de productos (requiere id). Este id efectivo se usa para
  // el subtitle y para refrescar el detalle.
  const [effectiveId, setEffectiveId] = useState<string | null>(promotionId);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const form = useForm<PromotionFormValues>({
    // `raw: true` → handleSubmit recibe los valores CRUDOS del form, no el objeto
    // parseado por Zod. Sin esto, promotionCreateSchema descarta `active` /
    // `applies_to_all_products` del payload en edición. El Server Action re-valida.
    resolver: zodResolver(promotionCreateSchema, undefined, { raw: true }),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      discount_type: "percentage",
      discount_value: "",
      currency: "PEN",
      start_date: "",
      end_date: "",
      max_uses_total: null,
      max_uses_per_person: null,
      applies_to_all_products: false,
      active: true,
    },
  });

  // Edit/View: hidratar el form desde el detalle cargado.
  useEffect(() => {
    if (!promotionId) return;
    let cancelled = false;
    void getPromotion(promotionId).then((res) => {
      if (cancelled) return;
      const p = res.data;
      setPromotion(p);
      setEffectiveId(p.id);
      form.reset({
        code: p.code,
        name: p.name,
        description: p.description ?? "",
        discount_type: p.discount_type,
        discount_value: p.discount_value,
        currency: narrowCurrency(p.currency),
        start_date: p.start_date,
        end_date: p.end_date ?? "",
        max_uses_total: p.max_uses_total,
        max_uses_per_person: p.max_uses_per_person,
        applies_to_all_products: p.applies_to_all_products,
        active: p.active,
        // Inyecta el discount_type de la fila para que el superRefine del update
        // valide el rango de discount_value (el update no incluye discount_type).
        _discount_type: p.discount_type,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [promotionId, form]);

  const discountType = form.watch("discount_type");
  const appliesToAll = form.watch("applies_to_all_products");

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    // discount_value viaja como string (Decimal). max_uses vacíos → null (ilimitado).
    // end_date "" → null. El action descarta `_discount_type` antes del PUT.
    const payload = {
      ...values,
      discount_value: String(values.discount_value ?? "").trim(),
      end_date: values.end_date === "" ? null : values.end_date,
      max_uses_total: values.max_uses_total ?? null,
      max_uses_per_person: values.max_uses_per_person ?? null,
    };
    // `targetId` = el prop (edit normal abierto desde la lista) o el id efectivo tras el
    // pivot create→edit (effectiveId). El prop `promotionId` NO cambia tras crear, así que
    // routear por él re-ejecutaría createPromotion → 409 code duplicado (review F2 major).
    const targetId = promotionId ?? effectiveId;
    startTransition(async () => {
      const result = targetId
        ? await updatePromotion(targetId, payload)
        : await createPromotion(payload);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación.");
        return;
      }
      onChanged?.();
      if (targetId) {
        // Fue un update (edit normal o edición post-pivot) → cerrar.
        onClose();
        return;
      }
      // CREATE exitoso: en vez de cerrar, conmutamos a "edit" con el id devuelto
      // para que el usuario pueda asignar productos (el M:N requiere id).
      if (!result.data) {
        onClose();
        return;
      }
      const created = result.data.data;
      setPromotion(created);
      setEffectiveId(created.id);
      form.reset({
        code: created.code,
        name: created.name,
        description: created.description ?? "",
        discount_type: created.discount_type,
        discount_value: created.discount_value,
        currency: narrowCurrency(created.currency),
        start_date: created.start_date,
        end_date: created.end_date ?? "",
        max_uses_total: created.max_uses_total,
        max_uses_per_person: created.max_uses_per_person,
        applies_to_all_products: created.applies_to_all_products,
        active: created.active,
        _discount_type: created.discount_type,
      });
    });
  });

  // Tras crear pasamos a editar: el modo efectivo deja de ser "create".
  const wasCreatedNow = isCreate && effectiveId !== null;
  const effectiveReadOnly = readOnly;
  const showProductsTab = !isCreate || wasCreatedNow;

  const title = isCreate ? "Nueva promoción" : isEdit ? "Editar promoción" : "Detalle de promoción";

  return (
    <Drawer
      open
      onClose={onClose}
      title={wasCreatedNow ? "Editar promoción" : title}
      subtitle={promotion?.code ?? form.watch("code") ?? undefined}
      size="medium"
      footer={
        effectiveReadOnly ? (
          <Button onClick={onClose}>Cerrar</Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              {wasCreatedNow ? "Cerrar" : "Cancelar"}
            </Button>
            <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
              {pending
                ? isCreate && !wasCreatedNow
                  ? "Creando…"
                  : "Guardando…"
                : isCreate && !wasCreatedNow
                  ? "Crear promoción"
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

      {wasCreatedNow ? (
        <MessageBar intent="success">
          <MessageBarBody>
            Promoción creada. Ahora puedes asignar productos en la pestaña Productos.
          </MessageBarBody>
        </MessageBar>
      ) : null}

      <TabList
        selectedValue={tab}
        onTabSelect={(_e: SelectTabEvent, d: SelectTabData) => setTab(d.value as TabId)}
      >
        <Tab value="details">Datos</Tab>
        <Tab value="discount">Descuento</Tab>
        <Tab value="limits">Vigencia y límites</Tab>
        {showProductsTab ? <Tab value="products">Productos</Tab> : null}
        {hasAudit ? <Tab value="campaigns">Campañas</Tab> : null}
        {hasAudit ? <Tab value="audit">Auditoría</Tab> : null}
      </TabList>

      {tab === "details" ? (
        <div className={styles.tabPanel}>
          <FormField
            label="Código"
            required
            error={form.formState.errors.code?.message}
            hint="Slug en minúsculas, estable. No se puede cambiar luego."
          >
            <Controller
              control={form.control}
              name="code"
              render={({ field }) => (
                <Input
                  {...field}
                  disabled={effectiveReadOnly || isEdit || wasCreatedNow}
                  placeholder="ej. dscto_verano_10"
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
                  disabled={effectiveReadOnly}
                  placeholder="ej. Descuento de Verano 10%"
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
                  disabled={effectiveReadOnly}
                  rows={3}
                  placeholder="Describe brevemente esta promoción…"
                />
              )}
            />
          </FormField>

          {isEdit || wasCreatedNow ? (
            <FormField label="Habilitada">
              <Controller
                control={form.control}
                name="active"
                render={({ field }) => (
                  <div className={styles.switchRow}>
                    <Switch
                      checked={field.value ?? true}
                      onChange={(_, d) => field.onChange(d.checked)}
                      disabled={effectiveReadOnly}
                    />
                    <span>{field.value ? "Sí" : "No"}</span>
                  </div>
                )}
              />
            </FormField>
          ) : null}
        </div>
      ) : tab === "discount" ? (
        <div className={styles.tabPanel}>
          {/* discount_type es INMUTABLE post-create → disabled en edit. */}
          <FormField
            label="Tipo de descuento"
            required
            error={form.formState.errors.discount_type?.message}
            hint={
              isEdit || wasCreatedNow
                ? "El tipo de descuento no se puede cambiar tras crear la promoción."
                : undefined
            }
          >
            <Controller
              control={form.control}
              name="discount_type"
              render={({ field }) => (
                <Dropdown
                  value={field.value ? DISCOUNT_TYPE_META[field.value].label : ""}
                  selectedOptions={field.value ? [field.value] : []}
                  disabled={effectiveReadOnly || isEdit || wasCreatedNow}
                  onOptionSelect={(_, d) => field.onChange((d.optionValue as DiscountType) ?? "")}
                >
                  {DISCOUNT_TYPES.map((dt) => (
                    <Option key={dt} value={dt}>
                      {DISCOUNT_TYPE_META[dt].label}
                    </Option>
                  ))}
                </Dropdown>
              )}
            />
          </FormField>

          {discountType === "percentage" ? (
            <FormField
              label="Porcentaje"
              required
              error={form.formState.errors.discount_value?.message}
              hint="Mayor que 0 y como máximo 100."
            >
              <Controller
                control={form.control}
                name="discount_value"
                render={({ field }) => (
                  <Input
                    value={field.value ?? ""}
                    onChange={(_, d) => field.onChange(d.value)}
                    disabled={effectiveReadOnly}
                    inputMode="decimal"
                    contentAfter={<span>%</span>}
                    placeholder="ej. 10"
                  />
                )}
              />
            </FormField>
          ) : (
            <div className={styles.twoCol}>
              <FormField
                label="Monto del descuento"
                required
                error={form.formState.errors.discount_value?.message}
                hint="Mayor que 0 (hasta 2 decimales)."
              >
                <Controller
                  control={form.control}
                  name="discount_value"
                  render={({ field }) => (
                    <Input
                      value={field.value ?? ""}
                      onChange={(_, d) => field.onChange(d.value)}
                      disabled={effectiveReadOnly}
                      inputMode="decimal"
                      placeholder="ej. 25.00"
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
                      disabled={effectiveReadOnly}
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
          )}
        </div>
      ) : tab === "limits" ? (
        <div className={styles.tabPanel}>
          <div className={styles.twoCol}>
            <FormField label="Inicio" required error={form.formState.errors.start_date?.message}>
              <Controller
                control={form.control}
                name="start_date"
                render={({ field }) => (
                  <Input
                    type="date"
                    value={field.value ?? ""}
                    onChange={(_, d) => field.onChange(d.value)}
                    disabled={effectiveReadOnly}
                  />
                )}
              />
            </FormField>
            <FormField label="Fin" error={form.formState.errors.end_date?.message} hint="Opcional">
              <Controller
                control={form.control}
                name="end_date"
                render={({ field }) => (
                  <Input
                    type="date"
                    value={field.value ?? ""}
                    onChange={(_, d) => field.onChange(d.value)}
                    disabled={effectiveReadOnly}
                  />
                )}
              />
            </FormField>
          </div>

          <div className={styles.twoCol}>
            <FormField
              label="Usos máximos totales"
              error={form.formState.errors.max_uses_total?.message}
              hint="Vacío = ilimitado."
            >
              <Controller
                control={form.control}
                name="max_uses_total"
                render={({ field }) => (
                  <Input
                    type="number"
                    value={field.value == null ? "" : String(field.value)}
                    onChange={(_, d) => field.onChange(d.value === "" ? null : Number(d.value))}
                    disabled={effectiveReadOnly}
                    min={1}
                    placeholder="Ilimitado"
                  />
                )}
              />
            </FormField>
            <FormField
              label="Usos máximos por persona"
              error={form.formState.errors.max_uses_per_person?.message}
              hint="Vacío = ilimitado."
            >
              <Controller
                control={form.control}
                name="max_uses_per_person"
                render={({ field }) => (
                  <Input
                    type="number"
                    value={field.value == null ? "" : String(field.value)}
                    onChange={(_, d) => field.onChange(d.value === "" ? null : Number(d.value))}
                    disabled={effectiveReadOnly}
                    min={1}
                    placeholder="Ilimitado"
                  />
                )}
              />
            </FormField>
          </div>
        </div>
      ) : tab === "products" ? (
        <ProductsTab
          promotionId={effectiveId}
          products={products}
          appliesToAll={appliesToAll ?? false}
          readOnly={effectiveReadOnly}
          onToggleAppliesToAll={(checked) =>
            form.setValue("applies_to_all_products", checked, { shouldDirty: true })
          }
          styles={styles}
        />
      ) : tab === "campaigns" ? (
        <CampaignsTab promotion={promotion} styles={styles} />
      ) : (
        <AuditTab promotion={promotion} styles={styles} />
      )}
    </Drawer>
  );
}

function narrowCurrency(value: string): "PEN" | "USD" | "EUR" {
  return (SUPPORTED_CURRENCIES as readonly string[]).includes(value)
    ? (value as "PEN" | "USD" | "EUR")
    : "PEN";
}

/**
 * Tab Productos: editor M:N gated PROMOTIONS_UPDATE. Si `applies_to_all_products`
 * está activo, la promo cubre todo y el picker se oculta (el M:N se ignora).
 * Si no, carga `getPromotionProducts(id)` → preselecciona y guarda con
 * `setPromotionProducts(id, { product_ids })` (reemplazo del set completo).
 */
function ProductsTab({
  promotionId,
  products,
  appliesToAll,
  readOnly,
  onToggleAppliesToAll,
  styles,
}: {
  promotionId: string | null;
  products: ProductOption[];
  appliesToAll: boolean;
  readOnly: boolean;
  onToggleAppliesToAll: (checked: boolean) => void;
  styles: Styles;
}) {
  const { hasAnyPermission } = usePermissions();
  const canWrite = !readOnly && hasAnyPermission(["PROMOTIONS_UPDATE"]);

  const [pending, startTransition] = useTransition();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    // Sin id (create antes de guardar) no hay set que cargar.
    if (!promotionId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void getPromotionProducts(promotionId)
      .then((assigned) => {
        if (cancelled) return;
        setSelected(assigned.map((p) => p.id));
      })
      .catch(() => {
        if (!cancelled) setLoadError("No se pudieron cargar los productos asignados.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [promotionId]);

  const handleToggle = (id: string) => {
    setSavedOk(false);
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSave = () => {
    if (!promotionId) return;
    setSaveError(null);
    setSavedOk(false);
    startTransition(async () => {
      const result = await setPromotionProducts(promotionId, { product_ids: selected });
      if (!result.ok) {
        setSaveError(result.error ?? "No se pudieron guardar los productos.");
        return;
      }
      setSavedOk(true);
    });
  };

  const options = products.map((p) => ({
    id: p.id,
    primary: p.name,
    secondary: p.code,
  }));

  return (
    <div className={styles.tabPanel}>
      <FormField label="Aplica a todos los productos">
        <div className={styles.switchRow}>
          <Switch
            checked={appliesToAll}
            disabled={!canWrite}
            onChange={(_, d) => onToggleAppliesToAll(d.checked)}
          />
          <span>{appliesToAll ? "Sí (cubre todo el catálogo)" : "No (selección específica)"}</span>
        </div>
      </FormField>
      <p className={styles.hint}>
        Recuerda guardar los datos de la promoción para que “Aplica a todos los productos” quede
        registrado.
      </p>

      {appliesToAll ? (
        <MessageBar intent="info">
          <MessageBarBody>
            La promoción cubre todos los productos. La selección específica se ignora.
          </MessageBarBody>
        </MessageBar>
      ) : !promotionId ? (
        <p className={styles.emptyState}>Guarda la promoción primero para asignar productos.</p>
      ) : loading ? (
        <div className={styles.loading}>
          <Spinner size="small" label="Cargando productos…" />
        </div>
      ) : loadError ? (
        <MessageBar intent="error">
          <MessageBarBody>{loadError}</MessageBarBody>
        </MessageBar>
      ) : (
        <>
          {saveError ? (
            <MessageBar intent="error">
              <MessageBarBody>{saveError}</MessageBarBody>
            </MessageBar>
          ) : null}
          {savedOk ? (
            <MessageBar intent="success">
              <MessageBarBody>Productos actualizados.</MessageBarBody>
            </MessageBar>
          ) : null}

          <SearchableOptionList
            options={options}
            selected={selected}
            disabled={!canWrite || pending}
            onToggle={handleToggle}
            searchPlaceholder="Buscar productos…"
            emptyMessage="No hay productos activos en el catálogo."
          />
          <p className={styles.hint}>La promoción solo aplicará a los productos marcados.</p>
          {canWrite ? (
            <div className={styles.footerRow}>
              <Button appearance="secondary" disabled={pending} onClick={handleSave}>
                {pending ? "Guardando…" : "Guardar productos"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

/** Tab Campañas: chips read-only de las campañas que incluyen esta promoción. */
function CampaignsTab({
  promotion,
  styles,
}: {
  promotion: PromotionDetail | null;
  styles: Styles;
}) {
  if (!promotion) {
    return (
      <div className={styles.tabPanel}>
        <p className={styles.emptyState}>Cargando…</p>
      </div>
    );
  }
  return (
    <div className={styles.tabPanel}>
      {promotion.campaigns.length === 0 ? (
        <p className={styles.emptyState}>Esta promoción no está incluida en ninguna campaña.</p>
      ) : (
        <div className={styles.chipRow}>
          {promotion.campaigns.map((c) => (
            <span key={c.id} className={styles.chip}>
              {c.name}
              <CampaignStatusBadge status={c.status} />
            </span>
          ))}
        </div>
      )}
      <p className={styles.hint}>
        Las campañas que incluyen esta promoción se gestionan desde Campañas.
      </p>
    </div>
  );
}

function AuditTab({ promotion, styles }: { promotion: PromotionDetail | null; styles: Styles }) {
  if (!promotion) {
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
          <div className={styles.auditLabel}>Descuento</div>
          <div className={styles.auditValue}>
            {formatDiscount({
              discount_type: promotion.discount_type,
              discount_value: promotion.discount_value,
              currency: promotion.currency,
            })}
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Estado</div>
          <div className={styles.auditValue}>
            <Badge appearance="filled" color={promotion.active ? "success" : "informative"}>
              {promotion.active ? "Habilitada" : "Deshabilitada"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID de la promoción</div>
          <div className={styles.auditValue}>
            <code>{promotion.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creada el</div>
          <div className={styles.auditValue}>{formatDate(promotion.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creada por</div>
          <div className={styles.auditValue}>
            {promotion.created_by_user?.full_name ?? "Sistema"}
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada el</div>
          <div className={styles.auditValue}>{formatDate(promotion.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada por</div>
          <div className={styles.auditValue}>
            {promotion.updated_by_user?.full_name ?? "Sistema"}
          </div>
        </div>
      </div>
    </div>
  );
}
