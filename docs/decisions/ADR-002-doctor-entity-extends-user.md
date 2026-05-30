# ADR-002: Modelar al Doctor como entidad 1:1 con User, no como columnas en User

> **Status**: Accepted
> **Date**: 2026-05-28
> **Deciders**: @daniel, @marco

## Context

Medisage es un SaaS para una clínica con tres roles operativos: **Admin**, **Doctor** y **Asesor**. Los tres se autentican con el mismo mecanismo de `admin.User` + `Role` (RBAC) del template `saya-template-stack`.

El **Doctor** se diferencia de los otros dos roles porque tiene **datos profesionales propios** y **relaciones M:N específicas**:

- número de colegiatura (CMP),
- biografía pública (que el bot puede leer al lead),
- foto pública,
- firma digital (uso futuro: recetas),
- duración del slot agendable (`slot_duration_min`),
- M:N con **sedes** donde atiende (`doctor_branch`),
- M:N con **verticales** del catálogo que cubre (`doctor_vertical`),
- 1:N con **patrón de disponibilidad** (`doctor_availability_pattern`),
- 1:N con **overrides ad-hoc** (`doctor_availability_override`).

Asesor y Admin no tienen ninguno de estos atributos en el MVP. Lo único distintivo entre ellos es su `Role`.

Tenemos que decidir **dónde viven los datos profesionales del doctor** y **cómo cuelgan las relaciones M:N**. Esto es costoso de revertir porque varios módulos (`scheduling`, `crm`, `conversations`) van a apuntar FKs a la entidad elegida.

## Decision

**`Doctor` es una entidad propia con FK 1:1 a `admin.User`** (columna `user_id varchar(36) UNIQUE NOT NULL`).

- Las relaciones M:N (`doctor_branch`, `doctor_vertical`) y 1:N (`doctor_availability_pattern`, `doctor_availability_override`) cuelgan de `doctor.id`, no de `user.id`.
- Las FKs de otros módulos (`appointment.doctor_id`, etc.) apuntan a `doctor.id`.
- **Asesor y Admin no tienen tabla propia** — son `User` con su `Role` correspondiente. Si en el futuro el negocio pide atributos por asesor (capacity, métricas), se agrega `advisor` 1:1 con `User` de forma aditiva sin tocar nada más.
- La consistencia "todo User con Role DOCTOR debe tener fila en `doctor`" se valida en el service de creación/edición de usuarios, no como constraint en BD.

## Alternatives Considered

### Opción A — Columnas nullables en `User`

- **Pros**: una sola tabla, sin joins. Más simple al hacer `SELECT * FROM user` en exploración.
- **Cons**:
  - Infla `user` con columnas que solo tienen sentido para una porción de las filas (cmp, bio, photo_url, signature_url, slot_duration_min). Cada user no-doctor lleva 5 columnas `NULL`.
  - Las M:N `doctor_branch` y `doctor_vertical` tendrían que vivir como `user_branch` y `user_vertical` con semántica confusa ("¿en qué sedes atiende este admin?").
  - `appointment.doctor_id` tendría que ser `appointment.user_id` y todos los queries de agendamiento tendrían que filtrar `WHERE user.role = 'DOCTOR'` — lento y frágil ante cambios de role.
  - Si mañana queremos atributos propios para asesor, repetimos el problema con más columnas `NULL`.
- **Rechazada porque**: el costo de los `NULL` y la pérdida de claridad semántica supera el beneficio del join.

### Opción B — Single-Table Inheritance (STI) en `User`

Una columna `profile_type ∈ {doctor, advisor, admin}` + todas las columnas específicas como nullables.

- **Pros**: SQLAlchemy soporta STI nativamente con `polymorphic_identity`. Permite hacer `db.query(Doctor)` y obtener solo doctores.
- **Cons**:
  - Las M:N siguen siendo confusas (igual que Opción A) — la tabla de asociación apunta a `user.id` con la promesa implícita de que solo se usan filas con `profile_type='doctor'`.
  - SQLAlchemy STI con `lazy="raise"` y `selectinload` se vuelve frágil cuando una entidad polimórfica está en relaciones M:N selectin. Ya tuvimos sustos en el template con relaciones eager (`User.roles`, `User.permissions`).
  - El template del proyecto (`backend/CLAUDE.md`) menciona que el patrón "User folds Person/identity into one table" se aceptó por simplicidad — extenderlo con polimorfismo va contra esa simplicidad sin un beneficio claro.
