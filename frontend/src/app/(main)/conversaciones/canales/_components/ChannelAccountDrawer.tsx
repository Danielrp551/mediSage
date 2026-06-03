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
import {
  CheckmarkCircleRegular,
  DismissCircleRegular,
} from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import {
  createChannelAccount,
  getChannelAccount,
  updateChannelAccount,
} from "@/actions/channel-account.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { CHANNEL_TYPE_META } from "@/lib/constants/crm";
import {
  channelAccountCreateSchema,
  type ChannelAccountCreateInput,
} from "@/lib/schemas/channel-account.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ChannelAccountDetail } from "@/types/conversations.types";
import { CHANNEL_TYPES, type ChannelType } from "@/types/crm.types";

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
  credentialsRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  switchRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
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
});

// MVP: sólo WhatsApp es seleccionable; el resto se muestra "(próximamente)"
// deshabilitado. El schema acepta los 8 para no bloquear futuros canales.
const ENABLED_CHANNEL_TYPES: readonly ChannelType[] = ["whatsapp"];

interface Props {
  mode: "create" | "edit" | "view";
  channelAccountId: string | null;
  onClose: () => void;
}

type TabId = "details" | "audit";

type FormValues = ChannelAccountCreateInput & { active?: boolean };

export function ChannelAccountDrawer({ mode, channelAccountId, onClose }: Props) {
  const styles = useStyles();
  const [account, setAccount] = useState<ChannelAccountDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const isCreate = mode === "create";
  const hasAudit = mode !== "create";

  const form = useForm<FormValues>({
    resolver: zodResolver(channelAccountCreateSchema),
    defaultValues: {
      channel_type: "whatsapp",
      name: "",
      external_identifier: "",
      secret_name: "",
      webhook_verify_token: "",
      phone_number_id: "",
      active: true,
    },
  });

  useEffect(() => {
    if (!channelAccountId) return;
    let cancelled = false;
    void getChannelAccount(channelAccountId).then((res) => {
      if (cancelled) return;
      setAccount(res.data);
      form.reset({
        channel_type: res.data.channel_type,
        name: res.data.name,
        external_identifier: res.data.external_identifier,
        secret_name: res.data.secret_name ?? "",
        webhook_verify_token: res.data.webhook_verify_token ?? "",
        phone_number_id: res.data.phone_number_id ?? "",
        active: res.data.active,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [channelAccountId, form]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      // El Update schema omite `channel_type` (inmutable); enviamos el form
      // completo y el Zod del server toma lo que necesita.
      const result = channelAccountId
        ? await updateChannelAccount(channelAccountId, values)
        : await createChannelAccount(values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
    });
  });

  const title =
    mode === "create"
      ? "Nuevo canal"
      : mode === "edit"
        ? "Editar canal"
        : "Detalle del canal";

  // En create todavía no hay flag del backend; en edit/view lo trae el Detail.
  const credentialsConfigured = account?.credentials_configured ?? false;

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={account?.name ?? form.watch("name") ?? undefined}
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
                  ? "Crear canal"
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
            label="Canal"
            required
            error={form.formState.errors.channel_type?.message}
            hint="En el MVP sólo WhatsApp está disponible; el resto llegará más adelante."
          >
            <Controller
              control={form.control}
              name="channel_type"
              render={({ field }) => (
                <Dropdown
                  // channel_type es inmutable: sólo editable al crear.
                  disabled={readOnly || isEdit}
                  value={CHANNEL_TYPE_META[field.value as ChannelType]?.label ?? ""}
                  selectedOptions={[field.value]}
                  onOptionSelect={(_, data) =>
                    data.optionValue && field.onChange(data.optionValue as ChannelType)
                  }
                >
                  {CHANNEL_TYPES.map((c) => {
                    const enabled = ENABLED_CHANNEL_TYPES.includes(c);
                    return (
                      <Option key={c} value={c} disabled={!enabled} text={CHANNEL_TYPE_META[c].label}>
                        {enabled
                          ? CHANNEL_TYPE_META[c].label
                          : `${CHANNEL_TYPE_META[c].label} (próximamente)`}
                      </Option>
                    );
                  })}
                </Dropdown>
              )}
            />
          </FormField>

          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. WhatsApp Estética" />
              )}
            />
          </FormField>

          <FormField
            label="Identificador externo"
            required
            error={form.formState.errors.external_identifier?.message}
            hint="Número de WhatsApp Business (ej. 51999111222)."
          >
            <Controller
              control={form.control}
              name="external_identifier"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. 51999111222" />
              )}
            />
          </FormField>

          <FormField
            label="ID del número (WhatsApp Cloud API)"
            error={form.formState.errors.phone_number_id?.message}
            hint="phone_number_id del número en la API de Meta (para enviar mensajes)."
          >
            <Controller
              control={form.control}
              name="phone_number_id"
              render={({ field }) => (
                <Input
                  {...field}
                  value={field.value ?? ""}
                  disabled={readOnly}
                  placeholder="ej. 123456789012345"
                />
              )}
            />
          </FormField>

          <Divider />

          <FormField
            label="Nombre del secreto (Secret Manager)"
            error={form.formState.errors.secret_name?.message}
            hint="Sólo el NOMBRE del secreto en GCP Secret Manager (ej. medisage-whatsapp-estetica-qa). El token de acceso nunca se ingresa ni se muestra aquí; se gestiona en ops."
          >
            <Controller
              control={form.control}
              name="secret_name"
              render={({ field }) => (
                <Input
                  {...field}
                  value={field.value ?? ""}
                  disabled={readOnly}
                  placeholder="ej. medisage-whatsapp-estetica-qa"
                />
              )}
            />
          </FormField>

          <FormField
            label="Token de verificación del webhook"
            error={form.formState.errors.webhook_verify_token?.message}
            hint="Challenge que Meta envía en el GET del webhook. Editable en claro (no es un secreto duro)."
          >
            <Controller
              control={form.control}
              name="webhook_verify_token"
              render={({ field }) => (
                <Input
                  {...field}
                  value={field.value ?? ""}
                  disabled={readOnly}
                  placeholder="ej. mi-token-de-verificacion"
                />
              )}
            />
          </FormField>

          {!isCreate ? (
            <FormField label="Credenciales">
              <div className={styles.credentialsRow}>
                {credentialsConfigured ? (
                  <Badge appearance="tint" color="success" icon={<CheckmarkCircleRegular />}>
                    Configuradas
                  </Badge>
                ) : (
                  <Badge appearance="tint" color="warning" icon={<DismissCircleRegular />}>
                    Sin configurar
                  </Badge>
                )}
              </div>
            </FormField>
          ) : null}

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
        <AuditTab account={account} styles={styles} />
      )}
    </Drawer>
  );
}

type Styles = ReturnType<typeof useStyles>;

function AuditTab({
  account,
  styles,
}: {
  account: ChannelAccountDetail | null;
  styles: Styles;
}) {
  if (!account) {
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
            <Badge appearance="filled" color={account.active ? "success" : "informative"}>
              {account.active ? "Activo" : "Deshabilitado"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID del canal</div>
          <div className={styles.auditValue}>
            <code>{account.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creado el</div>
          <div className={styles.auditValue}>{formatDate(account.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creado por</div>
          <div className={styles.auditValue}>{account.created_by_user?.full_name ?? "—"}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado el</div>
          <div className={styles.auditValue}>{formatDate(account.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado por</div>
          <div className={styles.auditValue}>{account.updated_by_user?.full_name ?? "—"}</div>
        </div>
      </div>
    </div>
  );
}
