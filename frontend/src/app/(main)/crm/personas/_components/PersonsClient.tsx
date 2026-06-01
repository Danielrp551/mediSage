"use client";

import { Badge, Button, Input, makeStyles, tokens } from "@fluentui/react-components";
import {
  AddRegular,
  CheckmarkCircleRegular,
  DeleteRegular,
  EditRegular,
  EyeRegular,
  SearchRegular,
} from "@fluentui/react-icons";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { deletePerson, listPersons } from "@/actions/person.actions";
import { PermissionGuard } from "@/components/guards/PermissionGuard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { DataTable } from "@/components/ui/DataTable/DataTable";
import { RowActions, type RowAction } from "@/components/ui/RowActions/RowActions";
import { useTableQuery } from "@/hooks/useTableQuery";
import { CHANNEL_TYPE_META } from "@/lib/constants/crm";
import { appTokens } from "@/lib/theme/brand";
import type { ApiPaginated } from "@/types/api.types";
import type { PersonItem } from "@/types/crm.types";

import { PersonCreateDrawer } from "./PersonCreateDrawer";

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
  toolbar: {
    display: "flex",
    gap: tokens.spacingHorizontalM,
    alignItems: "center",
    flexWrap: "wrap",
  },
  search: { flex: 1, maxWidth: "360px" },
  contactCell: {
    display: "inline-flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalXS,
    minWidth: 0,
  },
  contactIcon: { color: appTokens.chromeTextMuted, flexShrink: 0, display: "inline-flex" },
  contactValue: { overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  verifiedIcon: {
    color: tokens.colorPaletteGreenForeground1,
    flexShrink: 0,
    display: "inline-flex",
  },
  muted: { color: appTokens.chromeTextMuted },
});

interface Props {
  initialData: ApiPaginated<PersonItem>;
}

