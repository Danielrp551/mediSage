"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { branchCreateSchema, branchUpdateSchema } from "@/lib/schemas/branch.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { BranchDetail, BranchItem, BranchOption } from "@/types/clinic.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const BRANCHES_TAG = "clinic:branches";
// OfficeItem denormalizes the branch's `name` (OfficeItem.branch_name) and the
// office detail eager-loads branch (BranchOption). A branch rename must
// invalidate the offices cache too (phase 2 onward; the tag is a no-op today).
const OFFICES_TAG = "clinic:offices";

export async function listBranches(query: QueryRequest): Promise<ApiPaginated<BranchItem>> {
  return backendClient.post<ApiPaginated<BranchItem>>(ENDPOINTS.BRANCHES.LIST, query, {
    tags: [BRANCHES_TAG],
  });
}

export async function listActiveBranches(): Promise<BranchOption[]> {
  // `/active` returns a RAW list (response_model=list[...]), not a
  // `{success, data}` envelope — read the array directly, no `.data`.
  return backendClient.get<BranchOption[]>(ENDPOINTS.BRANCHES.ACTIVE, { tags: [BRANCHES_TAG] });
}

export async function getBranch(id: string): Promise<ApiSingle<BranchDetail>> {
  return backendClient.get<ApiSingle<BranchDetail>>(ENDPOINTS.BRANCHES.GET(id), {
    tags: [BRANCHES_TAG],
  });
}

export async function createBranch(
  input: unknown,
): Promise<MutationResult<ApiSingle<BranchDetail>>> {
  const parsed = branchCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<BranchDetail>>(
      ENDPOINTS.BRANCHES.CREATE,
      parsed.data,
    );
    revalidateTag(BRANCHES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateBranch(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BranchDetail>>> {
  const parsed = branchUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<BranchDetail>>(
      ENDPOINTS.BRANCHES.UPDATE(id),
      parsed.data,
    );
    revalidateTag(BRANCHES_TAG, "max");
    // Cross-tag: a renamed branch makes the denormalized `branch_name` in
    // cached offices stale.
    if ("name" in parsed.data) {
      revalidateTag(OFFICES_TAG, "max");
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteBranch(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.BRANCHES.DELETE(id));
    revalidateTag(BRANCHES_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 BRANCH_HAS_ACTIVE_CHILDREN surfaces here as e.message; the
    // ConfirmDialog shows it without closing (same pattern as catalog).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
