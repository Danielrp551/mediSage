"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  DeleteRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { deleteBotConfiguration, listBotConfigurations } from "@/actions/bots.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { BOT_TYPE_META } from "@/lib/constants/bots";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { BotConfigurationItem } from "@/types/bots.types";

import { BotConfigurationDrawer } from "./BotConfigurationDrawer";

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
  versionCell: { display: "inline-flex", alignItems: "center", gap: tokens.spacingHorizontalXS },
  noVersion: { color: tokens.colorNeutralForeground3, fontSize: tokens.fontSizeBase200 },
});

interface Props {
  initialData: ApiPaginated<BotConfigurationItem>;
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; configId: string | null } | null;

export function BotConfigurationsClient({ initialData }: Props) {
  const styles = useStyles();
  const table = useTableQuery<BotConfigurationItem>({
    queryKey: "bots:configurations",
    fetcher: listBotConfigurations,
    // ⚠ DEBE coincidir con el sorting del prefetch del RSC (created_on desc) —
    // lección desync footer de crm.
    defaultSort: { field: "created_on", order: "desc" },
    searchFields: ["code", "name"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<BotConfigurationItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<BotConfigurationItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        permissions: ["BOT_CONFIGURATIONS_READ"],
        onSelect: (c) => setDrawer({ mode: "view", configId: c.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["BOT_CONFIGURATIONS_UPDATE"],
        onSelect: (c) => setDrawer({ mode: "edit", configId: c.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["BOT_CONFIGURATIONS_DELETE"],
        danger: true,
        onSelect: (c) => {
          setDeleteError(null);
          setDeleteTarget(c);
        },
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deleteBotConfiguration(deleteTarget.id);
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
        <h1 className={styles.title}>Configuraciones de bot</h1>
        <p className={styles.subtitle}>
          Define los bots que atienden automáticamente tus conversaciones.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por código o nombre…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["BOT_CONFIGURATIONS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", configId: null })}
          >
            Nuevo bot
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<BotConfigurationItem>
        items={data.data.items}
        getRowKey={(c) => c.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay bots"
        emptyMessage="Crea un bot para que atienda automáticamente las conversaciones entrantes de tus canales."
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
            onRender: (c) => <RowActions item={c} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Código",
            isSortable: true,
            truncate: true,
            minWidth: 180,
            onRender: (c) => <span className={styles.mono}>{c.code}</span>,
          },
          {
            key: "name",
            name: "Nombre",
            fieldName: "name",
            isSortable: true,
            truncate: true,
            minWidth: 220,
          },
          {
            key: "bot_type",
            name: "Tipo",
            minWidth: 130,
            onRender: (c) => (
              <Badge appearance="tint" color={BOT_TYPE_META[c.bot_type].color}>
                {BOT_TYPE_META[c.bot_type].label}
              </Badge>
            ),
          },
          {
            key: "current_version",
            name: "Versión vigente",
            minWidth: 170,
            onRender: (c) =>
              c.current_version_id && c.current_version_number !== null ? (
                <span className={styles.versionCell}>
                  <Badge appearance="outline">v{c.current_version_number}</Badge>
                </span>
              ) : (
                <span className={styles.noVersion}>— sin versión</span>
              ),
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (c) => (
              <Badge appearance="filled" color={c.active ? "success" : "informative"}>
                {c.active ? "Activo" : "Inactivo"}
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
        <BotConfigurationDrawer
          mode={drawer.mode}
          configId={drawer.configId}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar bot?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el bot "${deleteTarget.name}"? Las conversaciones que esté atendiendo dejarán de recibir respuestas automáticas. La traza de eventos se conserva.`
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
