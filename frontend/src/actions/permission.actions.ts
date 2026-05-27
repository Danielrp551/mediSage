"use server";

import { revalidateTag } from "next/cache";

import { backendClient } from "@/services/backend.client";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  permissionCreateSchema,
  permissionUpdateSchema,
} from "@/lib/schemas/permission.schema";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { QueryRequest } from "@/types/query.types";
import type {
  PermissionItem,
  PermissionOption,
} from "@/types/permission.types";
import type { MutationResult } from "./user.actions";

const PERMS_TAG = "admin:permissions";

export async function listPermissions(query: QueryRequest): Promise<ApiPaginated<PermissionItem>> {
  return backendClient.post<ApiPaginated<PermissionItem>>(ENDPOINTS.PERMISSIONS.LIST, query, {
    tags: [PERMS_TAG],
  });
}

export async function listActivePermissions(): Promise<PermissionOption[]> {
  return backendClient.get<PermissionOption[]>(ENDPOINTS.PERMISSIONS.ACTIVE, { tags: [PERMS_TAG] });
}

export async function createPermission(
  input: unknown,
): Promise<MutationResult<ApiSingle<PermissionItem>>> {
  const parsed = permissionCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<PermissionItem>>(
      ENDPOINTS.PERMISSIONS.CREATE,
      parsed.data,
    );
    revalidateTag(PERMS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}

export async function updatePermission(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PermissionItem>>> {
  const parsed = permissionUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<PermissionItem>>(
      ENDPOINTS.PERMISSIONS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(PERMS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}
