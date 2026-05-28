"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { listUsers } from "@/actions/user.actions";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import { formatDate } from "@/lib/utils/date";
import type { ApiPaginated } from "@/types/api.types";
import type { PermissionOption } from "@/types/permission.types";
import type { RoleOption } from "@/types/role.types";
import type { UserItem } from "@/types/user.types";
import { UserDrawer } from "./UserDrawer";

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
  initialData: ApiPaginated<UserItem>;
  roles: RoleOption[];
  permissions: PermissionOption[];
}

type DrawerMode = "create" | "edit" | "view";
type DrawerState = { mode: DrawerMode; userId: string | null } | null;

export function UsersClient({ initialData, roles, permissions }: Props) {
  const styles = useStyles();
  const table = useTableQuery<UserItem>({
    queryKey: "admin:users",
    fetcher: listUsers,
    defaultSort: { field: "created_on", order: "desc" },
    searchFields: ["first_name", "last_name", "email"],
    initialData,
  });
  const [drawer, setDrawer] = useState<DrawerState>(null);

  // Memoised so each row's `RowActions` receives a stable reference and
  // doesn't re-render on every page render. `setDrawer` is a useState
  // setter — stable identity, no dep needed.
  const rowActions = useMemo<RowAction<UserItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (u) => setDrawer({ mode: "view", userId: u.id }),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["USERS_UPDATE"],
        onSelect: (u) => setDrawer({ mode: "edit", userId: u.id }),
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;
  const items = data.data.items;
  const total = data.data.total;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Usuarios</h1>
        <p className={styles.subtitle}>
          Gestiona quién tiene acceso a la consola y qué puede hacer.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por nombre o correo…"
          value={table.search}
          onChange={(_, data) => table.setSearch(data.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["USERS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", userId: null })}
          >
            Nuevo usuario
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<UserItem>
        items={items}
        getRowKey={(u) => u.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="Aún no hay usuarios"
        emptyMessage="Invita a tu equipo creando el primer usuario."
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
            onRender: (u) => <RowActions item={u} actions={rowActions} />,
          },
          {
            key: "full_name",
            name: "Nombre",
            fieldName: "full_name",
            isSortable: true,
            truncate: true,
            minWidth: 200,
          },
          {
            key: "email",
            name: "Correo",
            fieldName: "email",
            isSortable: true,
            truncate: true,
            minWidth: 220,
          },
          {
            key: "active",
            name: "Estado",
            align: "center",
            minWidth: 110,
            onRender: (u) => (
              <Badge appearance="filled" color={u.active ? "success" : "informative"}>
                {u.active ? "Activo" : "Deshabilitado"}
              </Badge>
            ),
          },
          {
            key: "roles_count",
            name: "Roles",
            fieldName: "roles_count",
            numeric: true,
            minWidth: 80,
          },
          {
            key: "updated_on",
            name: "Última actualización",
            isSortable: true,
            minWidth: 160,
            onRender: (u) => formatDate(u.updated_on),
          },
        ]}
        pagination={{
          page: table.page,
          pageSize: table.pageSize,
          total,
          onPageChange: table.setPage,
          onPageSizeChange: table.setPageSize,
        }}
      />

      {drawer ? (
        <UserDrawer
          mode={drawer.mode}
          userId={drawer.userId}
          roles={roles}
          permissions={permissions}
          onClose={() => setDrawer(null)}
        />
      ) : null}
    </div>
  );
}
