# ADR-006: Slots de calendario híbridos — solo `Appointment` persiste; disponibilidad se calcula on-the-fly

> **Status**: Accepted (entradas de disponibilidad actualizadas el 2026-05-29 por [ADR-007](ADR-007-doctor-availability-concrete-blocks.md))
> **Date**: 2026-05-28
> **Deciders**: @daniel, @marco

## Actualización (2026-05-29) — las entradas de disponibilidad son bloques concretos (ADR-007)

La **decisión núcleo de este ADR sigue vigente**: no existe tabla `appointment_slot`; lo único persistido es `Appointment`; la disponibilidad se calcula on-the-fly (con cache TTL cuando aplique). Lo que cambió es **una de las fuentes de entrada**: [ADR-007](ADR-007-doctor-availability-concrete-blocks.md) reemplazó el modelo de disponibilidad del doctor de **patrón semanal recurrente (`DoctorAvailabilityPattern`) + excepciones (`DoctorAvailabilityOverride`)** por una sola entidad de **bloques concretos por fecha (`staff.DoctorAvailability`)**.

Efecto en el algoritmo de abajo: donde el pseudocódigo combina `doctor.pattern_for(day, office)` + `doctor.overrides_in(day, office)`, ahora se lee directamente `doctor.availability_blocks_on(day, office)` (los bloques concretos de esa fecha/office). El resto del cómputo (intersección con `OfficeOperatingHours`, resta de `OfficeClosure` y de citas activas, filtro por vertical apta, grano `slot_duration_min`, N slots contiguos) es **idéntico**. El pseudocódigo original se conserva abajo como referencia histórica; mentalmente, sustituir "pattern ∪ overrides" por "availability_blocks".

## Context

El calendario de Medisage tiene **muchas dimensiones que afectan si un slot está libre**:

- Patrón semanal del doctor (`DoctorAvailabilityPattern` en `staff`).
- Excepciones ad-hoc del doctor (`DoctorAvailabilityOverride` — vacaciones, apertura extra).
- Horario de operación del consultorio (`OfficeOperatingHours` en `clinic`).
- Excepciones ad-hoc del consultorio (`OfficeClosure` — feriado, mantenimiento).
- Vertical apta del consultorio (`office_vertical` — el consultorio dental no sirve para una limpieza facial).
- Sedes donde el doctor atiende (`doctor_branch`).
- Verticales que cubre el doctor (`doctor_vertical`).
- Grano del slot del doctor (`Doctor.slot_duration_min`).
- Duración del producto (`Product.duration_min` — puede ocupar varios slots).
- Citas ya agendadas no canceladas (`Appointment.scheduled_for + duration_min`).

La pregunta es: **¿generamos y persistimos los slots agendables en una tabla `appointment_slot` (`status ∈ {free, booked, blocked}`) o los calculamos al vuelo cada vez que alguien pregunta por disponibilidad?**

Confirmado por usuario: **híbrido — solo persisten citas, disponibilidad se calcula**. Este ADR documenta el razonamiento y las consecuencias.

## Decision

**No existe tabla `appointment_slot`.** La única entidad persistida del calendario es `Appointment`. Cuando se quiere saber qué slots están libres para un doctor/producto en un rango, el service `scheduling.availability.compute_available_slots(...)` combina al vuelo las 10 fuentes de datos listadas arriba y devuelve la lista de slots libres.

**Algoritmo conceptual** (pseudocódigo):

```python
def compute_available_slots(doctor_id, product_id, branch_id?, office_id?, from, to):
    product = catalog.get_product(product_id)
    doctor = staff.get_doctor(doctor_id)

    # Pre-filtros tabulares
    if product.service.vertical not in doctor.verticals: return []

    candidate_offices = clinic.offices_apt_for_vertical(
        vertical=product.service.vertical_id,
        in_branches=doctor.branches,
        filter_branch=branch_id,
        filter_office=office_id,
    )

    appts = scheduling.list_appointments_by_doctor(
        doctor_id, from, to,
        statuses_excluded=['CANCELLED', 'NO_SHOW', 'RESCHEDULED'],
    )

    slots = []
    for day in days_in_range(from, to):
        for office in candidate_offices:
            blocks = intersect(
                doctor.pattern_for(day, office),
                doctor.overrides_in(day, office),
                office.operating_hours_for(day),
                office.closures_in(day),
            )
            for block in blocks:
                slot_candidates = generate_slots(block, doctor.slot_duration_min)
                slot_candidates = exclude_overlaps_with(slot_candidates, appts)
                if product.duration_min > doctor.slot_duration_min:
                    slot_candidates = require_n_contiguous(slot_candidates, ceil(...))
                slots.extend(slot_candidates)
    return slots
```

