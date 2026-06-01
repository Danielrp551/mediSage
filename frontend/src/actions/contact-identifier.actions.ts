"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  contactIdentifierCreateSchema,
  contactIdentifierUpdateSchema,
} from "@/lib/schemas/contact-identifier.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { PersonContactIdentifierItem } from "@/types/crm.types";

import type { MutationResult } from "./user.actions";

const PERSONS_TAG = "crm:persons";
const identifiersTag = (personId: string) => `crm:identifiers:${personId}`;

export async function listIdentifiers(personId: string): Promise<PersonContactIdentifierItem[]> {
  // GET devuelve SingleResponse[list[Item]] → se lee `.data` (NO es /active).
  const res = await backendClient.get<ApiSingle<PersonContactIdentifierItem[]>>(
    ENDPOINTS.PERSONS.IDENTIFIERS(personId),
    { tags: [identifiersTag(personId)] },
  );
  return res.data;
}

export async function addIdentifier(
  personId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonContactIdentifierItem>>> {
  const parsed = contactIdentifierCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PersonContactIdentifierItem>>(
      ENDPOINTS.PERSONS.IDENTIFIERS(personId),
      parsed.data,
    );
    revalidateTag(identifiersTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max"); // primary_identifier denormalizado en el listado
    return { ok: true, data };
  } catch (e) {
    // 409 IDENTIFIER_TAKEN en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateIdentifier(
  personId: string,
  identId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PersonContactIdentifierItem>>> {
  const parsed = contactIdentifierUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<PersonContactIdentifierItem>>(
      ENDPOINTS.PERSONS.IDENTIFIER(personId, identId), // ← PUT
      parsed.data,
    );
    revalidateTag(identifiersTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function removeIdentifier(
  personId: string,
  identId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PERSONS.IDENTIFIER(personId, identId)); // soft delete
    revalidateTag(identifiersTag(personId), "max");
    revalidateTag(PERSONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 404 IDENTIFIER_NOT_FOUND si el identifier no existe o no es de la persona.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
