import { getMyDoctor } from "@/actions/me.actions";
import { requirePermission } from "@/lib/auth/session";

import { NotADoctorNotice } from "../_components/NotADoctorNotice";
import { MyProfileClient } from "./_components/MyProfileClient";

export const metadata = { title: "Mi perfil" };

export default async function MyProfilePage() {
  await requirePermission("MY_DOCTOR_PROFILE_READ");

  let me;
  try {
    me = await getMyDoctor();
  } catch {
    // 403 NOT_A_DOCTOR (u otro error de resolución) → estado vacío de negocio, no
    // un 404 ni el error boundary. Un admin sin perfil de doctor cae aquí.
    return <NotADoctorNotice title="No tienes un perfil de doctor" />;
  }

  return <MyProfileClient doctor={me.data} />;
}
