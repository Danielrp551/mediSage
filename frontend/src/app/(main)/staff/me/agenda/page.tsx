import { getMyDoctor } from "@/actions/me.actions";
import { requirePermission } from "@/lib/auth/session";

import { NotADoctorNotice } from "../_components/NotADoctorNotice";
import { MyAvailabilityClient } from "./_components/MyAvailabilityClient";

export const metadata = { title: "Mi agenda" };

export default async function MyAgendaPage() {
  await requirePermission("MY_AVAILABILITY_READ");

  // Se trae el perfil para (a) detectar NOT_A_DOCTOR y (b) poblar el selector de
  // sede del drawer con SOLO las sedes del propio doctor. Los endpoints /me/
  // availability no llevan doctorId (sale del token).
  let me;
  try {
    me = await getMyDoctor();
  } catch {
    return <NotADoctorNotice title="No tienes un perfil de doctor" />;
  }

  return <MyAvailabilityClient doctorBranches={me.data.branches} />;
}
