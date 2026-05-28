# Módulo `staff`

> **Última actualización**: 2026-05-28
> **Propósito**: perfil profesional de los doctores y su disponibilidad para atender citas.
> **Path del código**: `backend/app/modules/staff/`

## Resumen

`staff` extiende el `User` del módulo `admin` con el perfil profesional del **doctor** (colegiatura, biografía, foto, duración de slot). El doctor:

- está asociado a una o más **sedes** (M:N con `clinic.Branch`);
- está asociado a una o más **verticales** del catálogo (M:N con `catalog.Vertical`);
- declara su disponibilidad como **patrón semanal recurrente** por (sede, consultorio) + **excepciones ad-hoc** (vacaciones, licencias, días extra).

Los **asesores** y los **admin** no tienen tabla propia — son `User` con su `Role` correspondiente. El round-robin de leads en `crm` consulta directamente a `admin.user` filtrando por role.

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Doctor` | `doctor` | Perfil profesional 1:1 con `User`. CMP, bio, foto, duración del slot. |
| `DoctorAvailabilityPattern` | `doctor_availability_pattern` | Patrón semanal recurrente por (doctor, sede, consultorio, día). |
| `DoctorAvailabilityOverride` | `doctor_availability_override` | Excepción ad-hoc: vacaciones, licencia, disponibilidad extra. |
| _(M:N)_ `doctor_branch` | `doctor_branch` | En qué sedes atiende cada doctor. |
| _(M:N)_ `doctor_vertical` | `doctor_vertical` | Qué verticales del catálogo cubre cada doctor. |

### `Doctor`

Entidad 1:1 con `admin.User`. Decisión documentada en [ADR-002](../decisions/ADR-002-doctor-entity-extends-user.md). La regla operativa es: un `User` con `Role = DOCTOR` debe tener una fila correspondiente en `doctor` (validado en el service de creación de usuarios cuando se asigna el role).

- `user_id: varchar(36)` `<<unique, FK→user>>` — relación 1:1.
- `cmp_code: varchar(40)` `<<nullable, indexed>>` — número del Colegio Médico del Perú u homólogo. Nullable para perfiles no-médicos (esteticistas, kinesiólogos). Indexado por si se reportan listados oficiales.
- `bio: text` `<<nullable>>` — biografía pública (lo que el bot puede leer al lead).
- `photo_url: varchar(500)` `<<nullable>>` — foto pública.
- `signature_url: varchar(500)` `<<nullable>>` — firma digital escaneada para futuras recetas.
- `slot_duration_min: int` `default 30` — duración base del slot agendable del doctor. **Ver "Slot duration" abajo**.
- M:N con `clinic.Branch` via `doctor_branch`.
- M:N con `catalog.Vertical` via `doctor_vertical`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `DoctorAvailabilityPattern`

Patrón semanal recurrente. Cada fila representa **un bloque de atención** en un día específico, en una sede y consultorio específicos.

- `doctor_id: varchar(36)` `<<FK→doctor>>`.
- `branch_id: varchar(36)` `<<FK→branch>>` — sede donde se atiende.
- `office_id: varchar(36)` `<<FK→office>>` — consultorio específico (el doctor lo reserva).
- `day_of_week: smallint` — convención Python (0=Lun ... 6=Dom).
- `opens_at: time` — hora local (interpretada en `branch.timezone`).
- `closes_at: time` — CHECK `closes_at > opens_at`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.
- **Sin `UNIQUE` estricto** sobre `(doctor_id, day_of_week)`: un doctor puede tener mañana en Sede A y tarde en Sede B el mismo día. La no-superposición se valida en el service.

**Invariantes validados en el service** (no en CHECK, porque cruzan tablas):
1. El `office_id` declarado debe pertenecer al `branch_id` declarado.
2. El `doctor` debe estar asignado al `branch` (via `doctor_branch`).
3. Dos patterns del mismo doctor no se superponen en el mismo `(day_of_week, office_id)` ni en el mismo `(day_of_week, branch_id, doctor_id)` (el doctor no puede estar en dos lugares a la vez).
4. El bloque debe caber dentro del horario de operación del office (`OfficeOperatingHours`) para ese día.

### `DoctorAvailabilityOverride`

Excepción ad-hoc al patrón. Mismo principio que `clinic.OfficeClosure`: un solo modelo cubre dos casos con `is_available: bool`.

- `doctor_id: varchar(36)` `<<FK→doctor>>`.
- `branch_id: varchar(36)` `<<nullable, FK→branch>>` — ver tabla abajo.
- `office_id: varchar(36)` `<<nullable, FK→office>>` — ver tabla abajo.
- `starts_at: timestamptz` — UTC en BD, ISO 8601 con offset en JSON.
- `ends_at: timestamptz` — CHECK `ends_at > starts_at`.
- `is_available: bool` — `true` = disponibilidad extra; `false` = no disponible.
- `reason: varchar(255)` — texto libre ("Vacaciones", "Capacitación", "Cobertura extra por demanda").
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Regla de `branch_id` / `office_id` según `is_available`** (validado en service, no constraint):

| `is_available` | `branch_id` | `office_id` | Significado |
|---|---|---|---|
| `false` | `NULL` | `NULL` | Doctor no disponible globalmente en el rango (vacaciones). |
| `false` | requerido | `NULL` | No disponible solo en esa sede en el rango. |
| `false` | requerido | requerido | No disponible solo en ese office en el rango. |
| `true` | requerido | requerido | Disponibilidad extra: dónde se atiende debe quedar claro. |

## Esquemas (Pydantic v2)

Por entidad las variantes son `Create / Update / Item / Detail / Option`.

**Decisión específica para `DoctorAvailabilityPattern`**: se gestiona con **bulk PUT** (`PUT /doctors/{id}/availability/patterns`) — coherente con `OfficeOperatingHours` y por la misma razón: el patrón semanal es un agregado, editar bloques uno por uno abre estados intermedios inválidos.

**`DoctorAvailabilityOverride`**: CRUD individual (cada excepción es una unidad con su razón).

**Creación de Doctor**: el `DoctorCreate` recibe `user_id` (un User existente con role DOCTOR) **o** un payload anidado para crear el User en la misma operación. Decidido por el service:
- Si `user_id` viene → vincula el doctor a ese user; valida que el user no tenga ya un doctor.
- Si `user` (payload nested) viene → crea User (asignando role DOCTOR) y doctor en la misma transacción.

Schemas adicionales:
- `DoctorAvailabilityPatternItem { id, day_of_week, branch_id, branch_name, office_id, office_name, opens_at, closes_at }`
- `DoctorAvailabilityPatternReplace { patterns: list[DoctorAvailabilityPatternInput] }` — body del bulk PUT. Cada input solo lleva `branch_id, office_id, day_of_week, opens_at, closes_at`.

## Endpoints

Todos bajo `/api/v1/staff/`.

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `POST` | `/doctors/list` | `DOCTORS_READ` | listado paginado |
| `POST` | `/doctors` | `DOCTORS_CREATE` | crear (vincula a User existente o crea ambos) |
| `GET` | `/doctors/{id}` | `DOCTORS_READ` | detalle (incluye user, branches, verticals) |
| `PATCH` | `/doctors/{id}` | `DOCTORS_UPDATE` | actualizar (incluye `branch_ids`, `vertical_ids`) |
| `DELETE` | `/doctors/{id}` | `DOCTORS_DELETE` | soft delete (NO borra User asociado) |
| `GET` | `/doctors/options?branch_id=&vertical_id=` | `DOCTORS_READ` | dropdown filtrable |
| `GET` | `/doctors/{id}/availability/patterns` | `DOCTOR_AVAILABILITY_READ` | listar patrón semanal |
| `PUT` | `/doctors/{id}/availability/patterns` | `DOCTOR_AVAILABILITY_WRITE` | bulk replace del patrón completo |
| `GET` | `/doctors/{id}/availability/overrides?from=&to=` | `DOCTOR_AVAILABILITY_READ` | listar overrides en rango |
| `POST` | `/doctors/{id}/availability/overrides` | `DOCTOR_AVAILABILITY_WRITE` | agregar override |
| `DELETE` | `/doctors/{id}/availability/overrides/{ov_id}` | `DOCTOR_AVAILABILITY_WRITE` | eliminar override |
| `GET` | `/me/doctor` | `MY_DOCTOR_PROFILE_READ` | perfil del doctor logueado |
| `PATCH` | `/me/doctor` | `MY_DOCTOR_PROFILE_WRITE` | editar bio, foto, slot_duration |
| `GET` | `/me/availability/patterns` | `MY_AVAILABILITY_READ` | self-service del doctor |
| `PUT` | `/me/availability/patterns` | `MY_AVAILABILITY_WRITE` | self-service del doctor |
| `GET` | `/me/availability/overrides` | `MY_AVAILABILITY_READ` | self-service del doctor |
| `POST` | `/me/availability/overrides` | `MY_AVAILABILITY_WRITE` | self-service del doctor |
| `DELETE` | `/me/availability/overrides/{ov_id}` | `MY_AVAILABILITY_WRITE` | self-service del doctor |

**Endpoints `/me/...`**: el service resuelve el `doctor_id` desde `CurrentAuth.user.id` (`doctor_repository.get_by_user_id(...)`). Si el user logueado no tiene perfil de doctor, devuelve `403 ForbiddenException(code="NOT_A_DOCTOR")`. Esto separa "editar mi propia disponibilidad" (rol DOCTOR) de "editar la disponibilidad de cualquier doctor" (rol ADMIN).

## Permisos seed

Agregar a `app/core/seed.py:SEED_PERMISSIONS`:

```python
# Module: staff
("MENU-STAFF", "Ver menú staff", "Gestión de doctores y disponibilidad", "staff"),
("DOCTORS_READ", "Ver doctores", "Listar y consultar doctores", "staff"),
("DOCTORS_CREATE", "Crear doctores", "Crear nuevos doctores", "staff"),
("DOCTORS_UPDATE", "Editar doctores", "Editar perfiles de doctores", "staff"),
("DOCTORS_DELETE", "Eliminar doctores", "Soft-delete de doctores", "staff"),
("DOCTOR_AVAILABILITY_READ", "Ver disponibilidad ajena", "Consultar agenda de cualquier doctor", "staff"),
("DOCTOR_AVAILABILITY_WRITE", "Editar disponibilidad ajena", "Editar agenda de cualquier doctor", "staff"),
("MY_DOCTOR_PROFILE_READ", "Ver mi perfil de doctor", "Consultar mi propio perfil", "staff"),
("MY_DOCTOR_PROFILE_WRITE", "Editar mi perfil de doctor", "Editar mi bio, foto, slot_duration", "staff"),
("MY_AVAILABILITY_READ", "Ver mi disponibilidad", "Consultar mi propio patrón y overrides", "staff"),
("MY_AVAILABILITY_WRITE", "Editar mi disponibilidad", "Self-service de patrón y overrides", "staff"),
```

**Roles seed que tocan `staff`**:
- `ADMIN` — todos.
- `DOCTOR` — `MENU-STAFF`, `DOCTORS_READ`, `MY_DOCTOR_PROFILE_*`, `MY_AVAILABILITY_*`. **No** edita disponibilidad ni perfil de otros doctores.
- `ASESOR` — `DOCTORS_READ`, `DOCTOR_AVAILABILITY_READ` (necesita ver agenda para agendar leads).

## Decisiones de diseño

### Doctor como entidad 1:1 con User
Documentado en [ADR-002](../decisions/ADR-002-doctor-entity-extends-user.md). Alternativas (columnas en User, single-table inheritance) y su rechazo viven ahí.

### Asesor / Admin sin tabla propia
Confirmado por el usuario. Razón: estos roles **no necesitan datos profesionales** ni relaciones M:N propias en el MVP. `admin.user` con su `Role` basta. Si el negocio pide más adelante (ej. capacity por asesor, métricas de cierre, cuotas), se agrega `advisor` 1:1 con User de forma aditiva.

### Pattern a nivel (doctor, branch, office) — el doctor reserva consultorio

Confirmado por usuario. Razón: la clínica conoce qué doctor usa qué consultorio porque el doctor lo declara — no hay sorpresa de "te asigno el consultorio que esté libre". Esto también permite que `scheduling` sea determinista: dado un slot del doctor, ya sabemos en qué office se atiende, y validamos en service que ese office sea apto para la vertical del producto (`office_vertical` M:N).

**Trade-off explícito**: si dos doctores quieren atender el mismo consultorio en el mismo horario, hay conflicto. Lo detectamos al `PUT /patterns` con el invariante #3 — el service consulta y rechaza con `BadRequestException(code="OFFICE_OCCUPIED")` indicando quién ya lo tiene.

### `slot_duration_min` en `Doctor` (no por (doctor, product))

Confirmado por usuario. El slot del doctor es la unidad temporal mínima de su agenda. Cuando `scheduling` agenda una cita:

- `product.duration_min` = duración real esperada de la atención.
- `doctor.slot_duration_min` = grano de su calendario.

**Reglas de cómputo** (documentadas para el módulo `scheduling`):

- Si `product.duration_min` es `NULL` → reservar 1 slot del doctor.
- Si `product.duration_min <= doctor.slot_duration_min` → reservar 1 slot.
- Si `product.duration_min > doctor.slot_duration_min` → reservar `ceil(product.duration_min / doctor.slot_duration_min)` slots **contiguos**. Si no hay contiguos suficientes, scheduling rechaza con `BadRequestException(code="NO_CONTIGUOUS_SLOTS")`.

Esto evita inventar una tabla `doctor_product_duration` antes de tiempo. Si negocio quiere durations específicas por (doctor, product), se agrega después.

### `DoctorAvailabilityOverride` con `branch_id`/`office_id` nullable

Vacaciones del doctor pisan TODA su disponibilidad (cualquier sede, cualquier consultorio). Una apertura extra requiere saber dónde. La tabla acepta ambos casos con `NULL` en lo aplicable; la validación es de service, no constraint, porque depende de `is_available`.

**Por qué no `CHECK` constraint**: las constraints expresables son del estilo `(is_available = false) OR (branch_id IS NOT NULL AND office_id IS NOT NULL)`. Funciona, pero esconde un caso válido (override "no disponible solo en Sede X"). Mantenerlo en el service deja la regla legible y permite mensajes de error específicos.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `admin` | `doctor.user_id` (FK 1:1). Audit users por mixin Timestamp. |
| `clinic` | `doctor_branch` M:N → `clinic.branch`; `doctor_availability_pattern.branch_id/office_id` (FKs); override branch/office (FKs nullable). |
| `catalog` | `doctor_vertical` M:N → `catalog.vertical`. |
| `scheduling` | Consume pattern + overrides + `slot_duration_min` para calcular slots libres. NO escribe en `staff`. |

## Diagramas

- ER: [`docs/diagrams/er-staff.puml`](../diagrams/er-staff.puml)
- Class: [`docs/diagrams/class-backend-staff.puml`](../diagrams/class-backend-staff.puml)

## Próximos pasos / TODOs deliberados

- [ ] Cuando se diseñe `scheduling`, verificar que el cálculo de slots use índices `(doctor_id, day_of_week)` y `(office_id, day_of_week)` para `DoctorAvailabilityPattern`. Considerar índice compuesto si los queries lo justifican.
- [ ] Validar al consolidar permisos que `MY_AVAILABILITY_*` se asigne automáticamente a cualquier user con role DOCTOR (o cubrirlo desde el role en seed).
- [ ] Si el negocio quiere ver "el calendario consolidado de la sede" (todos los doctores en una vista), eso se construye en `scheduling` agrupando patterns por branch — no requiere nueva tabla.
- [ ] Considerar `DoctorVerticalCertification` si en el futuro la clínica quiere registrar certificaciones específicas por vertical (ej. "Dr. X está certificado para HydraFacial Premium"). Por ahora `doctor_vertical` basta.
