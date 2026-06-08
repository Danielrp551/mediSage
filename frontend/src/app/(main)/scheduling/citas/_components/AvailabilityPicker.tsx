"use client";

import {
  Button,
  Input,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { CalendarLtrRegular, CheckmarkCircleRegular } from "@fluentui/react-icons";
import { useEffect, useMemo, useRef, useState } from "react";

import { computeAvailability } from "@/actions/appointment.actions";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { formatDateShort, formatTime } from "@/lib/utils/date";
import type { AvailabilitySlot } from "@/types/scheduling.types";

const useStyles = makeStyles({
  panel: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted, margin: 0 },
  loadingRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  // width 100% + minWidth 0 para que el input nativo de fecha (dentro del <Input> de
  // Fluent) no desborde el grid de dos columnas (mismo arreglo que AddAvailabilityDrawer).
  control: { width: "100%", minWidth: 0 },
  // Disponibilidad: cada día agrupa sus slots; los slots son botones togglables.
  dayGroup: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  dayHeader: {
    fontSize: tokens.fontSizeBase300,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
  },
  slotGrid: { display: "flex", flexWrap: "wrap", gap: tokens.spacingHorizontalS },
  slotButton: { minWidth: "auto" },
  emptyBox: {
    padding: tokens.spacingVerticalL,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px dashed ${appTokens.chromeBorder}`,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase300,
    textAlign: "center",
  },
});

interface Props {
  // Insumos del cómputo. Al cambiar cualquiera se invalida la disponibilidad ya
  // calculada y la selección (conservando el rango de fechas), obligando a re-buscar.
  doctorId: string | null;
  productId: string | null;
  branchId: string | null;
  officeId: string | null;
  // El slot elegido lo posee el PADRE (lo necesita el resumen/submit); este componente
  // solo lo resalta y reporta los cambios vía onSelectSlot. `null` = ninguno / invalidado.
  selectedSlot: AvailabilitySlot | null;
  onSelectSlot: (slot: AvailabilitySlot | null) => void;
}

// Grupo de slots por día local (la clave de día se deriva client-side de starts_at).
interface DayGroup {
  key: string;
  slots: AvailabilitySlot[];
}

/**
 * Selector de disponibilidad reusable (rango de fechas → cómputo on-the-fly → slots
 * agrupados por día → elegir uno). Extraído del paso 3 del BookingWizard; lo reusan el
 * wizard de reserva y el RescheduleDrawer (y la grilla de calendario F4).
 *
 * Posee internamente el rango de fechas + los slots computados; el slot ELEGIDO es
 * controlado por el padre. Cuando cambia un insumo del cómputo (doctor/producto/sede/
 * consultorio) invalida los slots y la selección (no el rango), igual que el wizard.
 */
export function AvailabilityPicker({
  doctorId,
  productId,
  branchId,
  officeId,
  selectedSlot,
  onSelectSlot,
}: Props) {
  const styles = useStyles();

  const [fromDate, setFromDate] = useState<string>("");
  const [toDate, setToDate] = useState<string>("");
  const [slots, setSlots] = useState<AvailabilitySlot[] | null>(null);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [slotsError, setSlotsError] = useState<string | null>(null);

  // use-latest: el effect de invalidación depende SOLO de los insumos del cómputo, no de
  // la identidad de onSelectSlot (que el padre podría recrear en cada render).
  const onSelectSlotRef = useRef(onSelectSlot);
  onSelectSlotRef.current = onSelectSlot;

  // Al cambiar cualquier insumo del cómputo, invalidar slots/selección computados (sin
  // tocar el rango de fechas) → el usuario debe re-buscar. Espeja resetAvailability() del
  // wizard. NO se setea selectedSlot localmente (lo posee el padre) → onSelectSlot(null).
  useEffect(() => {
    setSlots(null);
    setSlotsError(null);
    onSelectSlotRef.current(null);
  }, [doctorId, productId, branchId, officeId]);

  const handleSearchSlots = async () => {
    if (!doctorId || !productId || !fromDate || !toDate) return;
    // Validación client-side del rango: el backend también lo rechaza (422) pero su
    // `detail` llega en inglés genérico; acá damos un mensaje claro en español. Las
    // fechas son "YYYY-MM-DD" → comparar como string es cronológicamente correcto.
    if (toDate < fromDate) {
      setSlotsError('La fecha "Hasta" debe ser igual o posterior a "Desde".');
      return;
    }
    setLoadingSlots(true);
    setSlotsError(null);
    setSlots(null);
    onSelectSlot(null);
    try {
      const res = await computeAvailability({
        doctor_id: doctorId,
        product_id: productId,
        branch_id: branchId || null,
        office_id: officeId || null,
        from_date: fromDate,
        to_date: toDate,
      });
      setSlots(res.slots);
    } catch (e) {
      setSlotsError(e instanceof Error ? e.message : "No se pudo calcular la disponibilidad.");
    } finally {
      setLoadingSlots(false);
    }
  };

  // Agrupa los slots por día LOCAL. La clave del día se deriva de
  // formatDateShort(starts_at) — client-safe (TZ del navegador); NO se construye una
  // fecha con la hora actual, para no desfasar entre SSR y cliente.
  const dayGroups = useMemo<DayGroup[]>(() => {
    if (!slots) return [];
    const map = new Map<string, AvailabilitySlot[]>();
    for (const slot of slots) {
      const key = formatDateShort(slot.starts_at);
      const bucket = map.get(key);
      if (bucket) bucket.push(slot);
      else map.set(key, [slot]);
    }
    return Array.from(map.entries()).map(([key, daySlots]) => ({ key, slots: daySlots }));
  }, [slots]);

  return (
    <div className={styles.panel}>
      <div className={styles.twoCol}>
        <FormField label="Desde" required>
          {/* Fechas como strings "YYYY-MM-DD"; NO se parsean con el constructor Date. */}
          <Input
            type="date"
            className={styles.control}
            value={fromDate}
            onChange={(_, d) => {
              setFromDate(d.value);
              setSlots(null);
              onSelectSlot(null);
            }}
          />
        </FormField>
        <FormField label="Hasta" required>
          <Input
            type="date"
            className={styles.control}
            value={toDate}
            onChange={(_, d) => {
              setToDate(d.value);
              setSlots(null);
              onSelectSlot(null);
            }}
          />
        </FormField>
      </div>
      <div>
        <Button
          appearance="primary"
          icon={<CalendarLtrRegular />}
          onClick={() => void handleSearchSlots()}
          disabled={!fromDate || !toDate || loadingSlots}
        >
          {loadingSlots ? "Buscando…" : "Buscar horarios"}
        </Button>
      </div>

      {slotsError ? (
        <MessageBar intent="error">
          <MessageBarBody>{slotsError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {loadingSlots ? (
        <span className={styles.loadingRow}>
          <Spinner size="small" />
          <span className={styles.hint}>Calculando disponibilidad…</span>
        </span>
      ) : null}

      {slots !== null && !loadingSlots && slots.length === 0 ? (
        <div className={styles.emptyBox}>No hay horarios disponibles en ese rango.</div>
      ) : null}

      {dayGroups.map((group) => (
        <div key={group.key} className={styles.dayGroup}>
          <span className={styles.dayHeader}>
            <CalendarLtrRegular />
            {group.key}
          </span>
          <div className={styles.slotGrid}>
            {group.slots.map((slot) => {
              const selected =
                selectedSlot?.starts_at === slot.starts_at &&
                selectedSlot?.office_id === slot.office_id;
              return (
                <Button
                  key={`${slot.starts_at}-${slot.office_id}`}
                  className={styles.slotButton}
                  appearance={selected ? "primary" : "outline"}
                  icon={selected ? <CheckmarkCircleRegular /> : undefined}
                  aria-pressed={selected}
                  onClick={() => onSelectSlot(slot)}
                >
                  {formatTime(slot.starts_at)} · {slot.office_name}
                </Button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
