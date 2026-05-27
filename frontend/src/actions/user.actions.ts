"use server";

import { revalidateTag } from "next/cache";

import { backendClient } from "@/services/backend.client";
import { ENDPOINTS } from "@/lib/constants/endpoints";
import { userCreateSchema, userUpdateSchema } from "@/lib/schemas/user.schema";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { QueryRequest } from "@/types/query.types";
import type {
  UserCreatedResponse,
  UserDetail,
  UserItem,
} from "@/types/user.types";

const USERS_TAG = "admin:users";

export async function listUsers(query: QueryRequest): Promise<ApiPaginated<UserItem>> {
  return backendClient.post<ApiPaginated<UserItem>>(ENDPOINTS.USERS.LIST, query, {
    tags: [USERS_TAG],
  });
}

export async function getUser(id: string): Promise<ApiSingle<UserDetail>> {
  return backendClient.get<ApiSingle<UserDetail>>(ENDPOINTS.USERS.GET(id), { tags: [USERS_TAG] });
}

export interface MutationResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  fieldErrors?: Record<string, string[]>;
}

export async function createUser(input: unknown): Promise<MutationResult<UserCreatedResponse>> {
  const parsed = userCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<UserCreatedResponse>(ENDPOINTS.USERS.CREATE, parsed.data);
    revalidateTag(USERS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}

export async function updateUser(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<UserDetail>>> {
  const parsed = userUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<UserDetail>>(
      ENDPOINTS.USERS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(USERS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}
