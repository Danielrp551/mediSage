"use client";

import {
  Accordion,
  AccordionHeader,
  AccordionItem,
  AccordionPanel,
  Button,
  Checkbox,
  Input,
  MessageBar,
  MessageBarBody,
  Textarea,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { SearchRegular } from "@fluentui/react-icons";
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createRole, getRole, updateRole } from "@/actions/role.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import { appTokens } from "@/lib/theme/brand";
import { roleCreateSchema, type RoleCreateInput } from "@/lib/schemas/role.schema";
import type { PermissionOption } from "@/types/permission.types";
import type { RoleDetail } from "@/types/role.types";

const useStyles = makeStyles({
  searchRow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    marginBottom: tokens.spacingVerticalM,
  },
  searchInput: { flex: 1 },
  moduleHeader: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    width: "100%",
  },
  moduleName: { fontWeight: tokens.fontWeightSemibold, color: appTokens.chromeText },
  moduleCount: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    fontWeight: tokens.fontWeightRegular,
  },
  moduleActions: {
    marginLeft: "auto",
    display: "flex",
    gap: tokens.spacingHorizontalXS,
  },
  permList: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  permRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalXS} ${tokens.spacingHorizontalS}`,
    borderRadius: tokens.borderRadiusMedium,
    cursor: "pointer",
    "&:hover": { backgroundColor: appTokens.chromeBgHover },
  },
  permRowDisabled: { cursor: "default", "&:hover": { backgroundColor: "transparent" } },
  permBody: { display: "flex", flexDirection: "column", gap: "2px", flex: 1, minWidth: 0 },
  permCode: {
    fontFamily: tokens.fontFamilyMonospace,
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeText,
  },
  permName: { fontSize: tokens.fontSizeBase200, color: appTokens.chromeTextMuted },
  emptyState: {
    fontSize: tokens.fontSizeBase200,
    color: appTokens.chromeTextMuted,
    padding: tokens.spacingVerticalM,
    textAlign: "center",
  },
  summary: {
    fontSize: tokens.fontSizeBase300,
    color: appTokens.chromeTextMuted,
    paddingBottom: tokens.spacingVerticalM,
  },
});

interface Props {
  mode: "create" | "edit" | "view";
  roleId: string | null;
  permissions: PermissionOption[];
  onClose: () => void;
}

export function RoleDrawer({ mode, roleId, permissions, onClose }: Props) {
  const styles = useStyles();
  const [, setRole] = useState<RoleDetail | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const [query, setQuery] = useState("");
  const readOnly = mode === "view";

  const form = useForm<RoleCreateInput>({
    resolver: zodResolver(roleCreateSchema),
    defaultValues: { name: "", description: "", permission_ids: [] },
  });

  useEffect(() => {
    if (!roleId) return;
    let cancelled = false;
    void getRole(roleId).then((res) => {
      if (cancelled) return;
      setRole(res.data);
      form.reset({
        name: res.data.name,
        description: res.data.description,
        permission_ids: res.data.permissions.map((p) => p.id),
      });
    });
    return () => {
      cancelled = true;
    };
  }, [roleId, form]);

  // Group permissions by module + filter by search.
  const filteredGroups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = q
      ? permissions.filter(
          (p) =>
            p.code.toLowerCase().includes(q) ||
            p.name.toLowerCase().includes(q) ||
            p.module.toLowerCase().includes(q),
        )
      : permissions;
    return matches.reduce<Record<string, PermissionOption[]>>((acc, p) => {
      (acc[p.module] ??= []).push(p);
      return acc;
    }, {});
  }, [permissions, query]);

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = roleId ? await updateRole(roleId, values) : await createRole(values);
      if (!result.ok) {
        setServerError(result.error ?? "Validation failed");
        return;
      }
      onClose();
    });
  });

  const selectedIds = form.watch("permission_ids");

  return (
    <Drawer
      open
      onClose={onClose}
      title={mode === "create" ? "New role" : mode === "edit" ? "Edit role" : "Role detail"}
      size="medium"
      footer={
        readOnly ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button appearance="secondary" onClick={onClose} disabled={pending}>
              Cancel
            </Button>
            <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
              {pending ? "Saving…" : mode === "create" ? "Create role" : "Save changes"}
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

      <FormField label="Name" required error={form.formState.errors.name?.message}>
        <Controller
          control={form.control}
          name="name"
          render={({ field }) => (
            <Input {...field} disabled={readOnly} placeholder="e.g. EDITOR" />
          )}
        />
      </FormField>

      <FormField label="Description" required error={form.formState.errors.description?.message}>
        <Controller
          control={form.control}
          name="description"
          render={({ field }) => (
            <Textarea
              {...field}
              disabled={readOnly}
              rows={2}
              placeholder="What this role grants…"
            />
          )}
        />
      </FormField>

      <div>
        <div className={styles.summary}>
          Permissions: <strong>{selectedIds.length}</strong> of {permissions.length} selected
        </div>
        <div className={styles.searchRow}>
          <Input
            className={styles.searchInput}
            value={query}
            onChange={(_, d) => setQuery(d.value)}
            placeholder="Search by code, name or module…"
            contentBefore={<SearchRegular />}
            size="medium"
          />
        </div>

        <Controller
          control={form.control}
          name="permission_ids"
          render={({ field }) => {
            const moduleEntries = Object.entries(filteredGroups);
            if (moduleEntries.length === 0) {
              return <div className={styles.emptyState}>No permissions match your search.</div>;
            }
            return (
              <Accordion
                collapsible
                multiple
                defaultOpenItems={moduleEntries.map(([m]) => m)}
              >
                {moduleEntries.map(([module, items]) => {
                  const itemIds = items.map((p) => p.id);
                  const allSelected = itemIds.every((id) => field.value.includes(id));
                  const someSelected = itemIds.some((id) => field.value.includes(id));
                  return (
                    <AccordionItem key={module} value={module}>
                      <AccordionHeader>
                        <div className={styles.moduleHeader}>
                          <span className={styles.moduleName}>{module}</span>
                          <span className={styles.moduleCount}>
                            {itemIds.filter((id) => field.value.includes(id)).length}/{itemIds.length}
                          </span>
                          {!readOnly ? (
                            <div className={styles.moduleActions}>
                              <Button
                                size="small"
                                appearance="subtle"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const next = allSelected
                                    ? field.value.filter((id) => !itemIds.includes(id))
                                    : Array.from(new Set([...field.value, ...itemIds]));
                                  field.onChange(next);
                                }}
                              >
                                {allSelected ? "Clear" : someSelected ? "Select all" : "Select all"}
                              </Button>
                            </div>
                          ) : null}
                        </div>
                      </AccordionHeader>
                      <AccordionPanel>
                        <div className={styles.permList}>
                          {items.map((p) => {
                            const checked = field.value.includes(p.id);
                            return (
                              <label
                                key={p.id}
                                className={`${styles.permRow} ${
                                  readOnly ? styles.permRowDisabled : ""
                                }`}
                              >
                                <Checkbox
                                  checked={checked}
                                  disabled={readOnly}
                                  onChange={() => {
                                    const next = checked
                                      ? field.value.filter((id) => id !== p.id)
                                      : [...field.value, p.id];
                                    field.onChange(next);
                                  }}
                                />
                                <div className={styles.permBody}>
                                  <span className={styles.permCode}>{p.code}</span>
                                  <span className={styles.permName}>{p.name}</span>
                                </div>
                              </label>
                            );
                          })}
                        </div>
                      </AccordionPanel>
                    </AccordionItem>
                  );
                })}
              </Accordion>
            );
          }}
        />
      </div>
    </Drawer>
  );
}
