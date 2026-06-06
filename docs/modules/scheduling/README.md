# Módulo `scheduling`

> **Última actualización**: 2026-06-06
> **Propósito**: gestión de **citas** (`Appointment`) de la clínica y **cálculo on-the-fly de la disponibilidad** del calendario (sin tabla de slots). Cierra el loop de negocio **lead → conversación/bot → cita → cliente**: cuando una cita se atiende, la persona se promueve a cliente. Es el módulo #7, montado sobre `crm`, `staff`, `clinic` y `catalog`, y consumido por `bots`.
> **Path del código**: `backend/app/modules/scheduling/` (backend) · `frontend/src/app/(main)/scheduling/` (frontend).

> **Este documento es el overview**. Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts (request/response/errores), lógica de service, `compute_available_slots`, draft SQL de migraciones.
> - 🎨 [`ui.md`](ui.md) — mockups por pantalla (tabla, wizard de reserva, grilla de calendario, timeline), estados, componentes Fluent UI, UX writing en español.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación, types espejo.

## Resumen

`scheduling` **persiste las citas** y **calcula la disponibilidad** del calendario combinando insumos de otros módulos. **No existe una tabla de slots** ([ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md)): la única unidad persistida del calendario es `Appointment`; los slots libres se calculan al vuelo (`compute_available_slots`) cada vez que alguien pregunta por disponibilidad. La disponibilidad del doctor son **bloques concretos por fecha** (`staff.DoctorAvailability`), no patrones recurrentes ([ADR-007](../../decisions/ADR-007-doctor-availability-concrete-blocks.md)).

```
                  ┌─ DoctorAvailability (staff, bloques concretos por fecha)
                  ├─ OfficeOperatingHours       (clinic, patrón semanal)
                  ├─ OfficeClosure              (clinic, ad-hoc; resta/suma)
disponibilidad = ─┤  office_vertical            (clinic, filtra office apto)
                  ├─ Doctor.slot_duration_min   (staff, grano del slot)
                  ├─ Product.duration_min       (catalog, N slots contiguos)
                  └─ Appointment (estados activos: ocupan tiempo)
                       ↓
        compute_available_slots(doctor, product, branch?, office?, from, to)
                       ↓
                 list[AvailabilitySlot]  ←  NO se persiste — solo se devuelve
```

El módulo cierra el **flujo de negocio end-to-end**: el `crm` capta un `Person` (lead), `conversations`/`bots` lo cultivan, `scheduling` le agenda una **cita** y, cuando la cita se **atiende**, dispara `crm.promote_to_customer` (cierra el lead como ganado + crea el cliente). El **bot** consume el módulo vía una facade (`/appointments/from-bot`, `/appointments/{id}/cancel-from-bot`) y tres tools registradas en `TOOL_REGISTRY` (`check_availability`, `book_appointment`, `cancel_appointment`).

Depende de módulos **ya en producción**: `crm` (`Person`, `promote_to_customer`, `LeadActivity`), `staff` (`Doctor`, `DoctorAvailability`, `slot_duration_min`), `clinic` (`Office`/`OfficeOperatingHours`/`OfficeClosure`/`Branch.timezone`/`office_vertical`), `catalog` (`Product.duration_min`, `Product.min_hours_to_cancel`, `Service→vertical`).

## Entidades

5 entidades. Mixins: `PK`=`PrimaryKeyMixin`, `A`=`ActiveMixin`, `SD`=`SoftDeleteMixin`, `T`=`TimestampMixin`. Las **trazas** (`AppointmentStatusHistory`, `AppointmentChangeLog`) y la **matriz** (`AppointmentStatusTransition`) **NO llevan `SD`** (mismo criterio que crm: auditoría honesta + config). `scheduling` **no tiene M:N**; la matriz es una tabla propia con identidad, no una association.

| Entidad | Tabla | Mixins | Propósito |
|---|---|---|---|
| `AppointmentStatus` | `appointment_status` | PK·A·SD·T | Catálogo configurable de estados de cita (espeja `crm.LeadStatus`). |
| `AppointmentStatusTransition` | `appointment_status_transition` | PK·A·T | Matriz configurable de aristas `from→to` permitidas (espeja `crm.LeadStatusTransition`). |
| `Appointment` | `appointment` | PK·A·SD·T | Cita concreta: `person` + `doctor` + `office`/`branch` + `product` + `scheduled_for`. Unidad persistida del calendario. |
| `AppointmentStatusHistory` | `appointment_status_history` | PK·A·T | Timeline inmutable de transiciones de estado (append-only). |
| `AppointmentChangeLog` | `appointment_change_log` | PK·A·T | Traza de cambios in-place de columnas **no-estado** (`doctor_id`/`office_id`/`notes`/…). |

