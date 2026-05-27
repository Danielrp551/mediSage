"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import { AddRegular, EditRegular, SearchRegular } from "@fluentui/react-icons";
import { useMemo, useState } from "react";

import { listPermissions } from "@/actions/permission.actions";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { PermissionItem } from "@/types/permission.types";
import { PermissionDrawer } from "./PermissionDrawer";

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
  code: { fontFamily: tokens.fontFamilyMonospace, fontSize: tokens.fontSizeBase300 },
});

interface Props {
  initialData: ApiPaginated<PermissionItem>;
}

type DrawerState = { mode: "create" | "edit"; perm: PermissionItem | null } | null;

export function PermissionsClient({ initialData }: Props) {
  const styles = useStyles();
  const table = useTableQuery<PermissionItem>({
    queryKey: "admin:permissions",
    fetcher: listPermissions,
    defaultSort: { field: "module", order: "asc" },
    searchFields: ["code", "name", "module"],
    initialData,
  });
  const [drawer, setDrawer] = useState<DrawerState>(null);

  const rowActions = useMemo<RowAction<PermissionItem>[]>(
    () => [
      {
        key: "edit",
        label: "Edit",
        icon: <EditRegular />,
        permissions: ["PERMISSIONS_UPDATE"],
        onSelect: (p) => setDrawer({ mode: "edit", perm: p }),
      },
    ],
    [],
  );

  const data = table.query.data ?? initialData;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Permissions</h1>
        <p className={styles.subtitle}>
          The atomic capabilities you can group into roles or assign directly.
        </p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Search by code, name or module…"
          value={table.search}
          onChange={(_, d) => table.setSearch(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["PERMISSIONS_CREATE"]}>
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => setDrawer({ mode: "create", perm: null })}
          >
            New permission
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<PermissionItem>
        items={data.data.items}
        getRowKey={(p) => p.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={table.search.length > 0}
        emptyTitle="No permissions yet"
        emptyMessage="Create your first permission to control access in the app."
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
            onRender: (p) => <RowActions item={p} actions={rowActions} />,
          },
          {
            key: "code",
            name: "Code",
            isSortable: true,
            minWidth: 220,
            onRender: (p) => <span className={styles.code}>{p.code}</span>,
          },
          {
            key: "name",
            name: "Name",
            fieldName: "name",
            truncate: true,
            minWidth: 220,
          },
          {
            key: "module",
            name: "Module",
            fieldName: "module",
            isSortable: true,
            minWidth: 140,
          },
          {
            key: "active",
            name: "Status",
            align: "center",
            minWidth: 110,
            onRender: (p) => (
              <Badge appearance="filled" color={p.active ? "success" : "informative"}>
                {p.active ? "Active" : "Disabled"}
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
        <PermissionDrawer
          mode={drawer.mode}
          permission={drawer.perm}
          onClose={() => setDrawer(null)}
        />
      ) : null}
    </div>
  );
}
