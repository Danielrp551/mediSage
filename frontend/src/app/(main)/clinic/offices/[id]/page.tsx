import { notFound } from "next/navigation";

import { getOffice } from "@/actions/office.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { HttpError } from "@/types/api.types";

import { OfficeDetailShell } from "./_components/OfficeDetailShell";

interface PageProps {
  params: Promise<{ id: string }>;
  // Tab routing lives in a query param, NOT a sub-route: ?tab=hours|closures|audit.
  // One URL, deep-linkable, no nested layout.tsx needed.
  searchParams: Promise<{ tab?: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const res = await getOffice(id);
    return { title: `${res.data.name} · Consultorio` };
  } catch {
    return { title: "Consultorio" };
  }
}

export default async function OfficeDetailPage({ params, searchParams }: PageProps) {
  await requirePermission("OFFICES_READ");
  const { id } = await params;
  const { tab } = await searchParams;

  let office;
  try {
    office = await getOffice(id);
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) notFound();
    throw e; // let error.tsx handle anything else
  }

  // The verticals list feeds the Details tab's multi-select (reused from catalog).
  const verticals = await listActiveVerticals();

  return (
    <OfficeDetailShell
      office={office.data}
      verticals={verticals}
      initialTab={tab === "hours" || tab === "closures" || tab === "audit" ? tab : "details"}
    />
  );
}
