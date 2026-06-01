# Módulo `scheduling`

> **Última actualización**: 2026-05-28
> **Propósito**: citas de la clínica, sus estados, cancelación, reagendamiento y cálculo on-the-fly de slots disponibles.
> **Path del código**: `backend/app/modules/scheduling/`

## Resumen

`scheduling` es el módulo que **persiste las citas** y **calcula la disponibilidad** del calendario combinando insumos de otros módulos: el patrón del doctor, los overrides ad-hoc, los horarios de operación del consultorio, las excepciones de la sede y las citas ya agendadas.

**No existe una tabla de slots**. La unidad persistida es `Appointment` — los slots libres se calculan al vuelo cada vez que alguien pregunta por disponibilidad. Decisión documentada en [ADR-006](../decisions/ADR-006-hybrid-calendar-slots.md).

```
                  ┌─ DoctorAvailabilityPattern  (staff, recurrente)
                  ├─ DoctorAvailabilityOverride (staff, ad-hoc)
                  ├─ OfficeOperatingHours       (clinic, recurrente)
                  ├─ OfficeClosure              (clinic, ad-hoc)
disponibilidad = ─┤
                  ├─ office_vertical            (clinic, filtra apto)
                  ├─ Doctor.slot_duration_min   (staff)
                  └─ Appointment (no canceladas, no completadas)
                       ↓
              compute_available_slots(doctor, product, branch?, office?, from, to)
                       ↓
                 list[Slot]  ←  NO se persiste — solo se devuelve
```

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `AppointmentStatus` | `appointment_status` | Catálogo configurable de estados de cita. |
| `Appointment` | `appointment` | Cita concreta: doctor + office + person + product + scheduled_for. |
| `AppointmentStatusHistory` | `appointment_status_history` | Timeline inmutable de transiciones de estado. |
| `AppointmentChangeLog` | `appointment_change_log` | Traza genérica de cambios en columnas de la cita (no estados). |

### `AppointmentStatus` (catálogo)

Catálogo configurable. Mismo patrón que `crm.LeadStatus` y `crm.CustomerStatus`: flags para que el código no hardcodee codes.

- `code: varchar(40)` `<<unique>>` — slug estable.
- `name: varchar(120)`.
- `description: text` `<<nullable>>`.
- `color: varchar(20)` `<<nullable>>` — hex para badges.
- `is_initial: bool` `default false` — estado por defecto al crear (`SCHEDULED`).
- `is_final: bool` `default false` — terminal (`ATTENDED`, `NO_SHOW`, `CANCELLED`, `RESCHEDULED`).
- `is_active_attention: bool` `default false` — flag para "la cita está en atención" (`IN_PROGRESS`). Útil para vistas operativas en tiempo real.
- `display_order: int` `default 0`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Estados seed (granular: 8)** confirmados por usuario:

```python
APPOINTMENT_STATUSES_SEED = [
    # code, name, color, is_initial, is_final, is_active_attention, display_order
    ("SCHEDULED",   "Agendada",       "#3B82F6", True,  False, False, 10),
    ("CONFIRMED",   "Confirmada",     "#06B6D4", False, False, False, 20),
    ("CHECKED_IN",  "En recepción",   "#F59E0B", False, False, False, 30),
    ("IN_PROGRESS", "En atención",    "#8B5CF6", False, False, True,  40),
    ("ATTENDED",    "Atendida",       "#22C55E", False, True,  False, 50),
    ("NO_SHOW",     "No asistió",     "#EF4444", False, True,  False, 60),
    ("CANCELLED",   "Cancelada",      "#6B7280", False, True,  False, 70),
    ("RESCHEDULED", "Reagendada",     "#9CA3AF", False, True,  False, 80),
]
```

### `Appointment`

Cita concreta. Es la unidad persistida que ocupa tiempo en el calendario.

