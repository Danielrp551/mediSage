"use client";

import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Badge,
  Button,
  Checkbox,
  Divider,
  Dropdown,
  Input,
  MessageBar,
  MessageBarBody,
  Option,
  Tab,
  TabList,
  makeStyles,
  tokens,
  type SelectTabData,
  type SelectTabEvent,
} from "@fluentui/react-components";
import { SearchRegular } from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createUser, getUser, updateUser } from "@/actions/user.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import {
  DOCUMENT_RULES,
  DOCUMENT_TYPES,
  type DocumentType,
  userCreateSchema,
  type UserCreateInput,
} from "@/lib/schemas/user.schema";
import { formatDate } from "@/lib/utils/date";
import type { PermissionOption } from "@/types/permission.types";
import type { RoleOption } from "@/types/role.types";
import type { UserDetail } from "@/types/user.types";

const useStyles = makeStyles({
  twoCol: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: tokens.spacingHorizontalM,
  },
  searchRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    marginBottom: tokens.spacingVerticalS,
  },
  searchInput: { flex: 1 },
  optionList: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
    maxHeight: "320px",
    overflowY: "auto",
    paddingRight: tokens.spacingHorizontalXS,
  },
  optionRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusMedium,
    cursor: "pointer",
    "&:hover": { backgroundColor: appTokens.chromeBgHover },
  },
  optionRowDisabled: { cursor: "default", opacity: 0.6, "&:hover": { backgroundColor: "transparent" } },
  optionBody: {
    display: "flex",
    flexDirection: "column",
    gap: "2px",
    flex: 1,
    minWidth: 0,
  },
  optionTitle: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeText,
    fontWeight: tokens.fontWeightSemibold,
  },
  optionSubtle: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
  },
  emptyState: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    padding: tokens.spacingVerticalM,
    textAlign: "center",
  },
  selectedCount: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    fontWeight: tokens.fontWeightRegular,
    marginLeft: tokens.spacingHorizontalS,
  },
  audit: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: `${tokens.spacingVerticalS} ${tokens.spacingHorizontalL}`,
    fontSize: tokens.fontSizeBase200,
  },
  auditLabel: { color: appTokens.chromeTextMuted, fontSize: tokens.fontSizeBase200 },
  auditValue: { color: appTokens.chromeText, fontWeight: tokens.fontWeightMedium },
  tabPanel: {
    paddingTop: tokens.spacingVerticalL,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
});

interface Props {
  mode: "create" | "edit" | "view";
  userId: string | null;
  roles: RoleOption[];
  permissions: PermissionOption[];
  onClose: () => void;
}

type TabId = "details" | "access" | "audit";

export function UserDrawer({ mode, userId, roles, permissions, onClose }: Props) {
  const styles = useStyles();
  const [user, setUser] = useState<UserDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [generatedPassword, setGeneratedPassword] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [tab, setTab] = useState<TabId>("details");

  const readOnly = mode === "view";
  const hasAudit = mode !== "create";

  const form = useForm<UserCreateInput>({
    resolver: zodResolver(userCreateSchema),
    defaultValues: {
      email: "",
      first_name: "",
      last_name: "",
      role_ids: [],
      permission_ids: [],
    },
  });

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    void getUser(userId).then((res) => {
      if (cancelled) return;
      setUser(res.data);
      // `UserDetail.document_type` is `string | null` in the wire type (backend
      // doesn't constrain it). Narrow to our DocumentType enum at the boundary
      // — anything outside the enum becomes undefined.
      const rawDocType = res.data.document_type;
      const docType =
        rawDocType && (DOCUMENT_TYPES as readonly string[]).includes(rawDocType)
          ? (rawDocType as DocumentType)
          : undefined;
      form.reset({
        email: res.data.email,
        first_name: res.data.first_name,
        last_name: res.data.last_name,
        second_last_name: res.data.second_last_name ?? undefined,
        document_type: docType,
        document_number: res.data.document_number ?? undefined,
        phone: res.data.phone ?? undefined,
        role_ids: res.data.roles.map((r) => r.id),
        permission_ids: res.data.permissions.map((p) => p.id),
      });
    });
    return () => {
      cancelled = true;
    };
  }, [userId, form]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    setGeneratedPassword(null);
    startTransition(async () => {
      const action = userId ? updateUser(userId, values) : createUser(values);
      const result = await action;
      if (!result.ok) {
        setServerError(result.error ?? "Falló la validación");
        return;
      }
      if (mode === "create" && result.data && "generated_password" in result.data) {
        const pwd = (result.data as { generated_password: string | null }).generated_password;
        if (pwd) {
          setGeneratedPassword(pwd);
          return;
        }
      }
      onClose();
    });
  });

  return (
    <Drawer
      open
      onClose={onClose}
      title={
        mode === "create"
          ? "Nuevo usuario"
          : mode === "edit"
            ? "Editar usuario"
            : "Detalle de usuario"
      }
      subtitle={user?.email ?? form.watch("email") ?? undefined}
      size="medium"
      footer={
        readOnly ? (
          <Button onClick={onClose}>Cerrar</Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button
              appearance="primary"
              disabled={pending}
              onClick={() => void onSubmit()}
            >
              {pending
                ? "Guardando…"
                : mode === "create"
                  ? "Crear usuario"
                  : "Guardar cambios"}
            </Button>
          </>
        )
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      {generatedPassword ? (
        <MessageBar intent="info">
          <MessageBarBody>
            Usuario creado. Contraseña temporal (cópiala ahora — no se mostrará otra vez):{" "}
            <code>{generatedPassword}</code>
          </MessageBarBody>
        </MessageBar>
      ) : null}

      <TabList
        selectedValue={tab}
        onTabSelect={(_e: SelectTabEvent, d: SelectTabData) => setTab(d.value as TabId)}
      >
        <Tab value="details">Detalles</Tab>
        <Tab value="access">
          Acceso
          <span className={styles.selectedCount}>
            {form.watch("role_ids").length} rol(es) · {form.watch("permission_ids").length} permiso(s)
          </span>
        </Tab>
        {hasAudit ? <Tab value="audit">Auditoría</Tab> : null}
      </TabList>

      {tab === "details" ? (
        <DetailsTab form={form} readOnly={readOnly} styles={styles} />
      ) : tab === "access" ? (
        <AccessTab
          form={form}
          readOnly={readOnly}
          roles={roles}
          permissions={permissions}
          styles={styles}
        />
      ) : (
        <AuditTab user={user} styles={styles} />
      )}
    </Drawer>
  );
}