- **Rechazada porque**: complica el ORM sin resolver el problema de los M:N apuntando a `user.id` con semántica confusa.

### Opción C — Class Table Inheritance (CTI) en `User`

Tabla `user` base + tabla `doctor` (id FK a `user.id` y PK también) + tabla `advisor` etc. Cada subtipo extiende.

- **Pros**: Limpia conceptualmente. Cada subtipo en su tabla con sus columnas.
- **Cons**:
  - `doctor.id = user.id` significa que el PK de `doctor` es el mismo UUID que `user`. Tema sutil: el `User` tiene mixin `PrimaryKeyMixin` que auto-genera UUID; al crear `Doctor` hay que pasar el UUID del user existente como PK del doctor. SQLAlchemy lo soporta pero requiere cuidado para no romper el patrón uniforme de los demás módulos.
  - Soft-delete dual: si soft-deleto un `Doctor`, ¿qué pasa con el `User`? El template soft-deleta independientemente. Mezclar dos `deleted_at` sobre la misma identidad lógica abre casos de "User vivo, Doctor muerto" que hay que coordinar.
  - Querys de listado de doctores requieren JOIN obligatorio para mostrar `email`/`full_name`. Manejable, pero más fricción que la opción aceptada.
- **Rechazada porque**: el ahorro de columnas se paga con coordinación de identidades y soft-delete dual. La opción aceptada (FK 1:1 con UNIQUE) tiene 99% de los beneficios sin esos costos.

## Consequences

### Positivas

- **`appointment.doctor_id` apunta a un FK semántico** — no requiere validación adicional en agendamiento.
- **`User` queda limpio** y reutilizable para admin/asesor sin columnas muertas.
- **Las M:N específicas del doctor (`doctor_branch`, `doctor_vertical`) son legibles** — la tabla y sus FKs nombran exactamente lo que modelan.
- **Agregar otros perfiles (advisor, technician, ...) es aditivo**: nueva tabla 1:1 con `User`, sin tocar las existentes.
- **`get_by_user_id(db, user_id) → Doctor?`** habilita el patrón `/me/...` para el doctor logueado (resolver `doctor` desde `CurrentAuth.user.id`).

### Negativas / Trade-offs

- **Doble lookup en algunos paths**: para mostrar "Dr. Juan Pérez" en una lista de citas, hay que cargar `appointment → doctor → user` (dos joins). Mitigado con `selectinload` y vistas denormalizadas en los `Item` schemas (incluyen `doctor_name` directamente).
- **Consistencia "User con Role DOCTOR ↔ Doctor exists" es responsabilidad del service**, no del schema. Hay que vigilar en:
  - Crear doctor a partir de un User existente.
  - Quitar el role `DOCTOR` a un user que tiene perfil de doctor activo (debería soft-deletar el doctor o requerir hacerlo antes — decisión cuando se diseñe el servicio).
  - Crear un user con role `DOCTOR` sin crear su `Doctor` (el service de `staff.doctor.create` lo cubre, pero si se asigna el role manualmente desde `admin`, debe forzarse la creación).
- **Soft-delete del Doctor no desactiva el User**: si se quiere "bloquear el acceso del doctor a la plataforma", hay que tocar `user.active = false`. Lo documentaremos en el service.

### Lo que esto nos obliga a hacer

- En `staff.services.doctor`:
  - `create(db, payload, actor_id)` valida que el `user_id` no tenga ya un `doctor` y que el user tenga (o se le asigne en la misma operación) el role `DOCTOR`.
  - `delete(db, doctor_id, actor_id)` soft-deleta `doctor` y deja `user` intacto. Documentar comportamiento.
- En `admin.services.user`:
  - Si se quita el role `DOCTOR` de un user que tiene `doctor` activo, lanzar `BadRequestException(code="USER_HAS_ACTIVE_DOCTOR_PROFILE")`.
- En el seed inicial (`app/core/seed.py`): el usuario bootstrap admin **no** crea perfil de doctor.

## Referencias

- Código relevante (futuro):
  - `backend/app/modules/staff/models/doctor.py`
  - `backend/app/modules/staff/services/doctor.py`
- Patrón del template: el `User` del admin module (`backend/app/modules/admin/models/user.py`) ya documenta en su docstring que se aceptó "fold Person into User". Esta decisión extiende explícitamente al primer caso donde necesitamos perfil profesional aparte.
- Ficha del módulo: [`docs/modules/staff/README.md`](../modules/staff/README.md) (+ `backend.md`/`ui.md`/`frontend.md`)