- `person_id: varchar(36)` `<<FK→person>>` — paciente.
- `doctor_id: varchar(36)` `<<FK→doctor>>` — quien atiende.
- `office_id: varchar(36)` `<<FK→office>>` — consultorio.
- `branch_id: varchar(36)` `<<FK→branch>>` — sede. **Denormalizado** (deriva de `office.branch_id`) para queries rápidos por sede sin join — actualizable en cascada (si el office cambia de sede, se actualiza también; no debe pasar en operación normal).
- `product_id: varchar(36)` `<<FK→product>>` — qué se va a brindar.
- `scheduled_for: timestamptz` — inicio en UTC. Browser convierte al timezone del usuario (`Branch.timezone` en práctica).
- `duration_min: int` — duración efectiva **copiada de `product.duration_min` al agendar**. Si el producto se edita después, la cita mantiene su duración original. Si el producto tenía `duration_min=NULL`, se usa `doctor.slot_duration_min`.
- `status_id: varchar(36)` `<<FK→appointment_status>>` — estado actual.
- `source: varchar(20)` — enum cerrado en código: `bot / advisor / admin / import / api`. Confirmado por usuario para reportes de canal de agendamiento.
- `previous_appointment_id: varchar(36)` `<<nullable, FK→appointment>>` (self-reference) — si la cita es resultado de un reagendamiento, FK a la anterior. La cadena `appointment_1 ← appointment_2 ← appointment_3` muestra todos los reagendamientos sucesivos. La vieja queda en estado `RESCHEDULED` (final).
- `notes: text` `<<nullable>>` — nota libre del que agenda.
- `cancellation_reason: varchar(255)` `<<nullable>>` — texto al cancelar.
- `cancelled_at: timestamptz` `<<nullable>>`.
- `cancelled_by: varchar(36)` `<<nullable, FK→user>>` — quien canceló (NULL si fue automático).
- `attended_at: timestamptz` `<<nullable>>` — marca de cuándo se completó la atención.
- `confirmed_at: timestamptz` `<<nullable>>` — marca de cuándo se confirmó (CONFIRMED).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Índices**:
- `(doctor_id, scheduled_for)` — detección rápida de conflictos al agendar.
- `(office_id, scheduled_for)` — conflictos por consultorio.
- `(person_id, scheduled_for)` — "agenda del paciente" en orden cronológico.
- `(branch_id, scheduled_for, status_id)` — vista del calendario de la sede filtrando por estado.

**Invariantes validados en service** (no constraints SQL, porque cruzan tablas):
1. `office.branch_id == appointment.branch_id` — consistencia denormalización.
2. Office acepta la vertical del producto — `office.verticals ∋ product.service.vertical_id`.
3. Doctor está asignado al branch — `doctor.branches ∋ branch_id`.
4. Doctor cubre la vertical del producto — `doctor.verticals ∋ product.service.vertical_id`.
5. **No conflict de tiempo del doctor**: ninguna otra `Appointment` del mismo `doctor_id` solapa el rango `[scheduled_for, scheduled_for + duration_min)` en estados no-finales (`SCHEDULED / CONFIRMED / CHECKED_IN / IN_PROGRESS`) o `ATTENDED`. Se ignoran `CANCELLED / NO_SHOW / RESCHEDULED`.
6. **No conflict de tiempo del office**: análogo para `office_id`.
7. **Cabe en el patrón del doctor**: el rango cae dentro de `DoctorAvailabilityPattern(doctor, branch, office, day_of_week)` y no es bloqueado por un `DoctorAvailabilityOverride(is_available=false)`.
8. **Office abierto en ese rango**: cabe en `OfficeOperatingHours(office, day)` y no es bloqueado por `OfficeClosure(is_closed=true)`.
9. **Cancelación temporal**: si `product.min_hours_to_cancel IS NOT NULL` y el actor intenta cancelar con menos antelación, rechaza salvo permiso `APPOINTMENTS_CANCEL_OVERRIDE`.

### `AppointmentStatusHistory`

Timeline inmutable de transiciones. Misma forma que `crm.LeadStatusHistory`.

- `appointment_id: varchar(36)` `<<FK→appointment>>`.
- `from_status_id: varchar(36)` `<<nullable, FK→appointment_status>>` — `NULL` cuando se crea.
- `to_status_id: varchar(36)` `<<FK→appointment_status>>`.
- `changed_at: timestamptz`.
- `changed_by: varchar(36)` `<<nullable, FK→user>>` — actor; `NULL` si automático (bot, sistema).
- `reason: varchar(255)` `<<nullable>>`.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`**.

### `AppointmentChangeLog`

Traza genérica de cambios en columnas (no estados). El `AppointmentStatusHistory` cubre estados específicamente; este cubre los demás (cambios de doctor, de office, de scheduled_for, de product, de notes).

- `appointment_id: varchar(36)` `<<FK→appointment>>`.
- `field_name: varchar(60)` — qué columna cambió (`doctor_id`, `office_id`, `scheduled_for`, `notes`, ...).
- `previous_value: text` `<<nullable>>` — serializado a string. Para FKs es el UUID; para datetimes es ISO 8601; para enums es el string.
- `new_value: text` `<<nullable>>`.
- `changed_at: timestamptz`.
- `changed_by: varchar(36)` `<<nullable, FK→user>>`.
- `reason: varchar(255)` `<<nullable>>`.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`**.

