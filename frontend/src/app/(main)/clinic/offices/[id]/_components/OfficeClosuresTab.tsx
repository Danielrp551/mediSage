"use client";

import {
  Badge,
  Button,
  Input,
  MessageBar,
  MessageBarBody,
  Spinner,
  Switch,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { AddRegular, DeleteRegular } from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createClosure, deleteClosure, listClosures } from "@/actions/office-closure.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { usePermissions } from "@/hooks/usePermissions";
import {
  officeClosureCreateSchema,
  type OfficeClosureCreateInput,
} from "@/lib/schemas/office-closure.schema";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { OfficeClosureItem } from "@/types/clinic.types";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
    maxWidth: "760px",
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
  },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeBase500,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  filterRow: {
    display: "flex",
    alignItems: "flex-end",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  filterField: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  filterLabel: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  list: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  row: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  rowBadge: { flexShrink: 0 },
  rowRange: { fontSize: tokens.fontSizeBase300, color: appTokens.chromeText, whiteSpace: "nowrap" },
  rowReason: {
    flex: 1,
    minWidth: 0,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
  },
  empty: {
    textAlign: "center",
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
    padding: tokens.spacingVerticalXL,
  },
  loadingRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
  },
  switchRow: { display: "flex", alignItems: "center", gap: tokens.spacingHorizontalS },
  twoCol: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.spacingHorizontalM },
});

interface Props {
  officeId: string;
  branchTimezone: string;
}

function toIsoStart(date: string): string | undefined {
  return date ? new Date(`${date}T00:00:00`).toISOString() : undefined;
}

function toIsoEnd(date: string): string | undefined {
  return date ? new Date(`${date}T23:59:59`).toISOString() : undefined;
}

export function OfficeClosuresTab({ officeId, branchTimezone }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("OFFICE_CLOSURES_WRITE");

  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [closures, setClosures] = useState<OfficeClosureItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<OfficeClosureItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const fromIso = useMemo(() => toIsoStart(fromDate), [fromDate]);
  const toIso = useMemo(() => toIsoEnd(toDate), [toDate]);

  // A monotonic request id supersedes stale responses across ALL callers (the
  // filter-change effect AND the imperative post-create/delete reloads), so an
  // out-of-order fetch can never overwrite the list with results for a previous
  // filter range. Replaces a per-call `cancelled` closure that only the effect
  // could trip.
  const reqIdRef = useRef(0);

  const load = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setListError(null);
    void listClosures(officeId, fromIso, toIso)
      .then((rows) => {
        if (reqId !== reqIdRef.current) return;
        setClosures(rows);
        setLoading(false);
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setClosures([]); // don't leave stale rows under the error bar
        setListError("No se pudieron cargar las excepciones. Intenta de nuevo.");
        setLoading(false);
      });
  }, [officeId, fromIso, toIso]);

  useEffect(() => {
    load();
  }, [load]);

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteClosure(officeId, deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
      load();
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  };

  return (
    <div className={styles.root}>
      <div className={styles.headerRow}>
        <h2 className={styles.title}>Excepciones</h2>
        {canWrite ? (
          <Button appearance="primary" icon={<AddRegular />} onClick={() => setAddOpen(true)}>
            Agregar excepción
          </Button>
        ) : null}
      </div>

      <MessageBar intent="info">
        <MessageBarBody>
          Un cierre bloquea la atención en ese rango; una apertura extra habilita atención fuera del
          horario semanal. Las fechas se interpretan en la zona horaria de la sede ({branchTimezone}
          ).
        </MessageBarBody>
      </MessageBar>

      <div className={styles.filterRow}>
        <div className={styles.filterField}>
          <span className={styles.filterLabel}>Desde</span>
          <Input type="date" value={fromDate} onChange={(_, d) => setFromDate(d.value)} />
        </div>
        <div className={styles.filterField}>
          <span className={styles.filterLabel}>Hasta</span>
          <Input type="date" value={toDate} onChange={(_, d) => setToDate(d.value)} />
        </div>
      </div>

      {listError ? (
        <MessageBar intent="error">
          <MessageBarBody>{listError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.loadingRow}>
          <Spinner size="tiny" />
          Cargando excepciones…
        </div>
      ) : closures.length === 0 ? (
        <div className={styles.empty}>
          No hay excepciones en este rango. Agrega un cierre o una apertura extra.
        </div>
      ) : (
        <div className={styles.list}>
          {closures.map((c) => (
            <div key={c.id} className={styles.row}>
              <Badge
                className={styles.rowBadge}
                appearance="filled"
                color={c.is_closed ? "danger" : "success"}
              >
                {c.is_closed ? "Cierre" : "Apertura"}
              </Badge>
              <span className={styles.rowRange}>
                {formatDate(c.starts_at)} → {formatDate(c.ends_at)}
              </span>
              <span className={styles.rowReason}>{c.reason}</span>
              {canWrite ? (
                <Button
                  appearance="subtle"
                  size="small"
                  icon={<DeleteRegular />}
                  aria-label="Eliminar excepción"
                  onClick={() => {
                    setDeleteError(null);
                    setDeleteTarget(c);
                  }}
                />
              ) : null}
            </div>
          ))}
        </div>
      )}

      {addOpen ? (
        <ClosureCreateDrawer
          officeId={officeId}
          styles={styles}
          onClose={() => setAddOpen(false)}
          onCreated={() => {
            setAddOpen(false);
            load();
          }}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar esta excepción?"
        description={
          deleteError
            ? deleteError
            : "El consultorio volverá a seguir su horario normal en ese rango."
        }
        confirmText={deletePending ? "Eliminando…" : "Eliminar"}
        cancelText="Cancelar"
        destructive
        onConfirm={() => void handleConfirmDelete()}
        onCancel={() => {
          if (!deletePending) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
      />
    </div>
  );
}

type Styles = ReturnType<typeof useStyles>;

function ClosureCreateDrawer({
  officeId,
  styles,
  onClose,
  onCreated,
}: {
  officeId: string;
  styles: Styles;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<OfficeClosureCreateInput>({
    resolver: zodResolver(officeClosureCreateSchema),
    defaultValues: { starts_at: "", ends_at: "", is_closed: true, reason: "" },
  });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = await createClosure(officeId, values);
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onCreated();
    });
  });

  return (
    <Drawer
      open
      onClose={onClose}
      title="Nueva excepción"
      size="small"
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Agregando…" : "Agregar"}
          </Button>
        </>
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.twoCol}>
        <FormField label="Inicio" required error={form.formState.errors.starts_at?.message}>
          <Controller
            control={form.control}
            name="starts_at"
            render={({ field }) => <Input {...field} type="datetime-local" />}
          />
        </FormField>
        <FormField label="Fin" required error={form.formState.errors.ends_at?.message}>
          <Controller
            control={form.control}
            name="ends_at"
            render={({ field }) => <Input {...field} type="datetime-local" />}
          />
        </FormField>
      </div>

      <FormField label="Tipo">
        <Controller
          control={form.control}
          name="is_closed"
          render={({ field }) => (
            <div className={styles.switchRow}>
              <Switch checked={field.value} onChange={(_, d) => field.onChange(d.checked)} />
              <span>{field.value ? "Cerrado en este rango" : "Abierto en este rango"}</span>
            </div>
          )}
        />
      </FormField>

      <FormField label="Motivo" required error={form.formState.errors.reason?.message}>
        <Controller
          control={form.control}
          name="reason"
          render={({ field }) => <Input {...field} placeholder="ej. Feriado 28 de julio" />}
        />
      </FormField>
    </Drawer>
  );
}
