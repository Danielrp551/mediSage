import { notFound } from "next/navigation";

import { getPerson } from "@/actions/person.actions";
import { requirePermission } from "@/lib/auth/session";
import { HttpError } from "@/types/api.types";

import { PersonDetailShell } from "./_components/PersonDetailShell";

type TabId = "summary" | "identifiers" | "lead" | "customer" | "activity" | "audit";
const ALLOWED_TABS: Record<TabId, true> = {
  summary: true,
  identifiers: true,
  lead: true,
  customer: true,
  activity: true,
  audit: true,
};

interface PageProps {
  params: Promise<{ id: string }>;
  // Tab routing en query param, NO sub-ruta: ?tab=lead|activity|… Una URL, deep-linkable.
  searchParams: Promise<{ tab?: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const res = await getPerson(id);
    return { title: `${res.data.full_name} · Contacto` };
  } catch {
    return { title: "Contacto" };
  }
}

export default async function PersonDetailPage({ params, searchParams }: PageProps) {
  await requirePermission("PERSONS_READ");
  const { id } = await params;
  const { tab } = await searchParams;

  let person;
  try {
    person = await getPerson(id);
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) notFound(); // 404 PERSON_NOT_FOUND
    throw e; // que error.tsx maneje el resto
  }

  const initialTab: TabId = tab && tab in ALLOWED_TABS ? (tab as TabId) : "summary";

  // F1: los catálogos activos (lead/customer statuses) que alimentarán el
  // TransitionControl de los tabs Lead/Cliente se prefetchearán en F2/F3, cuando
  // existan sus endpoints. En F1 esos tabs son placeholders.
  return <PersonDetailShell person={person.data} initialTab={initialTab} />;
}