**Nota sobre reagendamiento**: confirmado por usuario que el reagendamiento crea una **nueva** `Appointment` con `previous_appointment_id` FK a la anterior. El cambio de `scheduled_for` en sí no produce `AppointmentChangeLog` — produce **un cierre de la cita vieja** (`status=RESCHEDULED`) y **creación de la nueva** (apuntando a la vieja). El changelog cubre solo edits in-place sobre una cita existente que **no son** reagendamientos (ej. el asesor corrige una nota, cambia el office a otro libre, etc.).

## Esquemas (Pydantic v2)

Variantes habituales. Específicos del módulo:

- `AppointmentCreate { person_id, doctor_id, office_id, product_id, scheduled_for, source?, notes? }` — `branch_id` se deriva del office en el service; `duration_min` se copia del product; `status_id = is_initial`.
- `AppointmentRescheduleRequest { new_scheduled_for, new_doctor_id?, new_office_id?, reason? }` — body del `/reschedule` endpoint. Service:
  1. Valida estado actual no-final.
  2. Crea nueva `Appointment` con `previous_appointment_id` apuntando a la actual.
  3. Marca la actual como `RESCHEDULED` (registra en `AppointmentStatusHistory`).
- `AppointmentCancelRequest { reason? }` — el service valida `min_hours_to_cancel` del producto (si admin no tiene `APPOINTMENTS_CANCEL_OVERRIDE`).
- `AppointmentTransitionRequest { to_status_id, reason? }` — body genérico para transiciones.
- `AvailabilityRequest { doctor_id, product_id, branch_id?, office_id?, from_date, to_date }` — body del cómputo de slots.
- `AvailabilitySlot { starts_at, ends_at, doctor_id, doctor_name, office_id, office_name, branch_id, branch_name }`.
- `AvailabilityResponse { slots: list[AvailabilitySlot], duration_min: int, doctor_slot_duration_min: int }`.

## Endpoints

Bajo `/api/v1/scheduling/`.

### Catálogo

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/appointment-statuses/list` | `APPOINTMENT_STATUSES_READ` |
| `POST` | `/appointment-statuses` | `APPOINTMENT_STATUSES_WRITE` |
| `PATCH` | `/appointment-statuses/{id}` | `APPOINTMENT_STATUSES_WRITE` |
| `DELETE` | `/appointment-statuses/{id}` | `APPOINTMENT_STATUSES_WRITE` |
| `GET` | `/appointment-statuses/options` | `APPOINTMENT_STATUSES_READ` |

### Citas

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/appointments/list` | `APPOINTMENTS_READ` |
| `POST` | `/appointments` | `APPOINTMENTS_CREATE` |
| `GET` | `/appointments/{id}` | `APPOINTMENTS_READ` |
| `PATCH` | `/appointments/{id}` | `APPOINTMENTS_UPDATE` | edit in-place: notes / cambios menores. NO mueve scheduled_for (eso usa `/reschedule`). |
| `DELETE` | `/appointments/{id}` | `APPOINTMENTS_DELETE` | soft delete — distinto de `CANCELLED` (el delete es "esta cita fue un error de captura"). |
| `POST` | `/appointments/{id}/transition` | `APPOINTMENTS_TRANSITION` | cambio de estado genérico |
| `POST` | `/appointments/{id}/confirm` | `APPOINTMENTS_TRANSITION` | shortcut: → CONFIRMED |
| `POST` | `/appointments/{id}/check-in` | `APPOINTMENTS_TRANSITION` | shortcut: → CHECKED_IN |
| `POST` | `/appointments/{id}/start` | `APPOINTMENTS_TRANSITION` | shortcut: → IN_PROGRESS |
| `POST` | `/appointments/{id}/attend` | `APPOINTMENTS_TRANSITION` | shortcut: → ATTENDED + emite `LeadActivity` + posiblemente `promote_to_customer` (decisión del service, ver flujo) |
| `POST` | `/appointments/{id}/mark-no-show` | `APPOINTMENTS_TRANSITION` | → NO_SHOW |
| `POST` | `/appointments/{id}/cancel` | `APPOINTMENTS_CANCEL` | → CANCELLED; valida `min_hours_to_cancel` salvo permiso override |
| `POST` | `/appointments/{id}/reschedule` | `APPOINTMENTS_RESCHEDULE` | crea nueva, marca vieja RESCHEDULED |
| `GET` | `/appointments/{id}/status-history` | `APPOINTMENTS_READ` |
| `GET` | `/appointments/{id}/change-log` | `APPOINTMENTS_READ` |
| `GET` | `/persons/{person_id}/appointments` | `APPOINTMENTS_READ` | agenda del paciente |
| `GET` | `/me/appointments` | `MY_APPOINTMENTS_READ` | agenda del doctor logueado |

