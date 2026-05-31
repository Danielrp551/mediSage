"use client";

import {
  Button,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { DeleteRegular } from "@fluentui/react-icons";
import { useEffect, useMemo, useState, useTransition } from "react";

import { listActiveOffices } from "@/actions/office.actions";
import {
  createDoctorAvailability,
  updateDoctorAvailability,
} from "@/actions/doctor-availability.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { TIME_HHMM_REGEX } from "@/lib/schemas/doctor-availability.schema";
import { appTokens } from "@/lib/theme/brand";
import type { OfficeOption } from "@/types/clinic.types";
import type { BranchOption } from "@/types/clinic.types";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import { addDays, parseIsoDate, toIsoDate } from "./week";

const useStyles = makeStyles({
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  loadingRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
  },
});

// Valor inicial del form. En "create" date_from/date_to acotan el rango (un click
// los iguala a la fecha de la celda). En "edit" se preselecciona el bloque.
export interface AvailabilityDraft {
  branch_id: string;
  office_id: string;
  date_from: string; // "YYYY-MM-DD"
  date_to: string; // "YYYY-MM-DD"
  opens_at: string; // "HH:MM"
  closes_at: string; // "HH:MM"
}

interface Props {
  doctorId: string;
  doctorBranches: BranchOption[];
  mode: "create" | "edit";
  /** En modo edit, el bloque que se está editando (para el PUT). */
  editingBlock?: DoctorAvailabilityItem | null;
  initial: AvailabilityDraft;
  onClose: () => void;
  onSaved: () => void;
  /** En modo edit, abre la confirmación de borrado del bloque. */
  onRequestDelete?: () => void;
}

// Expande [date_from..date_to] (ambos inclusive) a la lista de fechas "YYYY-MM-DD".
function expandDates(fromIso: string, toIso: string): string[] {
  const from = parseIsoDate(fromIso);
  const to = parseIsoDate(toIso);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to < from) return [];
  const out: string[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) out.push(toIsoDate(d));
  return out;
}

