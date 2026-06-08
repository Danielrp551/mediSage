import { getMyDoctor } from "@/actions/me.actions";
import { requirePermission } from "@/lib/auth/session";

import { NotADoctorNotice } from "../../staff/me/_components/NotADoctorNotice";
import { MyAgendaClient } from "./_components/MyAgendaClient";

export const metadata = { title: "Mi agenda" };

export default async function MyAgendaPage() {
  await requirePermission("MY_APPOINTMENTS_READ");

  // Si el usuario logueado no tiene perfil de doctor el backend responde 403
  // NOT_A_DOCTOR (caso de negocio, no crash) → estado vacío. Reusa el mismo
  // NotADoctorNotice del self-service de staff.
  try {
    await getMyDoctor();
  } catch {
    return <NotADoctorNotice title="No tienes un perfil de doctor" />;
  }

  return <MyAgendaClient />;
}
