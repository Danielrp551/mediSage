"use client";

import {
  Button,
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { useQuery } from "@tanstack/react-query";
import { useState, useTransition } from "react";

import { updateAppointment } from "@/actions/appointment.actions";
import { listActiveOffices } from "@/actions/office.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ProductOption } from "@/types/catalog.types";
import type { AppointmentDetail } from "@/types/scheduling.types";
import type { DoctorOption } from "@/types/staff.types";

const useStyles = makeStyles({
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  // width 100% + minWidth 0 para que el control no desborde el grid de dos columnas.
  control: { width: "100%", minWidth: 0 },
  // Fecha/hora de solo-lectura (no editable aquí → se usa Reagendar).
  readonlyBlock: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    padding: tokens.spacingVerticalM,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${appTokens.chromeBorder}`,
    backgroundColor: appTokens.chromeBg,
  },
  readonlyLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  readonlyValue: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted, margin: 0 },
});

interface Props {
  appointment: AppointmentDetail;
  doctors: DoctorOption[];
  products: ProductOption[];
  onClose: () => void;
  onUpdated: () => void;
}

/**
 * Edita los metadatos de la cita SIN cambiar la fecha/hora (eso es Reagendar) ni el
 * estado (eso son los shortcuts). El backend re-deriva branch_id/duration_min si cambia
 * office/product y revalida invariantes 1-8 (puede dar SLOT_TAKEN/DOCTOR_NOT_IN_BRANCH).
 * El `reason` se registra en el change_log. Los consultorios salen de la sede fija de la
 * cita (cambiar de sede es reagendar, no editar).
 */
export function EditAppointmentDrawer({
  appointment,
  doctors,
  products,
  onClose,
  onUpdated,
}: Props) {
  const styles = useStyles();

  const [doctorId, setDoctorId] = useState<string | null>(appointment.doctor_id);
  const [officeId, setOfficeId] = useState<string | null>(appointment.office_id);
  const [productId, setProductId] = useState<string | null>(appointment.product_id);
  const [notes, setNotes] = useState<string>(appointment.notes ?? "");
  const [reason, setReason] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  // Consultorios de la sede de la cita (la edición no cambia de sede; eso es reagendar).
  const officesQuery = useQuery({
    queryKey: ["scheduling", "offices-active", appointment.branch_id],
    queryFn: () => listActiveOffices(appointment.branch_id),
  });

  const selectedDoctorName = doctors.find((d) => d.id === doctorId)?.full_name ?? "";
  const selectedProductName = products.find((p) => p.id === productId)?.name ?? "";
  const selectedOffice = officesQuery.data?.find((o) => o.id === officeId);
  const officesEmpty = !officesQuery.isPending && (officesQuery.data?.length ?? 0) === 0;

  // Solo habilitamos "Guardar" si cambió un campo EDITABLE (doctor/consultorio/producto/
  // notas). El `reason` solo NO basta: sin un cambio real el backend no escribe change_log
  // → guardar sería un no-op (llamada y motivo huérfano).
  const hasChanges =
    doctorId !== appointment.doctor_id ||
    officeId !== appointment.office_id ||
    productId !== appointment.product_id ||
    notes !== (appointment.notes ?? "");

  const handleSave = () => {
    setError(null);
    startTransition(async () => {
      const r = await updateAppointment(appointment.id, {
        doctor_id: doctorId,
        office_id: officeId,
        product_id: productId,
        notes,
        reason,
      });
      if (!r.ok) {
        const fieldMsg = r.fieldErrors ? Object.values(r.fieldErrors).flat()[0] : undefined;
        setError(r.error ?? fieldMsg ?? "No se pudieron guardar los cambios.");
        return;
      }
      onUpdated();
    });
  };

  return (
    <Drawer
      open
      onClose={onClose}
      size="medium"
      title="Editar cita"
      subtitle={appointment.person_name}
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" onClick={handleSave} disabled={pending || !hasChanges}>
            {pending ? "Guardando…" : "Guardar cambios"}
          </Button>
        </>
      }
    >
      <div className={styles.panel}>
        {error ? (
          <MessageBar intent="error">
            <MessageBarBody>{error}</MessageBarBody>
          </MessageBar>
        ) : null}

        {/* Fecha/hora de solo-lectura — no se edita aquí. */}
        <div className={styles.readonlyBlock}>
          <span className={styles.readonlyLabel}>Fecha y hora</span>
          <span className={styles.readonlyValue}>{formatDate(appointment.scheduled_for)}</span>
          <span className={styles.hint}>Para cambiar la fecha/hora usa Reagendar.</span>
        </div>

        <div className={styles.twoCol}>
          <FormField label="Doctor">
            <Dropdown
              className={styles.control}
              placeholder="Seleccionar doctor…"
              value={selectedDoctorName}
              selectedOptions={doctorId ? [doctorId] : []}
              onOptionSelect={(_, d) => setDoctorId(d.optionValue || null)}
            >
              {doctors.length === 0 ? (
                <Option key="__none" value="__none" disabled text="Sin doctores">
                  No hay doctores disponibles
                </Option>
              ) : (
                doctors.map((dc) => (
                  <Option key={dc.id} value={dc.id}>
                    {dc.full_name}
                  </Option>
                ))
              )}
            </Dropdown>
          </FormField>
          <FormField label="Producto">
            <Dropdown
              className={styles.control}
              placeholder="Seleccionar producto…"
              value={selectedProductName}
              selectedOptions={productId ? [productId] : []}
              onOptionSelect={(_, d) => setProductId(d.optionValue || null)}
            >
              {products.length === 0 ? (
                <Option key="__none" value="__none" disabled text="Sin productos">
                  No hay productos disponibles
                </Option>
              ) : (
                products.map((p) => (
                  <Option key={p.id} value={p.id}>
                    {p.name}
                  </Option>
                ))
              )}
            </Dropdown>
          </FormField>
        </div>

        <FormField label="Consultorio">
          <Dropdown
            className={styles.control}
            placeholder="Seleccionar consultorio…"
            value={selectedOffice?.name ?? ""}
            selectedOptions={officeId ? [officeId] : []}
            onOptionSelect={(_, d) => setOfficeId(d.optionValue || null)}
            disabled={officesQuery.isPending}
          >
            {officesEmpty ? (
              <Option key="__none" value="__none" disabled text="Sin consultorios">
                No hay consultorios en esta sede
              </Option>
            ) : (
              (officesQuery.data ?? []).map((o) => (
                <Option key={o.id} value={o.id}>
                  {o.name}
                </Option>
              ))
            )}
          </Dropdown>
        </FormField>

        <FormField label="Notas" hint="Opcional.">
          <Textarea
            className={styles.control}
            value={notes}
            onChange={(_, d) => setNotes(d.value)}
            rows={3}
            placeholder="Notas internas de la cita…"
          />
        </FormField>

        <FormField
          label="Motivo del cambio (opcional)"
          hint="Se registra en el historial de cambios."
        >
          <Textarea
            className={styles.control}
            value={reason}
            onChange={(_, d) => setReason(d.value)}
            rows={2}
            placeholder="Anota por qué cambias estos datos…"
          />
        </FormField>
      </div>
    </Drawer>
  );
}
