# ADR-007: Disponibilidad del doctor como bloques concretos por fecha (no patrón semanal recurrente)

> **Status**: Accepted
> **Date**: 2026-05-29
> **Deciders**: @daniel, @marco
> **Relacionado**: refina las entradas de [ADR-006](ADR-006-hybrid-calendar-slots.md) (que sigue vigente); no toca [ADR-002](ADR-002-doctor-entity-extends-user.md).

## Context

El diseño inicial del módulo `staff` (overview `docs/modules/staff.md` + el modelo de entrada de [ADR-006](ADR-006-hybrid-calendar-slots.md)) modelaba la disponibilidad del doctor como:

- `DoctorAvailabilityPattern` — **patrón semanal recurrente** (`day_of_week`, `opens_at`, `closes_at`) por `(doctor, branch, office)`. Implica "todos los lunes 8–13 en el consultorio X, indefinidamente, hasta que se cambie".
- `DoctorAvailabilityOverride` — **excepciones ad-hoc** sobre un rango `timestamptz` con flag `is_available` (vacaciones / licencia / disponibilidad extra).

Al validar el módulo con el usuario surgió una corrección de dominio importante: **los doctores de esta clínica no tienen un horario semanal fijo**. Cada mes (re)definen sus horarios concretos y cambian de un mes a otro. Es decir, la recurrencia casi nunca se sostiene: el "patrón" se estaría reemplazando mes a mes, y la dualidad patrón + override constante para representar lo que en realidad es "el calendario real de este mes" es complejidad que no paga su costo.

Esta decisión es costosa de revertir porque `scheduling` (ADR-006) consume estas entidades para calcular slots, y la UI del calendario se construye sobre el modelo elegido.

## Decision

**La disponibilidad del doctor se modela como una sola entidad `DoctorAvailability` de bloques concretos por fecha.** Se eliminan `DoctorAvailabilityPattern` (recurrente) y `DoctorAvailabilityOverride` (flag `is_available`).

- `DoctorAvailability { doctor_id, branch_id, office_id, date, opens_at, closes_at }` — un bloque puntual: el doctor atiende **esa fecha**, de `opens_at` a `closes_at`, en ese `(branch, office)`. La hora local se interpreta en `branch.timezone` (igual que `clinic.OfficeOperatingHours`, pero con fecha concreta en vez de `day_of_week`). CHECK `closes_at > opens_at`. Sin recurrencia, sin `is_available`.
- Semántica derivada (sin tablas ni flags extra):
  - **"No disponible"** un día = **no hay bloque** esa fecha.
  - **"Disponibilidad extra"** = **agregar un bloque** en esa fecha.
  - **"Vacaciones" / licencia** = **sin bloques** en el rango.
  - **Cierre del consultorio** (feriado, mantenimiento) NO vive aquí — sigue en `clinic.OfficeClosure`; `scheduling` lo resta.
- Edición: **CRUD por bloque** (crear / editar / borrar) + **alta masiva** (un POST con varios bloques) para "llenar varios días a la vez". UI = **grilla semanal tipo calendario** (ver [`docs/modules/staff/ui.md`](../modules/staff/ui.md)).
- Invariantes cross-tabla (validados en el service, con `code`): `OFFICE_NOT_IN_BRANCH`, `DOCTOR_NOT_IN_BRANCH`, `AVAILABILITY_OVERLAP` (dos bloques del mismo doctor en la misma fecha no se solapan; adyacentes OK).

## Alternatives Considered

### Opción A — Patrón semanal recurrente + excepciones (el diseño original)
- **Pros**: si un doctor tuviera horario estable, lo declara una vez; las vacaciones/aperturas extra son overrides puntuales.
- **Cons**: dado que el horario **cambia cada mes**, el "patrón recurrente" es una abstracción que casi nunca se cumple — se reemplazaría mensualmente. La dualidad patrón + override obliga a combinar dos fuentes por día en `scheduling` y en la UI, para representar algo que es, en el fondo, "el calendario concreto de este mes".
- **Rechazada porque**: agrega complejidad (recurrencia + flag + dos tablas + combinación) sin beneficio real para el patrón de uso observado (redefinición mensual).

