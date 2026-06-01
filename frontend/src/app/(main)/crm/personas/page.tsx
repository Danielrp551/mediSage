import { listPersons } from "@/actions/person.actions";
import { requirePermission } from "@/lib/auth/session";

import { PersonsClient } from "./_components/PersonsClient";

export const metadata = { title: "Contactos" };

export default async function PersonsPage() {
  await requirePermission("PERSONS_READ");

  // F1: el listado sólo trae búsqueda client-side (+ toggle Activo). Los filtros
  // por estado lead/cliente y por asesor (deep-link `?lead_status_id=` /
  // `?customer_status_id=` / `?advisor_user_id=`) se DIFIEREN a F2/F3 — sus
  // catálogos (`/lead-statuses/active`, `/customer-statuses/active`,
  // `/advisors/active`) y endpoints no existen en backend hasta esas fases. Por
  // eso aquí no se prefetchea ningún catálogo ni se traducen searchParams.
  //
  // defaultSort = `created_on` desc (columna REAL de ALLOWED_FIELDS). DEBE
  // coincidir con el defaultSort del PersonsClient: ordenar por un denormalizado
  // (full_name, primary_identifier, lead_status…) devuelve 400 (lección cd10c78).
  const initialData = await listPersons({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "created_on", sort_order: "desc" },
    filters: null,
  });

  return <PersonsClient initialData={initialData} />;
}