La operación es **read-heavy y cacheable**, pero no se escribe nada.

## Alternatives Considered

### Opción A — Pre-generar tabla `appointment_slot` con job programado

Un cron job (Cloud Scheduler) corre cada noche y genera slots para los próximos N días. Cada fila: `(slot_id, doctor_id, office_id, branch_id, starts_at, ends_at, status ∈ {free, booked, blocked})`. Al agendar, se cambia `status = booked` y se crea la `Appointment`.

- **Pros**:
  - Queries simples: `SELECT * FROM appointment_slot WHERE doctor_id = ? AND starts_at BETWEEN ? AND ? AND status = 'free'`.
  - El frontend recibe la lista lista para renderizar.
  - Reportes "uso del calendario" son triviales.
- **Cons**:
  - **Mantenimiento permanente**: cada vez que el doctor edita su patrón, el job tiene que regenerar slots futuros. Cada vez que se cierra un office. Cada vez que se cambia el horario de operación. Esto es un coreography frágil.
  - **Inconsistencia transitoria**: entre que el patrón cambia y el job regenera, el calendario tiene slots inválidos (doctor ya no atiende ese día, pero hay slots `free` para esa fecha).
  - **Tabla gigante**: 50 doctores × 8 sedes × 8 slots de 30 min × 365 días = 1.16M filas/año. Manejable pero hay que mantener índices y vacuum.
  - **Cambios retroactivos son complejos**: si un doctor agrega disponibilidad extra el sábado (un override `is_available=true`), hay que generar slots solo para esa ventana. La complejidad del job crece.
  - **Producto con `duration_min > slot_duration_min`**: el job tendría que saber qué productos hay y pre-marcar bloques contiguos para cada uno — o mover esa lógica al runtime de booking, lo que rompe el "queries simples".
- **Rechazada porque**: el costo de mantenimiento del job es alto, y la inconsistencia entre patrón/overrides/closures y la tabla de slots es una fuente conocida de bugs en sistemas de calendario.

### Opción B — Generar slots en una **vista materializada** Postgres

Vista materializada que se refresca con triggers cuando cambian las tablas fuente.

- **Pros**: similar a Opción A pero el mantenimiento es declarativo (refresh on dependent table change).
- **Cons**:
  - `REFRESH MATERIALIZED VIEW` es bloqueante (a menos que sea `CONCURRENTLY`, que requiere unique index).
  - Triggers para refresh on change añaden latencia a updates de las tablas fuente.
  - La lógica de generación de slots (con `slot_duration_min` y `product.duration_min`) es difícil de expresar como vista SQL pura.
- **Rechazada porque**: tiene los mismos problemas de inconsistencia transitoria, ahora con un mecanismo de refresh más opaco.

### Opción C — Cómputo on-the-fly puro, sin cache

Cada request de disponibilidad recalcula todo. Sin caché.

- **Pros**: cero inconsistencia. Cero mantenimiento.
- **Cons**:
  - Si el cómputo es lento (>500ms p95 con 50 doctores), la UX se degrada. Especialmente el frontend que muestra el calendario semanal de toda la sede (carga muchos cómputos en paralelo).
  - Postgres lee múltiples tablas por request — sin caché, no escala más allá de cierta carga.
- **Rechazada para producción de gran escala**, pero válida como punto de partida.

### Opción D — Aceptada: cómputo on-the-fly + cache TTL corto en Redis (cuando aplique)