// ─────────────────────────────────────────────────
// Sub-tabs
// ─────────────────────────────────────────────────

type FormType = ReturnType<typeof useForm<UserCreateInput>>;
type Styles = ReturnType<typeof useStyles>;

function DetailsTab({
  form,
  readOnly,
  styles,
}: {
  form: FormType;
  readOnly: boolean;
  styles: Styles;
}) {
  // Watching the type lets us drive both the hint text and the per-type
  // validation feedback as soon as the user changes the dropdown.
  const documentType = form.watch("document_type") as DocumentType | null | undefined;
  const docRule = documentType ? DOCUMENT_RULES[documentType] : null;
  const docError = form.formState.errors.document_number?.message;

  return (
    <div className={styles.tabPanel}>
      <FormField label="Correo" required error={form.formState.errors.email?.message}>
        <Controller
          control={form.control}
          name="email"
          render={({ field }) => (
            <Input {...field} type="email" disabled={readOnly} placeholder="tu@ejemplo.com" />
          )}
        />
      </FormField>

      <div className={styles.twoCol}>
        <FormField label="Nombres" required error={form.formState.errors.first_name?.message}>
          <Controller
            control={form.control}
            name="first_name"
            render={({ field }) => <Input {...field} disabled={readOnly} />}
          />
        </FormField>
        <FormField label="Apellido paterno" required error={form.formState.errors.last_name?.message}>
          <Controller
            control={form.control}
            name="last_name"
            render={({ field }) => <Input {...field} disabled={readOnly} />}
          />
        </FormField>
      </div>

      <FormField label="Apellido materno">
        <Controller
          control={form.control}
          name="second_last_name"
          render={({ field }) => (
            <Input {...field} value={field.value ?? ""} disabled={readOnly} />
          )}
        />
      </FormField>

      <div className={styles.twoCol}>
        <FormField label="Tipo de documento">
          <Controller
            control={form.control}
            name="document_type"
            render={({ field }) => (
              <Dropdown
                value={field.value ?? ""}
                selectedOptions={field.value ? [field.value] : []}
                disabled={readOnly}
                placeholder="Seleccionar…"
                onOptionSelect={(_, data) => {
                  const next = data.optionValue ? data.optionValue : null;
                  field.onChange(next);
                  // Re-validate the number against the new type's rules so
                  // the error message stays in sync without needing a submit.
                  void form.trigger("document_number");
                }}
              >
                <Option value="">— Ninguno —</Option>
                {DOCUMENT_TYPES.map((t) => (
                  <Option key={t} value={t}>
                    {t}
                  </Option>
                ))}
              </Dropdown>
            )}
          />
        </FormField>
        <FormField
          label="Número de documento"
          hint={docRule?.hint}
          error={docError}
        >
          <Controller
            control={form.control}
            name="document_number"
            render={({ field }) => (
              <Input
                {...field}
                value={field.value ?? ""}
                disabled={readOnly}
                onBlur={() => {
                  field.onBlur();
                  // Validate on blur so the user gets feedback before submit.
                  void form.trigger("document_number");
                }}
              />
            )}
          />
        </FormField>
      </div>

      <FormField label="Teléfono">
        <Controller
          control={form.control}
          name="phone"
          render={({ field }) => (
            <Input {...field} value={field.value ?? ""} disabled={readOnly} placeholder="+51 …" />
          )}
        />
      </FormField>
    </div>
  );
}