export function AddAvailabilityDrawer({
  doctorId,
  doctorBranches,
  mode,
  editingBlock,
  initial,
  onClose,
  onSaved,
  onRequestDelete,
}: Props) {
  const styles = useStyles();

  const [branchId, setBranchId] = useState(initial.branch_id);
  const [officeId, setOfficeId] = useState(initial.office_id);
  const [dateFrom, setDateFrom] = useState(initial.date_from);
  const [dateTo, setDateTo] = useState(initial.date_to);
  const [opensAt, setOpensAt] = useState(initial.opens_at);
  const [closesAt, setClosesAt] = useState(initial.closes_at);

  const [offices, setOffices] = useState<OfficeOption[]>([]);
  const [officesLoading, setOfficesLoading] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  // Consultorios activos de la sede elegida (filtrados server-side por branch_id).
  // Al cambiar de sede se resetea el consultorio si ya no pertenece a la nueva.
  useEffect(() => {
    if (!branchId) {
      setOffices([]);
      return;
    }
    let cancelled = false;
    setOfficesLoading(true);
    void listActiveOffices(branchId)
      .then((rows) => {
        if (cancelled) return;
        // En modo edit, si el consultorio del bloque ya no está activo (se
        // desactivó/borró tras crear el bloque), no aparece en /offices/active.
        // Lo conservamos en las opciones para no perder silenciosamente la
        // selección original — un edit de solo-hora no debe forzar a re-elegir.
        let options = rows;
        if (
          mode === "edit" &&
          editingBlock &&
          editingBlock.branch_id === branchId &&
          !rows.some((o) => o.id === editingBlock.office_id)
        ) {
          options = [
            ...rows,
            {
              id: editingBlock.office_id,
              branch_id: editingBlock.branch_id,
              code: editingBlock.office_code,
              name: editingBlock.office_name,
            },
          ];
        }
        setOffices(options);
        setOfficesLoading(false);
        setOfficeId((cur) => (options.some((o) => o.id === cur) ? cur : ""));
      })
      .catch(() => {
        if (cancelled) return;
        setOffices([]);
        setOfficesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [branchId]);

  const branchName = useMemo(
    () => doctorBranches.find((b) => b.id === branchId)?.name ?? "",
    [doctorBranches, branchId],
  );
  const officeName = useMemo(
    () => offices.find((o) => o.id === officeId)?.name ?? "",
    [offices, officeId],
  );

  // Validación inline (espeja el backend en lo que se puede sin BD).
  const timesValid =
    TIME_HHMM_REGEX.test(opensAt) && TIME_HHMM_REGEX.test(closesAt) && closesAt > opensAt;
  const datesValid = mode === "edit" ? !!dateFrom : !!dateFrom && !!dateTo && dateTo >= dateFrom;
  const canSubmit = !!branchId && !!officeId && timesValid && datesValid && !pending;

  const onSubmit = () => {
    setServerError(null);
    startTransition(async () => {
      if (mode === "edit" && editingBlock) {
        const result = await updateDoctorAvailability(doctorId, editingBlock.id, {
          branch_id: branchId,
          office_id: officeId,
          date: dateFrom,
          opens_at: opensAt,
          closes_at: closesAt,
        });
        if (!result.ok) {
          setServerError(result.error ?? "No se pudo guardar el bloque.");
          return;
        }
        onSaved();
        return;
      }

      const dates = expandDates(dateFrom, dateTo);
      if (dates.length === 0) {
        setServerError("El rango de fechas no es válido.");
        return;
      }
      const blocks = dates.map((date) => ({
        branch_id: branchId,
        office_id: officeId,
        date,
        opens_at: opensAt,
        closes_at: closesAt,
      }));
      const result = await createDoctorAvailability(doctorId, { blocks });
      if (!result.ok) {
        // AVAILABILITY_OVERLAP / OFFICE_NOT_IN_BRANCH / DOCTOR_NOT_IN_BRANCH llegan
        // aquí ya en español.
        setServerError(result.error ?? "No se pudo agregar la disponibilidad.");
        return;
      }
      onSaved();
    });
  };

  const title = mode === "edit" ? "Editar disponibilidad" : "Agregar disponibilidad";
  const submitLabel = pending ? "Guardando…" : "Guardar";

  return (
    <Drawer
      open
      onClose={onClose}
      title={title}
      size="small"
      footer={
        <>
          {mode === "edit" && onRequestDelete ? (
            <Button
              appearance="subtle"
              icon={<DeleteRegular />}
              disabled={pending}
              onClick={onRequestDelete}
            >
              Eliminar
            </Button>
          ) : null}
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" disabled={!canSubmit} onClick={onSubmit}>
            {submitLabel}
          </Button>
        </>
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <FormField label="Sede" required>
        <Dropdown
          placeholder="Elige una sede"
          value={branchName}
          selectedOptions={branchId ? [branchId] : []}
          onOptionSelect={(_, d) => setBranchId(d.optionValue ?? "")}
        >
          {doctorBranches.map((b) => (
            <Option key={b.id} value={b.id} text={b.name}>
              {b.name}
            </Option>
          ))}
        </Dropdown>
      </FormField>

      <FormField label="Consultorio" required>
        {officesLoading ? (
          <div className={styles.loadingRow}>
            <Spinner size="tiny" />
            Cargando consultorios…
          </div>
        ) : (
          <Dropdown
            placeholder={branchId ? "Elige un consultorio" : "Elige una sede primero"}
            value={officeName}
            selectedOptions={officeId ? [officeId] : []}
            disabled={!branchId || offices.length === 0}
            onOptionSelect={(_, d) => setOfficeId(d.optionValue ?? "")}
          >
            {offices.map((o) => (
              <Option key={o.id} value={o.id} text={`${o.code} · ${o.name}`}>
                {o.code} · {o.name}
              </Option>
            ))}
          </Dropdown>
        )}
      </FormField>

      {mode === "edit" ? (
        <FormField label="Fecha" required>
          <Input type="date" value={dateFrom} onChange={(_, d) => setDateFrom(d.value)} />
        </FormField>
      ) : (
        <div className={styles.twoCol}>
          <FormField label="Desde" required>
            <Input type="date" value={dateFrom} onChange={(_, d) => setDateFrom(d.value)} />
          </FormField>
          <FormField label="Hasta" required>
            <Input type="date" value={dateTo} onChange={(_, d) => setDateTo(d.value)} />
          </FormField>
        </div>
      )}

      <div className={styles.twoCol}>
        <FormField
          label="Apertura"
          required
          error={TIME_HHMM_REGEX.test(opensAt) ? undefined : "Hora como HH:MM"}
        >
          <Input type="time" value={opensAt} onChange={(_, d) => setOpensAt(d.value)} />
        </FormField>
        <FormField
          label="Cierre"
          required
          error={
            !TIME_HHMM_REGEX.test(closesAt)
              ? "Hora como HH:MM"
              : closesAt <= opensAt
                ? "La hora de cierre debe ser mayor que la de apertura."
                : undefined
          }
        >
          <Input type="time" value={closesAt} onChange={(_, d) => setClosesAt(d.value)} />
        </FormField>
      </div>

      {mode === "create" ? (
        <span className={styles.hint}>
          Se creará un bloque con este horario en cada día del rango seleccionado.
        </span>
      ) : null}
    </Drawer>
  );
}
