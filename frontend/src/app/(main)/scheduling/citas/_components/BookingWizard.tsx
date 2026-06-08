"use client";

import {
  Button,
  Combobox,
  Dropdown,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Textarea,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import { PersonRegular, SearchRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useTransition } from "react";

import { createAppointment } from "@/actions/appointment.actions";
import { listActiveOffices } from "@/actions/office.actions";
import { listActivePersons } from "@/actions/person.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ProductOption } from "@/types/catalog.types";
import type { BranchOption } from "@/types/clinic.types";
import type { AvailabilitySlot } from "@/types/scheduling.types";
import type { DoctorOption } from "@/types/staff.types";

import { AvailabilityPicker } from "./AvailabilityPicker";

const useStyles = makeStyles({
  body: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  // Indicador de pasos: fila de pastillas numeradas; la actual resaltada con la marca.
  stepper: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
  },
  stepWrap: { display: "inline-flex", alignItems: "center" },
  step: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    padding: `${tokens.spacingVerticalXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusCircular,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    border: `1px solid ${appTokens.chromeBorder}`,
    whiteSpace: "nowrap",
  },
  stepCurrent: {
    backgroundColor: tokens.colorBrandBackground,
    color: tokens.colorNeutralForegroundOnBrand,
    // `border` shorthand (no `borderColor` longhand): mezclar shorthand+longhand
    // entre clases del mismo makeStyles confunde la inferencia de tipos de Griffel.
    border: `1px solid ${tokens.colorBrandBackground}`,
    fontWeight: tokens.fontWeightSemibold,
  },
  stepDone: {
    backgroundColor: appTokens.chromeBgHover,
    color: appTokens.chromeText,
  },
  stepIndex: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "18px",
    height: "18px",
    borderRadius: tokens.borderRadiusCircular,
    fontSize: tokens.fontSizeBase100,
    fontWeight: tokens.fontWeightSemibold,
    backgroundColor: tokens.colorNeutralBackground3,
    color: appTokens.chromeText,
  },
  stepSeparator: { color: appTokens.chromeTextMuted, flexShrink: 0 },
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted, margin: 0 },
  loadingRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  // width 100% + minWidth 0 para que el input nativo (dentro del <Input> de Fluent) no
  // desborde el grid de dos columnas (mismo arreglo que AddAvailabilityDrawer).
  control: { width: "100%", minWidth: 0 },
  // Resumen: filas etiqueta/valor.
  summary: {
    display: "grid",
    gridTemplateColumns: "auto 1fr",
    gap: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    alignItems: "baseline",
  },
  summaryLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  summaryValue: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText },
});

interface Props {
  doctors: DoctorOption[];
  products: ProductOption[];
  branches: BranchOption[];
  onClose: () => void;
  onCreated: () => void;
}

const STEP_LABELS = ["Contacto", "Servicio y profesional", "Disponibilidad", "Resumen"] as const;

export function BookingWizard({ doctors, products, branches, onClose, onCreated }: Props) {
  const styles = useStyles();

  const [step, setStep] = useState(1);

  // ── Estado del formulario (controlado a mano; el create lo valida Zod en la action) ──
  // Paso 1
  const [personId, setPersonId] = useState<string | null>(null);
  const [personName, setPersonName] = useState<string>("");
  const [personQuery, setPersonQuery] = useState<string>("");
  // Paso 2 — `officeId` es SOLO el filtro opcional de búsqueda (acota el cómputo); el
  // consultorio que se reserva sale del slot elegido (selectedSlot), no de aquí.
  const [productId, setProductId] = useState<string | null>(null);
  const [doctorId, setDoctorId] = useState<string | null>(null);
  const [branchId, setBranchId] = useState<string | null>(null);
  const [officeId, setOfficeId] = useState<string | null>(null);
  // Paso 3 — el slot elegido. El AvailabilityPicker posee el cómputo y lo INVALIDA (vía
  // onSelectSlot(null)) cuando cambia cualquier insumo (doctor/producto/sede/consultorio).
  const [selectedSlot, setSelectedSlot] = useState<AvailabilitySlot | null>(null);
  // Paso 4
  const [notes, setNotes] = useState<string>("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  // ── Paso 1: personas (búsqueda local en el Combobox) ──
  const personsQuery = useQuery({
    queryKey: ["scheduling", "persons-active"],
    queryFn: () => listActivePersons(),
  });

  const filteredPersons = useMemo(() => {
    const all = personsQuery.data ?? [];
    const needle = personQuery.trim().toLowerCase();
    // Sin texto (o tras seleccionar, el texto = nombre exacto): mostramos todo.
    if (!needle) return all;
    return all.filter((p) =>
      [p.full_name, p.document_number].some((f) => (f ?? "").toLowerCase().includes(needle)),
    );
  }, [personsQuery.data, personQuery]);

  // ── Paso 2: consultorios (acotados a la sede elegida) ──
  const officesQuery = useQuery({
    queryKey: ["scheduling", "offices-active", branchId],
    queryFn: () => listActiveOffices(branchId ?? undefined),
    enabled: step >= 2,
  });

  // ── Crear cita ── (office_id y scheduled_for salen del slot elegido) ──
  const handleCreate = () => {
    if (!personId || !doctorId || !productId || !selectedSlot) return;
    setCreateError(null);
    startTransition(async () => {
      const result = await createAppointment({
        person_id: personId,
        doctor_id: doctorId,
        office_id: selectedSlot.office_id,
        product_id: productId,
        scheduled_for: selectedSlot.starts_at,
        notes,
      });
      if (!result.ok) {
        // 400 de invariante (SLOT_TAKEN/OFFICE_SLOT_TAKEN/…) en español: el slot pudo
        // tomarse entre el compute y el create → invitamos a recomputar en el paso 3.
        const fieldMsg = result.fieldErrors
          ? Object.values(result.fieldErrors).flat()[0]
          : undefined;
        setCreateError(result.error ?? fieldMsg ?? "No se pudo crear la cita.");
        return;
      }
      onCreated();
    });
  };

  // ── Gating de "Siguiente" por paso ──
  const canAdvance =
    (step === 1 && !!personId) ||
    (step === 2 && !!productId && !!doctorId) ||
    (step === 3 && !!selectedSlot);

  const selectedProductName = products.find((p) => p.id === productId)?.name ?? "";
  const selectedDoctorName = doctors.find((d) => d.id === doctorId)?.full_name ?? "";
  const selectedBranchName = branches.find((b) => b.id === branchId)?.name ?? "";
  const selectedOffice = officesQuery.data?.find((o) => o.id === officeId);
  const officesEmpty = !officesQuery.isPending && (officesQuery.data?.length ?? 0) === 0;

  // Duración derivada del slot elegido (ends_at − starts_at en minutos; es una diferencia,
  // independiente de la TZ). Equivale a product.duration_min (ends_at = starts_at + dur).
  const selectedDurationMin = selectedSlot
    ? Math.round(
        (new Date(selectedSlot.ends_at).getTime() - new Date(selectedSlot.starts_at).getTime()) /
          60000,
      )
    : null;

  return (
    <Drawer
      open
      onClose={onClose}
      size="large"
      title="Nueva cita"
      subtitle={STEP_LABELS[step - 1]}
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button
            appearance="secondary"
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            disabled={step === 1 || pending}
          >
            Atrás
          </Button>
          {step < 4 ? (
            <Button
              appearance="primary"
              onClick={() => setStep((s) => Math.min(4, s + 1))}
              disabled={!canAdvance}
            >
              Siguiente
            </Button>
          ) : (
            <Button appearance="primary" onClick={handleCreate} disabled={pending || !selectedSlot}>
              {pending ? "Creando…" : "Crear cita"}
            </Button>
          )}
        </>
      }
    >
      <div className={styles.body}>
        {/* Indicador de pasos */}
        <div className={styles.stepper}>
          {STEP_LABELS.map((label, i) => {
            const n = i + 1;
            const isCurrent = n === step;
            const isDone = n < step;
            return (
              <span key={label} className={styles.stepWrap}>
                <span
                  className={mergeClasses(
                    styles.step,
                    isCurrent && styles.stepCurrent,
                    isDone && styles.stepDone,
                  )}
                >
                  <span className={styles.stepIndex}>{isDone ? "✓" : n}</span>
                  {label}
                </span>
                {n < STEP_LABELS.length ? <span className={styles.stepSeparator}>›</span> : null}
              </span>
            );
          })}
        </div>

        {/* ── Paso 1: Contacto ── */}
        {step === 1 ? (
          <div className={styles.panel}>
            <FormField
              label="Contacto"
              required
              hint="Busca por nombre o documento y elige el paciente."
            >
              <Combobox
                className={styles.control}
                placeholder="Buscar contacto…"
                value={personId ? personName : personQuery}
                selectedOptions={personId ? [personId] : []}
                expandIcon={<SearchRegular />}
                onOptionSelect={(_, d) => {
                  if (!d.optionValue) return;
                  const picked = (personsQuery.data ?? []).find((p) => p.id === d.optionValue);
                  setPersonId(d.optionValue);
                  setPersonName(picked?.full_name ?? d.optionText ?? "");
                  setPersonQuery(picked?.full_name ?? "");
                }}
                onInput={(e) => {
                  // Al teclear se invalida la selección previa (el usuario re-busca).
                  setPersonQuery((e.target as HTMLInputElement).value);
                  setPersonId(null);
                }}
              >
                {personsQuery.isPending ? (
                  <Option key="__loading" value="__loading" disabled text="Cargando…">
                    Cargando contactos…
                  </Option>
                ) : personsQuery.isError ? (
                  <Option key="__error" value="__error" disabled text="Error">
                    No se pudieron cargar los contactos.
                  </Option>
                ) : filteredPersons.length === 0 ? (
                  <Option key="__empty" value="__empty" disabled text="Sin resultados">
                    Sin resultados
                  </Option>
                ) : (
                  filteredPersons.map((p) => (
                    <Option key={p.id} value={p.id} text={p.full_name}>
                      <PersonRegular />
                      {p.full_name}
                      {p.document_number ? ` · ${p.document_number}` : ""}
                    </Option>
                  ))
                )}
              </Combobox>
            </FormField>
            {personsQuery.isPending ? (
              <span className={styles.loadingRow}>
                <Spinner size="extra-small" />
                <span className={styles.hint}>Cargando contactos…</span>
              </span>
            ) : null}
          </div>
        ) : null}

        {/* ── Paso 2: Servicio y profesional ── */}
        {step === 2 ? (
          <div className={styles.panel}>
            <div className={styles.twoCol}>
              <FormField label="Producto" required>
                <Dropdown
                  className={styles.control}
                  placeholder="Seleccionar producto…"
                  value={selectedProductName}
                  selectedOptions={productId ? [productId] : []}
                  onOptionSelect={(_, d) => setProductId(d.optionValue || null)}
                >
                  {products.length === 0 ? (
                    <Option key="__none" value="__none" disabled>
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
              <FormField label="Doctor" required>
                <Dropdown
                  className={styles.control}
                  placeholder="Seleccionar doctor…"
                  value={selectedDoctorName}
                  selectedOptions={doctorId ? [doctorId] : []}
                  onOptionSelect={(_, d) => setDoctorId(d.optionValue || null)}
                >
                  {doctors.length === 0 ? (
                    <Option key="__none" value="__none" disabled>
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
            </div>
            <div className={styles.twoCol}>
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
              <FormField
                label="Consultorio"
                hint="Opcional: el slot elegido lo fija si lo dejas vacío."
              >
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
            </div>
          </div>
        ) : null}

        {/* ── Paso 3: Disponibilidad ── El picker se mantiene MONTADO (visibilidad por
            display) para que la selección y los slots computados persistan al navegar
            entre pasos; solo se invalidan cuando cambia un insumo del cómputo. */}
        <div style={{ display: step === 3 ? undefined : "none" }}>
          <AvailabilityPicker
            doctorId={doctorId}
            productId={productId}
            branchId={branchId}
            officeId={officeId}
            selectedSlot={selectedSlot}
            onSelectSlot={setSelectedSlot}
          />
        </div>

        {/* ── Paso 4: Resumen y confirmación ── */}
        {step === 4 ? (
          <div className={styles.panel}>
            {createError ? (
              <MessageBar intent="error">
                <MessageBarBody>
                  {createError} Si el horario ya no está disponible, vuelve atrás y busca horarios
                  de nuevo.
                </MessageBarBody>
              </MessageBar>
            ) : null}

            <div className={styles.summary}>
              <span className={styles.summaryLabel}>Contacto</span>
              <span className={styles.summaryValue}>{personName || "—"}</span>
              <span className={styles.summaryLabel}>Producto</span>
              <span className={styles.summaryValue}>{selectedProductName || "—"}</span>
              <span className={styles.summaryLabel}>Doctor</span>
              <span className={styles.summaryValue}>{selectedDoctorName || "—"}</span>
              <span className={styles.summaryLabel}>Consultorio</span>
              <span className={styles.summaryValue}>
                {selectedSlot ? `${selectedSlot.office_name} · ${selectedSlot.branch_name}` : "—"}
              </span>
              <span className={styles.summaryLabel}>Fecha y hora</span>
              <span className={styles.summaryValue}>
                {formatDate(selectedSlot?.starts_at ?? null)}
              </span>
              <span className={styles.summaryLabel}>Duración</span>
              <span className={styles.summaryValue}>
                {selectedDurationMin !== null ? `${selectedDurationMin} min` : "—"}
              </span>
            </div>

            <FormField label="Notas" hint="Opcional.">
              <Textarea
                className={styles.control}
                value={notes}
                onChange={(_, d) => setNotes(d.value)}
                rows={3}
                placeholder="Notas internas de la cita…"
              />
            </FormField>
          </div>
        ) : null}
      </div>
    </Drawer>
  );
}