function AccessTab({
  form,
  readOnly,
  roles,
  permissions,
  styles,
}: {
  form: FormType;
  readOnly: boolean;
  roles: RoleOption[];
  permissions: PermissionOption[];
  styles: Styles;
}) {
  return (
    <div className={styles.tabPanel}>
      <Accordion collapsible multiple defaultOpenItems={["roles", "perms"]}>
        <AccordionItem value="roles">
          <AccordionHeader>
            Roles
            <span className={styles.selectedCount}>
              {form.watch("role_ids").length} de {roles.length} seleccionados
            </span>
          </AccordionHeader>
          <AccordionPanel>
            <Controller
              control={form.control}
              name="role_ids"
              render={({ field }) => (
                <SearchableOptionList
                  styles={styles}
                  options={roles.map((r) => ({ id: r.id, primary: r.name }))}
                  selected={field.value}
                  disabled={readOnly}
                  onToggle={(id) => {
                    const next = field.value.includes(id)
                      ? field.value.filter((x) => x !== id)
                      : [...field.value, id];
                    field.onChange(next);
                  }}
                  searchPlaceholder="Buscar roles…"
                  emptyMessage="Ningún rol coincide con la búsqueda."
                />
              )}
            />
          </AccordionPanel>
        </AccordionItem>

        <AccordionItem value="perms">
          <AccordionHeader>
            Permisos directos
            <span className={styles.selectedCount}>
              {form.watch("permission_ids").length} de {permissions.length} seleccionados
            </span>
          </AccordionHeader>
          <AccordionPanel>
            <Controller
              control={form.control}
              name="permission_ids"
              render={({ field }) => (
                <SearchableOptionList
                  styles={styles}
                  options={permissions.map((p) => ({
                    id: p.id,
                    primary: p.code,
                    secondary: `${p.name} · ${p.module}`,
                  }))}
                  selected={field.value}
                  disabled={readOnly}
                  onToggle={(id) => {
                    const next = field.value.includes(id)
                      ? field.value.filter((x) => x !== id)
                      : [...field.value, id];
                    field.onChange(next);
                  }}
                  searchPlaceholder="Buscar por código, nombre o módulo…"
                  emptyMessage="Ningún permiso coincide con la búsqueda."
                />
              )}
            />
          </AccordionPanel>
        </AccordionItem>
      </Accordion>
    </div>
  );
}

function AuditTab({ user, styles }: { user: UserDetail | null; styles: Styles }) {
  if (!user) {
    return (
      <div className={styles.tabPanel}>
        <p className={styles.emptyState}>Cargando…</p>
      </div>
    );
  }
  return (
    <div className={styles.tabPanel}>
      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Estado</div>
          <div className={styles.auditValue}>
            <Badge appearance="filled" color={user.active ? "success" : "informative"}>
              {user.active ? "Activo" : "Deshabilitado"}
            </Badge>
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>ID del usuario</div>
          <div className={styles.auditValue}>
            <code>{user.id}</code>
          </div>
        </div>
      </div>

      <Divider />

      <div className={styles.audit}>
        <div>
          <div className={styles.auditLabel}>Creado el</div>
          <div className={styles.auditValue}>{formatDate(user.created_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Creado por</div>
          <div className={styles.auditValue}>
            {user.created_by_user?.full_name ?? "—"}
          </div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado el</div>
          <div className={styles.auditValue}>{formatDate(user.updated_on)}</div>
        </div>
        <div>
          <div className={styles.auditLabel}>Actualizado por</div>
          <div className={styles.auditValue}>
            {user.updated_by_user?.full_name ?? "—"}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────
// Searchable selectable list — generic helper
// ─────────────────────────────────────────────────

interface OptionItem {
  id: string;
  primary: string;
  secondary?: string;
}

function SearchableOptionList({
  styles,
  options,
  selected,
  disabled,
  onToggle,
  searchPlaceholder,
  emptyMessage,
}: {
  styles: Styles;
  options: OptionItem[];
  selected: string[];
  disabled: boolean;
  onToggle: (id: string) => void;
  searchPlaceholder: string;
  emptyMessage: string;
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) =>
        o.primary.toLowerCase().includes(q) ||
        (o.secondary && o.secondary.toLowerCase().includes(q)),
    );
  }, [options, query]);

  return (
    <>
      <div className={styles.searchRow}>
        <Input
          className={styles.searchInput}
          value={query}
          onChange={(_, d) => setQuery(d.value)}
          placeholder={searchPlaceholder}
          contentBefore={<SearchRegular />}
          size="small"
        />
      </div>
      <div className={styles.optionList}>
        {filtered.length === 0 ? (
          <div className={styles.emptyState}>{emptyMessage}</div>
        ) : (
          filtered.map((opt) => {
            const checked = selected.includes(opt.id);
            return (
              <label
                key={opt.id}
                className={`${styles.optionRow} ${disabled ? styles.optionRowDisabled : ""}`}
              >
                <Checkbox
                  checked={checked}
                  disabled={disabled}
                  onChange={() => onToggle(opt.id)}
                />
                <div className={styles.optionBody}>
                  <span className={styles.optionTitle}>{opt.primary}</span>
                  {opt.secondary ? (
                    <span className={styles.optionSubtle}>{opt.secondary}</span>
                  ) : null}
                </div>
              </label>
            );
          })
        )}
      </div>
    </>
  );
}
