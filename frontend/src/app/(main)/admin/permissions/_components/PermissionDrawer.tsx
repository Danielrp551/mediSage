"use client";

import { Button, Input, MessageBar, MessageBarBody, Switch, Textarea } from "@fluentui/react-components";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState, useTransition } from "react";
import { Controller, useForm } from "react-hook-form";

import { createPermission, updatePermission } from "@/actions/permission.actions";
import { Drawer } from "@/components/ui/Drawer/Drawer";
import { FormField } from "@/components/ui/Form/FormField";
import {
  permissionCreateSchema,
  type PermissionCreateInput,
} from "@/lib/schemas/permission.schema";
import type { PermissionItem } from "@/types/permission.types";

interface Props {
  mode: "create" | "edit";
  permission: PermissionItem | null;
  onClose: () => void;
}

export function PermissionDrawer({ mode, permission, onClose }: Props) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const form = useForm<PermissionCreateInput & { active?: boolean }>({
    resolver: zodResolver(permissionCreateSchema),
    defaultValues: {
      code: permission?.code ?? "",
      name: permission?.name ?? "",
      description: permission?.description ?? "",
      module: permission?.module ?? "",
      active: permission?.active ?? true,
    },
  });

  const onSubmit = form.handleSubmit((values) => {
    setServerError(null);
    startTransition(async () => {
      const result = permission
        ? await updatePermission(permission.id, values)
        : await createPermission(values);
      if (!result.ok) {
        setServerError(result.error ?? "Validation failed");
        return;
      }
      onClose();
    });
  });

  return (
    <Drawer
      open
      onClose={onClose}
      title={mode === "create" ? "New permission" : "Edit permission"}
      footer={
        <>
          <Button appearance="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button appearance="primary" disabled={pending} onClick={() => void onSubmit()}>
            {pending ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      {serverError ? (
        <MessageBar intent="error">
          <MessageBarBody>{serverError}</MessageBarBody>
        </MessageBar>
      ) : null}

      <FormField label="Code" required error={form.formState.errors.code?.message} hint="Uppercase / digits / `_` / `-`">
        <Controller
          control={form.control}
          name="code"
          render={({ field }) => <Input {...field} disabled={mode === "edit"} />}
        />
      </FormField>

      <FormField label="Module" required error={form.formState.errors.module?.message}>
        <Controller
          control={form.control}
          name="module"
          render={({ field }) => <Input {...field} />}
        />
      </FormField>

      <FormField label="Name" required error={form.formState.errors.name?.message}>
        <Controller
          control={form.control}
          name="name"
          render={({ field }) => <Input {...field} />}
        />
      </FormField>

      <FormField label="Description">
        <Controller
          control={form.control}
          name="description"
          render={({ field }) => <Textarea {...field} rows={3} />}
        />
      </FormField>

      {mode === "edit" ? (
        <FormField label="Active">
          <Controller
            control={form.control}
            name="active"
            render={({ field }) => (
              <Switch checked={field.value ?? true} onChange={(_, d) => field.onChange(d.checked)} />
            )}
          />
        </FormField>
      ) : null}
    </Drawer>
  );
}
