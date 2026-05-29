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
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { updateOffice } from "@/actions/office.actions";
import { FormField } from "@/components/ui/Form/FormField";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { usePermissions } from "@/hooks/usePermissions";
import { officeUpdateSchema, type OfficeUpdateInput } from "@/lib/schemas/office.schema";
import type { VerticalOption } from "@/types/catalog.types";
import type { OfficeDetail } from "@/types/clinic.types";

const useStyles = makeStyles({
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    maxWidth: "720px",
  },
  twoCol: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: tokens.spacingHorizontalM,
  },
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  actions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: tokens.spacingHorizontalS,
    marginTop: tokens.spacingVerticalS,
  },
});

interface Props {
  office: OfficeDetail;
  verticals: VerticalOption[];
}

export function OfficeDetailsTab({ office, verticals }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const { hasPermission } = usePermissions();
  const readOnly = !hasPermission("OFFICES_UPDATE");

  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<OfficeUpdateInput>({
    resolver: zodResolver(officeUpdateSchema),
    defaultValues: {
      name: office.name,
      room_number: office.room_number ?? "",
      floor: office.floor ?? "",
      description: office.description ?? "",
      vertical_ids: office.verticals.map((v) => v.id),
      active: office.active,
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = await updateOffice(office.id, values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      // Re-render the RSC so the header (name, status) reflects the new data.
      router.refresh();
    });
  });

  return (
    <div className={styles.panel}>
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.twoCol}>
        <FormField label="Sede" hint="La sede no se puede cambiar tras crear el consultorio.">
          <Input value={office.branch.name} disabled />
        </FormField>
        <FormField label="Código" hint="Único dentro de la sede. No editable.">
          <Input value={office.code} disabled />
        </FormField>
      </div>

      <FormField label="Nombre" required error={form.formState.errors.name?.message}>
        <Controller
          control={form.control}
          name="name"
          render={({ field }) => <Input {...field} value={field.value ?? ""} disabled={readOnly} />}
        />
      </FormField>

      <div className={styles.twoCol}>
        <FormField label="N° de sala" error={form.formState.errors.room_number?.message}>
          <Controller
            control={form.control}
            name="room_number"
            render={({ field }) => (
              <Input {...field} value={field.value ?? ""} disabled={readOnly} />
            )}
          />
        </FormField>
        <FormField label="Piso" error={form.formState.errors.floor?.message}>
          <Controller
            control={form.control}
            name="floor"
            render={({ field }) => (
              <Input {...field} value={field.value ?? ""} disabled={readOnly} />
            )}
          />
        </FormField>
      </div>

      <FormField label="Descripción" error={form.formState.errors.description?.message}>
        <Controller
          control={form.control}
          name="description"
          render={({ field }) => (
            <Textarea {...field} value={field.value ?? ""} rows={3} disabled={readOnly} />
          )}
        />
      </FormField>

      <FormField
        label="Verticales aptas"
        error={form.formState.errors.vertical_ids?.message}
        hint={`${(form.watch("vertical_ids") ?? []).length} de ${verticals.length} · verticales que este consultorio puede acoger.`}
      >
        <Controller
          control={form.control}
          name="vertical_ids"
          render={({ field }) => (
            <SearchableOptionList
              options={verticals.map((v) => ({ id: v.id, primary: v.name, secondary: v.code }))}
              selected={field.value ?? []}
              disabled={readOnly}
              onToggle={(id) => {
                const current = field.value ?? [];
                const next = current.includes(id)
                  ? current.filter((x) => x !== id)
                  : [...current, id];
                field.onChange(next);
              }}
              searchPlaceholder="Buscar verticales…"
              emptyMessage="Ninguna vertical coincide con la búsqueda."
            />
          )}
        />
      </FormField>

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

      {!readOnly ? (
        <div className={styles.actions}>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Guardando…" : "Guardar cambios"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
