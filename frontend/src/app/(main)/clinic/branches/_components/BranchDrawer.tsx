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
  makeStyles,
  tokens,
  type SelectTabData,
  type SelectTabEvent,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createBranch, getBranch, updateBranch } from "@/actions/branch.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { TIMEZONE_OPTIONS } from "@/lib/constants/timezones";
import { branchCreateSchema, type BranchCreateInput } from "@/lib/schemas/branch.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { BranchDetail } from "@/types/clinic.types";

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
  sectionLabel: {
    fontSize: tokens.fontSizeBase200,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeTextMuted,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    marginTop: tokens.spacingVerticalS,
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
  branchId: string | null;
  onClose: () => void;
}

type TabId = "details" | "audit";

export function BranchDrawer({ mode, branchId, onClose }: Props) {
  const styles = useStyles();
  const [branch, setBranch] = useState<BranchDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const hasAudit = mode !== "create";

  const form = useForm<BranchCreateInput & { active?: boolean }>({
    resolver: zodResolver(branchCreateSchema),
    defaultValues: {
      code: "",
      name: "",
      address_line: "",
      district: "",
      city: "",
      region: "",
      country: "PE",
      postal_code: "",
      latitude: null,
      longitude: null,
      phone: "",
      email: "",
      timezone: "America/Lima",
      active: true,
    },
  });

  useEffect(() => {
    if (!branchId) return;
    let cancelled = false;
    void getBranch(branchId).then((res) => {
      if (cancelled) return;
      setBranch(res.data);
      form.reset({
        code: res.data.code,
        name: res.data.name,
        address_line: res.data.address_line,
        district: res.data.district ?? undefined,
        city: res.data.city,
        region: res.data.region ?? undefined,
        country: res.data.country,
        postal_code: res.data.postal_code ?? undefined,
        latitude: res.data.latitude ?? undefined,
        longitude: res.data.longitude ?? undefined,
        phone: res.data.phone ?? undefined,
        email: res.data.email ?? undefined,
        timezone: res.data.timezone,
        active: res.data.active,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [branchId, form]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = branchId ? await updateBranch(branchId, values) : await createBranch(values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
    });
  });

  const title =
    mode === "create" ? "Nueva sede" : mode === "edit" ? "Editar sede" : "Detalle de sede";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={branch?.code ?? form.watch("code") ?? undefined}
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
                  ? "Crear sede"
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
          <div className={styles.twoCol}>
            <FormField
              label="Código"
              required
              error={form.formState.errors.code?.message}
              hint="Slug estable. Lo usan los bots y las URLs internas."
            >
              <Controller
                control={form.control}
                name="code"
                render={({ field }) => (
                  <Input {...field} disabled={readOnly || isEdit} placeholder="ej. lima_centro" />
                )}
              />
            </FormField>
            <FormField label="Nombre" required error={form.formState.errors.name?.message}>
              <Controller
                control={form.control}
                name="name"
                render={({ field }) => (
                  <Input {...field} disabled={readOnly} placeholder="ej. Sede Lima Centro" />
                )}
              />
            </FormField>
          </div>

          <div className={styles.sectionLabel}>Ubicación</div>
          <FormField label="Dirección" required error={form.formState.errors.address_line?.message}>
            <Controller
              control={form.control}
              name="address_line"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. Av. Larco 1234" />
              )}
            />
          </FormField>
          <div className={styles.twoCol}>
            <FormField label="Distrito" error={form.formState.errors.district?.message}>
              <Controller
                control={form.control}
                name="district"
                render={({ field }) => (
                  <Input {...field} value={field.value ?? ""} disabled={readOnly} />
                )}
              />
            </FormField>
            <FormField label="Ciudad" required error={form.formState.errors.city?.message}>
              <Controller
                control={form.control}
                name="city"
                render={({ field }) => <Input {...field} disabled={readOnly} />}
              />
            </FormField>
          </div>
          <div className={styles.twoCol}>
            <FormField label="Región" error={form.formState.errors.region?.message}>
              <Controller
                control={form.control}
                name="region"
                render={({ field }) => (
                  <Input {...field} value={field.value ?? ""} disabled={readOnly} />
                )}
              />
            </FormField>
            <FormField
              label="País"
              error={form.formState.errors.country?.message}
              hint="ISO de 2 letras (ej. PE)"
            >
              <Controller
                control={form.control}
                name="country"
                render={({ field }) => (
                  <Input
                    {...field}
                    disabled={readOnly}
                    maxLength={2}
                    onChange={(_, d) => field.onChange(d.value.toUpperCase())}
                  />
                )}
              />
            </FormField>
          </div>
          <div className={styles.twoCol}>
            <FormField label="Código postal" error={form.formState.errors.postal_code?.message}>
              <Controller
                control={form.control}
                name="postal_code"
                render={({ field }) => (
                  <Input {...field} value={field.value ?? ""} disabled={readOnly} />
                )}
              />
            </FormField>
            <FormField
              label="Zona horaria"
              required
              error={form.formState.errors.timezone?.message}
            >
              <Controller
                control={form.control}
                name="timezone"
                render={({ field }) => {
                  const selected = TIMEZONE_OPTIONS.find((t) => t.key === field.value);
                  return (
                    <Dropdown
                      value={selected?.label ?? field.value ?? ""}
                      selectedOptions={field.value ? [field.value] : []}
                      disabled={readOnly}
                      onOptionSelect={(_, d) => field.onChange(d.optionValue ?? "America/Lima")}
                    >
                      {TIMEZONE_OPTIONS.map((t) => (
                        <Option key={t.key} value={t.key}>
                          {t.label}
                        </Option>
                      ))}
                    </Dropdown>
                  );
                }}
              />
            </FormField>
          </div>
          <div className={styles.twoCol}>
            <FormField
              label="Latitud"
              error={form.formState.errors.latitude?.message}
              hint="Opcional, ej. -12.046374"
            >
              <Controller
                control={form.control}
                name="latitude"
                render={({ field }) => (
                  <Input
                    value={field.value ?? ""}
                    onChange={(_, d) => field.onChange(d.value || null)}
                    disabled={readOnly}
                    inputMode="decimal"
                  />
                )}
              />
            </FormField>
            <FormField
              label="Longitud"
              error={form.formState.errors.longitude?.message}
              hint="Opcional, ej. -77.042793"
            >
              <Controller
                control={form.control}
                name="longitude"
                render={({ field }) => (
                  <Input
                    value={field.value ?? ""}
                    onChange={(_, d) => field.onChange(d.value || null)}
                    disabled={readOnly}
                    inputMode="decimal"
                  />
                )}
              />
            </FormField>
          </div>

          <div className={styles.sectionLabel}>Contacto</div>
          <div className={styles.twoCol}>
            <FormField label="Teléfono" error={form.formState.errors.phone?.message}>
              <Controller
                control={form.control}
                name="phone"
                render={({ field }) => (
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    disabled={readOnly}
                    placeholder="+51 …"
                  />
                )}
              />
            </FormField>
            <FormField label="Correo" error={form.formState.errors.email?.message}>
              <Controller
                control={form.control}
                name="email"
                render={({ field }) => (
                  <Input
                    {...field}
                    value={field.value ?? ""}
                    type="email"
                    disabled={readOnly}
                    placeholder="sede@ejemplo.com"
                  />
                )}
              />
            </FormField>
          </div>

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
        <AuditTab branch={branch} styles={styles} />
      )}
    </Drawer>
  );
}

type Styles = ReturnType<typeof useStyles>;

function AuditTab({ branch, styles }: { branch: BranchDetail | null; styles: Styles }) {
  if (!branch) {
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
            <Badge appearance="filled" color={branch.active ? "success" : "informative"}>
              {branch.active ? "Activa" : "Deshabilitada"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID de la sede</div>
          <div className={styles.auditValue}>
            <code>{branch.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creada el</div>
          <div className={styles.auditValue}>{formatDate(branch.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creada por</div>
          <div className={styles.auditValue}>{branch.created_by_user?.full_name ?? "—"}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada el</div>
          <div className={styles.auditValue}>{formatDate(branch.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizada por</div>
          <div className={styles.auditValue}>{branch.updated_by_user?.full_name ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}
