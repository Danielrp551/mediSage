"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  CheckmarkCircleRegular,
  DeleteRegular,
  DismissCircleRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import {
  deleteChannelAccount,
  listChannelAccounts,
} from "@/actions/channel-account.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { CHANNEL_TYPE_META } from "@/lib/constants/crm";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { ChannelAccountItem } from "@/types/conversations.types";

import { ChannelAccountDrawer } from "./ChannelAccountDrawer";

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
  channelCell: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
  },
});

interface Props {
  initialData: ApiPaginated<ChannelAccountItem>;
  pageSize: number;
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; channelAccountId: string | null } | null;

export function ChannelAccountsClient({ initialData, pageSize }: Props) {
  const styles = useStyles();
  const table = useTableQuery<ChannelAccountItem>({
    queryKey: "conversations:channel-accounts",
    fetcher: listChannelAccounts,
    // defaultSort = columna REAL; coincide con el prefetch del RSC.
    defaultSort: { field: "created_on", order: "desc" },
    defaultPageSize: pageSize,
    // Búsqueda client-side sobre columnas reales (name/external_identifier).
    searchFields: ["name", "external_identifier"],
    initialData,
  });

  const [drawer, setDrawer] = useState<DrawerState>(null);
  const [deleteTarget, setDeleteTarget] = useState<ChannelAccountItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  const rowActions = useMemo<RowAction<ChannelAccountItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (c) => setDrawer({ mode: "view", channelAccountId: c.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["CHANNEL_ACCOUNTS_UPDATE"],
        onSelect: (c) => setDrawer({ mode: "edit", channelAccountId: c.id }),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["CHANNEL_ACCOUNTS_DELETE"],
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
    const result = await deleteChannelAccount(deleteTarget.id);
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
        <h1 className={styles.title}>Canales</h1>
        <p className={styles.subtitle}>
          Gestiona las cuentas de canal (WhatsApp) por las que entran y salen los mensajes.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por nombre o identificador…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["CHANNEL_ACCOUNTS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", channelAccountId: null })}
          >
            Nuevo canal
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<ChannelAccountItem>
        items={data.data.items}
        getRowKey={(c) => c.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay canales"
        emptyMessage="Crea el primero para empezar a recibir y enviar mensajes."
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
            key: "name",
            name: "Nombre",
            fieldName: "name",
            isSortable: true,
            truncate: true,
            minWidth: 220,
          },
          {
            key: "channel_type",
            name: "Canal",
            fieldName: "channel_type",
            isSortable: true,
            minWidth: 160,
            onRender: (c) => {
              const meta = CHANNEL_TYPE_META[c.channel_type];
              const Icon = meta.icon;
              return (
                <span className={styles.channelCell}>
                  <Icon aria-hidden />
                  {meta.label}
                </span>
              );
            },
          },
          {
            key: "external_identifier",
            name: "Identificador",
            fieldName: "external_identifier",
            isSortable: true,
            truncate: true,
            minWidth: 180,
          },
          {
            key: "credentials_configured",
            name: "Credenciales",
            align: "center",
            minWidth: 150,
            onRender: (c) =>
              c.credentials_configured ? (
                <Badge appearance="tint" color="success" icon={<CheckmarkCircleRegular />}>
                  Configurado
                </Badge>
              ) : (
                <Badge appearance="tint" color="warning" icon={<DismissCircleRegular />}>
                  Sin configurar
                </Badge>
              ),
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (c) => (
              <Badge appearance="filled" color={c.active ? "success" : "informative"}>
                {c.active ? "Activo" : "Deshabilitado"}
              </Badge>
            ),
          },
          {
            key: "created_on",
            name: "Creado el",
            fieldName: "created_on",
            isSortable: true,
            minWidth: 170,
            onRender: (c) => formatDate(c.created_on),
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
        <ChannelAccountDrawer
          mode={drawer.mode}
          channelAccountId={drawer.channelAccountId}
          onClose={() => setDrawer(null)}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar canal?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el canal "${deleteTarget.name}"? Las conversaciones existentes se conservan, pero dejará de recibir y enviar mensajes nuevos.`
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
