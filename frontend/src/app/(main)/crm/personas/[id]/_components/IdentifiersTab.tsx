"use client";

import {
  Badge,
  Button,
  Checkbox,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import {
  AddRegular,
  CheckmarkCircleRegular,
  DeleteRegular,
  EditRegular,
  StarRegular,
} from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import {
  addIdentifier,
  listIdentifiers,
  removeIdentifier,
  updateIdentifier,
} from "@/actions/contact-identifier.actions";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog/ConfirmDialog";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { CHANNEL_TYPE_META } from "@/lib/constants/crm";
import {
  contactIdentifierCreateSchema,
  type ContactIdentifierCreateInput,
} from "@/lib/schemas/contact-identifier.schema";
import { appTokens } from "@/lib/theme/brand";
import {
  CHANNEL_TYPES,
  type ChannelType,
  type PersonContactIdentifierItem,
} from "@/types/crm.types";

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
  list: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
  row: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    padding: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalM}`,
    borderRadius: tokens.borderRadiusMedium,
    border: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  rowIcon: { color: appTokens.chromeTextMuted, flexShrink: 0, display: "inline-flex" },
  rowValue: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  },
  rowBadges: { display: "flex", gap: tokens.spacingHorizontalXS, flexShrink: 0 },
  spacer: { flex: 1 },
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
  hint: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  checks: { display: "flex", flexDirection: "column", gap: tokens.spacingVerticalXS },
});

interface Props {
  personId: string;
  canWrite: boolean;
}

export function IdentifiersTab({ personId, canWrite }: Props) {
  const styles = useStyles();

  const [identifiers, setIdentifiers] = useState<PersonContactIdentifierItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<PersonContactIdentifierItem | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PersonContactIdentifierItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletePending, setDeletePending] = useState(false);

  // Token monotónico para descartar respuestas fuera de orden (mismo patrón que
  // OfficeClosuresTab) — los re-fetch tras mutar no deben pisar resultados nuevos.
  const reqIdRef = useRef(0);

  const load = useCallback(() => {
    const reqId = ++reqIdRef.current;
    setLoading(true);
    setListError(null);
    void listIdentifiers(personId)
      .then((rows) => {
        if (reqId !== reqIdRef.current) return;
        setIdentifiers(rows);
        setLoading(false);
      })
      .catch(() => {
        if (reqId !== reqIdRef.current) return;
        setIdentifiers([]);
        setListError("No se pudieron cargar los identificadores. Intenta de nuevo.");
        setLoading(false);
      });
  }, [personId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleMarkPrimary = async (item: PersonContactIdentifierItem) => {
    setRowError(null);
    const result = await updateIdentifier(personId, item.id, {
      channel_type: item.channel_type,
      identifier: item.identifier,
      is_primary: true,
    });
    if (result.ok) {
      load();
    } else {
      setRowError(result.error ?? "No se pudo marcar como principal.");
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeletePending(true);
    const result = await removeIdentifier(personId, deleteTarget.id);
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
        <h2 className={styles.title}>Identificadores</h2>
        {canWrite ? (
          <Button
            appearance="primary"
            icon={<AddRegular />}
            onClick={() => {
              setRowError(null);
              setEditTarget(null);
              setEditorOpen(true);
            }}
          >
            Agregar
          </Button>
        ) : null}
      </div>

      {listError ? (
        <MessageBar intent="error">
          <MessageBarBody>{listError}</MessageBarBody>
        </MessageBar>
      ) : null}
      {rowError ? (
        <MessageBar intent="error">
          <MessageBarBody>{rowError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {loading ? (
        <div className={styles.loadingRow}>
          <Spinner size="tiny" />
          Cargando identificadores…
        </div>
      ) : identifiers.length === 0 ? (
        <div className={styles.empty}>
          Este contacto aún no tiene identificadores. Agrega uno para poder contactarlo.
        </div>
      ) : (
        <div className={styles.list}>
          {identifiers.map((it) => {
            const Icon = CHANNEL_TYPE_META[it.channel_type].icon;
            return (
              <div key={it.id} className={styles.row}>
                <span className={styles.rowIcon}>
                  <Icon />
                </span>
                <span className={styles.rowValue}>{it.identifier}</span>
                <div className={styles.rowBadges}>
                  {it.is_primary ? (
                    <Badge appearance="filled" color="brand">
                      Principal
                    </Badge>
                  ) : null}
                  {it.verified ? (
                    <Badge appearance="tint" color="success" icon={<CheckmarkCircleRegular />}>
                      Verificado
                    </Badge>
                  ) : null}
                </div>
                <span className={styles.spacer} />
                {canWrite ? (
                  <>
                    {!it.is_primary ? (
                      <Button
                        appearance="subtle"
                        size="small"
                        icon={<StarRegular />}
                        aria-label="Marcar como principal"
                        title="Marcar como principal"
                        onClick={() => void handleMarkPrimary(it)}
                      />
                    ) : null}
                    <Button
                      appearance="subtle"
                      size="small"
                      icon={<EditRegular />}
                      aria-label="Editar identificador"
                      onClick={() => {
                        setRowError(null);
                        setEditTarget(it);
                        setEditorOpen(true);
                      }}
                    />
                    <Button
                      appearance="subtle"
                      size="small"
                      icon={<DeleteRegular />}
                      aria-label="Eliminar identificador"
                      onClick={() => {
                        setDeleteError(null);
                        setDeleteTarget(it);
                      }}
                    />
                  </>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      <p className={styles.hint}>El identificador principal de cada canal se usa para contactar.</p>

      {editorOpen ? (
        <IdentifierEditorDrawer
          personId={personId}
          target={editTarget}
          styles={styles}
          onClose={() => setEditorOpen(false)}
          onSaved={() => {
            setEditorOpen(false);
            load();
          }}
        />
      ) : null}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="¿Eliminar identificador?"
        description={
          deleteError
            ? deleteError
            : deleteTarget
              ? `Se eliminará "${deleteTarget.identifier}". Podrás volver a registrar ese valor más adelante.`
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

type Styles = ReturnType<typeof useStyles>;

function IdentifierEditorDrawer({
  personId,
  target,
  styles,
  onClose,
  onSaved,
}: {
  personId: string;
  target: PersonContactIdentifierItem | null;
  styles: Styles;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = target !== null;
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<ContactIdentifierCreateInput>({
    resolver: zodResolver(contactIdentifierCreateSchema),
    defaultValues: {
      channel_type: target?.channel_type ?? "whatsapp",
      identifier: target?.identifier ?? "",
      is_primary: target?.is_primary ?? false,
      verified: target?.verified ?? false,
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = isEdit
        ? await updateIdentifier(personId, target.id, values)
        : await addIdentifier(personId, values);
      if (!result.ok) {
        // 409 IDENTIFIER_TAKEN / 404 IDENTIFIER_NOT_FOUND en español.
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      onSaved();
    });
  });

  return (
    <Drawer
      open
      onClose={onClose}
      title={isEdit ? "Editar identificador" : "Nuevo identificador"}
      size="small"
      footer={
        <>
          <Button appearance="secondary" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Guardando…" : "Guardar"}
          </Button>
        </>
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <FormField label="Canal" required error={form.formState.errors.channel_type?.message}>
        <Controller
          control={form.control}
          name="channel_type"
          render={({ field }) => (
            <Dropdown
              value={CHANNEL_TYPE_META[field.value as ChannelType]?.label ?? ""}
              selectedOptions={[field.value]}
              onOptionSelect={(_, data) =>
                data.optionValue && field.onChange(data.optionValue as ChannelType)
              }
            >
              {CHANNEL_TYPES.map((c) => (
                <Option key={c} value={c}>
                  {CHANNEL_TYPE_META[c].label}
                </Option>
              ))}
            </Dropdown>
          )}
        />
      </FormField>

      <FormField label="Valor" required error={form.formState.errors.identifier?.message}>
        <Controller
          control={form.control}
          name="identifier"
          render={({ field }) => (
            <Input {...field} value={field.value ?? ""} placeholder="ej. +51999111222" />
          )}
        />
      </FormField>

      <div className={styles.checks}>
        <Controller
          control={form.control}
          name="is_primary"
          render={({ field }) => (
            <Checkbox
              label="Principal de su canal"
              checked={field.value ?? false}
              onChange={(_, d) => field.onChange(!!d.checked)}
            />
          )}
        />
        <Controller
          control={form.control}
          name="verified"
          render={({ field }) => (
            <Checkbox
              label="Verificado"
              checked={field.value ?? false}
              onChange={(_, d) => field.onChange(!!d.checked)}
            />
          )}
        />
      </div>
    </Drawer>
  );
}
