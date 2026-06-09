"use client";

import {
  Badge,
  Button,
  Divider,
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
  Dropdown as FluentDropdown,
  type SelectTabData,
  type SelectTabEvent,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowSyncRegular } from "@fluentui/react-icons";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import {
  createCampaign,
  getCampaign,
  getCampaignPromotions,
  setCampaignPromotions,
  transitionCampaign,
  updateCampaign,
} from "@/actions/campaign.actions";
import { listActivePromotions } from "@/actions/promotion.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { usePermissions } from "@/hooks/usePermissions";
import {
  CAMPAIGN_STATUS_META,
  CAMPAIGN_TRANSITIONS,
  CAMPAIGN_TRANSITION_VERB,
  DISCOUNT_TYPE_META,
  formatDiscount,
} from "@/lib/constants/marketing";
import { campaignCreateSchema, type CampaignCreateInput } from "@/lib/schemas/campaign.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { VerticalOption } from "@/types/catalog.types";
import type { CampaignDetail, CampaignStatus, PromotionOption } from "@/types/marketing.types";

const TRANSVERSAL_VALUE = "__transversal__";

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
  statusPanel: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: tokens.spacingVerticalM,
    backgroundColor: appTokens.chromeBgHover,
    borderRadius: tokens.borderRadiusMedium,
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  statusLabel: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  loading: { display: "flex", justifyContent: "center", padding: tokens.spacingVerticalXXL },
  footerRow: { display: "flex", justifyContent: "flex-end" },
});

interface Props {
  mode: "create" | "edit" | "view";
  campaignId: string | null;
  verticals: VerticalOption[];
  onClose: () => void;
  onChanged?: () => void;
}

type TabId = "details" | "promociones" | "audit";