- **MVP**: cómputo puro, sin caché. Suficiente para 5-10 doctores con cargas modestas.
- **Cuando p95 supere ~200ms o haya 50+ doctores**: agregar caché Redis de 30-60s por `(doctor_id, from, to)`. Invalidación on-change (al crear/cancelar/reagendar una Appointment del doctor, drop del cache). Redis ya está en `docs/HARDENING.md §1` como hardening pre-prod.
- **Persistido: solo `Appointment`**. Cero gestión de tabla de slots.

## Consequences

### Positivas

- **Cero inconsistencia**: cualquier cambio en patrón/overrides/closures se refleja **inmediatamente** en el siguiente cálculo de disponibilidad.
- **Cero mantenimiento**: ningún job nocturno, ningún trigger, ninguna vista materializada que mantener.
- **Modelo sencillo**: una sola tabla nueva en este módulo (`appointment`). El resto vive en `staff` y `clinic` donde corresponde.
- **Cambios retroactivos triviales**: agregar disponibilidad extra el sábado no requiere regenerar nada — el siguiente cómputo lo incluye.
- **Lógica de "duración del producto requiere N slots contiguos" vive en un solo lugar** (`compute_available_slots`).
- **Tests más simples**: el cálculo de disponibilidad se testea como función pura con fixtures de patrón/overrides/citas. No hay tabla de slots cuyo estado validar.

### Negativas / Trade-offs

- **Cómputo cada request**: a baja escala (5-50 doctores), trivial. A gran escala, hay que cachear. Mitigación documentada.
- **Reportes de "horas vacantes del doctor" requieren correr el cómputo** (no se puede `SELECT COUNT(*) FROM slot WHERE status = 'free' AND ...`). Mitigación: vista materializada de **agregados de utilización** (no de slots individuales) si negocio lo pide. Es aditivo, no rompe nada.
- **Concurrencia al agendar**: dos asesores agendan el mismo slot simultáneamente. Resuelto vía `SELECT FOR UPDATE` sobre las `Appointment` overlapping del doctor en el rango del nuevo slot. Si el segundo intento detecta overlap → `BadRequestException(code="SLOT_TAKEN")`. **No** se usa `UNIQUE(doctor_id, scheduled_for)` porque el conflict es por **rango**, no por punto exacto.
- **Renderizado del calendario semanal de una sede** (vista "todos los doctores del lunes") requiere cómputos por doctor — paralelizable, pero requiere medir.

### Lo que esto nos obliga a hacer

- **`scheduling.services.availability.compute_available_slots()`** es el corazón del módulo. Implementación + tests con fixtures completas.
- **Concurrencia**: el service `create_appointment` envuelve en transacción con `SELECT FOR UPDATE`. Documentado en `docs/modules/scheduling/backend.md`.
- **Métrica de p95 de `availability.compute_available_slots()`** en observabilidad. Cuando supere 200ms p95, activar cache Redis.
- **Tests obligatorios**:
  - Slots libres = patrón ∩ override_extra − override_block − closures − appointments_activas.
  - Producto con `duration_min > slot_duration_min` requiere contiguos.
  - Office no-apto para vertical del producto → 0 slots en ese office.
  - Override `is_available=false` global del doctor → 0 slots ese día.
  - Concurrencia: 2 creates al mismo slot → 1 OK, 1 `SLOT_TAKEN`.

## Referencias

- Ficha del módulo: [`docs/modules/scheduling/README.md`](../modules/scheduling/README.md) (overview + [backend](../modules/scheduling/backend.md) + [ui](../modules/scheduling/ui.md) + [frontend](../modules/scheduling/frontend.md))
- Ficha del módulo staff: [`docs/modules/staff/README.md`](../modules/staff/README.md) — `DoctorAvailability` (bloques concretos por fecha, ver [ADR-007](ADR-007-doctor-availability-concrete-blocks.md)), `Doctor.slot_duration_min`.
- Ficha del módulo clinic: [`docs/modules/clinic/`](../modules/clinic/README.md) — `OfficeOperatingHours`, `OfficeClosure`, `office_vertical`.
- Hardening: [`docs/HARDENING.md`](../HARDENING.md) §1 — Redis para rate limit distribuido y cache.
- Patrón análogo en otros sistemas: Calendly, Google Calendar free/busy API — ambos calculan disponibilidad on-the-fly contra fuentes diversas, no persisten slots individuales.
