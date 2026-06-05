"use client";

import { Badge, Button, Input, Tooltip, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  CheckmarkCircleRegular,
  DeleteRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
  WarningRegular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { deleteBotTool, listBotTools } from "@/actions/bot-tools.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { BotToolItem } from "@/types/bots.types";

import { BotToolDrawer } from "./BotToolDrawer";

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
  subtitle: {
    margin: 0,
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
  },
  toolbar: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  search: { flex: 1, maxWidth: "360px" },
  mono: { fontFamily: appTokens.fontMono, fontSize: tokens.fontSizeBase200 },
  monoTruncate: {
    fontFamily: appTokens.fontMono,
    fontSize: tokens.fontSizeBase200,
    display: "block",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  neutral: { color: tokens.colorNeutralForeground3, fontSize: tokens.fontSizeBase200 },
});

interface Props {
  initialData: ApiPaginated<BotToolItem>;
}

type DrawerState = { mode: "create" | "edit" | "view"; toolId: string | null } | null;

export function BotToolsClient({ initialData }: Props) {
  const styles = useStyles();
  const table = useTableQuery<BotToolItem>({
    queryKey: "bots:tools",
    fetcher: listBotTools,
    // ⚠ DEBE coincidir con el sorting del prefetch del RSC (created_on desc) —
    // lección desync footer de crm.
    defaultSort: { field: "created_on", order: "desc" },
    // Solo columnas reales del repo (ALLOWED_FIELDS) — `is_registered`/`description`
    // NO son ordenables/filtrables (darían 400; lección hotfix staff).
    searchFields: ["code", "name", "target_service"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<BotToolItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<BotToolItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        permissions: ["BOT_TOOLS_READ"],
        onSelect: (t) => setDrawer({ mode: "view", toolId: t.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["BOT_TOOLS_WRITE"],
        onSelect: (t) => setDrawer({ mode: "edit", toolId: t.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["BOT_TOOLS_WRITE"],
        danger: true,
        onSelect: (t) => {
          setDeleteError(null);
          setDeleteTarget(t);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteBotTool(deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  };

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Herramientas</h1>
        <p className={styles.subtitle}>
          Acciones que un bot puede invocar durante una conversación.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por código, nombre o servicio…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["BOT_TOOLS_WRITE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", toolId: null })}
          >
            Nueva herramienta
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<BotToolItem>
        items={data.data.items}
        getRowKey={(t) => t.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay herramientas"
        emptyMessage="Crea herramientas (acciones de crm/catálogo) para que tus bots puedan ejecutarlas durante una conversación."
        sortField={table.sortField}
        sortOrder={table.sortOrder}
        onSort={(field, descending) => table.setSort(field, descending ? "desc" : "asc")}
        columns={[
          {
            key: "actions",
            name: "",
            align: "center",
            minWidth: 48,
            maxWidth: 56,
            onRender: (t) => <RowActions item={t} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Código",
            isSortable: true,
            truncate: true,
            minWidth: 180,
            onRender: (t) => <span className={styles.mono}>{t.code}</span>,
          },
          {
            key: "name",
            name: "Nombre",
            fieldName: "name",
            isSortable: true,
            truncate: true,
            minWidth: 200,
          },
          {
            key: "target_service",
            name: "Servicio destino",
            isSortable: true,
            minWidth: 200,
            maxWidth: 260,
            onRender: (t) => (
              <Tooltip content={t.target_service} relationship="label" withArrow>
                <span className={styles.monoTruncate}>{t.target_service}</span>
              </Tooltip>
            ),
          },
          {
            key: "requires_confirmation",
            name: "Confirmación",
            align: "center",
            minWidth: 120,
            onRender: (t) =>
              t.requires_confirmation ? (
                <Badge appearance="tint" color="warning" icon={<WarningRegular />}>
                  Sí
                </Badge>
              ) : (
                <span className={styles.neutral}>—</span>
              ),
          },
          {
            key: "is_registered",
            name: "Registrada",
            align: "center",
            minWidth: 130,
            onRender: (t) =>
              t.is_registered ? (
                <Badge appearance="tint" color="success" icon={<CheckmarkCircleRegular />}>
                  Registrada
                </Badge>
              ) : (
                <Tooltip
                  content="El servicio destino no está disponible en este entorno; invocarla dará error."
                  relationship="label"
                  withArrow
                >
                  <Badge appearance="tint" color="warning">
                    No registrada
                  </Badge>
                </Tooltip>
              ),
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (t) => (
              <Badge appearance="filled" color={t.active ? "success" : "informative"}>
                {t.active ? "Activo" : "Inactivo"}
              </Badge>
            ),
          },
        ]}
        pagination={{
          page: table.page,
          pageSize: table.pageSize,
          total: data.data.total,
          onPageChange: table.setPage,
          onPageSizeChange: table.setPageSize,
        }}
      />

      {drawer ? (
        <BotToolDrawer mode={drawer.mode} toolId={drawer.toolId} onClose={() => setDrawer(null)} />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar herramienta?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar la herramienta "${deleteTarget.name}"? Los bots que la tengan asignada dejarán de poder invocarla. Las llamadas registradas se conservan.`
              : ""
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
