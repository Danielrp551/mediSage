"use client";

import {
  Button,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Switch,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { updatePerson } from "@/actions/person.actions";
import { FormField } from "@/components/ui/Form/FormField";
import { usePermissions } from "@/hooks/usePermissions";
import { personUpdateSchema, type PersonUpdateInput } from "@/lib/schemas/person.schema";
import { DOCUMENT_TYPES } from "@/lib/schemas/user.schema";
import type { PersonDetail } from "@/types/crm.types";

const useStyles = makeStyles({
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    maxWidth: "720px",
  },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  actions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: tokens.spacingHorizontalS,
    marginTop: tokens.spacingVerticalS,
  },
});

interface Props {
  person: PersonDetail;
}

export function PersonSummaryTab({ person }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const { hasPermission } = usePermissions();
  const readOnly = !hasPermission("PERSONS_UPDATE");

  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<PersonUpdateInput>({
    resolver: zodResolver(personUpdateSchema),
    defaultValues: {
      first_name: person.first_name,
      last_name: person.last_name,
      second_last_name: person.second_last_name ?? "",
      document_type: person.document_type ?? null,
      document_number: person.document_number ?? "",
      birth_date: person.birth_date ?? "",
      gender: person.gender ?? "",
      address: person.address ?? "",
      notes: person.notes ?? "",
      active: person.active,
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = await updatePerson(person.id, values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      // Re-render el RSC para que el header (nombre, estado) refleje los cambios.
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
        <FormField label="Nombres" required error={form.formState.errors.first_name?.message}>
          <Controller
            control={form.control}
            name="first_name"
            render={({ field }) => (
              <Input {...field} value={field.value ?? ""} disabled={readOnly} />
            )}
          />
        </FormField>
        <FormField
          label="Apellido paterno"
          required
          error={form.formState.errors.last_name?.message}
        >
          <Controller
            control={form.control}
            name="last_name"
            render={({ field }) => (
              <Input {...field} value={field.value ?? ""} disabled={readOnly} />
            )}
          />
        </FormField>
      </div>

      <FormField label="Apellido materno" error={form.formState.errors.second_last_name?.message}>
        <Controller
          control={form.control}
          name="second_last_name"
          render={({ field }) => <Input {...field} value={field.value ?? ""} disabled={readOnly} />}
        />
      </FormField>

      <div className={styles.twoCol}>
        <FormField label="Tipo de documento">
          <Controller
            control={form.control}
            name="document_type"
            render={({ field }) => (
              <Dropdown
                value={field.value ?? ""}
                selectedOptions={field.value ? [field.value] : []}
                placeholder="Seleccionar…"
                disabled={readOnly}
                onOptionSelect={(_, data) => field.onChange(data.optionValue || null)}
              >
                <Option value="">— Ninguno —</Option>
                {DOCUMENT_TYPES.map((t) => (
                  <Option key={t} value={t}>
                    {t}
                  </Option>
                ))}
              </Dropdown>
            )}
          />
        </FormField>
        <FormField label="N° de documento" error={form.formState.errors.document_number?.message}>
          <Controller
            control={form.control}
            name="document_number"
            render={({ field }) => (
              <Input {...field} value={field.value ?? ""} disabled={readOnly} />
            )}
          />
        </FormField>
      </div>

      <div className={styles.twoCol}>
        <FormField label="Fecha de nacimiento" error={form.formState.errors.birth_date?.message}>
          <Controller
            control={form.control}
            name="birth_date"
            render={({ field }) => (
              <Input
                type="date"
                name={field.name}
                ref={field.ref}
                value={field.value ?? ""}
                onBlur={field.onBlur}
                onChange={(_, d) => field.onChange(d.value)}
                disabled={readOnly}
              />
            )}
          />
        </FormField>
        <FormField label="Género" error={form.formState.errors.gender?.message}>
          <Controller
            control={form.control}
            name="gender"
            render={({ field }) => (
              <Input {...field} value={field.value ?? ""} disabled={readOnly} />
            )}
          />
        </FormField>
      </div>

      <FormField label="Dirección" error={form.formState.errors.address?.message}>
        <Controller
          control={form.control}
          name="address"
          render={({ field }) => <Input {...field} value={field.value ?? ""} disabled={readOnly} />}
        />
      </FormField>

      <FormField label="Notas" error={form.formState.errors.notes?.message}>
        <Controller
          control={form.control}
          name="notes"
          render={({ field }) => (
            <Textarea {...field} value={field.value ?? ""} rows={3} disabled={readOnly} />
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
              <span>{field.value ? "Activo" : "Inactivo"}</span>
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
