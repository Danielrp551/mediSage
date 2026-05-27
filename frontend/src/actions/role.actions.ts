"use server";

import { revalidateTag } from "next/cache";

import { backendClient } from "@/services/backend.client";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import { roleCreateSchema, roleUpdateSchema } from "@/lib/schemas/role.schema";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { QueryRequest } from "@/types/query.types";
import type { RoleDetail, RoleItem, RoleOption } from "@/types/role.types";
import type { MutationResult } from "./user.actions";

const ROLES_TAG = "admin:roles";

export async function listRoles(query: QueryRequest): Promise<ApiPaginated<RoleItem>> {
  return backendClient.post<ApiPaginated<RoleItem>>(ENDPOINTS.ROLES.LIST, query, {
    tags: [ROLES_TAG],
  });
}

export async function listActiveRoles(): Promise<RoleOption[]> {
  return backendClient.get<RoleOption[]>(ENDPOINTS.ROLES.ACTIVE, { tags: [ROLES_TAG] });
}

export async function getRole(id: string): Promise<ApiSingle<RoleDetail>> {
  return backendClient.get<ApiSingle<RoleDetail>>(ENDPOINTS.ROLES.GET(id), { tags: [ROLES_TAG] });
}

export async function createRole(input: unknown): Promise<MutationResult<ApiSingle<RoleDetail>>> {
  const parsed = roleCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<RoleDetail>>(ENDPOINTS.ROLES.CREATE, parsed.data);
    revalidateTag(ROLES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}

export async function updateRole(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<RoleDetail>>> {
  const parsed = roleUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<RoleDetail>>(
      ENDPOINTS.ROLES.UPDATE(id),
      parsed.data,
    );
    revalidateTag(ROLES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}
