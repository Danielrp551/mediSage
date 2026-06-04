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
import { useRouter } from "next/navigation";

import {
  createBotConfiguration,
  getBotConfiguration,
  updateBotConfiguration,
} from "@/actions/bots.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { usePermissions } from "@/hooks/usePermissions";
import { BOT_PROVIDER_META, BOT_TYPE_META } from "@/lib/constants/bots";
import {
  botConfigurationCreateSchema,
  type BotConfigurationCreateInput,
} from "@/lib/schemas/bots.schema";
import { appTokens } from "@/lib/theme/brand";
import { BOT_TYPES, type BotConfigurationDetail, type BotType } from "@/types/bots.types";

import { BotVersionsTab } from "./BotVersionsTab";

const useStyles = makeStyles({
  tabPanel: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  switchRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  currentVersionRow: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  currentVersionLabel: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  currentVersionValue: {
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightMedium,
    color: appTokens.chromeText,
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  noVersion: {
    color: tokens.colorPaletteRedForeground1,
    fontWeight: tokens.fontWeightMedium,
  },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
});

interface Props {
  mode: "create" | "edit" | "view";
  configId: string | null;
  onClose: () => void;
}

type TabId = "details" | "versions";

type FormValues = BotConfigurationCreateInput & { active?: boolean };

export function BotConfigurationDrawer({ mode: initialMode, configId, onClose }: Props) {
  const styles = useStyles();
  const router = useRouter();

  // El modo es estado interno: tras crear, pasamos a "edit" (mismo drawer abierto)
  // y se habilita el tab Versiones — decisión: mantener el drawer abierto.
  const [mode, setMode] = useState<Props["mode"]>(initialMode);
  const [currentId, setCurrentId] = useState<string | null>(configId);
  const [config, setConfig] = useState<BotConfigurationDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const isCreate = mode === "create";
  const { hasAnyPermission } = usePermissions();
  // El tab Versiones lee GET /configurations/{id}/versions → exige VERSIONS_READ (permiso
  // separado de CONFIGURATIONS_READ). El ASESOR tiene CONFIGURATIONS_READ pero NO VERSIONS_READ:
  // sin este gate, al abrir el tab dispararía un 403 visible.
  const canReadVersions = hasAnyPermission(["BOT_CONFIGURATION_VERSIONS_READ"]);
  // Versiones solo existen para un bot ya creado Y si el viewer puede leerlas.
  const versionsAvailable = currentId !== null && canReadVersions;

  const form = useForm<FormValues>({
    resolver: zodResolver(botConfigurationCreateSchema),
    defaultValues: {
      code: "",
      name: "",
      bot_type: "preventa",
      description: "",
      max_turns_per_conversation: null,
      active: true,
    },
  });

  // (Re)carga del detalle cuando hay un id (edit/view, o tras crear).
  const loadConfig = (id: string) => {
    void getBotConfiguration(id).then((res) => {
      setConfig(res.data);
      form.reset({
        code: res.data.code,
        name: res.data.name,
        bot_type: res.data.bot_type,
        description: res.data.description ?? "",
        max_turns_per_conversation: res.data.max_turns_per_conversation,
        active: res.data.active,
      });
    });
  };

  useEffect(() => {
    if (!configId) return;
    let cancelled = false;
    void getBotConfiguration(configId).then((res) => {
      if (cancelled) return;
      setConfig(res.data);
      form.reset({
        code: res.data.code,
        name: res.data.name,
        bot_type: res.data.bot_type,
        description: res.data.description ?? "",
        max_turns_per_conversation: res.data.max_turns_per_conversation,
        active: res.data.active,
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configId]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    // Descripción vacía → null (no persistir "" en la columna nullable; consistente con el resto).
    const payload = {
      ...values,
      description: values.description && values.description.trim() ? values.description : null,
    };
    startTransition(async () => {
      if (currentId) {
        const result = await updateBotConfiguration(currentId, payload);
        if (!result.ok) {
          setServerError(result.error ?? "No se pudo guardar.");
          return;
        }
        setConfig(result.data?.data ?? null);
        router.refresh();
        onClose();
      } else {
        const result = await createBotConfiguration(payload);
        if (!result.ok) {
          setServerError(result.error ?? "No se pudo crear el bot.");
          return;
        }
        const created = result.data?.data;
        router.refresh();
        if (created) {
          // Mantener el drawer abierto en modo edit → habilita el tab Versiones.
          setConfig(created);
          setCurrentId(created.id);
          setMode("edit");
          setServerError(null);
        } else {
          onClose();
        }
      }
    });
  });

  const title =
    mode === "create"
      ? "Nuevo bot"
      : (config?.name ??
        form.watch("name") ??
        (mode === "view" ? "Detalle del bot" : "Editar bot"));

  const currentVersionNumber = config?.current_version_number ?? null;
  const currentVersionProvider = config?.current_version?.provider ?? null;

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={config?.code ?? undefined}
      size="large"
      footer={
        // El footer es del tab Datos; el tab Versiones tiene sus propias acciones.
        tab !== "details" ? (
          <Button onClick={onClose}>Cerrar</Button>
        ) : readOnly ? (
          <Button onClick={onClose}>Cerrar</Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
              {pending
                ? isCreate
                  ? "Creando…"
                  : "Guardando…"
                : isCreate
                  ? "Crear bot"
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
        <Tab value="versions" disabled={!versionsAvailable}>
          Versiones
        </Tab>
      </TabList>

      {tab === "details" ? (
        <div className={styles.tabPanel}>
          <FormField
            label="Código"
            required
            error={form.formState.errors.code?.message}
            hint="Slug estable en minúsculas, números y guion bajo. No se puede cambiar luego."
          >
            <Controller
              control={form.control}
              name="code"
              render={({ field }) => (
                <Input {...field} disabled={readOnly || isEdit} placeholder="ej. preventa_dental" />
              )}
            />
          </FormField>

          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => (
                <Input {...field} disabled={readOnly} placeholder="ej. Bot de Preventa" />
              )}
            />
          </FormField>

          <FormField label="Tipo de bot" required error={form.formState.errors.bot_type?.message}>
            <Controller
              control={form.control}
              name="bot_type"
              render={({ field }) => (
                <Dropdown
                  disabled={readOnly}
                  value={BOT_TYPE_META[field.value as BotType].label}
                  selectedOptions={[field.value]}
                  onOptionSelect={(_, data) =>
                    data.optionValue && field.onChange(data.optionValue as BotType)
                  }
                >
                  {BOT_TYPES.map((t) => (
                    <Option key={t} value={t} text={BOT_TYPE_META[t].label}>
                      {BOT_TYPE_META[t].label}
                    </Option>
                  ))}
                </Dropdown>
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
                  placeholder="Describe brevemente qué hace este bot…"
                />
              )}
            />
          </FormField>

          <FormField
            label="Máx. turnos por conversación (opcional)"
            error={form.formState.errors.max_turns_per_conversation?.message}
            hint="Vacío = sin límite. Guard opcional para evitar bucles largos."
          >
            <Controller
              control={form.control}
              name="max_turns_per_conversation"
              render={({ field }) => (
                <Input
                  type="number"
                  min={1}
                  disabled={readOnly}
                  value={
                    field.value === null || field.value === undefined ? "" : String(field.value)
                  }
                  onChange={(_, d) => field.onChange(d.value === "" ? null : Number(d.value))}
                  placeholder="ej. 20"
                />
              )}
            />
          </FormField>

          {!isCreate ? (
            <>
              <Divider />
              <div className={styles.currentVersionRow}>
                <span className={styles.currentVersionLabel}>Versión vigente</span>
                {currentVersionNumber !== null ? (
                  <span className={styles.currentVersionValue}>
                    <Badge appearance="outline">v{currentVersionNumber}</Badge>
                    {currentVersionProvider ? (
                      <span className={styles.hint}>
                        {BOT_PROVIDER_META[currentVersionProvider].label}
                        {config?.current_version?.model_name
                          ? ` (${config.current_version.model_name})`
                          : ""}
                      </span>
                    ) : null}
                  </span>
                ) : (
                  <span className={`${styles.currentVersionValue} ${styles.noVersion}`}>
                    — sin versión (no usable)
                  </span>
                )}
                {currentVersionNumber === null ? (
                  <span className={styles.hint}>
                    Crea y activa una versión (pestaña Versiones) para que el bot pueda responder.
                  </span>
                ) : (
                  <span className={styles.hint}>
                    El prompt y los parámetros se editan creando una nueva versión (pestaña
                    Versiones).
                  </span>
                )}
              </div>
            </>
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
                    <span>{field.value ? "Activo" : "Inactivo"}</span>
                  </div>
                )}
              />
            </FormField>
          ) : null}
        </div>
      ) : currentId ? (
        <BotVersionsTab
          configId={currentId}
          currentVersionId={config?.current_version_id ?? null}
          readOnly={readOnly}
          onVersionActivated={() => {
            loadConfig(currentId);
            router.refresh();
          }}
          onVersionsChanged={() => loadConfig(currentId)}
        />
      ) : null}
    </Drawer>
  );
}