### Cálculo de disponibilidad

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/availability/compute` | `AVAILABILITY_READ` | body `AvailabilityRequest`; response `AvailabilityResponse` |
| `POST` | `/availability/check-slot` | `AVAILABILITY_READ` | verifica si un slot específico está libre (usado por bot/asesor antes de agendar) |

### Engine externo (usado por bots como tool)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/appointments/from-bot` | `BOT_ENGINE_INVOKE` o sistema interno | el tool `book_appointment` del bot llama acá con `BotInvocationContext` |
| `POST` | `/appointments/{id}/cancel-from-bot` | sistema interno | tool `cancel_appointment` del bot |

## Permisos seed

```python
# Module: scheduling
("MENU-SCHEDULING", "Ver menú agenda", "Bandeja de citas y calendario", "scheduling"),
("APPOINTMENT_STATUSES_READ", "Ver estados de cita", "Consultar catálogo de estados", "scheduling"),
("APPOINTMENT_STATUSES_WRITE", "Editar estados de cita", "CRUD del catálogo", "scheduling"),
("APPOINTMENTS_READ", "Ver citas", "Listar y consultar citas", "scheduling"),
("APPOINTMENTS_CREATE", "Crear citas", "Agendar nueva cita", "scheduling"),
("APPOINTMENTS_UPDATE", "Editar citas", "Edit in-place (notes, etc.)", "scheduling"),
("APPOINTMENTS_DELETE", "Eliminar citas", "Soft-delete (errores de captura)", "scheduling"),
("APPOINTMENTS_TRANSITION", "Cambiar estado de cita", "Confirmar, check-in, atender, no-show", "scheduling"),
("APPOINTMENTS_CANCEL", "Cancelar citas", "Marcar como cancelada", "scheduling"),
("APPOINTMENTS_CANCEL_OVERRIDE", "Forzar cancelación tardía", "Cancelar saltándose min_hours_to_cancel", "scheduling"),
("APPOINTMENTS_RESCHEDULE", "Reagendar citas", "Crear nueva con previous_appointment_id", "scheduling"),
("AVAILABILITY_READ", "Ver disponibilidad", "Calcular slots libres", "scheduling"),
("MY_APPOINTMENTS_READ", "Ver mi agenda", "Doctor ve su propia agenda", "scheduling"),
```

**Roles seed que tocan `scheduling`**:
- `ADMIN` — todos.
- `DOCTOR` — `MY_APPOINTMENTS_READ`, `APPOINTMENTS_READ` (limited a sus propias citas via filtros del service), `APPOINTMENTS_TRANSITION` (confirma, check-in, atende), `AVAILABILITY_READ`. **No** crea ni cancela (eso lo hace el asesor).
- `ASESOR` — `MENU-SCHEDULING`, `APPOINTMENTS_{READ,CREATE,UPDATE,TRANSITION,CANCEL,RESCHEDULE}`, `AVAILABILITY_READ`, `APPOINTMENT_STATUSES_READ`. **No** `APPOINTMENTS_DELETE` ni `APPOINTMENTS_CANCEL_OVERRIDE`.

## Decisiones de diseño

### Slots híbridos (sin tabla de slots) — ver [ADR-006](../decisions/ADR-006-hybrid-calendar-slots.md)
Solo persisten las `Appointment`. La disponibilidad se calcula on-the-fly cada vez que alguien pregunta. Trade-off: cómputo en cada request vs cero mantenimiento de tabla de slots.

### Reagendamiento como nueva cita con `previous_appointment_id` FK
Confirmado por usuario. Razón: deja la cadena de reagendamientos visible (`appt_v1 ← appt_v2 ← appt_v3`). Cada una mantiene su propia traza de status. La vieja queda en estado `RESCHEDULED` (final).

