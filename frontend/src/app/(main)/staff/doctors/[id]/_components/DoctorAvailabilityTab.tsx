"use client";

import {
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { AddRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import {
  deleteDoctorAvailability,
  listDoctorAvailability,
} from "@/actions/doctor-availability.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { CALENDAR, minutesToTime, timeToMinutes } from "@/lib/constants/calendar";
import { appTokens } from "@/lib/theme/brand";
import type { BranchOption } from "@/types/clinic.types";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import { AddAvailabilityDrawer, type AvailabilityDraft } from "./AddAvailabilityDrawer";
import { AvailabilityGrid } from "./AvailabilityGrid";
import { WeekNavigator } from "./WeekNavigator";
import { addDays, startOfWeek, toIsoDate } from "./week";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  gridWrap: { position: "relative" },
  overlay: {
    position: "absolute",
    inset: 0,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: tokens.spacingVerticalS,
    backgroundColor: tokens.colorNeutralBackgroundAlpha,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase300,
    textAlign: "center",
    padding: tokens.spacingHorizontalL,
    pointerEvents: "none",
  },
  loadingRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    color: appTokens.chromeTextMuted,
    fontSize: tokens.fontSizeBase200,
  },
});

interface Props {
  doctorId: string;
  doctorBranches: BranchOption[];
  canWrite: boolean;
}

interface DrawerState {
  mode: "create" | "edit";
  editingBlock?: DoctorAvailabilityItem | null;
  initial: AvailabilityDraft;
}

export function DoctorAvailabilityTab({ doctorId, doctorBranches, canWrite }: Props) {
  const styles = useStyles();

  // Lunes (local, medianoche) de la semana visible. Navegación ‹ › / "Hoy".
  const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(new Date()));
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DoctorAvailabilityItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const weekFrom = useMemo(() => toIsoDate(weekStart), [weekStart]);
  const weekTo = useMemo(() => toIsoDate(addDays(weekStart, 6)), [weekStart]);

  // TanStack Query keyed on (doctorId, semana visible). Cambiar de semana cambia la
  // key → refetch automático; respuestas viejas no pisan la nueva (Query las descarta
  // por key). No refetch en cada render: la key es estable mientras la semana no cambie.
  const query = useQuery({
    queryKey: ["staff:availability", doctorId, weekFrom],
    queryFn: () => listDoctorAvailability(doctorId, weekFrom, weekTo),
  });

  // Bloques indexados por id (edición/borrado O(1)). Memoizado para no recalcular en
  // cada render mientras los datos no cambien.
  const blocks = useMemo(() => {
    const rows = query.data ?? [];
    return Object.fromEntries(rows.map((r) => [r.id, r])) as Record<string, DoctorAvailabilityItem>;
  }, [query.data]);

  const isEmpty = !query.isLoading && Object.keys(blocks).length === 0;

  // La sede/consultorio sugeridos en el drawer al crear: la primera sede del doctor.
  const defaultBranchId = doctorBranches[0]?.id ?? "";

  const openCreateForCell = useCallback(
    (dateIso: string, hhmm: string) => {
      const opensMin = timeToMinutes(hhmm);
      const closesMin = Math.min(opensMin + CALENDAR.DEFAULT_BLOCK_MINUTES, CALENDAR.END_HOUR * 60);
      setSelectedBlockId(null);
      setDrawer({
        mode: "create",
        initial: {
          branch_id: defaultBranchId,
          office_id: "",
          date_from: dateIso,
          date_to: dateIso,
          opens_at: hhmm,
          closes_at: minutesToTime(closesMin),
        },
      });
    },
    [defaultBranchId],
  );

  const openCreateGeneric = useCallback(() => {
    setSelectedBlockId(null);
    setDrawer({
      mode: "create",
      initial: {
        branch_id: defaultBranchId,
        office_id: "",
        date_from: weekFrom,
        date_to: weekFrom,
        opens_at: minutesToTime(CALENDAR.START_HOUR * 60 + 120),
        closes_at: minutesToTime(CALENDAR.START_HOUR * 60 + 120 + CALENDAR.DEFAULT_BLOCK_MINUTES),
      },
    });
  }, [defaultBranchId, weekFrom]);

  const openEdit = useCallback((block: DoctorAvailabilityItem) => {
    setSelectedBlockId(block.id);
    setDrawer({
      mode: "edit",
      editingBlock: block,
      initial: {
        branch_id: block.branch_id,
        office_id: block.office_id,
        date_from: block.date,
        date_to: block.date,
        opens_at: block.opens_at.slice(0, 5),
        closes_at: block.closes_at.slice(0, 5),
      },
    });
  }, []);

  const handleSaved = useCallback(() => {
    setDrawer(null);
    setSelectedBlockId(null);
    void query.refetch();
  }, [query]);

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteDoctorAvailability(doctorId, deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
      setSelectedBlockId(null);
      void query.refetch();
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  }, [deleteTarget, doctorId, query]);

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <WeekNavigator
          weekStart={weekStart}
          onPrev={() => setWeekStart((w) => addDays(w, -7))}
          onNext={() => setWeekStart((w) => addDays(w, 7))}
          onToday={() => setWeekStart(startOfWeek(new Date()))}
        />
        {canWrite ? (
          <Button appearance="primary" icon={<AddRegular />} onClick={openCreateGeneric}>
            Agregar disponibilidad
          </Button>
        ) : null}
      </div>

      {query.isError ? (
        <MessageBar intent="error">
          <MessageBarBody>No se pudo cargar la disponibilidad. Intenta de nuevo.</MessageBarBody>
        </MessageBar>
      ) : null}

      <div className={styles.gridWrap}>
        <AvailabilityGrid
          weekStart={weekStart}
          blocks={blocks}
          canWrite={canWrite}
          selectedBlockId={selectedBlockId}
          onCreateAt={openCreateForCell}
          onSelectBlock={openEdit}
        />

        {query.isLoading ? (
          <div className={styles.overlay}>
            <Spinner size="small" />
            <span>Cargando disponibilidad…</span>
          </div>
        ) : isEmpty ? (
          <div className={styles.overlay}>
            <span>
              {canWrite
                ? "Aún no hay disponibilidad esta semana — haz clic en una celda o usa Agregar disponibilidad."
                : "Este doctor no tiene disponibilidad esta semana."}
            </span>
          </div>
        ) : null}
      </div>

      {drawer ? (
        <AddAvailabilityDrawer
          doctorId={doctorId}
          doctorBranches={doctorBranches}
          mode={drawer.mode}
          editingBlock={drawer.editingBlock}
          initial={drawer.initial}
          onClose={() => {
            setDrawer(null);
            setSelectedBlockId(null);
          }}
          onSaved={handleSaved}
          onRequestDelete={
            drawer.mode === "edit" && drawer.editingBlock
              ? () => {
                  const target = drawer.editingBlock ?? null;
                  setDrawer(null);
                  setDeleteError(null);
                  setDeleteTarget(target);
                }
              : undefined
          }
        />
      ) : null}

      {/* Borrado del bloque seleccionado: se ofrece desde el drawer de edición vía
          el botón "Eliminar" del footer; aquí el ConfirmDialog confirma. */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar este bloque?"
        description={
          deleteError ? deleteError : "El bloque de disponibilidad se eliminará de esta fecha."
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
