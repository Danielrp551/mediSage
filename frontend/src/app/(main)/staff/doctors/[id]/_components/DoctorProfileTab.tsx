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

import { updateDoctor } from "@/actions/doctor.actions";
import { FormField } from "@/components/ui/Form/FormField";
import { SearchableOptionList } from "@/components/ui/SearchableOptionList/SearchableOptionList";
import { usePermissions } from "@/hooks/usePermissions";
import { doctorUpdateSchema, type DoctorUpdateInput } from "@/lib/schemas/doctor.schema";
import { appTokens } from "@/lib/theme/brand";
import type { VerticalOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import type { DoctorDetail } from "@/types/staff.types";

const useStyles = makeStyles({
  panel: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    maxWidth: "640px",
  },
  readonly: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    padding: tokens.spacingVerticalM,
    backgroundColor: appTokens.chromeBgHover,
    borderRadius: tokens.borderRadiusMedium,
  },
  readonlyLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  readonlyValue: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  actions: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    justifyContent: "flex-end",
    marginTop: tokens.spacingVerticalM,
  },
});

interface Props {
  doctor: DoctorDetail;
  branches: BranchOption[];
  verticals: VerticalOption[];
}

export function DoctorProfileTab({ doctor, branches, verticals }: Props) {
  const styles = useStyles();
  const router = useRouter();
  const { hasPermission } = usePermissions();
  const canEdit = hasPermission("DOCTORS_UPDATE");

  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<DoctorUpdateInput>({
    resolver: zodResolver(doctorUpdateSchema),
    defaultValues: {
      cmp_code: doctor.cmp_code ?? "",
      bio: doctor.bio ?? "",
      photo_url: doctor.photo_url ?? "",
      signature_url: doctor.signature_url ?? "",
      slot_duration_min: doctor.slot_duration_min,
      branch_ids: doctor.branches.map((b) => b.id),
      vertical_ids: doctor.verticals.map((v) => v.id),
      active: doctor.active,
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    // Las relaciones M:N (`branch_ids` / `vertical_ids`) solo se envían cuando
    // el usuario las cambió. El detalle del backend (get_full) filtra los padres
    // soft-deleted, así que un full-replace ciego perdería esas asociaciones.
    // El backend interpreta el campo ausente como "no tocar" y presente como
    // "reemplazo completo".
    const { branch_ids: branchDirty, vertical_ids: verticalDirty } = form.formState.dirtyFields;
    const payload: DoctorUpdateInput = { ...values };
    if (!branchDirty) delete payload.branch_ids;
    if (!verticalDirty) delete payload.vertical_ids;
    startTransition(async () => {
      const result = await updateDoctor(doctor.id, payload);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      router.refresh();
    });
  });

  return (
    <form onSubmit={onSubmit} className={styles.panel}>
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {/* Usuario solo-lectura — se gestiona en Administración → Usuarios. */}
      <div className={styles.readonly}>
        <span className={styles.readonlyLabel}>Usuario</span>
        <span className={styles.readonlyValue}>{doctor.user.full_name}</span>
        <span className={styles.readonlyValue}>{doctor.user.email}</span>
        <span className={styles.readonlyLabel}>Gestionado en Administración → Usuarios.</span>
      </div>

      <FormField label="CMP" error={form.formState.errors.cmp_code?.message}>
        <Controller
          control={form.control}
          name="cmp_code"
          render={({ field }) => <Input {...field} value={field.value ?? ""} disabled={!canEdit} />}
        />
      </FormField>

      <FormField label="Biografía" error={form.formState.errors.bio?.message}>
        <Controller
          control={form.control}
          name="bio"
          render={({ field }) => (
            <Textarea {...field} value={field.value ?? ""} rows={3} disabled={!canEdit} />
          )}
        />
      </FormField>

      <FormField label="Foto (URL)" error={form.formState.errors.photo_url?.message}>
        <Controller
          control={form.control}
          name="photo_url"
          render={({ field }) => <Input {...field} value={field.value ?? ""} disabled={!canEdit} />}
        />
      </FormField>

      <FormField label="Firma (URL)" error={form.formState.errors.signature_url?.message}>
        <Controller
          control={form.control}
          name="signature_url"
          render={({ field }) => <Input {...field} value={field.value ?? ""} disabled={!canEdit} />}
        />
      </FormField>

      <FormField
        label="Duración del slot (minutos)"
        error={form.formState.errors.slot_duration_min?.message}
      >
        <Controller
          control={form.control}
          name="slot_duration_min"
          render={({ field }) => (
            <Input
              type="number"
              disabled={!canEdit}
              value={String(field.value ?? "")}
              onChange={(_, d) => field.onChange(d.value === "" ? undefined : Number(d.value))}
            />
          )}
        />
      </FormField>

      <FormField
        label="Sedes"
        error={form.formState.errors.branch_ids?.message}
        hint={`${form.watch("branch_ids")?.length ?? 0} seleccionadas`}
      >
        <Controller
          control={form.control}
          name="branch_ids"
          render={({ field }) => (
            <SearchableOptionList
              options={branches.map((b) => ({ id: b.id, primary: b.name, secondary: b.city }))}
              selected={field.value ?? []}
              disabled={!canEdit}
              onToggle={(id) =>
                field.onChange(
                  (field.value ?? []).includes(id)
                    ? (field.value ?? []).filter((x) => x !== id)
                    : [...(field.value ?? []), id],
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
        error={form.formState.errors.vertical_ids?.message}
        hint={`${form.watch("vertical_ids")?.length ?? 0} seleccionadas`}
      >
        <Controller
          control={form.control}
          name="vertical_ids"
          render={({ field }) => (
            <SearchableOptionList
              options={verticals.map((v) => ({ id: v.id, primary: v.name, secondary: v.code }))}
              selected={field.value ?? []}
              disabled={!canEdit}
              onToggle={(id) =>
                field.onChange(
                  (field.value ?? []).includes(id)
                    ? (field.value ?? []).filter((x) => x !== id)
                    : [...(field.value ?? []), id],
                )
              }
              searchPlaceholder="Buscar verticales…"
              emptyMessage="Ninguna vertical coincide con la búsqueda."
            />
          )}
        />
      </FormField>

      <div className={styles.switchRow}>
        <Controller
          control={form.control}
          name="active"
          render={({ field }) => (
            <Switch
              checked={field.value ?? false}
              disabled={!canEdit}
              onChange={(_, d) => field.onChange(d.checked)}
              label={field.value ? "Activo" : "Inactivo"}
            />
          )}
        />
      </div>

      {canEdit ? (
        <div className={styles.actions}>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Guardando…" : "Guardar cambios"}
          </Button>
        </div>
      ) : null}
    </form>
  );
}
