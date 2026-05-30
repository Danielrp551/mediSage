import { notFound } from "next/navigation";

import { listActiveBranches } from "@/actions/branch.actions";
import { getDoctor } from "@/actions/doctor.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { HttpError } from "@/types/api.types";

import { DoctorDetailShell } from "./_components/DoctorDetailShell";

interface PageProps {
  params: Promise<{ id: string }>;
  // Tab routing en query param, NO sub-ruta: ?tab=availability|audit. Una URL,
  // deep-linkable, sin layout.tsx anidado.
  searchParams: Promise<{ tab?: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const res = await getDoctor(id);
    return { title: `${res.data.full_name} · Doctor` };
  } catch {
    return { title: "Doctor" };
  }
}

export default async function DoctorDetailPage({ params, searchParams }: PageProps) {
  await requirePermission("DOCTORS_READ");
  const { id } = await params;
  const { tab } = await searchParams;

  let doctor;
  try {
    doctor = await getDoctor(id);
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) notFound(); // 404 DOCTOR_NOT_FOUND
    throw e; // que error.tsx maneje el resto
  }

  // Sedes y verticales activas pueblan los multiselect del tab Perfil (editar M:N).
  const [branches, verticals] = await Promise.all([listActiveBranches(), listActiveVerticals()]);

  return (
    <DoctorDetailShell
      doctor={doctor.data}
      branches={branches}
      verticals={verticals}
      initialTab={tab === "availability" || tab === "audit" ? tab : "profile"}
    />
  );
}