### Opción B — Plantilla recurrente opcional + bloques concretos
- **Pros**: lo mejor de ambos para clínicas mixtas (algunos estables, otros variables).
- **Cons**: sigue cargando la maquinaria de recurrencia (y su combinación con lo concreto) para una minoría de casos; más superficie que mantener en MVP.
- **Rechazada (por ahora)**: si en el futuro aparecen doctores con horario realmente estable y el data-entry molesta, se puede agregar una **plantilla** como ayuda de UI que **genere bloques concretos** (no como entidad recurrente persistida) — aditivo, sin tocar el modelo.

### Opción C — Bloques concretos por fecha (Aceptada)
- Una sola entidad, sin recurrencia, sin flag. Ver Decision.

## Consequences

### Positivas
- **Modelo más simple**: una entidad en vez de dos; sin recurrencia ni flag `is_available`.
- **`scheduling` se simplifica**: `compute_available_slots` pasa de "combinar pattern + override por día" a `bloques_del_doctor ∩ horario_del_office − office_closures − citas_activas` (más los pre-filtros de vertical/office apto y el grano `slot_duration_min`). Ver actualización en [ADR-006](ADR-006-hybrid-calendar-slots.md).
- **Cero ambigüedad**: lo que el doctor ve es lo que hay; "no disponible" es la ausencia de bloque, no un override que pisa un patrón invisible.
- **Refleja la realidad** descrita por el usuario (redefinición mensual).

### Negativas / Trade-offs
- **Data-entry**: el doctor debe llenar su calendario cada periodo (no hay "se repite solo"). **Mitigación**: la UI es una **grilla semanal** con click/arrastre para pintar bloques y **alta masiva multi-día** ("aplicar el mismo horario a varios días"); a futuro, un helper "copiar semana/mes anterior" o "aplicar plantilla L-V" que genere bloques concretos (aditivo).
- **Sin traza histórica de "cómo era el patrón"**: no aplica — nunca hubo patrón; cada bloque es un hecho concreto con fecha.
- **Volumen de filas**: ~N bloques/doctor/mes (chico); soft-delete acumula filas retiradas (despreciable; mismo criterio que el resto del template).

### Lo que esto nos obliga a hacer
- `staff` implementa **una sola entidad** `DoctorAvailability` (no Pattern/Override). Fichas: [`staff/README.md`](../modules/staff/README.md), [`staff/backend.md`](../modules/staff/backend.md), [`staff/ui.md`](../modules/staff/ui.md), [`staff/frontend.md`](../modules/staff/frontend.md).
- **Actualizar [ADR-006](ADR-006-hybrid-calendar-slots.md)**: el pseudocódigo de `compute_available_slots` usa **bloques concretos** en vez de `pattern_for(day) + overrides_in(day)`. (Hecho: ver la nota de actualización en ADR-006.)
- **Regenerar** `docs/diagrams/er-staff.puml` y `class-backend-staff.puml`: quitar `DoctorAvailabilityPattern`/`DoctorAvailabilityOverride`, dejar `DoctorAvailability`.
- **Borrar** el overview viejo `docs/modules/staff.md` (consolidado en `staff/README.md`).

## Referencias

- Ficha del módulo: [`docs/modules/staff/README.md`](../modules/staff/README.md) (sección "Decisiones de diseño › Modelo de disponibilidad").
- [ADR-006](ADR-006-hybrid-calendar-slots.md) — slots híbridos (decisión núcleo intacta; entradas refinadas por este ADR).
- [ADR-002](ADR-002-doctor-entity-extends-user.md) — Doctor 1:1 con User (sin cambios).
