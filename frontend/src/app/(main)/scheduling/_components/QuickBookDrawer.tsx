"use client";

import {
  Button,
  Combobox,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { PersonRegular, SearchRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useTransition } from "react";

import { createAppointment } from "@/actions/appointment.actions";
import { listActivePersons } from "@/actions/person.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { AvailabilitySlot } from "@/types/scheduling.types";

const useStyles = makeStyles({
  body: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted, margin: 0 },
  loadingRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  // width 100% + minWidth 0 para que el Combobox/Textarea no desborden el panel.
  control: { width: "100%", minWidth: 0 },
  // Resumen del slot: filas etiqueta/valor (mismo molde que el paso 4 del wizard).
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
  slot: AvailabilitySlot;
  productId: string;
  productName: string;
  onClose: () => void;
  onBooked: () => void;
}

// Reserva rápida desde un hueco libre del calendario: el slot ya fija doctor/
// consultorio/fecha/producto; sólo falta elegir el contacto (y notas opcionales).
export function QuickBookDrawer({ slot, productId, productName, onClose, onBooked }: Props) {
  const styles = useStyles();

  // ── Estado del contacto (búsqueda local en el Combobox, igual que el wizard) ──
  const [personId, setPersonId] = useState<string | null>(null);
  const [personName, setPersonName] = useState<string>("");
  const [personQuery, setPersonQuery] = useState<string>("");
  const [notes, setNotes] = useState<string>("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

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

  const handleCreate = () => {
    if (!personId) return;
    setCreateError(null);
    startTransition(async () => {
      const result = await createAppointment({
        person_id: personId,
        doctor_id: slot.doctor_id,
        office_id: slot.office_id,
        product_id: productId,
        scheduled_for: slot.starts_at,
        notes,
      });
      if (!result.ok) {
        // 400 de invariante (SLOT_TAKEN/OFFICE_SLOT_TAKEN/…) en español: el slot pudo
        // tomarse entre el compute del calendario y este book → invitamos a re-buscar.
        const fieldMsg = result.fieldErrors
          ? Object.values(result.fieldErrors).flat()[0]
          : undefined;
        setCreateError(result.error ?? fieldMsg ?? "No se pudo reservar la cita.");
        return;
      }
      onBooked();
    });
  };

  return (
    <Drawer
      open
      onClose={onClose}
      size="medium"
      title="Reservar cita"
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" onClick={handleCreate} disabled={!personId || pending}>
            {pending ? "Reservando…" : "Reservar"}
          </Button>
        </>
      }
    >
      <div className={styles.body}>
        {/* Resumen de solo lectura del hueco elegido (todo sale del slot). */}
        <div className={styles.summary}>
          <span className={styles.summaryLabel}>Producto</span>
          <span className={styles.summaryValue}>{productName || "—"}</span>
          <span className={styles.summaryLabel}>Doctor</span>
          <span className={styles.summaryValue}>{slot.doctor_name}</span>
          <span className={styles.summaryLabel}>Consultorio</span>
          <span className={styles.summaryValue}>{`${slot.office_name} · ${slot.branch_name}`}</span>
          <span className={styles.summaryLabel}>Fecha y hora</span>
          <span className={styles.summaryValue}>{formatDate(slot.starts_at)}</span>
        </div>

        <div className={styles.panel}>
          {createError ? (
            <MessageBar intent="error">
              <MessageBarBody>
                {createError} Si el horario ya no está disponible, cierra y busca otro hueco.
              </MessageBarBody>
            </MessageBar>
          ) : null}

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
      </div>
    </Drawer>
  );
}
