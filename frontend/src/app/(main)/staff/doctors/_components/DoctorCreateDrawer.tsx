"use client";

import {
  Button,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  MessageBarTitle,
  Option,
  Tab,
  TabList,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { CopyRegular } from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createDoctor } from "@/actions/doctor.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { doctorCreateSchema, type DoctorCreateInput } from "@/lib/schemas/doctor.schema";
import { DOCUMENT_RULES, DOCUMENT_TYPES, type DocumentType } from "@/lib/schemas/user.schema";
import type { VerticalOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";

const useStyles = makeStyles({
  panel: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  successPanel: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  credBlock: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  credLabel: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground3,
  },
  credValue: {
    fontSize: tokens.fontSizeBase300,
    fontFamily: tokens.fontFamilyMonospace,
  },
  credRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
});

type TabId = "account" | "profile";

interface Props {
  branches: BranchOption[];
  verticals: VerticalOption[];
  onClose: () => void;
}

export function DoctorCreateDrawer({ branches, verticals, onClose }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const [tab, setTab] = useState<TabId>("account");
  const [serverError, setServerError] = useState<string | null>(null);
  const [generatedPassword, setGeneratedPassword] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [createdEmail, setCreatedEmail] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pending, startTransition] = useTransition();

  const form = useForm<DoctorCreateInput>({
    resolver: zodResolver(doctorCreateSchema),
    defaultValues: {
      user: {
        email: "",
        first_name: "",
        last_name: "",
        second_last_name: "",
        document_number: "",
        phone: "",
        password: "",
      },
      cmp_code: "",
      bio: "",
      photo_url: "",
      signature_url: "",
      slot_duration_min: 30,
      branch_ids: [],
      vertical_ids: [],
    },
  });

  const documentType = form.watch("user.document_type") as DocumentType | null | undefined;
  const docRule = documentType ? DOCUMENT_RULES[documentType] : null;

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = await createDoctor(values);
      if (!result.ok || !result.data) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      // El POST devuelve { data: DoctorDetail, generated_password }.
      if (result.data.generated_password) {
        // Mantener el drawer abierto para mostrar la contraseña temporal:
        // si el admin no fijó una contraseña, el backend genera una de un solo
        // uso que no se vuelve a exponer.
        setCreatedId(result.data.data.id);
        setCreatedEmail(result.data.data.user.email);
        setGeneratedPassword(result.data.generated_password);
        return;
      }
      onClose();
      router.push(`/staff/doctors/${result.data.data.id}`);
    });
  });

  const copyPassword = () => {
    if (!generatedPassword) return;
    void navigator.clipboard.writeText(generatedPassword).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Drawer
      open
      onClose={onClose}
      title="Nuevo doctor"
      subtitle={form.watch("user.email") || undefined}
      size="medium"
      footer={
        generatedPassword ? (
          <Button
            appearance="primary"
            onClick={() => {
              onClose();
              if (createdId) router.push(`/staff/doctors/${createdId}`);
            }}
          >
            Listo
          </Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
              {pending ? "Creando…" : "Crear doctor"}
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

      {generatedPassword ? (
        <div className={styles.successPanel}>
          <MessageBar intent="success">
            <MessageBarBody>
              <MessageBarTitle>Doctor creado</MessageBarTitle>
              Contraseña temporal generada — cópiala y compártela con el doctor; no se volverá a
              mostrar.
            </MessageBarBody>
          </MessageBar>

          <div className={styles.credBlock}>
            <span className={styles.credLabel}>Correo</span>
            <span className={styles.credValue}>{createdEmail}</span>
          </div>

          <div className={styles.credBlock}>
            <span className={styles.credLabel}>Contraseña temporal</span>
            <div className={styles.credRow}>
              <code className={styles.credValue}>{generatedPassword}</code>
              <Button
                size="small"
                appearance="secondary"
                icon={<CopyRegular />}
                onClick={copyPassword}
              >
                {copied ? "Copiada" : "Copiar"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {generatedPassword ? null : (
        <>
          <TabList selectedValue={tab} onTabSelect={(_, d) => setTab(d.value as TabId)}>
            <Tab value="account">Datos de la cuenta</Tab>
            <Tab value="profile">Perfil profesional</Tab>
          </TabList>

          {tab === "account" ? (
            <div className={styles.panel}>
              <FormField label="Correo" required error={form.formState.errors.user?.email?.message}>
                <Controller
                  control={form.control}
                  name="user.email"
                  render={({ field }) => (
                    <Input {...field} type="email" placeholder="doctor@ejemplo.com" />
                  )}
                />
              </FormField>

              <div className={styles.twoCol}>
                <FormField
                  label="Nombres"
                  required
                  error={form.formState.errors.user?.first_name?.message}
                >
                  <Controller
                    control={form.control}
                    name="user.first_name"
                    render={({ field }) => <Input {...field} />}
                  />
                </FormField>
                <FormField
                  label="Apellido paterno"
                  required
                  error={form.formState.errors.user?.last_name?.message}
                >
                  <Controller
                    control={form.control}
                    name="user.last_name"
                    render={({ field }) => <Input {...field} />}
                  />
                </FormField>
              </div>

              <FormField
                label="Apellido materno"
                error={form.formState.errors.user?.second_last_name?.message}
              >
                <Controller
                  control={form.control}
                  name="user.second_last_name"
                  render={({ field }) => <Input {...field} value={field.value ?? ""} />}
                />
              </FormField>

              <div className={styles.twoCol}>
                <FormField label="Tipo de documento">
                  <Controller
                    control={form.control}
                    name="user.document_type"
                    render={({ field }) => (
                      <Dropdown
                        value={field.value ?? ""}
                        selectedOptions={field.value ? [field.value] : []}
                        placeholder="Seleccionar…"
                        onOptionSelect={(_, data) => {
                          field.onChange(data.optionValue ? data.optionValue : null);
                          void form.trigger("user.document_number");
                        }}
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
                <FormField
                  label="Número de documento"
                  hint={docRule?.hint}
                  error={form.formState.errors.user?.document_number?.message}
                >
                  <Controller
                    control={form.control}
                    name="user.document_number"
                    render={({ field }) => (
                      <Input
                        {...field}
                        value={field.value ?? ""}
                        onBlur={() => {
                          field.onBlur();
                          void form.trigger("user.document_number");
                        }}
                      />
                    )}
                  />
                </FormField>
              </div>

              <FormField label="Teléfono" error={form.formState.errors.user?.phone?.message}>
                <Controller
                  control={form.control}
                  name="user.phone"
                  render={({ field }) => (
                    <Input {...field} value={field.value ?? ""} placeholder="+51 …" />
                  )}
                />
              </FormField>

              <FormField
                label="Contraseña"
                hint="Si lo dejas vacío se genera una contraseña temporal automáticamente."
                error={form.formState.errors.user?.password?.message}
              >
                <Controller
                  control={form.control}
                  name="user.password"
                  render={({ field }) => (
                    <Input {...field} value={field.value ?? ""} type="password" />
                  )}
                />
              </FormField>
            </div>
          ) : (
            <div className={styles.panel}>
              <FormField label="CMP" error={form.formState.errors.cmp_code?.message}>
                <Controller
                  control={form.control}
                  name="cmp_code"
                  render={({ field }) => <Input {...field} value={field.value ?? ""} />}
                />
              </FormField>

              <FormField label="Biografía" error={form.formState.errors.bio?.message}>
                <Controller
                  control={form.control}
                  name="bio"
                  render={({ field }) => <Textarea {...field} value={field.value ?? ""} rows={3} />}
                />
              </FormField>

              <FormField label="Foto (URL)" error={form.formState.errors.photo_url?.message}>
                <Controller
                  control={form.control}
                  name="photo_url"
                  render={({ field }) => <Input {...field} value={field.value ?? ""} />}
                />
              </FormField>

              <FormField label="Firma (URL)" error={form.formState.errors.signature_url?.message}>
                <Controller
                  control={form.control}
                  name="signature_url"
                  render={({ field }) => <Input {...field} value={field.value ?? ""} />}
                />
              </FormField>

              <FormField
                label="Duración del slot (minutos)"
                hint="Grano de tu calendario para agendar."
                error={form.formState.errors.slot_duration_min?.message}
              >
                <Controller
                  control={form.control}
                  name="slot_duration_min"
                  render={({ field }) => (
                    <Input
                      type="number"
                      name={field.name}
                      ref={field.ref}
                      value={String(field.value ?? "")}
                      onBlur={field.onBlur}
                      onChange={(_, d) =>
                        field.onChange(d.value === "" ? undefined : Number(d.value))
                      }
                    />
                  )}
                />
              </FormField>

              <FormField
                label="Sedes"
                required
                error={form.formState.errors.branch_ids?.message}
                hint={`${form.watch("branch_ids").length} seleccionadas`}
              >
                <Controller
                  control={form.control}
                  name="branch_ids"
                  render={({ field }) => (
                    <SearchableOptionList
                      options={branches.map((b) => ({
                        id: b.id,
                        primary: b.name,
                        secondary: b.city,
                      }))}
                      selected={field.value}
                      disabled={false}
                      onToggle={(id) =>
                        field.onChange(
                          field.value.includes(id)
                            ? field.value.filter((x) => x !== id)
                            : [...field.value, id],
                        )
                      }
                      searchPlaceholder="Buscar sedes…"
                      emptyMessage="Ninguna sede coincide con la búsqueda."
                    />
                  )}
                />
              </FormField>

              <FormField
                label="Verticales"
                required
                error={form.formState.errors.vertical_ids?.message}
                hint={`${form.watch("vertical_ids").length} seleccionadas`}
              >
                <Controller
                  control={form.control}
                  name="vertical_ids"
                  render={({ field }) => (
                    <SearchableOptionList
                      options={verticals.map((v) => ({
                        id: v.id,
                        primary: v.name,
                        secondary: v.code ?? undefined,
                      }))}
                      selected={field.value}
                      disabled={false}
                      onToggle={(id) =>
                        field.onChange(
                          field.value.includes(id)
                            ? field.value.filter((x) => x !== id)
                            : [...field.value, id],
                        )
                      }
                      searchPlaceholder="Buscar verticales…"
                      emptyMessage="Ninguna vertical coincide con la búsqueda."
                    />
                  )}
                />
              </FormField>
            </div>
          )}
        </>
      )}
    </Drawer>
  );
}