**Implicancia**: queries "agenda del paciente" deben filtrar `status != RESCHEDULED` para no mostrar las viejas. O bien filtrar `previous_appointment_id IS NULL` para mostrar solo "raíces" + seguir la cadena hacia adelante.

### Cancelación configurable en `Product.min_hours_to_cancel`
Confirmado por usuario. La columna se **agrega a `catalog.Product`** (actualización de la ficha de catalog). Si `NULL`, no hay límite. Si está set, el service de cancelación valida que `(scheduled_for - now()) >= min_hours_to_cancel * 60 min`, salvo `APPOINTMENTS_CANCEL_OVERRIDE`.

**Trade-off**: una columna en cada producto vs un setting global. La granularidad por producto es más realista (una limpieza dental tolera cancelación tardía; una cirugía no).

### 8 estados granulares
Confirmado por usuario. Permite vista operativa en tiempo real: "qué pacientes están en recepción ahora", "cuántas atenciones en curso". El flag `is_active_attention` permite al frontend filtrar la vista "en consulta ahora".

### `source: enum` en Appointment además de `LeadActivity(APPOINTMENT_BOOKED)`
Confirmado por usuario. Trade-off explícito: denormalización para queries rápidos de reporting ("citas agendadas por el bot esta semana") sin parsear `LeadActivity`. El `LeadActivity` queda como fuente de verdad granular (con actor, conversation_id, etc.); `Appointment.source` es agregado para reporting.

### `branch_id` denormalizado en Appointment
Aunque `branch_id` es derivable de `office.branch_id`, vivirla en `appointment` permite queries por sede directos sin join. Si el office cambia de sede (no debería pasar), un trigger o el service que mueve el office actualiza las citas asociadas.

### Concurrencia al agendar
Dos asesores agendan el mismo doctor en el mismo slot simultáneamente. Mitigación documentada en service:

```python
async def create_appointment(...):
    async with db.begin():
        # SELECT FOR UPDATE sobre todas las citas overlapping del doctor en el rango
        # Si hay overlap → BadRequestException(code="SLOT_TAKEN")
        # Si no → INSERT new appointment
```

El UNIQUE constraint sobre `(doctor_id, scheduled_for)` **no se usa** porque el conflict es por rango, no por punto exacto. Mejor: índice GIST con `tsrange` (`scheduled_for, scheduled_for + duration_min`) y exclusion constraint. Postergado hasta tener carga real — el `SELECT FOR UPDATE` basta para empezar.

### Cálculo de slots de disponibilidad
Service `availability.compute_available_slots(...)` recibe `(doctor_id, product_id, branch_id?, office_id?, from, to)` y devuelve lista. Pasos del algoritmo (documentar al implementar):

1. Cargar `product` → tomar `duration_min` y `vertical_id` (vía `service`).
2. Validar que `doctor.verticals ∋ vertical_id` (sino: lista vacía).
3. Cargar `doctor.slot_duration_min`.
4. Determinar candidate offices: `office.branch_id IN doctor.branches`, opcionalmente filtrado por `branch_id`/`office_id` del request, y `office.verticals ∋ vertical_id`.
5. Por cada día en el rango `[from, to]`:
   - Cargar `DoctorAvailabilityPattern` para `(doctor, day_of_week)` × `office` (los candidates).
   - Cargar `DoctorAvailabilityOverride` que solapan ese día.
   - Cargar `OfficeOperatingHours` para `(office, day_of_week)`.
   - Cargar `OfficeClosure` que solapan ese día.
   - Cargar `Appointment` del doctor en el día (no canceladas/no-show/rescheduled).
   - Generar slots de `slot_duration_min` dentro de la intersección.
   - Filtrar slots que solapan con citas existentes.
   - Si `product.duration_min > slot_duration_min`: requerir contiguos suficientes.
6. Aplanar y retornar.

**Caching**: si la operación lo pide, agregar cache de short-TTL (30-60s) por `(doctor_id, from, to)` en Redis (cuando se implemente Redis del [Hardening §1](../HARDENING.md)). Por ahora cómputo en cada request.

### `attend` puede disparar `crm.promote_to_customer`
Cuando la cita llega a `ATTENDED`, el service decide:
- Si el `Person` no tiene `PersonCustomerStatus` activo → `promote_to_customer` (close LeadStatus con `is_won=true`, create CustomerStatus con `is_initial`).
- Si ya es customer → no-op en CRM, solo emite `LeadActivity(APPOINTMENT_ATTENDED)`.

