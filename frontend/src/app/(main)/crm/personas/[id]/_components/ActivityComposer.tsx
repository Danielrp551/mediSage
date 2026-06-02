"use client";

import {
  Button,
  Card,
  Dropdown,
  Field,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Tab,
  TabList,
  Textarea,
  makeStyles,
  tokens,
  type SelectTabData,
  type SelectTabEvent,
} from "@fluentui/react-components";
import { useCallback, useMemo, useState, useTransition } from "react";

import { createActivity } from "@/actions/lead-activity.actions";
import { ACTIVITY_OUTCOME_LABELS, ACTIVITY_TYPE_META } from "@/lib/constants/crm";
import { localDatetimeInputToISO } from "@/lib/utils/date";
import type { ActivityOutcome } from "@/types/crm.types";

// Sólo los 3 tipos que el composer ofrece como tabs. FOLLOW_UP_COMPLETED se emite
// desde la tarjeta ("Marcar completado"), no desde el composer.
type ComposerTab = "NOTE" | "CALL_ATTEMPT" | "FOLLOW_UP_SCHEDULED";

const OUTCOME_VALUES = Object.keys(ACTIVITY_OUTCOME_LABELS) as ActivityOutcome[];

// Canales de recordatorio para el seguimiento (van a payload.reminder_channel).
const REMINDER_CHANNELS: { value: string; label: string }[] = [
  { value: "whatsapp", label: "WhatsApp" },
  { value: "email", label: "Correo" },
  { value: "phone", label: "Teléfono" },
];

const useStyles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    padding: tokens.spacingVerticalM,
  },
  form: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalS },
  row: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
    alignItems: "flex-start",
  },
  grow: { flex: 1, minWidth: "200px" },
  actions: { display: "flex", justifyContent: "flex-end" },
});

interface Props {
  personId: string;
  /** Re-fetch del feed tras registrar (mismo `load()` del timeline). */
  onCreated: () => void;
}

/**
 * Composer del timeline (gated `canWrite` por el padre). `TabList` con 3 tabs
 * (Nota/Llamada/Seguimiento); el form cambia según la tab. Un solo botón
 * "Registrar" (con `useTransition` para el pending). El `scheduled_for` se compone
 * desde un `datetime-local` y se serializa a ISO con offset local (client-only),
 * NO `.toISOString()` ciego. Al éxito limpia el form + `onCreated()`.
 */
