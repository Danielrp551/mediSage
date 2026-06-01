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
import { AddRegular, DismissRegular } from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";

import { createPerson } from "@/actions/person.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { CHANNEL_TYPE_META } from "@/lib/constants/crm";
import { personCreateSchema, type PersonCreateInput } from "@/lib/schemas/person.schema";
import { DOCUMENT_TYPES } from "@/lib/schemas/user.schema";
import { appTokens } from "@/lib/theme/brand";
import { CHANNEL_TYPES, type ChannelType } from "@/types/crm.types";

const useStyles = makeStyles({
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  sectionTitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  sectionHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
  },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  identList: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  // Tarjeta por identificador: fila superior (Canal | Valor | quitar) + fila de
  // flags debajo. Evita el apretujamiento de meter todo en una sola línea.
  identRow: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  // Canal | Valor | quitar. Mitades iguales (como `twoCol` de la sección Datos)
  // con `minmax(0,1fr)` para que ambos encojan sin cortarse; NO capear Canal a un
  // ancho fijo (el Dropdown de Fluent desborda su track y se pega al input). Gutter
  // `spacingHorizontalM` = igual que el resto del form (sin esto Canal y Valor se ven pegados).
  identTopRow: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr) auto",
    gap: tokens.spacingHorizontalM,
    alignItems: "flex-end",
  },
  identChecksRow: {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: tokens.spacingHorizontalL,
  },
  // El grid item (FormField/Field) debe poder encoger por debajo del ancho de su
  // contenido (min-width:auto por defecto lo impide).
  gridCell: { minWidth: 0 },
  // El control llena su celda y encoge CON ella. Sin esto el Dropdown de Fluent
  // conserva su min-width intrínseco (~250px), desborda su track del grid y se
  // pega al vecino (el track encoge con minmax(0,1fr) pero el control no).
  control: { width: "100%", minWidth: 0 },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
});

interface Props {
  onClose: () => void;
}

export function PersonCreateDrawer({ onClose }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<PersonCreateInput>({
    resolver: zodResolver(personCreateSchema),
    defaultValues: {
      first_name: "",
      last_name: "",
      second_last_name: "",
      document_type: null,
      document_number: "",
      birth_date: "",
      gender: "",
      address: "",
      notes: "",
      identifiers: [],
    },
  });

  const identifiers = useFieldArray({ control: form.control, name: "identifiers" });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = await createPerson(values);
      if (!result.ok || !result.data) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onClose();
      router.push(`/crm/personas/${result.data.data.id}`);
    });
  });

  const identifierErrors = form.formState.errors.identifiers;

  return (
    <Drawer
      open
      onClose={onClose}
      title="Nuevo contacto"
      subtitle={
        [form.watch("first_name"), form.watch("last_name")].filter(Boolean).join(" ") || undefined
      }
      size="medium"
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Creando…" : "Crear"}
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
        <h3 className={styles.sectionTitle}>Datos de la persona</h3>

        <div className={styles.twoCol}>
          <FormField label="Nombres" required error={form.formState.errors.first_name?.message}>
            <Controller
              control={form.control}
              name="first_name"
              render={({ field }) => <Input {...field} value={field.value ?? ""} />}
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
              render={({ field }) => <Input {...field} value={field.value ?? ""} />}
            />
          </FormField>
        </div>

        <FormField label="Apellido materno" error={form.formState.errors.second_last_name?.message}>
          <Controller
            control={form.control}
            name="second_last_name"
            render={({ field }) => <Input {...field} value={field.value ?? ""} />}
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
              render={({ field }) => <Input {...field} value={field.value ?? ""} />}
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
                />
              )}
            />
          </FormField>
          <FormField label="Género" error={form.formState.errors.gender?.message}>
            <Controller
              control={form.control}
              name="gender"
              render={({ field }) => (
                <Input {...field} value={field.value ?? ""} placeholder="Texto libre" />
              )}
            />
          </FormField>
        </div>

        <FormField label="Dirección" error={form.formState.errors.address?.message}>
          <Controller
            control={form.control}
            name="address"
            render={({ field }) => <Input {...field} value={field.value ?? ""} />}
          />
        </FormField>

        <FormField label="Notas" error={form.formState.errors.notes?.message}>
          <Controller
            control={form.control}
            name="notes"
            render={({ field }) => <Textarea {...field} value={field.value ?? ""} rows={3} />}
          />
        </FormField>

        <div className={styles.sectionHeader}>
          <h3 className={styles.sectionTitle}>Identificadores (opcional)</h3>
          <Button
            appearance="subtle"
            icon={<AddRegular />}
            onClick={() =>
              identifiers.append({
                channel_type: "whatsapp",
                identifier: "",
                is_primary: false,
                verified: false,
              })
            }
          >
            Agregar
          </Button>
        </div>

        {identifiers.fields.length === 0 ? (
          <p className={styles.hint}>
            Agrega un identificador (WhatsApp, correo, teléfono…) para poder contactar a esta
            persona.
          </p>
        ) : (
          <div className={styles.identList}>
            {identifiers.fields.map((row, i) => (
              <div key={row.id} className={styles.identRow}>
                <div className={styles.identTopRow}>
                  <FormField label="Canal" className={styles.gridCell}>
                    <Controller
                      control={form.control}
                      name={`identifiers.${i}.channel_type`}
                      render={({ field }) => (
                        <Dropdown
                          className={styles.control}
                          value={CHANNEL_TYPE_META[field.value as ChannelType]?.label ?? ""}
                          selectedOptions={[field.value]}
                          onOptionSelect={(_, data) =>
                            data.optionValue && field.onChange(data.optionValue as ChannelType)
                          }
                        >
                          {CHANNEL_TYPES.map((c) => (
                            <Option key={c} value={c}>
                              {CHANNEL_TYPE_META[c].label}
                            </Option>
                          ))}
                        </Dropdown>
                      )}
                    />
                  </FormField>
                  <FormField
                    label="Valor"
                    className={styles.gridCell}
                    error={identifierErrors?.[i]?.identifier?.message}
                  >
                    <Controller
                      control={form.control}
                      name={`identifiers.${i}.identifier`}
                      render={({ field }) => (
                        <Input
                          className={styles.control}
                          {...field}
                          value={field.value ?? ""}
                          placeholder="ej. +51999111222"
                        />
                      )}
                    />
                  </FormField>
                  <Button
                    appearance="subtle"
                    icon={<DismissRegular />}
                    aria-label="Quitar identificador"
                    onClick={() => identifiers.remove(i)}
                  />
                </div>
                <div className={styles.identChecksRow}>
                  <Controller
                    control={form.control}
                    name={`identifiers.${i}.is_primary`}
                    render={({ field }) => (
                      <Checkbox
                        label="Principal"
                        checked={field.value ?? false}
                        onChange={(_, d) => field.onChange(!!d.checked)}
                      />
                    )}
                  />
                  <Controller
                    control={form.control}
                    name={`identifiers.${i}.verified`}
                    render={({ field }) => (
                      <Checkbox
                        label="Verificado"
                        checked={field.value ?? false}
                        onChange={(_, d) => field.onChange(!!d.checked)}
                      />
                    )}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
        {identifierErrors?.[0]?.is_primary?.message ||
        typeof identifierErrors?.message === "string" ? (
          <p className={styles.hint} style={{ color: tokens.colorPaletteRedForeground1 }}>
            {identifierErrors?.[0]?.is_primary?.message ?? identifierErrors?.message}
          </p>
        ) : null}

        <p className={styles.hint}>
          Se valida que ningún identificador esté en uso por otro contacto.
        </p>
      </div>
    </Drawer>
  );
}
