"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { listRoles } from "@/actions/role.actions";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { PermissionOption } from "@/types/permission.types";
import type { RoleItem } from "@/types/role.types";
import { RoleDrawer } from "./RoleDrawer";

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
});

interface Props {
  initialData: ApiPaginated<RoleItem>;
  permissions: PermissionOption[];
}

type DrawerState = { mode: "create" | "edit" | "view"; roleId: string | null } | null;

export function RolesClient({ initialData, permissions }: Props) {
  const styles = useStyles();
  const table = useTableQuery<RoleItem>({
    queryKey: "admin:roles",
    fetcher: listRoles,
    defaultSort: { field: "created_on", order: "desc" },
    searchFields: ["name", "description"],
    initialData,
  });
  const [drawer, setDrawer] = useState<DrawerState>(null);

  const rowActions = useMemo<RowAction<RoleItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (r) => setDrawer({ mode: "view", roleId: r.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["ROLES_UPDATE"],
        onSelect: (r) => setDrawer({ mode: "edit", roleId: r.id }),
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Roles</h1>
        <p className={styles.subtitle}>
          Agrupa permisos en paquetes reutilizables que puedes asignar a usuarios.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por nombre o descripción…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["ROLES_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", roleId: null })}
          >
            Nuevo rol
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<RoleItem>
        items={data.data.items}
        getRowKey={(r) => r.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay roles"
        emptyMessage="Crea tu primer rol para empezar a agrupar permisos."
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
            onRender: (r) => <RowActions item={r} actions={rowActions} />,
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
            key: "description",
            name: "Descripción",
            fieldName: "description",
            truncate: true,
            minWidth: 280,
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (r) => (
              <Badge appearance="filled" color={r.active ? "success" : "informative"}>
                {r.active ? "Activo" : "Deshabilitado"}
              </Badge>
            ),
          },
          {
            key: "permissions_count",
            name: "Permisos",
            fieldName: "permissions_count",
            numeric: true,
            minWidth: 80,
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 160,
            onRender: (r) => formatDate(r.updated_on),
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
        <RoleDrawer
          mode={drawer.mode}
          roleId={drawer.roleId}
          permissions={permissions}
          onClose={() => setDrawer(null)}
        />
      ) : null}
    </div>
  );
}