Esto cierra el flujo lead → cita → cliente del [flujo end-to-end del módulo `crm`](crm/README.md#flujo-end-to-end-típico).

### User "sistema" para citas creadas por el bot
Cuando el bot agenda, el `created_by` de la `Appointment` necesita un `user.id`. Decisión: en el seed se crea un user `system@medisage.internal` con `active=false` (no puede loguearse) y role `SYSTEM` (sin permisos operativos). Su id se usa para `created_by` de las citas del bot, los `LeadActivity` automáticos, etc. El `source='bot'` distingue claramente.

## Flujo de agendamiento por el bot (end-to-end)

1. Bot recolecta slots del lead via conversación.
2. Bot invoca tool `check_availability` → `POST /availability/compute` → recibe lista.
3. Bot ofrece opciones al lead, el lead elige.
4. Bot invoca tool `book_appointment` → `POST /appointments/from-bot`:
   - `BotInvocationContext` lleva `conversation_id`, `person_id`, `bot_tool_call_id`.
   - Service valida invariantes 1-8.
   - INSERT `Appointment` con `source='bot'`, `created_by=system_user_id`.
   - INSERT `AppointmentStatusHistory(from=NULL, to=SCHEDULED, by=NULL, reason="bot_booking")`.
   - Emite `crm.LeadActivity(activity_type=APPOINTMENT_BOOKED, related_appointment_id=...)`.
   - Si el lead todavía no estaba en estado `CITA_AGENDADA`, transition lead status.
5. Si los invariantes fallan (slot taken concurrencia, doctor no cubre vertical), service lanza `BadRequestException(code=...)`; el tool falla y el bot informa al lead.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `crm` | `Appointment.person_id` (FK). Emite `LeadActivity(APPOINTMENT_*)`. Disparador de `promote_to_customer`. |
| `staff` | `Appointment.doctor_id` (FK). Lee `DoctorAvailabilityPattern`, `DoctorAvailabilityOverride`, `Doctor.slot_duration_min`. |
| `clinic` | `Appointment.office_id`, `Appointment.branch_id` (FKs). Lee `OfficeOperatingHours`, `OfficeClosure`, `office_vertical`. |
| `catalog` | `Appointment.product_id` (FK). Lee `Product.duration_min`, `Product.min_hours_to_cancel`. |
| `bots` | Tools `check_availability`, `book_appointment`, `cancel_appointment` ejecutan endpoints de scheduling. |
| `admin` | `cancelled_by` FK, audit users. User "sistema" para bot. |

## Diagramas

- ER: [`docs/diagrams/er-scheduling.puml`](../diagrams/er-scheduling.puml)
- Class: [`docs/diagrams/class-backend-scheduling.puml`](../diagrams/class-backend-scheduling.puml)

## Próximos pasos / TODOs deliberados

- [ ] Agregar `min_hours_to_cancel: int | None` a `catalog.Product` (actualizado en [docs/modules/catalog/README.md](catalog/README.md) y [er-catalog.puml](../diagrams/er-catalog.puml) en este mismo PR).
- [ ] Crear user "sistema" en `app/core/seed.py`: `system@medisage.internal` con `active=false` y role `SYSTEM` (sin permisos). Su id se inyecta como `actor_id` en operaciones automáticas.
- [ ] Implementar `compute_available_slots` con benchmarks. Si supera ~200ms p95 con 50 doctores y 8 sedes, considerar cache TTL 30s en Redis o vista materializada.
- [ ] Tests obligatorios:
  - Crear cita: invariantes 1-8 cada uno con su mensaje de error específico.
  - Reagendar: nueva cita apunta con FK; vieja queda en RESCHEDULED.
  - Cancelar con `min_hours_to_cancel`: rechaza < umbral salvo override.
  - `attend` promueve a customer si era lead.
  - Concurrencia: dos creates simultáneos del mismo slot → uno gana, otro `SLOT_TAKEN`.
- [ ] Cuando se quiera un calendario tipo "Google Calendar" en frontend, evaluar endpoint `GET /scheduling/calendar?branch_id=&from=&to=` que combine `Appointment` + slots libres en una sola payload optimizada para render.
- [ ] **Recordatorios automáticos**: enviar WhatsApp al paciente N horas antes de la cita. Cuando aplique, modelar como cron job (`reminder_dispatched_at` columna en Appointment) o `ScheduledTask` aparte. Postergado.
- [ ] **Lista de espera (waitlist)**: si un slot popular se cancela, notificar a leads que estaban en la lista. Postergado al MVP+1.
