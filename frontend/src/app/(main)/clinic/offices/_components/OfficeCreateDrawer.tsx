"use client";

import {
  Button,
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
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createOffice } from "@/actions/office.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { officeCreateSchema, type OfficeCreateInput } from "@/lib/schemas/office.schema";
import type { VerticalOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";

const useStyles = makeStyles({
  panel: {
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
});

interface Props {
  branches: BranchOption[];
  /** Pre-selects the branch in create mode (from the active list filter). */
  defaultBranchId?: string | null;
  onClose: () => void;
}

export function OfficeCreateDrawer({ branches, defaultBranchId, onClose }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const [verticals, setVerticals] = useState<VerticalOption[]>([]);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<OfficeCreateInput>({
    resolver: zodResolver(officeCreateSchema),
    defaultValues: {
      branch_id: defaultBranchId ?? "",
      code: "",
      name: "",
      room_number: "",
      floor: "",
      description: "",
      vertical_ids: [],
    },
  });

  useEffect(() => {
    let cancelled = false;
    void listActiveVerticals().then((rows) => {
      if (!cancelled) setVerticals(rows);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = await createOffice(values);
      if (!result.ok || !result.data) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
      // Land on the new office's detail page to configure hours/closures next.
      router.push(`/clinic/offices/${result.data.data.id}`);
    });
  });

  return (
    <Drawer
      open
      onClose={onClose}
      title="Nuevo consultorio"
      subtitle={form.watch("code") || undefined}
      size="medium"
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Creando…" : "Crear consultorio"}
          </Button>
        </>
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.panel}>
        <FormField label="Sede" required error={form.formState.errors.branch_id?.message}>
          <Controller
            control={form.control}
            name="branch_id"
            render={({ field }) => {
              const selectedName = branches.find((b) => b.id === field.value)?.name ?? "";
              return (
                <Dropdown
                  value={selectedName}
                  selectedOptions={field.value ? [field.value] : []}
                  placeholder="Selecciona una sede…"
                  onOptionSelect={(_, d) => field.onChange(d.optionValue ?? "")}
                >
                  {branches.map((b) => (
                    <Option key={b.id} value={b.id}>
                      {b.name}
                    </Option>
                  ))}
                </Dropdown>
              );
            }}
          />
        </FormField>

        <div className={styles.twoCol}>
          <FormField
            label="Código"
            required
            error={form.formState.errors.code?.message}
            hint="Único dentro de la sede."
          >
            <Controller
              control={form.control}
              name="code"
              render={({ field }) => <Input {...field} placeholder="ej. C-04" />}
            />
          </FormField>
          <FormField label="Nombre" required error={form.formState.errors.name?.message}>
            <Controller
              control={form.control}
              name="name"
              render={({ field }) => <Input {...field} placeholder="ej. Consultorio 4" />}
            />
          </FormField>
        </div>

        <div className={styles.twoCol}>
          <FormField label="N° de sala" error={form.formState.errors.room_number?.message}>
            <Controller
              control={form.control}
              name="room_number"
              render={({ field }) => <Input {...field} value={field.value ?? ""} />}
            />
          </FormField>
          <FormField label="Piso" error={form.formState.errors.floor?.message}>
            <Controller
              control={form.control}
              name="floor"
              render={({ field }) => <Input {...field} value={field.value ?? ""} />}
            />
          </FormField>
        </div>

        <FormField label="Descripción" error={form.formState.errors.description?.message}>
          <Controller
            control={form.control}
            name="description"
            render={({ field }) => (
              <Textarea
                {...field}
                value={field.value ?? ""}
                rows={3}
                placeholder="Describe brevemente este consultorio…"
              />
            )}
          />
        </FormField>

        <FormField
          label="Verticales aptas"
          required
          error={form.formState.errors.vertical_ids?.message}
          hint={`${form.watch("vertical_ids").length} de ${verticals.length} · verticales que este consultorio puede acoger.`}
        >
          <Controller
            control={form.control}
            name="vertical_ids"
            render={({ field }) => (
              <SearchableOptionList
                options={verticals.map((v) => ({ id: v.id, primary: v.name, secondary: v.code }))}
                selected={field.value}
                disabled={false}
                onToggle={(id) => {
                  const next = field.value.includes(id)
                    ? field.value.filter((x) => x !== id)
                    : [...field.value, id];
                  field.onChange(next);
                }}
                searchPlaceholder="Buscar verticales…"
                emptyMessage="Ninguna vertical coincide con la búsqueda."
              />
            )}
          />
        </FormField>
      </div>
    </Drawer>
  );
}