export function ActivityComposer({ personId, onCreated }: Props) {
  const styles = useStyles();

  const [tab, setTab] = useState<ComposerTab>("NOTE");

  // Estado del form (un solo objeto; cada tab usa el subconjunto que le aplica).
  const [content, setContent] = useState("");
  const [outcome, setOutcome] = useState<ActivityOutcome | "">("");
  const [durationMin, setDurationMin] = useState("");
  const [scheduledLocal, setScheduledLocal] = useState("");
  const [reminderChannel, setReminderChannel] = useState("");

  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const resetForm = useCallback(() => {
    setContent("");
    setOutcome("");
    setDurationMin("");
    setScheduledLocal("");
    setReminderChannel("");
    setFieldError(null);
    setServerError(null);
  }, []);

  const handleTabSelect = useCallback(
    (_e: SelectTabEvent, data: SelectTabData) => {
      setTab(data.value as ComposerTab);
      resetForm();
    },
    [resetForm],
  );

  const submit = useCallback(() => {
    setServerError(null);
    setFieldError(null);

    // Body por tipo (validación dura en el server vía Zod; acá pre-chequeamos lo
    // mínimo para feedback inmediato por campo).
    let body: Record<string, unknown>;
    if (tab === "NOTE") {
      if (!content.trim()) {
        setFieldError("Escribe el contenido de la nota.");
        return;
      }
      body = { activity_type: "NOTE", content: content.trim() };
    } else if (tab === "CALL_ATTEMPT") {
      if (!outcome) {
        setFieldError("Indica el resultado de la llamada.");
        return;
      }
      const duration = durationMin.trim() ? Number(durationMin) : null;
      body = {
        activity_type: "CALL_ATTEMPT",
        outcome,
        content: content.trim() ? content.trim() : null,
        payload:
          duration !== null && Number.isFinite(duration) ? { duration_min: duration } : undefined,
      };
    } else {
      const iso = localDatetimeInputToISO(scheduledLocal);
      if (!iso) {
        setFieldError("Elige la fecha y hora del seguimiento.");
        return;
      }
      body = {
        activity_type: "FOLLOW_UP_SCHEDULED",
        scheduled_for: iso,
        content: content.trim() ? content.trim() : null,
        payload: reminderChannel ? { reminder_channel: reminderChannel } : undefined,
      };
    }

    startTransition(async () => {
      const result = await createActivity(personId, body);
      if (!result.ok) {
        // fieldErrors del Zod (defensa en profundidad) o error del servidor.
        const first = result.fieldErrors ? Object.values(result.fieldErrors).flat()[0] : undefined;
        if (first) setFieldError(first);
        else setServerError(result.error ?? "No se pudo registrar la actividad.");
        return;
      }
      resetForm();
      onCreated();
    });
  }, [
    tab,
    content,
    outcome,
    durationMin,
    scheduledLocal,
    reminderChannel,
    personId,
    onCreated,
    resetForm,
  ]);

  const noteMeta = ACTIVITY_TYPE_META.NOTE;
  const callMeta = ACTIVITY_TYPE_META.CALL_ATTEMPT;
  const followMeta = ACTIVITY_TYPE_META.FOLLOW_UP_SCHEDULED;

  const reminderLabel = useMemo(
    () => REMINDER_CHANNELS.find((c) => c.value === reminderChannel)?.label ?? "",
    [reminderChannel],
  );

  return (
    <Card className={styles.card}>
      <TabList selectedValue={tab} onTabSelect={handleTabSelect}>
        <Tab value="NOTE" icon={<noteMeta.icon />}>
          Nota
        </Tab>
        <Tab value="CALL_ATTEMPT" icon={<callMeta.icon />}>
          Llamada
        </Tab>
        <Tab value="FOLLOW_UP_SCHEDULED" icon={<followMeta.icon />}>
          Seguimiento
        </Tab>
      </TabList>

      <div className={styles.form}>
        {tab === "NOTE" ? (
          <Field label="Nota">
            <Textarea
              value={content}
              onChange={(_, d) => setContent(d.value)}
              rows={3}
              placeholder="Escribe una nota sobre este contacto…"
              disabled={pending}
            />
          </Field>
        ) : null}

        {tab === "CALL_ATTEMPT" ? (
          <>
            <div className={styles.row}>
              <Field label="Resultado" required className={styles.grow}>
                <Dropdown
                  value={outcome ? ACTIVITY_OUTCOME_LABELS[outcome] : ""}
                  selectedOptions={outcome ? [outcome] : []}
                  placeholder="Selecciona…"
                  disabled={pending}
                  onOptionSelect={(_, data) =>
                    setOutcome((data.optionValue as ActivityOutcome) ?? "")
                  }
                >
                  {OUTCOME_VALUES.map((o) => (
                    <Option key={o} value={o}>
                      {ACTIVITY_OUTCOME_LABELS[o]}
                    </Option>
                  ))}
                </Dropdown>
              </Field>
              <Field label="Duración (min)">
                <Input
                  type="number"
                  min={0}
                  value={durationMin}
                  onChange={(_, d) => setDurationMin(d.value)}
                  placeholder="ej. 5"
                  disabled={pending}
                />
              </Field>
            </div>
            <Field label="Nota (opcional)">
              <Textarea
                value={content}
                onChange={(_, d) => setContent(d.value)}
                rows={2}
                placeholder="Detalle de la llamada…"
                disabled={pending}
              />
            </Field>
          </>
        ) : null}

        {tab === "FOLLOW_UP_SCHEDULED" ? (
          <>
            <div className={styles.row}>
              <Field label="Fecha y hora" required className={styles.grow}>
                <Input
                  type="datetime-local"
                  value={scheduledLocal}
                  onChange={(_, d) => setScheduledLocal(d.value)}
                  disabled={pending}
                />
              </Field>
              <Field label="Recordatorio (opcional)">
                <Dropdown
                  value={reminderLabel}
                  selectedOptions={reminderChannel ? [reminderChannel] : []}
                  placeholder="Canal…"
                  disabled={pending}
                  onOptionSelect={(_, data) => setReminderChannel(data.optionValue ?? "")}
                >
                  {REMINDER_CHANNELS.map((c) => (
                    <Option key={c.value} value={c.value}>
                      {c.label}
                    </Option>
                  ))}
                </Dropdown>
              </Field>
            </div>
            <Field label="Nota (opcional)">
              <Textarea
                value={content}
                onChange={(_, d) => setContent(d.value)}
                rows={2}
                placeholder="ej. Llamar para confirmar la cita."
                disabled={pending}
              />
            </Field>
          </>
        ) : null}

        {fieldError ? (
          <MessageBar intent="warning">
            <MessageBarBody>{fieldError}</MessageBarBody>
          </MessageBar>
        ) : null}
        {serverError ? (
          <MessageBar intent="error">
            <MessageBarBody>{serverError}</MessageBarBody>
          </MessageBar>
        ) : null}

        <div className={styles.actions}>
          <Button appearance="primary" disabled={pending} onClick={submit}>
            {pending ? "Registrando…" : "Registrar"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
