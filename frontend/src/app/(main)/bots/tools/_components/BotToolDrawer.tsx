"use client";

import {
  Button,
  Input,
  MessageBar,
  MessageBarBody,
  Switch,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createBotTool, getBotTool, updateBotTool } from "@/actions/bot-tools.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { usePermissions } from "@/hooks/usePermissions";
import { botToolCreateSchema } from "@/lib/schemas/bot-tools.schema";
import { appTokens } from "@/lib/theme/brand";

const useStyles = makeStyles({
  body: {
    paddingTop: tokens.spacingVerticalS,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  mono: { fontFamily: appTokens.fontMono },
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
});

// El form del editor: campos crudos de texto. `parameters_schema` viaja como
// string en el form (textarea JSON) y el Zod lo transforma a objeto en el submit.
type FormValues = {
  code: string;
  name: string;
  description: string;
  parameters_schema: string;
  target_service: string;
  requires_confirmation: boolean;
  active: boolean;
};

const EMPTY_SCHEMA = '{\n  "type": "object",\n  "properties": {}\n}';

interface Props {
  mode: "create" | "edit" | "view";
  toolId: string | null;
  onClose: () => void;
}

export function BotToolDrawer({ mode, toolId, onClose }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("BOT_TOOLS_WRITE");

  const readOnly = mode === "view";
  const isEdit = mode === "edit";
  const isCreate = mode === "create";

  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<FormValues>({
    // El resolver corre el botToolCreateSchema (que transforma `parameters_schema`
    // a objeto). El form mantiene `parameters_schema` como string; el submit envía
    // los valores ya validados/transformados por Zod en el Server Action.
    resolver: zodResolver(botToolCreateSchema) as never,
    defaultValues: {
      code: "",
      name: "",
      description: "",
      parameters_schema: isCreate ? EMPTY_SCHEMA : "",
      target_service: "",
      requires_confirmation: false,
      active: true,
    },
  });

  // (Re)carga del detalle cuando hay un id (edit/view) — trae parameters_schema.
  useEffect(() => {
    if (!toolId) return;
    let cancelled = false;
    void getBotTool(toolId)
      .then((res) => {
        if (cancelled) return;
        form.reset({
          code: res.data.code,
          name: res.data.name,
          description: res.data.description,
          parameters_schema: JSON.stringify(res.data.parameters_schema ?? {}, null, 2),
          target_service: res.data.target_service,
          requires_confirmation: res.data.requires_confirmation,
          active: res.data.active,
        });
      })
      .catch(() => {
        // El detalle pudo no cargar (404 si otro usuario la eliminó, o 5xx). No dejar el form
        // en defaults vacíos en silencio: avisar para que el usuario no guarde datos parciales.
        if (!cancelled)
          setServerError("No se pudo cargar la herramienta. Cierra y vuelve a intentar.");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toolId]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      // `values` ya pasó por el resolver (parameters_schema string→objeto). El action
      // vuelve a validar con el mismo schema (defensa en profundidad, idempotente).
      const result =
        toolId !== null ? await updateBotTool(toolId, values) : await createBotTool(values);
      if (!result.ok) {
        // 409 BOT_TOOL_CODE_TAKEN → MessageBar + error inline en `code`.
        if (result.error && /código|code/i.test(result.error) && isCreate) {
          form.setError("code", { message: "Ya existe una herramienta con este código." });
        }
        setServerError(result.error ?? "No se pudo guardar. Intenta de nuevo.");
        return;
      }
      onClose();
    });
  });

  const title =
    mode === "create"
      ? "Nueva herramienta"
      : mode === "view"
        ? "Herramienta"
        : "Editar herramienta";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      subtitle={form.watch("code") || undefined}
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
              disabled={pending || !canWrite}
              onClick={() => void onSubmit()}
            >
              {pending
                ? isCreate
                  ? "Creando…"
                  : "Guardando…"
                : isCreate
                  ? "Crear"
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

      <div className={styles.body}>
        <FormField
          label="Código"
          required
          error={form.formState.errors.code?.message}
          hint="Slug en minúsculas, números y guion bajo. No se puede cambiar luego."
        >
          <Controller
            control={form.control}
            name="code"
            render={({ field }) => (
              <Input
                {...field}
                disabled={readOnly || isEdit}
                className={styles.mono}
                placeholder="ej. list_services_by_vertical"
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
                placeholder="ej. Listar servicios por vertical"
              />
            )}
          />
        </FormField>

        <FormField
          label="Descripción"
          required
          error={form.formState.errors.description?.message}
          hint="La lee el modelo para decidir cuándo invocar esta herramienta. Sé claro y específico."
        >
          <Controller
            control={form.control}
            name="description"
            render={({ field }) => (
              <Textarea
                {...field}
                disabled={readOnly}
                resize="vertical"
                rows={3}
                placeholder="Devuelve los servicios activos de una vertical dada. Úsala cuando el contacto pregunte qué servicios hay…"
              />
            )}
          />
        </FormField>

        <FormField
          label="Esquema de parámetros (JSON Schema)"
          required
          error={form.formState.errors.parameters_schema?.message}
          hint="Subset común OpenAI/Anthropic. Debe ser un objeto JSON Schema válido. Define los argumentos que el bot debe pasar."
        >
          <Controller
            control={form.control}
            name="parameters_schema"
            render={({ field }) => (
              <Textarea
                {...field}
                disabled={readOnly}
                resize="vertical"
                rows={8}
                className={styles.mono}
                placeholder={EMPTY_SCHEMA}
              />
            )}
          />
        </FormField>

        <FormField
          label="Servicio destino"
          required
          error={form.formState.errors.target_service?.message}
          hint="<módulo>.<servicio>.<función> resuelto por el registro de herramientas. Ej.: crm.person_lead_status.transition."
        >
          <Controller
            control={form.control}
            name="target_service"
            render={({ field }) => (
              <Input
                {...field}
                disabled={readOnly}
                className={styles.mono}
                placeholder="ej. catalog.service.list_by_vertical"
              />
            )}
          />
        </FormField>

        <FormField
          label="Requiere confirmación"
          hint="Si está activo, las acciones de esta herramienta requerirán confirmación antes de ejecutarse."
        >
          <Controller
            control={form.control}
            name="requires_confirmation"
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

        {!isCreate ? (
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
                  <span>{field.value ? "Activa" : "Inactiva"}</span>
                </div>
              )}
            />
          </FormField>
        ) : null}
      </div>
    </Drawer>
  );
}
