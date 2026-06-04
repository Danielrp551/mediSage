"use client";

import {
  Button,
  Checkbox,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { activateBotVersion, createBotVersion } from "@/actions/bots.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { BOT_PROVIDER_META, PROVIDER_MODEL_PLACEHOLDER } from "@/lib/constants/bots";
import { botVersionSchema } from "@/lib/schemas/bots.schema";
import { appTokens } from "@/lib/theme/brand";
import {
  BOT_PROVIDERS,
  type BotConfigurationVersionDetail,
  type BotProvider,
} from "@/types/bots.types";

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
  mono: { fontFamily: appTokens.fontMono },
  hint: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    marginTop: tokens.spacingVerticalXXS,
  },
});

// El form del editor: campos crudos de texto. `parameters` viaja como string en
// el form (textarea JSON) y el Zod lo transforma a objeto en el submit.
export type VersionFormValues = {
  provider: BotProvider;
  model_name: string;
  system_prompt: string;
  parameters: string;
  notes: string;
};

interface Props {
  /** "create" = nueva versión; "view" = solo lectura de una versión existente. */
  mode: "create" | "view";
  configId: string;
  /** En "view", la versión a mostrar (ya cargada por el padre). */
  version?: BotConfigurationVersionDetail | null;
  /** Valores pre-rellenados (atajo "Crear nueva a partir de esta"). */
  seed?: Partial<VersionFormValues> | null;
  onClose: () => void;
  /** Tras crear (+activar opcional) — el padre refetcha versiones + fila del bot. */
  onCreated: () => void;
  /** Atajo desde "view": abrir un create pre-rellenado con esta versión. */
  onCloneToNew?: (seed: VersionFormValues) => void;
}

function metaParamsToText(params: Record<string, unknown> | undefined | null): string {
  if (!params || Object.keys(params).length === 0) return "";
  return JSON.stringify(params, null, 2);
}

export function BotVersionDrawer({
  mode,
  configId,
  version,
  seed,
  onClose,
  onCreated,
  onCloneToNew,
}: Props) {
  const styles = useStyles();
  const readOnly = mode === "view";
  const [serverError, setServerError] = useState<string | null>(null);
  const [activateOnCreate, setActivateOnCreate] = useState(false);
  const [pending, startTransition] = useTransition();

  const defaults: VersionFormValues = readOnly
    ? {
        provider: version?.provider ?? "openai",
        model_name: version?.model_name ?? "",
        system_prompt: version?.system_prompt ?? "",
        parameters: metaParamsToText(version?.parameters),
        notes: version?.notes ?? "",
      }
    : {
        provider: seed?.provider ?? "openai",
        model_name: seed?.model_name ?? "gpt-4.1-mini",
        system_prompt: seed?.system_prompt ?? "",
        parameters: seed?.parameters ?? "",
        notes: seed?.notes ?? "",
      };

  const form = useForm<VersionFormValues>({
    // El resolver corre el botVersionSchema (que transforma `parameters` a objeto).
    // El form mantiene `parameters` como string; el submit envía los valores ya
    // validados/transformados por Zod en el Server Action.
    resolver: zodResolver(botVersionSchema) as never,
    defaultValues: defaults,
  });

  const currentProvider = form.watch("provider");

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      // `values` ya pasó por el resolver; el action vuelve a validar (defensa en
      // profundidad) y transforma `parameters` (string→objeto) con el mismo schema.
      const result = await createBotVersion(configId, values);
      if (!result.ok) {
        setServerError(result.error ?? "No se pudo crear la versión.");
        return;
      }
      if (activateOnCreate && result.data?.data?.id) {
        const act = await activateBotVersion(configId, result.data.data.id);
        if (!act.ok) {
          // La versión se creó; falló solo la activación → avisar, no perder el trabajo.
          setServerError(act.error ?? "La versión se creó, pero no se pudo activar.");
          onCreated();
          return;
        }
      }
      onCreated();
      onClose();
    });
  });

  const title = readOnly ? `Versión v${version?.version ?? ""}` : "Nueva versión";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      size="medium"
      footer={
        readOnly ? (
          <>
            <Button onClick={onClose}>Cerrar</Button>
            {onCloneToNew ? (
              <Button
                appearance="primary"
                onClick={() =>
                  onCloneToNew({
                    provider: version?.provider ?? "openai",
                    model_name: version?.model_name ?? "",
                    system_prompt: version?.system_prompt ?? "",
                    parameters: metaParamsToText(version?.parameters),
                    notes: "",
                  })
                }
              >
                Crear nueva a partir de esta
              </Button>
            ) : null}
          </>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
              {pending ? "Creando…" : "Crear versión"}
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

      <div className={styles.body}>
        <div className={styles.twoCol}>
          <FormField label="Proveedor" required error={form.formState.errors.provider?.message}>
            <Controller
              control={form.control}
              name="provider"
              render={({ field }) => (
                <Dropdown
                  disabled={readOnly}
                  value={BOT_PROVIDER_META[field.value].label}
                  selectedOptions={[field.value]}
                  onOptionSelect={(_, data) =>
                    data.optionValue && field.onChange(data.optionValue as BotProvider)
                  }
                >
                  {BOT_PROVIDERS.map((p) => {
                    const meta = BOT_PROVIDER_META[p];
                    return (
                      <Option key={p} value={p} disabled={!meta.supported} text={meta.label}>
                        {meta.supported ? meta.label : `${meta.label} (próximamente)`}
                      </Option>
                    );
                  })}
                </Dropdown>
              )}
            />
          </FormField>

          <FormField
            label="Modelo"
            required
            error={form.formState.errors.model_name?.message}
            hint="Depende del proveedor. Ej.: gpt-4.1-mini, claude-sonnet-4-5."
          >
            <Controller
              control={form.control}
              name="model_name"
              render={({ field }) => (
                <Input
                  {...field}
                  disabled={readOnly}
                  placeholder={PROVIDER_MODEL_PLACEHOLDER[currentProvider]}
                />
              )}
            />
          </FormField>
        </div>

        <FormField
          label="Prompt de sistema"
          required
          error={form.formState.errors.system_prompt?.message}
        >
          <Controller
            control={form.control}
            name="system_prompt"
            render={({ field }) => (
              <Textarea
                {...field}
                disabled={readOnly}
                resize="vertical"
                rows={12}
                placeholder="Eres el asistente de preventa de la clínica. Tu objetivo es…"
              />
            )}
          />
        </FormField>

        <FormField
          label="Parámetros (JSON)"
          error={form.formState.errors.parameters?.message}
          hint="Esquema libre por proveedor (temperature, max_tokens, top_p…). Vacío = {}."
        >
          <Controller
            control={form.control}
            name="parameters"
            render={({ field }) => (
              <Textarea
                {...field}
                disabled={readOnly}
                resize="vertical"
                rows={4}
                className={styles.mono}
                placeholder={'{ "temperature": 0.4, "max_tokens": 800 }'}
              />
            )}
          />
        </FormField>

        <FormField label="Notas (changelog, opcional)" error={form.formState.errors.notes?.message}>
          <Controller
            control={form.control}
            name="notes"
            render={({ field }) => (
              <Textarea
                {...field}
                value={field.value ?? ""}
                disabled={readOnly}
                rows={2}
                placeholder="Ajusté el tono y agregué el cierre de lead."
              />
            )}
          />
        </FormField>

        {!readOnly ? (
          <Checkbox
            checked={activateOnCreate}
            onChange={(_, d) => setActivateOnCreate(Boolean(d.checked))}
            label="Activar esta versión al crearla"
          />
        ) : null}
      </div>
    </Drawer>
  );
}