/** Badge de estado con color FIJO del front (ADR-013). */
function StatusBadge({ status }: { status: CampaignStatus }) {
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

export function CampaignDrawer({ mode, campaignId, verticals, onClose, onChanged }: Props) {
  const styles = useStyles();
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  // Transición de estado (solo edit). El control usa la matriz HARDCODEADA, no
  // refetchea destinos del backend.
  const [transitionError, setTransitionError] = useState<string | null>(null);
  const [transitioningTo, setTransitioningTo] = useState<CampaignStatus | null>(null);

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const hasAudit = mode !== "create";

  const form = useForm<CampaignCreateInput & { active?: boolean }>({
    // `raw: true` → handleSubmit recibe los valores CRUDOS del form, no el objeto parseado
    // por Zod. Sin esto, campaignCreateSchema (que no declara `active`) descarta el toggle
    // "Habilitada" en edición y nunca llega al payload. El Server Action re-valida igual.
    resolver: zodResolver(campaignCreateSchema, undefined, { raw: true }),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      start_date: "",
      end_date: "",
      target_vertical_id: null,
      active: true,
    },
  });

  useEffect(() => {
    if (!campaignId) return;
    let cancelled = false;
    void getCampaign(campaignId).then((res) => {
      if (cancelled) return;
      setCampaign(res.data);
      form.reset({
        code: res.data.code,
        name: res.data.name,
        description: res.data.description ?? "",
        start_date: res.data.start_date,
        end_date: res.data.end_date ?? "",
        target_vertical_id: res.data.target_vertical_id,
        active: res.data.active,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [campaignId, form]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    // end_date "" → null (campo opcional); target_vertical_id "" → null (transversal).
    const payload = {
      ...values,
      end_date: values.end_date === "" ? null : values.end_date,
      target_vertical_id: values.target_vertical_id ? values.target_vertical_id : null,
    };
    startTransition(async () => {
      const result = campaignId
        ? await updateCampaign(campaignId, payload)
        : await createCampaign(payload);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación.");
        return;
      }
      onChanged?.();
      onClose();
    });
  });

  // Recarga el detalle tras una transición (status/auditoría cambian).
  const reloadDetail = async () => {
    if (!campaignId) return;
    const res = await getCampaign(campaignId);
    setCampaign(res.data);
    form.setValue("active", res.data.active);
  };

  const handleTransition = (to: CampaignStatus) => {
    if (!campaignId) return;
    setTransitionError(null);
    setTransitioningTo(to);
    startTransition(async () => {
      const result = await transitionCampaign(campaignId, { to_status: to });
      setTransitioningTo(null);
      if (!result.ok) {
        setTransitionError(result.error ?? "No se pudo cambiar el estado.");
        return;
      }
      await reloadDetail();
      onChanged?.();
    });
  };

  const title =
    mode === "create" ? "Nueva campaña" : mode === "edit" ? "Editar campaña" : "Detalle de campaña";

  const allowedTargets: CampaignStatus[] = campaign ? CAMPAIGN_TRANSITIONS[campaign.status] : [];

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={campaign?.code ?? form.watch("code") ?? undefined}
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
                  ? "Crear campaña"
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
        <Tab value="details">Datos</Tab>
        <Tab value="promociones">Promociones</Tab>
        {hasAudit ? <Tab value="audit">Auditoría</Tab> : null}
      </TabList>

      {tab === "details" ? (
        <div className={styles.tabPanel}>
          {/* Estado + control de transición (solo edit/view, requiere detalle cargado). */}
          {!readOnly && isEdit && campaign ? (
            <PermissionGuardedStatus
              status={campaign.status}
              allowedTargets={allowedTargets}
              transitioningTo={transitioningTo}
              transitionError={transitionError}
              disabled={pending}
              onTransition={handleTransition}
              styles={styles}
            />
          ) : campaign ? (
            <div className={styles.statusPanel}>
              <div className={styles.statusRow}>
                <span className={styles.statusLabel}>Estado:</span>
                <StatusBadge status={campaign.status} />
              </div>
            </div>
          ) : null}

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
                <Input {...field} disabled={readOnly || isEdit} placeholder="ej. verano_2026" />
              )}
            />
          </FormField>

          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. Campaña de Verano 2026" />
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
                  placeholder="Describe brevemente esta campaña…"
                />
              )}
            />
          </FormField>

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
                    disabled={readOnly}
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
                    disabled={readOnly}
                  />
                )}
              />
            </FormField>
          </div>

          <FormField
            label="Vertical objetivo"
            error={form.formState.errors.target_vertical_id?.message}
            hint="“Transversal” = aplica a todas las verticales."
          >
            <Controller
              control={form.control}
              name="target_vertical_id"
              render={({ field }) => {
                const selectedVertical = verticals.find((v) => v.id === field.value);
                const selectedKey = field.value ? field.value : TRANSVERSAL_VALUE;
                return (
                  <FluentDropdown
                    disabled={readOnly}
                    value={selectedVertical?.name ?? "Transversal"}
                    selectedOptions={[selectedKey]}
                    onOptionSelect={(_, d) =>
                      field.onChange(
                        d.optionValue === TRANSVERSAL_VALUE ? null : (d.optionValue ?? null),
                      )
                    }
                  >
                    <Option value={TRANSVERSAL_VALUE}>Transversal</Option>
                    {verticals.map((v) => (
                      <Option key={v.id} value={v.id}>
                        {v.name}
                      </Option>
                    ))}
                  </FluentDropdown>
                );
              }}
            />
          </FormField>

          {isEdit ? (
            <FormField label="Habilitada">
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
                    <span>{field.value ? "Sí" : "No"}</span>
                  </div>
                )}
              />
            </FormField>
          ) : null}
        </div>
      ) : tab === "promociones" ? (
        <CampaignPromotionsTab
          campaignId={campaignId}
          readOnly={readOnly}
          onSaved={onChanged}
          styles={styles}
        />
      ) : (
        <AuditTab campaign={campaign} styles={styles} />
      )}
    </Drawer>
  );
}

type Styles = ReturnType<typeof useStyles>;

/**
 * Control "Cambiar estado": un botón por destino permitido (matriz hardcodeada).
 * Gated CAMPAIGNS_UPDATE. Si no hay destinos (ended) → hint terminal.
 */
function PermissionGuardedStatus({
  status,
  allowedTargets,
  transitioningTo,
  transitionError,
  disabled,
  onTransition,
  styles,
}: {
  status: CampaignStatus;
  allowedTargets: CampaignStatus[];
  transitioningTo: CampaignStatus | null;
  transitionError: string | null;
  disabled: boolean;
  onTransition: (to: CampaignStatus) => void;
  styles: Styles;
}) {
  return (
    <PermissionGuard anyOf={["CAMPAIGNS_UPDATE"]}>
      <div className={styles.statusPanel}>
        <div className={styles.statusRow}>
          <span className={styles.statusLabel}>Estado:</span>
          <StatusBadge status={status} />
        </div>
        {allowedTargets.length === 0 ? (
          <p className={styles.hint}>Campaña finalizada (estado terminal).</p>
        ) : (
          <div className={styles.statusRow}>
            <span className={styles.statusLabel}>Cambiar a:</span>
            {allowedTargets.map((to) => (
              <Button
                key={to}
                appearance="secondary"
                size="small"
                icon={transitioningTo === to ? <Spinner size="tiny" /> : <ArrowSyncRegular />}
                disabled={disabled}
                onClick={() => onTransition(to)}
              >
                {CAMPAIGN_TRANSITION_VERB[to]}
              </Button>
            ))}
          </div>
        )}
        {transitionError ? (
          <MessageBar intent="error">
            <MessageBarBody>{transitionError}</MessageBarBody>
          </MessageBar>
        ) : null}
      </div>
    </PermissionGuard>
  );
}