### `AppointmentStatus` (catálogo configurable)

Catálogo en BD para que admin renombre/agregue estados sin deploy. Mismo patrón que `crm.LeadStatus`: flags para que el código no hardcodee codes.

- `code: varchar(40)` UNIQUE NOT NULL — **MAYÚSCULAS, sin pattern slug restrictivo** (espeja `crm.LeadStatus`: `NUEVO`/`CONTACTADO`/…, que solo valida min/max length). Inmutable (los shortcuts del service resuelven por code).
- `name: varchar(120)` NOT NULL · `description: text` nullable · `color: varchar(20)` nullable (hex para badges).
- `is_initial: bool` default `false` — **exactamente uno** true (validado en service → `MULTIPLE_INITIAL_STATUS`). Estado por defecto al crear la cita.
- `is_final: bool` default `false` — terminal.
- `is_active_attention: bool` default `false` — "en atención ahora" (0..N; útil para vistas operativas en tiempo real).
- `display_order: int` NOT NULL default `0`.

**Seed (8 estados)** `(code, name, color, is_initial, is_final, is_active_attention, display_order)`:

```python
APPOINTMENT_STATUSES_SEED = [
    ("SCHEDULED",   "Agendada",     "#3B82F6", True,  False, False, 10),
    ("CONFIRMED",   "Confirmada",   "#06B6D4", False, False, False, 20),
    ("CHECKED_IN",  "En recepción", "#F59E0B", False, False, False, 30),
    ("IN_PROGRESS", "En atención",  "#8B5CF6", False, False, True,  40),
    ("ATTENDED",    "Atendida",     "#22C55E", False, True,  False, 50),
    ("NO_SHOW",     "No asistió",   "#EF4444", False, True,  False, 60),
    ("CANCELLED",   "Cancelada",    "#6B7280", False, True,  False, 70),
    ("RESCHEDULED", "Reagendada",   "#9CA3AF", False, True,  False, 80),
]
```

`is_initial` único = `SCHEDULED`; `is_final` = {`ATTENDED`, `NO_SHOW`, `CANCELLED`, `RESCHEDULED`}; `is_active_attention` único = `IN_PROGRESS`.

### `AppointmentStatusTransition` (matriz configurable)

Aristas `from→to` permitidas del grafo de estados de cita. Espeja `crm.LeadStatusTransition` y aplica [ADR-008](../../decisions/ADR-008-configurable-status-transition-matrix.md). Sin `SD`: deshabilitar una arista = `active=false` (conserva la fila) o `DELETE` real.

- `from_status_id: varchar(36)` FK→`appointment_status` NOT NULL · `to_status_id: varchar(36)` FK→`appointment_status` NOT NULL.
- **UNIQUE `(from_status_id, to_status_id)`**.
- `repo.is_allowed(db, from_id, to_id) → bool` decide si la transición es legal; ausencia → `APPOINTMENT_TRANSITION_NOT_ALLOWED` (400).

**Matriz base seedeada** (la clínica la refina luego, igual que crm):

```
SCHEDULED   → CONFIRMED, CHECKED_IN, NO_SHOW, CANCELLED, RESCHEDULED
CONFIRMED   → CHECKED_IN, NO_SHOW, CANCELLED, RESCHEDULED
CHECKED_IN  → IN_PROGRESS, CANCELLED
IN_PROGRESS → ATTENDED, CANCELLED
ATTENDED · NO_SHOW · CANCELLED · RESCHEDULED  → (finales, sin aristas de salida)
```

