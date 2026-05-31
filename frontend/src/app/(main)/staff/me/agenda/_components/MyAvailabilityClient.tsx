"use client";

import {
  Button,
  MessageBar,
  MessageBarBody,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { AddRegular, CalendarLtrRegular } from "@fluentui/react-icons";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

import {
  createMyAvailability,
  deleteMyAvailability,
  listMyAvailability,
  updateMyAvailability,
} from "@/actions/me.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { usePermissions } from "@/hooks/usePermissions";
import { CALENDAR, minutesToTime, timeToMinutes } from "@/lib/constants/calendar";
import { appTokens, brandPalette } from "@/lib/theme/brand";
import type { BranchOption } from "@/types/clinic.types";
import type { DoctorAvailabilityItem } from "@/types/staff.types";

import {
  AddAvailabilityDrawer,
  type AvailabilityDraft,
} from "../../../doctors/[id]/_components/AddAvailabilityDrawer";
import { AvailabilityGrid } from "../../../doctors/[id]/_components/AvailabilityGrid";
import { WeekNavigator } from "../../../doctors/[id]/_components/WeekNavigator";
import { addDays, startOfWeek, toIsoDate } from "../../../doctors/[id]/_components/week";

const useStyles = makeStyles({
  root: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalL },
  header: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXXS },
  title: {
    margin: 0,
    fontSize: tokens.fontSizeHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
    letterSpacing: "-0.02em",
  },
  subtitle: { margin: 0, fontSize: tokens.fontSizeBase300, color: appTokens.chromeTextMuted },
  body: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM },
  toolbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    flexWrap: "wrap",
  },
  gridWrap: { position: "relative" },
  // El estado de carga/vacío es una tarjeta anclada cerca del tope de la grilla
  // (no centrada en el vacío). pointerEvents:none deja las celdas clicables debajo.
  hintLayer: {
    position: "absolute",
    insetInline: 0,
    top: "92px",
    display: "flex",
    justifyContent: "center",
    pointerEvents: "none",
  },
  hintCard: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalXS,
    maxWidth: "380px",
    padding: `${tokens.spacingVerticalL} ${tokens.spacingHorizontalXL}`,
    backgroundColor: appTokens.chromeBg,
    border: `1px solid ${appTokens.tableBorder}`,
    borderRadius: tokens.borderRadiusLarge,
    boxShadow: tokens.shadow16,
    textAlign: "center",
  },
  hintIcon: { fontSize: "28px", color: brandPalette.primary },
  hintTitle: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
    color: appTokens.chromeText,
  },
  hintText: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
});

interface Props {
  doctorBranches: BranchOption[];
}

interface DrawerState {
  mode: "create" | "edit";
  editingBlock?: DoctorAvailabilityItem | null;
  initial: AvailabilityDraft;
}

// La agenda propia del doctor logueado. MISMA experiencia de grilla que
// DoctorAvailabilityTab (F2) — reusa AvailabilityGrid/WeekNavigator/
// AddAvailabilityDrawer verbatim — pero la capa de datos apunta a las actions
// /me (sin doctorId; el backend lo resuelve del token).
export function MyAvailabilityClient({ doctorBranches }: Props) {
  const styles = useStyles();
  const { hasPermission } = usePermissions();
  const canWrite = hasPermission("MY_AVAILABILITY_WRITE");

  // Lunes (local, medianoche) de la semana visible. Navegación ‹ › / "Hoy".
  const [weekStart, setWeekStart] = useState<Date>(() => startOfWeek(new Date()));
  const [drawer, setDrawer] = useState<DrawerState | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DoctorAvailabilityItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const weekFrom = useMemo(() => toIsoDate(weekStart), [weekStart]);
  const weekTo = useMemo(() => toIsoDate(addDays(weekStart, 6)), [weekStart]);

  // TanStack Query keyed on la semana visible. Cambiar de semana cambia la key →
  // refetch automático; respuestas viejas no pisan la nueva (Query las descarta
  // por key). No refetch en cada render: la key es estable mientras la semana no cambie.
  const query = useQuery({
    queryKey: ["staff:me:availability", weekFrom],
    queryFn: () => listMyAvailability(weekFrom, weekTo),
  });

  // Bloques indexados por id (edición/borrado O(1)). Memoizado.
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
    const result = await deleteMyAvailability(deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
      setSelectedBlockId(null);
      void query.refetch();
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  }, [deleteTarget, query]);

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Mi agenda</h1>
        <p className={styles.subtitle}>
          Define tus bloques de disponibilidad por sede y consultorio.
        </p>
      </header>

      <div className={styles.body}>
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
            <div className={styles.hintLayer}>
              <div className={styles.hintCard}>
                <Spinner size="small" />
                <span className={styles.hintText}>Cargando disponibilidad…</span>
              </div>
            </div>
          ) : isEmpty ? (
            <div className={styles.hintLayer}>
              <div className={styles.hintCard}>
                <CalendarLtrRegular className={styles.hintIcon} />
                <span className={styles.hintTitle}>Sin disponibilidad esta semana</span>
                <span className={styles.hintText}>
                  {canWrite
                    ? "Haz clic en una celda del calendario o usa “Agregar disponibilidad”."
                    : "No tienes disponibilidad registrada esta semana."}
                </span>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {drawer ? (
        <AddAvailabilityDrawer
          doctorBranches={doctorBranches}
          mode={drawer.mode}
          editingBlock={drawer.editingBlock}
          initial={drawer.initial}
          onCreate={(input) => createMyAvailability(input)}
          onUpdate={(blockId, input) => updateMyAvailability(blockId, input)}
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