/**
 * Tab Promociones: editor M:N gated CAMPAIGNS_UPDATE. Carga las promociones ya
 * vinculadas (`getCampaignPromotions`) → preselección, y el catálogo de promociones
 * activas (`listActivePromotions`) como candidatas. Guardar reemplaza el set
 * completo con `setCampaignPromotions(id, { promotion_ids })`. En create (sin id),
 * solo un hint: el M:N requiere el id de la campaña.
 */
function CampaignPromotionsTab({
  campaignId,
  readOnly,
  onSaved,
  styles,
}: {
  campaignId: string | null;
  readOnly: boolean;
  onSaved?: () => void;
  styles: Styles;
}) {
  const { hasAnyPermission } = usePermissions();
  const canWrite = !readOnly && hasAnyPermission(["CAMPAIGNS_UPDATE"]);

  const [pending, startTransition] = useTransition();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<PromotionOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  useEffect(() => {
    // Sin id (create antes de guardar) no hay set que cargar ni catálogo que mostrar.
    if (!campaignId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void Promise.all([listActivePromotions(), getCampaignPromotions(campaignId)])
      .then(([active, assigned]) => {
        if (cancelled) return;
        setCatalog(active);
        setSelected(assigned.map((p) => p.id));
      })
      .catch(() => {
        if (!cancelled) setLoadError("No se pudieron cargar las promociones.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [campaignId]);

  const handleToggle = (id: string) => {
    setSavedOk(false);
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleSave = () => {
    if (!campaignId) return;
    setSaveError(null);
    setSavedOk(false);
    startTransition(async () => {
      const result = await setCampaignPromotions(campaignId, { promotion_ids: selected });
      if (!result.ok) {
        setSaveError(result.error ?? "No se pudieron guardar las promociones.");
        return;
      }
      setSavedOk(true);
      onSaved?.();
    });
  };

  // Cada opción muestra el nombre + el descuento, y el código como secundario.
  const options = catalog.map((p) => ({
    id: p.id,
    primary: `${p.name} · ${formatDiscount({
      discount_type: p.discount_type,
      discount_value: p.discount_value,
      currency: p.currency,
    })} (${DISCOUNT_TYPE_META[p.discount_type].label})`,
    secondary: p.code,
  }));

  return (
    <div className={styles.tabPanel}>
      {!campaignId ? (
        <p className={styles.emptyState}>Guarda la campaña primero para asignar promociones.</p>
      ) : loading ? (
        <div className={styles.loading}>
          <Spinner size="small" label="Cargando promociones…" />
        </div>
      ) : loadError ? (
        <MessageBar intent="error">
          <MessageBarBody>{loadError}</MessageBarBody>
        </MessageBar>
      ) : catalog.length === 0 ? (
        <p className={styles.emptyState}>
          No hay promociones activas. Crea promociones en Promociones.
        </p>
      ) : (
        <>
          {saveError ? (
            <MessageBar intent="error">
              <MessageBarBody>{saveError}</MessageBarBody>
            </MessageBar>
          ) : null}
          {savedOk ? (
            <MessageBar intent="success">
              <MessageBarBody>Promociones actualizadas.</MessageBarBody>
            </MessageBar>
          ) : null}

          <SearchableOptionList
            options={options}
            selected={selected}
            disabled={!canWrite || pending}
            onToggle={handleToggle}
            searchPlaceholder="Buscar promociones…"
            emptyMessage="No hay promociones activas en el catálogo."
          />
          <p className={styles.hint}>La campaña incluirá las promociones marcadas.</p>
          {canWrite ? (
            <div className={styles.footerRow}>
              <Button appearance="secondary" disabled={pending} onClick={handleSave}>
                {pending ? "Guardando…" : "Guardar promociones"}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function AuditTab({ campaign, styles }: { campaign: CampaignDetail | null; styles: Styles }) {
  if (!campaign) {
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
            <StatusBadge status={campaign.status} />
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID de la campaña</div>
          <div className={styles.auditValue}>
            <code>{campaign.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creada el</div>
          <div className={styles.auditValue}>{formatDate(campaign.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creada por</div>
          <div className={styles.auditValue}>
            {campaign.created_by_user?.full_name ?? "Sistema"}
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada el</div>
          <div className={styles.auditValue}>{formatDate(campaign.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada por</div>
          <div className={styles.auditValue}>
            {campaign.updated_by_user?.full_name ?? "Sistema"}
          </div>
        </div>
      </div>
    </div>
  );
}