Reschedule permitido desde {`SCHEDULED`, `CONFIRMED`}; los shortcuts (`/confirm`, `/check-in`, `/start`, `/attend`, `/no-show`, `/cancel`) mapean cada uno a su to-state y consultan `is_allowed`. Los **side-effects** por transición (`attend→promote`, `cancel→min_hours`, `reschedule→nueva cita) viven en el SERVICE.

### `Appointment` (unidad persistida del calendario)

- `person_id: varchar(36)` FK→`person` NOT NULL · `doctor_id: varchar(36)` FK→`doctor` NOT NULL · `office_id: varchar(36)` FK→`office` NOT NULL · `branch_id: varchar(36)` FK→`branch` NOT NULL (**denorm** de `office.branch_id`) · `product_id: varchar(36)` FK→`product` NOT NULL.
- `scheduled_for: timestamptz` NOT NULL — inicio de la cita (UTC en BD, ISO 8601 con offset en JSON).
- `duration_min: int` NOT NULL — **copiado de `product.duration_min`** al agendar (fallback `doctor.slot_duration_min` si NULL). No se redondea: la cita reserva `[scheduled_for, scheduled_for + duration_min)` para el chequeo de conflicto.
- `status_id: varchar(36)` FK→`appointment_status` NOT NULL.
- `source: varchar(20)` NOT NULL — enum código `bot | advisor | admin | import | api`.
- `previous_appointment_id: varchar(36)` nullable FK→`appointment` (self-ref) — cadena de reagendamiento (acíclica por construcción).
- `notes: text` nullable · `cancellation_reason: varchar(255)` nullable · `cancelled_at: timestamptz` nullable · `cancelled_by: varchar(36)` nullable FK→`user` · `confirmed_at: timestamptz` nullable · `attended_at: timestamptz` nullable.
- **Índices**: `(doctor_id, scheduled_for)`, `(office_id, scheduled_for)`, `(person_id, scheduled_for)`, `(branch_id, scheduled_for, status_id)`.
- **No se soft-deletea al cerrar**: los estados finales (`ATTENDED`/`CANCELLED`/…) mantienen la fila viva como registro histórico. El soft-delete (`DELETE`) se reserva para "error de captura". **Diverge de crm**, donde alcanzar `is_final` soft-deletea la fila viva (ver [Decisiones](#appointment-no-se-soft-deletea-al-cerrar-diverge-de-crm)).

### `AppointmentStatusHistory` (timeline de estado)

Espeja `crm.LeadStatusHistory`. Append-only, sin `SD`, **sin relationship** al padre (acceso por `appointment_id` + batch maps).

- `appointment_id: varchar(36)` FK→`appointment` NOT NULL · `from_status_id: varchar(36)` nullable FK→`appointment_status` (NULL al crear) · `to_status_id: varchar(36)` FK→`appointment_status` NOT NULL.
- `changed_at: timestamptz` NOT NULL · `changed_by: varchar(36)` nullable FK→`user` (NULL = bot/sistema) · `reason: varchar(255)` nullable.

### `AppointmentChangeLog` (cambios in-place no-estado)

Traza genérica de cambios de columnas que **no** son `status_id`. Sin `SD`.

- `appointment_id: varchar(36)` FK→`appointment` NOT NULL · `field_name: varchar(60)` NOT NULL (`doctor_id`/`office_id`/`notes`/…) · `previous_value: text` nullable (serializado: UUID/ISO8601/string) · `new_value: text` nullable.
- `changed_at: timestamptz` NOT NULL · `changed_by: varchar(36)` nullable FK→`user` · `reason: varchar(255)` nullable.
- Los cambios de `status_id` **no** van acá (van a `AppointmentStatusHistory`); `scheduled_for` **no** se edita in-place (usa `/reschedule`).

## Disponibilidad on-the-fly — `compute_available_slots`

Corazón del módulo ([ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md) + [ADR-007](../../decisions/ADR-007-doctor-availability-concrete-blocks.md)). `services/availability.py: compute_available_slots(db, *, doctor_id, product_id, branch_id?, office_id?, from_date, to_date) -> AvailabilityResponse`. **No persiste nada.** Algoritmo resumido:

1. `product = catalog.get_product(product_id)` → `duration_min` (fallback `doctor.slot_duration_min`) + `vertical_id` (vía `product.service.vertical_id`, ya denormalizado en product).
2. Cargar `doctor` (`get_full`: branches + verticals, filtra soft-deleted). Si `doctor.active=false` → `[]` (gate de reserva, decisión #3). Si `vertical_id ∉ doctor.verticals` → `[]`.
3. `slot = doctor.slot_duration_min`; `N = ceil(duration_min / slot)` slots **contiguos** requeridos.
4. **Offices candidatos** = `office.list_active` filtrando: `office.branch_id ∈ doctor.branches` ∩ (`branch_id?`/`office_id?` del request) ∩ `office.verticals ∋ vertical_id` (EXISTS `office_vertical`, soft-deleted filtrado).
5. `appts` = citas del doctor en `[from, to]` con status **NOT IN** {`CANCELLED`, `NO_SHOW`, `RESCHEDULED`} (las activas ocupan tiempo).
6. Por cada `day ∈ [from, to]` × cada office candidato (TZ = `office.branch.timezone`):
   - `blocks` = bloques vivos de `DoctorAvailability` del `(doctor, day, office_id)` (scheduling filtra office/branch soft-deleted — el repo de staff **no** lo hace);
   - `∩ OfficeOperatingHours` del office para el `weekday(day)` **derivado en la TZ del branch** (varias filas/día: mañana + tarde);
   - `− OfficeClosure is_closed=true` (resta) / `∪ is_closed=false` (suma extraordinaria), convirtiendo `timestamptz ↔ local`;
   - `− appts` (resta rangos ocupados);
   - generar slots de `slot` min alineados al bloque; exigir `N` contiguos libres; cada inicio de slot → UTC.
7. Aplanar → `slots`. Cache Redis TTL 30–60 s por `(doctor, from, to)` **DIFERIDO** (MVP sin cache).

`POST /availability/check-slot` (`doctor_id`, `office_id`, `product_id`, `scheduled_for`) revalida vertical + bloque + horario + cierre + conflicto para **un** slot puntual (lo usa el bot/asesor antes de book) → `{available: bool, reason?: code}`.

Schemas: `AvailabilityRequest{doctor_id, product_id, branch_id?, office_id?, from_date, to_date}` · `AvailabilitySlot{starts_at, ends_at, doctor_id, doctor_name, office_id, office_name, branch_id, branch_name}` · `AvailabilityResponse{slots, duration_min, doctor_slot_duration_min}`.

> **TZ — lección recurrente**: `opens_at`/`closes_at` (`Time` naive) se interpretan en `branch.timezone` (IANA, default `America/Lima`); `OfficeClosure.starts_at/ends_at` y `Appointment.scheduled_for` son `timestamptz` UTC. El cómputo convierte local→UTC **por bloque** con `zoneinfo`, derivando el weekday **en la TZ del branch** — nunca desde UTC (en TZ negativas el día se desfasa).

## Invariantes del create/reschedule (en el SERVICE, con `code`)

9 invariantes de dominio, validados en `services/appointment.py` (`detail` en español, `code` en inglés):

| # | Invariante | `code` |
|---|---|---|
| 1 | `office.branch_id == appointment.branch_id` | `OFFICE_NOT_IN_BRANCH` |
| 2 | `office.verticals ∋ product.vertical_id` | `OFFICE_NOT_APT_FOR_VERTICAL` |
| 3 | `branch_id ∈ doctor.branches` | `DOCTOR_NOT_IN_BRANCH` |
| 4 | `product.vertical_id ∈ doctor.verticals` | `DOCTOR_NOT_APT_FOR_VERTICAL` |
| 5 | rango no solapa otra cita activa del doctor (SELECT FOR UPDATE) | `SLOT_TAKEN` |
| 6 | rango no solapa otra cita activa del office | `OFFICE_SLOT_TAKEN` |
| 7 | cabe en un bloque `DoctorAvailability` del día/office | `NO_AVAILABILITY_BLOCK` |
| 8 | office abierto (en `OfficeOperatingHours`, no bloqueado por `OfficeClosure is_closed=true`) | `OFFICE_CLOSED` |
| 9 | al cancelar: `(scheduled_for − now) >= product.min_hours_to_cancel`, salvo permiso `APPOINTMENTS_CANCEL_OVERRIDE` | `CANCEL_TOO_LATE` |

Códigos transversales adicionales: doctor `active=false` → `DOCTOR_INACTIVE` (gate de nueva reserva, decisión #3); transición fuera de la matriz → `APPOINTMENT_TRANSITION_NOT_ALLOWED`; no encontrado → `APPOINTMENT_NOT_FOUND` / `APPOINTMENT_STATUS_NOT_FOUND`; catálogo en uso al borrar → `APPOINTMENT_STATUS_IN_USE`.

> **`NO_AVAILABILITY_BLOCK`** reemplaza al obsoleto `OUTSIDE_PATTERN` del diseño viejo (ya no hay patrones recurrentes, son bloques concretos — ADR-007).

**Reschedule** revalida los invariantes 1–8 sobre la **nueva** cita, **excluye** la cita vieja del chequeo de conflicto (`exclude_id`), marca la vieja `RESCHEDULED` y crea la nueva con `previous_appointment_id` en la **misma transacción**. No está sujeto a `min_hours_to_cancel` (no es cancelación). **Concurrencia**: `create_appointment` envuelve la operación en una transacción con `SELECT FOR UPDATE` sobre las citas solapadas del doctor → un segundo intento detecta el overlap → `SLOT_TAKEN`. Exclusion-constraint GIST/`tsrange` **DIFERIDO**.

## Endpoints (resumen)

Todos bajo `/api/v1/scheduling/`. Listado paginado con `POST /<recurso>/list` + `QueryRequest`. Convención del codebase: **`PUT` (no `PATCH`)** para updates; **`/active` (no `/options`) lista cruda** (`response_model=list[...]`, sin envelope); el resto usa `SingleResponse`/`PaginatedResponse`. `ALLOWED_FIELDS` solo columnas reales. El detalle de request/response/errores está en [`backend.md`](backend.md#api-contracts).

### Catálogo `AppointmentStatus` + matriz

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/appointment-statuses/list` | `APPOINTMENT_STATUSES_READ` |
| `POST` · `PUT` · `DELETE` | `/appointment-statuses[/{id}]` | `APPOINTMENT_STATUSES_WRITE` (DELETE → 409 `APPOINTMENT_STATUS_IN_USE`) |
| `GET` | `/appointment-statuses/{id}` | `APPOINTMENT_STATUSES_READ` |
| `GET` | `/appointment-statuses/active` | `APPOINTMENT_STATUSES_READ` (lista cruda) |
| `GET` | `/appointment-statuses/{id}/transitions` | `APPOINTMENT_STATUSES_READ` (to-targets) |
| `PUT` | `/appointment-statuses/{id}/transitions` | `APPOINTMENT_STATUSES_WRITE` (bulk set de aristas de salida) |

### Disponibilidad

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/availability/compute` | `AVAILABILITY_READ` (body `AvailabilityRequest`) |
| `POST` | `/availability/check-slot` | `AVAILABILITY_READ` (revalida un slot puntual) |

### Citas + ciclo de vida

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/appointments/list` | `APPOINTMENTS_READ` |
| `POST` | `/appointments` | `APPOINTMENTS_CREATE` (create/book) |
| `GET` | `/appointments/{id}` | `APPOINTMENTS_READ` (detalle + `status_history` + `change_log`) |
| `PUT` | `/appointments/{id}` | `APPOINTMENTS_UPDATE` (edita columnas no-estado → changelog) |
| `GET` | `/appointments/calendar` | `APPOINTMENTS_READ` (citas; los slots libres requieren además `AVAILABILITY_READ`) |
| `POST` | `/appointments/{id}/transition` | `APPOINTMENTS_TRANSITION` (genérico, valida matriz) |
| `POST` | `/appointments/{id}/{confirm\|check-in\|start\|attend\|no-show}` | `APPOINTMENTS_TRANSITION` (shortcuts) |
| `POST` | `/appointments/{id}/cancel` | `APPOINTMENTS_CANCEL` (+`APPOINTMENTS_CANCEL_OVERRIDE` salta `min_hours`) |
| `POST` | `/appointments/{id}/reschedule` | `APPOINTMENTS_RESCHEDULE` |

### Self-service del doctor + bot facade

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/me/appointments/list` | `MY_APPOINTMENTS_READ` |
| `GET` | `/me/calendar` | `MY_APPOINTMENTS_READ` |
| `POST` | `/appointments/from-bot` | — (sin RBAC, SYSTEM; `BotInvocationContext`) |
| `POST` | `/appointments/{id}/cancel-from-bot` | — (sin RBAC, SYSTEM; `BotInvocationContext`) |

> **Scoping anti-IDOR**: el `DOCTOR` sin `APPOINTMENTS_READ` global ve **solo sus citas** — el service filtra `doctor_id == current.doctor.id` cuando el actor tiene únicamente `MY_*` (espeja `_assert_can_access` de `conversations`).

## Permisos seed

13 permisos. Se consolidan en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md) — aquí se referencian:

```
MENU-SCHEDULING ·
APPOINTMENT_STATUSES_{READ,WRITE} ·
APPOINTMENTS_{READ,CREATE,UPDATE,DELETE,TRANSITION,CANCEL,CANCEL_OVERRIDE,RESCHEDULE} ·
AVAILABILITY_READ ·
MY_APPOINTMENTS_READ
```

(Set canónico ya seedeado en [`_seed-and-roles.md`](../_seed-and-roles.md). `APPOINTMENTS_DELETE` = soft-delete "error de captura" [solo admin]; `AVAILABILITY_READ` gatea `/availability/*` + los slots libres de la grilla. NO existe `APPOINTMENT_CALENDAR_READ` ni `MY_APPOINTMENTS_WRITE`.)

**Roles seed**:

- `ADMIN` — todos.
- `ASESOR` — `MENU-SCHEDULING` + `APPOINTMENT_STATUSES_READ` + `APPOINTMENTS_{READ,CREATE,UPDATE,TRANSITION,CANCEL,RESCHEDULE}` + `AVAILABILITY_READ`. **No** `APPOINTMENTS_CANCEL_OVERRIDE`, **no** `APPOINTMENTS_DELETE`, **no** `APPOINTMENT_STATUSES_WRITE` (catálogo/matriz = admin).
- `DOCTOR` — `MENU-SCHEDULING` + `APPOINTMENT_STATUSES_READ` + `APPOINTMENTS_READ` (scoped a sí mismo vía service) + `APPOINTMENTS_TRANSITION` (su agenda) + `AVAILABILITY_READ` + `MY_APPOINTMENTS_READ`.

## Decisiones de diseño (no obvias)

### Disponibilidad on-the-fly, sin tabla de slots — [ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md)

Solo persiste `Appointment`; los slots libres se calculan al vuelo. Alternativa rechazada: materializar `appointment_slot` (`status ∈ {free, booked, blocked}`) — costosa de mantener consistente con tantas dimensiones (bloques del doctor × horario office × cierres × verticales × citas). **Aceptado, firmado @daniel/@marco, no se re-litiga.**

### Disponibilidad del doctor = bloques concretos por fecha — [ADR-007](../../decisions/ADR-007-doctor-availability-concrete-blocks.md)

`staff.DoctorAvailability { doctor_id, branch_id, office_id, date, opens_at, closes_at }` reemplazó el modelo `DoctorAvailabilityPattern` (recurrente) + `DoctorAvailabilityOverride` (eliminados): los doctores (re)definen sus horarios concretos cada mes. El algoritmo lee `doctor_availability_repository.list_for_doctor(doctor_id, date_from, date_to)` (filtra `deleted_at`); el code obsoleto `OUTSIDE_PATTERN` pasó a `NO_AVAILABILITY_BLOCK`.

### Matriz de transiciones configurable — [ADR-008](../../decisions/ADR-008-configurable-status-transition-matrix.md)

Igual que crm: las transiciones permitidas son filas en `appointment_status_transition` (`from→to`), seedeadas con una base y editables por admin. El service rechaza una arista ausente con `APPOINTMENT_TRANSITION_NOT_ALLOWED` (400). Los **side-effects** (attend→promote, cancel→min_hours, reschedule→nueva cita) viven en el SERVICE; los shortcuts solo consultan `is_allowed`.

### `Appointment` NO se soft-deletea al cerrar (diverge de crm)

En crm, alcanzar un estado `is_final` soft-deletea la fila viva (`PersonLeadStatus`) y la traza queda en el historial. En scheduling, una cita `ATTENDED`/`CANCELLED`/`NO_SHOW`/`RESCHEDULED` **mantiene la fila viva** — es un registro histórico que debe aparecer en la tabla, el calendario y los reportes. El soft-delete se reserva exclusivamente para "error de captura" (la cita nunca debió existir).

### Doctor `active=false` excluido de nuevas reservas (gate de scheduling)

Confirmado por usuario (decisión #3). En `staff`, `active` **no** es gate para que el doctor auto-gestione su agenda. En `scheduling`, `active=false` **sí** bloquea agendar contra ese doctor (`DOCTOR_INACTIVE`; `compute_available_slots` devuelve `[]`). Las citas existentes quedan intactas. Es una divergencia intencional entre módulos.

### Bot facade como fase final (decisión #4)

`scheduling` expone una facade SYSTEM para el bot: `/appointments/from-bot` + `/appointments/{id}/cancel-from-bot` (corren como `SYSTEM`, `source='bot'`, respetan **todos** los invariantes — incl. `min_hours_to_cancel`: el bot **no** hace override). Reschedule por bot = cancel + book (sin 4ta tool en el MVP). Se registran 3 tools en `bots/services/engine/tools/scheduling.py` (`check_availability`, `book_appointment`, `cancel_appointment`), indexadas por `code` en `TOOL_REGISTRY`, sin migración.

### Duración de la cita sale de `Product`, no de `Service`

`catalog.Product` ya trae `duration_min: int|None` y `min_hours_to_cancel: int|None` (verificado `product.py:59/62`). `Appointment.duration_min` se **copia** de `product.duration_min` al agendar (fallback `doctor.slot_duration_min` si NULL). `Service` no tiene duración. La grilla de slots exige `N = ceil(duration_min / slot_duration_min)` slots contiguos.

### UI MVP incluye grilla de calendario semanal (decisión #2)

Además de la tabla + wizard de reserva + Mi agenda del doctor, el MVP incluye una **grilla semanal** (`/scheduling/calendario`): citas = bloques sólidos coloreados por estado, slots libres = overlay clickeable que abre el wizard prefilled. TZ = `branch.timezone`. Cualquier `new Date()`/now que afecte el render (resaltar "hoy", default de fecha) es **client-only** (lección TZ recurrente).

## Cambios cross-módulo (aditivos)

| Módulo | Cambio | Naturaleza |
|---|---|---|
| `crm` | FK aditiva `lead_activity.related_appointment_id → appointment` (la columna ya existe sin FK, ADR-009). `appointment.person_id → person` (FK directa). | migración de scheduling agrega los constraints |
| `crm` | `enums.ActivityType += APPOINTMENT_ATTENDED` (ya hay `APPOINTMENT_BOOKED`/`APPOINTMENT_CANCELLED`). | aditivo en crm |
| `crm` | `attend` (→`ATTENDED`): si el Person no tiene `PersonCustomerStatus` activo → `crm.promote_to_customer` (cierra lead `is_won` + crea cliente `is_initial`); si ya es cliente → no-op CRM + `LeadActivity(APPOINTMENT_ATTENDED)`. Misma transacción. | orquestación en scheduling |
| `bots` | `services/engine/tools/scheduling.py` nuevo: registra las 3 tools en `TOOL_REGISTRY`. Pasan de `TOOL_NOT_REGISTERED` a operativas. | aditivo en bots (fase final) |

`scheduling` se construye **después** que `crm`/`staff`/`clinic`/`catalog` (en prod) y **antes/junto** que el enganche de `bots`. Las FKs forward que crm dejó como `varchar(36)` sin constraint las cierra esta migración de forma aditiva ([ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md)).

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `crm` | `appointment.person_id → person` (FK). Emite `LeadActivity(APPOINTMENT_BOOKED/CANCELLED/ATTENDED)` y dispara `promote_to_customer` al atender. Agrega FK a `lead_activity.related_appointment_id`. |
| `staff` | Lee `Doctor` (`get_full`: branches/verticals), `slot_duration_min` y `DoctorAvailability` (bloques) para `compute_available_slots`. `appointment.doctor_id → doctor` (FK). |
| `clinic` | Lee `OfficeOperatingHours`, `OfficeClosure`, `office_vertical`, `Branch.timezone`. `appointment.office_id → office`, `appointment.branch_id → branch` (FKs). |
| `catalog` | Lee `Product.duration_min` y `Product.min_hours_to_cancel`; deriva `vertical_id` vía `product.service.vertical_id`. `appointment.product_id → product` (FK). |
| `admin` | Audit users (`created_by`/`updated_by`/`cancelled_by`/`changed_by` → `user.id`); user/role `SYSTEM` (introducido por crm) como actor de la bot facade. |
| `bots` | Consume la facade SYSTEM + 3 tools (`check_availability`/`book_appointment`/`cancel_appointment`). NO escribe directo; pasa por la facade. |

## Diagramas

- ER: [`docs/diagrams/er-scheduling.puml`](../../diagrams/er-scheduling.puml)
- Class diagram (modelos + repos + services): [`docs/diagrams/class-backend-scheduling.puml`](../../diagrams/class-backend-scheduling.puml)

> Ambos reflejan el **modelo viejo** (4 entidades, sin matriz, patrón+overrides de disponibilidad). Se **regeneran al modelo de esta spec** en la consolidación post-fichas: agregar `AppointmentStatusTransition`, marcar `appointment.person_id`/FKs forward, reflejar bloques concretos (ADR-007) y `PUT`/`/active`.

## Implementación por fases

`scheduling` se implementa en fases que mapean al ciclo de vida del módulo. Molde global = **crm** (catálogo + matriz + history) + **clinic/staff** (las fuentes; `staff /me` como molde de "Mi agenda"). Migración inicial `0020` (revid ≤32 chars; la última aplicada es `0019_bots_engine_state`). Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist mapeado a estas fases.

| Fase | Alcance | Migración (revid ≤32) |
|---|---|---|
| **F0 — Prep** | 13 permisos en `SEED_PERMISSIONS` + role subsets (ADMIN/ASESOR/DOCTOR); nav grupo "Agenda" (`MENU-SCHEDULING` + iconMap); `endpoints.ts`; `types/scheduling.types.ts`; skeleton inerte. (Traducción ya hecha.) | ninguna (solo seed) |
| **F1 — AppointmentStatus + matriz** | Catálogo CRUD + matriz (GET/PUT) + seed 8 estados + matriz base; UI `/scheduling/estados` con editor de transiciones; registrar módulo. (Molde = crm F2.) | `0020_scheduling_status` |
| **F2 — Appointment + availability + booking** | `Appointment` + `AppointmentStatusHistory` + `AppointmentChangeLog` (FKs forward + self-FK); 9 invariantes + `compute_available_slots` + `check-slot` + create/get/list + `SLOT_TAKEN` (FOR UPDATE); UI tabla + wizard de reserva. (La fase más pesada.) | `0021_scheduling_appointment` |
| **F3 — Lifecycle + audit** | transitions (matriz) + shortcuts (`confirm`/`check-in`/`start`/`attend`/`no-show`/`cancel`/`reschedule`) + history/changelog + `attend→promote` + `APPOINTMENT_ATTENDED`; UI detalle + timeline + status control. | ninguna |
| **F4 — Calendar grid** | `/appointments/calendar` + grilla semanal UI + Mi agenda del doctor. [decisión #2] | ninguna |
| **F5 — Bot facade + tools** | `/appointments/from-bot` + `/appointments/{id}/cancel-from-bot` + registrar 3 tools en `TOOL_REGISTRY`. Cierra el loop. [decisión #4] | ninguna |

> **Migraciones**: revid ≤ 32 chars (`alembic_version varchar(32)`). Sugeridas y verificadas: `0020_scheduling_status` (22) · `0021_scheduling_appointment` (27). Las FKs forward (`person`/`appointment_status`/self-FK) y las aditivas a crm (`lead_activity.related_appointment_id`) se crean con `create_foreign_key` (el smoke sqlite no las ejercita; las valida el QA E2E en Postgres).

## Reconciliaciones resueltas (post-generación, 2026-06-06)

Decisiones que cierran las inconsistencias cross-ficha detectadas al generar las 4 fichas (este README es autoritativo):
- **`code` de AppointmentStatus = MAYÚSCULAS sin pattern slug** (`SCHEDULED`/`CONFIRMED`/…), espejando `crm.LeadStatus`. (Algunas líneas de `backend.md`/`frontend.md` aún muestran el code en minúsculas en prosa ilustrativa; prevalece el casing de esta nota + el seed table.)
- **`down_revision` de `0020_scheduling_status` = `0019_bots_engine_state`** (última migración aplicada; verificado en `alembic/versions/`).
- **Permisos = el set canónico de [`_seed-and-roles.md`](../_seed-and-roles.md)** (13): incluye `APPOINTMENTS_DELETE` (soft-delete "error de captura", admin) y `AVAILABILITY_READ`; **no** `APPOINTMENT_CALENDAR_READ` ni `MY_APPOINTMENTS_WRITE` (los inventó el borrador; quedan descartados). `/availability/compute` + `/availability/check-slot` → `AVAILABILITY_READ` (lo tienen ASESOR y DOCTOR). `/appointments/calendar` → `APPOINTMENTS_READ` (las citas) + `AVAILABILITY_READ` (los slots libres). `/me/calendar` → `MY_APPOINTMENTS_READ`.
- **`attend → promote_to_customer` es atómico**: corre en la misma transacción; si el promote falla por `NO_INITIAL_CUSTOMER_STATUS` (clínica sin estado-cliente inicial configurado) la atención **revierte** y surface el error (la mala config se corrige). El `attend` no es best-effort.
- **`/appointments/calendar` (+ `/me/calendar`)** devuelve `AppointmentCalendarResponse {appointments, free_slots, from_date, to_date}`; `free_slots` solo se pobla cuando hay `doctor_id` filtrado (el cómputo es por doctor+producto). La payload incluye `branch.timezone` para que la grilla pinte en hora local del branch.
- **`NO_AVAILABILITY_BLOCK`** cubre tanto "no hay bloque de disponibilidad" como "el bloque no tiene N slots contiguos para `product.duration_min`" (no hay un code separado tipo `NO_CONTIGUOUS_SLOTS`).
- **`source` enum** = `bot|advisor|admin|import|api` (en Python `AppointmentSource(StrEnum)` con miembro `IMPORT="import"`; en TS literal union).
- **Detalle de cita = drawer** (no página con tabs): coherente entre `ui.md` y `frontend.md`.

## Próximos pasos / TODOs deliberados

- [ ] **Consolidación post-fichas**: regenerar `er-scheduling.puml` + `class-backend-scheduling.puml` al modelo final (5 entidades, matriz, bloques concretos); borrar el overview plano viejo `docs/modules/scheduling.md` y repuntar sus links a este README; actualizar `docs/decisions/README.md` si hace falta.
- [ ] **Cache de disponibilidad** (Redis TTL 30–60 s por `(doctor, from, to)`) cuando la carga del cómputo on-the-fly lo justifique. Diferido del MVP.
- [ ] **Exclusion-constraint GIST/`tsrange`** sobre `(doctor_id, tsrange(scheduled_for, scheduled_for+duration_min))` como backstop de BD al `SLOT_TAKEN` aplicado por `SELECT FOR UPDATE`. Diferido.
- [ ] **4ta tool de reschedule** para el bot (hoy reschedule por bot = cancel + book). Postergado al MVP del bot.
- [ ] Si el negocio requiere durations por `(doctor, product)`, agregar `doctor_product_duration` de forma aditiva (hoy la duración sale de `Product.duration_min`).
