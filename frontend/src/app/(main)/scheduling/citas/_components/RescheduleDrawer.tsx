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

import { rescheduleAppointment } from "@/actions/appointment.actions";
import { listActiveOffices } from "@/actions/office.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { BranchOption } from "@/types/clinic.types";
import type { AppointmentDetail, AvailabilitySlot } from "@/types/scheduling.types";
import type { DoctorOption } from "@/types/staff.types";

import { AvailabilityPicker } from "./AvailabilityPicker";

const useStyles = makeStyles({
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  // width 100% + minWidth 0 para que el control no desborde el grid de dos columnas.
  control: { width: "100%", minWidth: 0 },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted, margin: 0 },
  // Producto fijo: se muestra como valor de solo-lectura (no se puede cambiar el servicio).
  readonlyValue: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
});

interface Props {
  appointment: AppointmentDetail;
  doctors: DoctorOption[];
  branches: BranchOption[];
  onClose: () => void;
  onRescheduled: () => void;
}

/**
 * Reagenda una cita: el backend marca la vieja RESCHEDULED y crea una NUEVA con
 * previous_appointment_id (misma transacción). El servicio se mantiene FIJO
 * (appointment.product_id) — solo cambian doctor/consultorio/horario. office_id sale
 * del SLOT elegido (no del filtro), igual que el wizard de reserva.
 */
export function RescheduleDrawer({
  appointment,
  doctors,
  branches,
  onClose,
  onRescheduled,
}: Props) {
  const styles = useStyles();

  const [doctorId, setDoctorId] = useState<string | null>(appointment.doctor_id);
  const [branchId, setBranchId] = useState<string | null>(appointment.branch_id);
  // officeId = SOLO el filtro opcional de búsqueda (acota el cómputo); el consultorio
  // que se reserva sale del slot elegido. Default null = cualquier consultorio.
  const [officeId, setOfficeId] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<AvailabilitySlot | null>(null);
  const [reason, setReason] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  // Consultorios acotados a la sede elegida (mismo patrón que el wizard).
  const officesQuery = useQuery({
    queryKey: ["scheduling", "offices-active", branchId],
    queryFn: () => listActiveOffices(branchId ?? undefined),
  });

  const selectedDoctorName = doctors.find((d) => d.id === doctorId)?.full_name ?? "";
  const selectedBranchName = branches.find((b) => b.id === branchId)?.name ?? "";
  const selectedOffice = officesQuery.data?.find((o) => o.id === officeId);
  const officesEmpty = !officesQuery.isPending && (officesQuery.data?.length ?? 0) === 0;

  const handleReschedule = () => {
    if (!selectedSlot) return;
    setError(null);
    startTransition(async () => {
      // office_id sale del SLOT elegido (no del filtro) — misma regla que el wizard.
      const r = await rescheduleAppointment(appointment.id, {
        scheduled_for: selectedSlot.starts_at,
        doctor_id: doctorId,
        office_id: selectedSlot.office_id,
        reason,
      });
      if (!r.ok) {
        // 400 de invariante (SLOT_TAKEN/1-8) en español: el slot pudo tomarse entre el
        // compute y el reschedule → el usuario re-busca horarios.
        const fieldMsg = r.fieldErrors ? Object.values(r.fieldErrors).flat()[0] : undefined;
        setError(r.error ?? fieldMsg ?? "No se pudo reagendar la cita.");
        return;
      }
      onRescheduled();
    });
  };

  return (
    <Drawer
      open
      onClose={onClose}
      size="large"
      title="Reagendar cita"
      subtitle={appointment.person_name}
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button
            appearance="primary"
            onClick={handleReschedule}
            disabled={!selectedSlot || pending}
          >
            {pending ? "Reagendando…" : "Reagendar"}
          </Button>
        </>
      }
    >
      <div className={styles.panel}>
        <MessageBar intent="info">
          <MessageBarBody>
            Se creará una NUEVA cita en el horario elegido y esta se marcará como reagendada.
          </MessageBarBody>
        </MessageBar>

        {error ? (
          <MessageBar intent="error">
            <MessageBarBody>
              {error} Si el horario ya no está disponible, busca horarios de nuevo.
            </MessageBarBody>
          </MessageBar>
        ) : null}

        {/* Producto FIJO — no se puede cambiar el servicio al reagendar. */}
        <FormField label="Producto" hint="El servicio no cambia al reagendar.">
          <span className={styles.readonlyValue}>{appointment.product_name}</span>
        </FormField>

        <div className={styles.twoCol}>
          <FormField label="Doctor" required>
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
          <FormField label="Sede" hint="Opcional: acota la búsqueda a una sede.">
            <Dropdown
              className={styles.control}
              placeholder="Cualquier sede"
              value={selectedBranchName}
              selectedOptions={branchId ? [branchId] : []}
              onOptionSelect={(_, d) => {
                setBranchId(d.optionValue || null);
                // Al cambiar de sede limpiamos el consultorio (puede no pertenecerle);
                // el AvailabilityPicker invalida la disponibilidad al cambiar el insumo.
                setOfficeId(null);
              }}
            >
              <Option value="">Cualquier sede</Option>
              {branches.map((b) => (
                <Option key={b.id} value={b.id}>
                  {b.name}
                </Option>
              ))}
            </Dropdown>
          </FormField>
        </div>

        <FormField label="Consultorio" hint="Opcional: el slot elegido lo fija si lo dejas vacío.">
          <Dropdown
            className={styles.control}
            placeholder="Cualquier consultorio"
            value={selectedOffice?.name ?? ""}
            selectedOptions={officeId ? [officeId] : []}
            onOptionSelect={(_, d) => setOfficeId(d.optionValue || null)}
            disabled={officesQuery.isPending}
          >
            <Option value="">Cualquier consultorio</Option>
            {officesEmpty ? (
              <Option key="__none" value="__none" disabled text="Sin consultorios">
                {`No hay consultorios${branchId ? " en esta sede" : ""}`}
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

        <AvailabilityPicker
          doctorId={doctorId}
          productId={appointment.product_id}
          branchId={branchId}
          officeId={officeId}
          selectedSlot={selectedSlot}
          onSelectSlot={setSelectedSlot}
        />

        <FormField label="Motivo (opcional)">
          <Textarea
            className={styles.control}
            value={reason}
            onChange={(_, d) => setReason(d.value)}
            rows={3}
            placeholder="Anota por qué reagendas la cita…"
          />
        </FormField>

        <p className={styles.hint}>Cita actual: {formatDate(appointment.scheduled_for)}.</p>
      </div>
    </Drawer>
  );
}
