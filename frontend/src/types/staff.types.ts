/**
 * Espejo TS de los Pydantic schemas del módulo `staff` (ver
 * `docs/modules/staff/backend.md`). Importable desde server actions y client
 * components. Reusa `UserAuditInfo`, `VerticalOption` y `BranchOption` — no se
 * redefinen.
 *
 * Declarado en F0 (Prep). Las pantallas que los consumen llegan por fases:
 * Doctor (F1), DoctorAvailability + grilla (F2), self-service `/me` (F3).
 */

import type { UserAuditInfo } from "./audit.types";
import type { VerticalOption } from "./catalog.types";
import type { BranchOption } from "./clinic.types";

// ── Doctor ──────────────────────────────────────────────

// Fila de listado. El backend DENORMALIZA full_name/email del User (evita join
// en la tabla) y los counts del M:N (mismo patrón que OfficeItem.verticals_count).
export interface DoctorItem {
  id: string;
  user_id: string;
  full_name: string; // denormalizado del User
  email: string; // denormalizado del User
  cmp_code: string | null;
  slot_duration_min: number; // default 30
  active: boolean;
  branches_count: number; // denormalizado — # de sedes asignadas
  verticals_count: number; // denormalizado — # de verticales cubiertas
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// El detalle agrega bio/foto/firma + el user resuelto + las dos relaciones M:N
// expandidas. `user` viaja como UserAuditInfo (id/full_name/email basta para el
// header de solo-lectura del perfil).
export interface DoctorDetail extends DoctorItem {
  bio: string | null;
  photo_url: string | null;
  signature_url: string | null;
  user: UserAuditInfo;
  branches: BranchOption[]; // sedes vivas; soft-deleted filtradas server-side
  verticals: VerticalOption[]; // verticales vivas; soft-deleted filtradas server-side
}

// Para dropdowns (selección de un doctor en scheduling/crm a futuro).
export interface DoctorOption {
  id: string;
  full_name: string;
  cmp_code: string | null;
}

// Payload anidado del User al crear un doctor (espejo del UserCreate del admin,
// SIN role_ids/permission_ids — el service le asigna el role DOCTOR). Si falta
// `password`, el backend lo genera y lo devuelve en `generated_password`.
export interface DoctorUserCreatePayload {
  email: string;
  first_name: string;
  last_name: string;
  second_last_name?: string | null;
  document_type?: string | null;
  document_number?: string | null;
  phone?: string | null;
  password?: string;
}

export interface DoctorCreatePayload {
  user: DoctorUserCreatePayload; // NESTED — crea User + Doctor en una transacción
  cmp_code?: string | null;
  bio?: string | null;
  photo_url?: string | null;
  signature_url?: string | null;
  slot_duration_min?: number; // default 30
  branch_ids: string[]; // M:N doctor_branch al crear
  vertical_ids: string[]; // M:N doctor_vertical al crear
}

// La respuesta del POST /doctors espeja UserCreatedResponse: devuelve el detalle
// + la contraseña temporal SI se generó (null si el admin la escribió).
export interface DoctorCreatedResponse {
  success: true;
  data: DoctorDetail;
  generated_password: string | null;
}

// user_id es INMUTABLE post-create → NO está en el update. branch_ids/vertical_ids
// presentes = REEMPLAZO TOTAL del M:N (mismo contrato que office.vertical_ids).
export interface DoctorUpdatePayload {
  cmp_code?: string | null;
  bio?: string | null;
  photo_url?: string | null;
  signature_url?: string | null;
  slot_duration_min?: number;
  branch_ids?: string[]; // si presente, reemplaza doctor_branch entero
  vertical_ids?: string[]; // si presente, reemplaza doctor_vertical entero
  active?: boolean;
}

// ── DoctorAvailability (bloque concreto por fecha) ──────
// NO hay day_of_week, NO hay is_available, NO hay recurrencia. Un bloque = un
// rango horario en UNA fecha concreta, en (branch, office).

export interface DoctorAvailabilityItem {
  id: string;
  doctor_id: string;
  branch_id: string;
  branch_name: string; // denormalizado — render sin join
  office_id: string;
  office_code: string; // denormalizado
  office_name: string; // denormalizado
  date: string; // "YYYY-MM-DD" (Date sin TZ; se interpreta en branch.timezone)
  opens_at: string; // "HH:MM" local time (Time sin TZ) — NO pasa por new Date()
  closes_at: string; // "HH:MM"; backend CHECK closes_at > opens_at
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Un bloque a crear (sin doctor_id — viaja en la URL).
export interface DoctorAvailabilityCreatePayload {
  branch_id: string;
  office_id: string;
  date: string; // "YYYY-MM-DD"
  opens_at: string; // "HH:MM"
  closes_at: string; // "HH:MM"
}

// Alta masiva: el body del POST. "Llenar varios a la vez" (arrastrar el mismo
// horario sobre varios días, o el form de Agregar disponibilidad).
export interface DoctorAvailabilityBulkCreatePayload {
  blocks: DoctorAvailabilityCreatePayload[];
}

// Editar un bloque (mover/redimensionar). Todos los campos opcionales.
export interface DoctorAvailabilityUpdatePayload {
  branch_id?: string;
  office_id?: string;
  date?: string;
  opens_at?: string;
  closes_at?: string;
}
