"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { personCreateSchema, personUpdateSchema } from "@/lib/schemas/person.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { PersonDetail, PersonItem, PersonOption } from "@/types/crm.types";
import type { QueryRequest } from "@/types/query.types";

import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";

export async function listPersons(query: QueryRequest): Promise<ApiPaginated<PersonItem>> {
  return backendClient.post<ApiPaginated<PersonItem>>(ENDPOINTS.PERSONS.LIST, query, {
    tags: [PERSONS_TAG],
  });
}

export async function listActivePersons(): Promise<PersonOption[]> {
  // `/active` devuelve lista CRUDA (sin envelope) — NO se lee `.data`.
  return backendClient.get<PersonOption[]>(ENDPOINTS.PERSONS.ACTIVE, { tags: [PERSONS_TAG] });
}

export async function searchPersons(
  q?: string,
  channelType?: string,
  identifier?: string,
): Promise<PersonOption[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (channelType) params.set("channel_type", channelType);
  if (identifier) params.set("identifier", identifier);
  const qs = params.toString();
  const url = qs ? `${ENDPOINTS.PERSONS.SEARCH}?${qs}` : ENDPOINTS.PERSONS.SEARCH;
  // `/search` devuelve lista CRUDA (sin envelope) — la usa el bot.
  return backendClient.get<PersonOption[]>(url, { tags: [PERSONS_TAG] });
}

export async function getPerson(id: string): Promise<ApiSingle<PersonDetail>> {
  // PersonDetail incluye identifiers + resúmenes de estado para el header.
  return backendClient.get<ApiSingle<PersonDetail>>(ENDPOINTS.PERSONS.GET(id), {
    tags: [PERSONS_TAG],
  });
}

export async function createPerson(
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonDetail>>> {
  const parsed = personCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<PersonDetail>>(
      ENDPOINTS.PERSONS.CREATE,
      parsed.data,
    );
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 IDENTIFIER_TAKEN (un identifier inicial ya existe) llega como
    // e.message en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updatePerson(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonDetail>>> {
  const parsed = personUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<PersonDetail>>(
      ENDPOINTS.PERSONS.UPDATE(id), // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deletePerson(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PERSONS.DELETE(id)); // soft delete
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