export function PersonsClient({ initialData }: Props) {
  const styles = useStyles();
  const router = useRouter();

  // F1: el listado no tiene filtros server-side por estado/asesor (se difieren a
  // F2/F3). En F1 sólo hay búsqueda client-side por nombre/documento. Las
  // columnas denormalizadas (full_name/primary_identifier) NO son ALLOWED_FIELDS
  // → NO son server-sortable (lección cd10c78); el defaultSort usa `created_on`
  // (columna real) y DEBE coincidir con el prefetch del page.tsx.
  const table = useTableQuery<PersonItem>({
    queryKey: "crm:persons",
    fetcher: listPersons,
    defaultSort: { field: "created_on", order: "desc" },
    initialData,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PersonItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  // Búsqueda por nombre/documento: client-side sobre la página cargada (ambos
  // son denormalizados, no server-searchable).
  const [searchText, setSearchText] = useState("");

  const data = table.query.data ?? initialData;

  const filteredItems = useMemo(() => {
    const needle = searchText.trim().toLowerCase();
    if (!needle) return data.data.items;
    return data.data.items.filter((p) =>
      [p.full_name, p.document_number, p.primary_identifier?.identifier].some((field) =>
        (field ?? "").toLowerCase().includes(needle),
      ),
    );
  }, [data.data.items, searchText]);

  const rowActions = useMemo<RowAction<PersonItem>[]>(
    () => [
      {
        key: "view",
        label: "Ver",
        icon: <EyeRegular />,
        onSelect: (p) => router.push(`/crm/personas/${p.id}`),
      },
      {
        key: "edit",
        label: "Editar",
        icon: <EditRegular />,
        permissions: ["PERSONS_UPDATE"],
        onSelect: (p) => router.push(`/crm/personas/${p.id}?tab=summary`),
      },
      {
        key: "delete",
        label: "Eliminar",
        icon: <DeleteRegular />,
        permissions: ["PERSONS_DELETE"],
        danger: true,
        onSelect: (p) => {
          setDeleteError(null);
          setDeleteTarget(p);
        },
      },
    ],
    [router],
  );

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await deletePerson(deleteTarget.id);
    setDeletePending(false);
    if (result.ok) {
      setDeleteTarget(null);
    } else {
      setDeleteError(result.error ?? "No se pudo eliminar.");
    }
  };

  const isFiltered = searchText.trim().length > 0;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Contactos</h1>
        <p className={styles.subtitle}>Gestiona las personas, sus leads y clientes.</p>
      </header>

      <div className={styles.toolbar}>
        <Input
          className={styles.search}
          placeholder="Buscar por nombre o contacto…"
          value={searchText}
          onChange={(_, d) => setSearchText(d.value)}
          contentBefore={<SearchRegular />}
        />
        <PermissionGuard anyOf={["PERSONS_CREATE"]}>
          <Button appearance="primary" icon={<AddRegular />} onClick={() => setCreateOpen(true)}>
            Nuevo contacto
          </Button>
        </PermissionGuard>
      </div>

      <DataTable<PersonItem>
        items={filteredItems}
        getRowKey={(p) => p.id}
        isLoading={table.query.isPending}
        isFetching={table.query.isFetching && !table.query.isPending}
        isFiltered={isFiltered}
        emptyTitle="Aún no hay contactos"
        emptyMessage="Registra el primer contacto para asignarle un lead, un asesor y empezar a registrar su actividad."
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
            // No isSortable: full_name es denormalizado (compuesto server-side),
            // no está en ALLOWED_FIELDS → ordenar por ella es 400. Se busca
            // client-side.
            key: "full_name",
            name: "Nombre",
            fieldName: "full_name",
            truncate: true,
            minWidth: 220,
          },
          {
            // No isSortable: primary_identifier es denormalizado.
            key: "primary_identifier",
            name: "Contacto principal",
            minWidth: 200,
            onRender: (p) => {
              if (!p.primary_identifier) return <span className={styles.muted}>—</span>;
              const Icon = CHANNEL_TYPE_META[p.primary_identifier.channel_type].icon;
              return (
                <span className={styles.contactCell}>
                  <span className={styles.contactIcon}>
                    <Icon />
                  </span>
                  <span className={styles.contactValue}>{p.primary_identifier.identifier}</span>
                  {p.primary_identifier.verified ? (
                    <span className={styles.verifiedIcon} title="Verificado">
                      <CheckmarkCircleRegular />
                    </span>
                  ) : null}
                </span>
              );
            },
          },
          {
            key: "document_number",
            name: "Documento",
            minWidth: 140,
            onRender: (p) =>
              p.document_number ? (
                `${p.document_type ? `${p.document_type} ` : ""}${p.document_number}`
              ) : (
                <span className={styles.muted}>—</span>
              ),
          },
          {
            // F1: lead_status llega null del backend → "—". El badge de color y el
            // filtro por estado llegan en F2/F3.
            key: "lead_status",
            name: "Estado lead",
            minWidth: 140,
            onRender: (p) =>
              p.lead_status ? (
                <Badge
                  appearance="filled"
                  style={{
                    backgroundColor: p.lead_status.color ?? tokens.colorNeutralBackground3,
                    color: tokens.colorNeutralForegroundOnBrand,
                  }}
                >
                  {p.lead_status.name}
                </Badge>
              ) : (
                <span className={styles.muted}>—</span>
              ),
          },
          {
            // F1: customer_status llega null del backend → "—". Llega en F4.
            key: "customer_status",
            name: "Estado cliente",
            minWidth: 140,
            onRender: (p) =>
              p.customer_status ? (
                <Badge
                  appearance="filled"
                  style={{
                    backgroundColor: p.customer_status.color ?? tokens.colorNeutralBackground3,
                    color: tokens.colorNeutralForegroundOnBrand,
                  }}
                >
                  {p.customer_status.name}
                </Badge>
              ) : (
                <span className={styles.muted}>—</span>
              ),
          },
          {
            // F1: assigned_advisor llega null del backend → "—". Llega en F3.
            key: "assigned_advisor",
            name: "Asesor",
            truncate: true,
            minWidth: 160,
            onRender: (p) =>
              p.assigned_advisor ? (
                p.assigned_advisor.full_name
              ) : (
                <span className={styles.muted}>Sin asignar</span>
              ),
          },
          {
            // F1: last_activity_at llega null del backend → "—". Es denormalizado
            // (no server-sortable). La fecha relativa llega con el timeline (F5).
            key: "last_activity_at",
            name: "Última actividad",
            minWidth: 140,
            onRender: () => <span className={styles.muted}>—</span>,
          },
          {
            key: "active",
            name: "Activo",
            align: "center",
            minWidth: 110,
            onRender: (p) => (
              <Badge appearance="filled" color={p.active ? "success" : "informative"}>
                {p.active ? "Activo" : "Inactivo"}
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

      {createOpen ? <PersonCreateDrawer onClose={() => setCreateOpen(false)} /> : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar contacto?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `¿Eliminar el contacto "${deleteTarget.full_name}"? Dejará de aparecer en los listados (borrado lógico) y sus identificadores se ocultarán. El historial se conserva.`
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
