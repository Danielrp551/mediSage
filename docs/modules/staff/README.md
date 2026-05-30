# Módulo `staff`

> **Última actualización**: 2026-05-29
> **Propósito**: perfil profesional del **doctor** (1:1 con `admin.User`) — colegiatura, biografía, foto, firma, grano de slot — más las sedes/verticales que cubre y su **disponibilidad** concreta (cuándo y dónde puede ser agendado). Alimenta a `scheduling` (ADR-006).
> **Path del código**: `backend/app/modules/staff/` (backend) · `frontend/src/app/(main)/staff/` (frontend).

> **Este documento es el overview**. Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts, lógica.
> - 🎨 [`ui.md`](ui.md) — mockups, estados, componentes Fluent UI (incl. la grilla semanal de disponibilidad).
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación.

## Resumen

`staff` es el módulo de **personas que atienden**. Hoy modela un único perfil profesional: el **doctor**, una entidad 1:1 con `admin.User` ([ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md)). Asesor y Admin **no tienen tabla propia** — son `User` con su `Role` correspondiente; si el negocio pide atributos por asesor más adelante (capacity, métricas), se agrega `advisor` 1:1 con `User` de forma aditiva, sin tocar lo existente.

```
Doctor (perfil profesional, 1:1 con admin.User)
   ├─ doctor_branch    (M:N → clinic.Branch)        sedes donde atiende
   ├─ doctor_vertical  (M:N → catalog.Vertical)      verticales que cubre
   └─ DoctorAvailability (1:N)                        bloques concretos por fecha (cuándo y dónde)
```

Cada `Doctor` extiende a un `User` con datos que solo tienen sentido para quien atiende (CMP, bio, foto, firma, `slot_duration_min`), declara en qué **sedes** atiende (M:N con `clinic.Branch`) y qué **verticales** del catálogo cubre (M:N con `catalog.Vertical`), y publica su **disponibilidad** como una colección de **bloques concretos por fecha** (`DoctorAvailability`).

Es la pieza sobre la que `scheduling` calcula slots disponibles ([ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md)): el cómputo intersecta los **bloques del doctor** con el **horario del office** (`clinic.OfficeOperatingHours`), resta los **cierres del office** (`clinic.OfficeClosure`) y las **citas activas**, y filtra por **vertical apta** (`office_vertical`) y por **grano de slot** del doctor (`Doctor.slot_duration_min`).

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Doctor` | `doctor` | Perfil profesional 1:1 con `admin.User`. CMP, bio, foto, firma, grano de slot. |
| `DoctorAvailability` | `doctor_availability` | Bloque **concreto por fecha** de disponibilidad: `(date, opens_at, closes_at)` en un `(branch, office)`. |
| _(M:N)_ `doctor_branch` | `doctor_branch` | En qué sedes atiende cada doctor. Asociación → `clinic.Branch`. |
| _(M:N)_ `doctor_vertical` | `doctor_vertical` | Qué verticales del catálogo cubre cada doctor. Asociación → `catalog.Vertical`. |

Las dos tablas de asociación viven en `staff/models/associations.py`. Siguen el mismo patrón que `clinic.office_vertical`: el lado **hijo** (`doctor_id`) es `ON DELETE CASCADE`, el lado **padre externo** (`branch_id`, `vertical_id`) es `ON DELETE RESTRICT` (backstop ante un hard-delete de la sede/vertical; el soft-delete se tolera filtrando, ver [Decisiones](#cross-module-consistencia-de-soft-delete-y-roles)).

### `Doctor`

Entidad 1:1 con `admin.User`. Decisión documentada en [ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md) (alternativas — columnas en `User`, STI, CTI — y su rechazo viven ahí). La regla operativa: un `User` con `Role = DOCTOR` tiene una fila correspondiente en `doctor`; la consistencia se valida en el service, no como constraint en BD.

- `user_id: varchar(36)` `<<unique, FK→user, NOT NULL>>` — relación 1:1. **Inmutable** post-creación (no aparece en `DoctorUpdate`).
- `cmp_code: varchar(40)` `<<nullable, indexed>>` — número del Colegio Médico del Perú u homólogo. Nullable para perfiles no-médicos (esteticistas, kinesiólogos). Indexado por si se reportan listados oficiales.
- `bio: Text` `<<nullable>>` — biografía pública (lo que el bot puede leer al lead).
- `photo_url: varchar(500)` `<<nullable>>` — foto pública.
- `signature_url: varchar(500)` `<<nullable>>` — firma digital escaneada (uso futuro: recetas).
- `slot_duration_min: int` `NOT NULL default 30` — grano del calendario del doctor. **Ver "Slot duration" en [Decisiones](#slot_duration_min-en-doctor-no-por-doctor-product)**.
- M:N con `clinic.Branch` via `doctor_branch`.
- M:N con `catalog.Vertical` via `doctor_vertical`.
- 1:N `availability` (`DoctorAvailability`) — `lazy="raise"` (se carga explícitamente vía `get_full`).
- Mixins: `PrimaryKeyMixin`, `ActiveMixin`, `SoftDeleteMixin`, `TimestampMixin`.

### `DoctorAvailability`

Bloque **concreto por fecha** de disponibilidad: declara que el doctor atiende el `date` desde `opens_at` hasta `closes_at` en un `(branch, office)` específico. **Reemplaza** al par `DoctorAvailabilityPattern` + `DoctorAvailabilityOverride` del overview viejo (patrón semanal recurrente + excepciones) — ver [Decisiones › Modelo de disponibilidad](#modelo-de-disponibilidad-bloques-concretos-por-fecha-en-vez-de-patrón-semanal--excepciones).

- `doctor_id: varchar(36)` `<<FK→doctor, NOT NULL, indexed>>`.
- `branch_id: varchar(36)` `<<FK→branch, NOT NULL>>` — sede donde se atiende.
- `office_id: varchar(36)` `<<FK→office, NOT NULL>>` — consultorio específico (el doctor lo reserva; ver [Decisiones](#el-doctor-reserva-consultorio-disponibilidad-a-nivel-doctor-branch-office)).
- `date: Date` `NOT NULL` — fecha concreta. La hora local se interpreta en `branch.timezone`.
- `opens_at: Time(timezone=False)` `NOT NULL` — hora local de apertura del bloque.
- `closes_at: Time(timezone=False)` `NOT NULL` — hora local de cierre. CHECK `closes_at > opens_at` (constraint `ck_doctor_availability_closes_after_opens`); un bloque no cruza medianoche.
- Index `ix_doctor_availability_doctor_id` sobre `doctor_id`. Index compuesto opcional `(doctor_id, date)` para las queries por rango.
- Mixins: `PrimaryKeyMixin`, `ActiveMixin`, `SoftDeleteMixin`, `TimestampMixin`.
- **NO** hay `day_of_week`, **NO** hay `is_available`, **NO** hay recurrencia. Cada fila es un bloque puntual.

**Semántica derivada del modelo de bloques concretos:**

| Caso de negocio | Cómo se representa |
|---|---|
| "No disponible" un día | **No hay bloque** para esa fecha. |
| "Disponibilidad extra" (abrir un sábado) | **Agregar un bloque** en esa fecha. |
| "Vacaciones" / licencia | **Sin bloques** en el rango de fechas. |
| Cierre del consultorio (feriado, mantenimiento) | NO vive aquí — sigue en `clinic.OfficeClosure`; `scheduling` lo resta al computar slots. |

## Endpoints (resumen)

Todos bajo `/api/v1/staff/`. Listado paginado con `POST /list` + `QueryRequest`. Convención **`PUT` (no `PATCH`) para updates** y **`/active` (no `/options`) para dropdowns** — alineada al catálogo y a clinic ya shipped (una sola convención en el codebase). Los `/active` devuelven **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`); el resto usa los envelopes del template (`SingleResponse` / `PaginatedResponse`). Detalle de request/response en [`backend.md`](backend.md#api-contracts).

### Doctores (admin)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `POST` | `/doctors/list` | `DOCTORS_READ` | listado paginado |
| `POST` | `/doctors` | `DOCTORS_CREATE` | crear **nested** (user + doctor en una transacción) → `201` `SingleResponse[DoctorCreatedResponse]` |
| `GET` | `/doctors/{id}` | `DOCTORS_READ` | detalle (incluye `user`, `branches`, `verticals`) |
| `PUT` | `/doctors/{id}` | `DOCTORS_UPDATE` | actualizar (`branch_ids`/`vertical_ids` = reemplazo total del M:N) |
| `DELETE` | `/doctors/{id}` | `DOCTORS_DELETE` | soft delete (**NO** toca el `User` asociado) |
| `GET` | `/doctors/active?branch_id=&vertical_id=` | `DOCTORS_READ` | dropdown filtrable (lista cruda de `DoctorOption`) |

### Disponibilidad de un doctor (admin)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `GET` | `/doctors/{id}/availability?from=&to=` | `DOCTOR_AVAILABILITY_READ` | bloques en rango de fechas (`SingleResponse[list[Item]]`); `from`/`to` = `date` ISO `YYYY-MM-DD`, filtran `date` entre `from..to` |
| `POST` | `/doctors/{id}/availability` | `DOCTOR_AVAILABILITY_WRITE` | alta masiva: body `DoctorAvailabilityBulkCreate {blocks:[...]}` → `201` `SingleResponse[list[Item]]` |
| `PUT` | `/doctors/{id}/availability/{block_id}` | `DOCTOR_AVAILABILITY_WRITE` | editar un bloque (mover/redimensionar) → `SingleResponse[Item]` |
| `DELETE` | `/doctors/{id}/availability/{block_id}` | `DOCTOR_AVAILABILITY_WRITE` | borrar un bloque → `204` |

### Self-service `/me` (el doctor logueado) — fase F3

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/me/doctor` | `MY_DOCTOR_PROFILE_READ` |
| `PUT` | `/me/doctor` | `MY_DOCTOR_PROFILE_WRITE` (solo `bio`/`photo_url`/`signature_url`/`slot_duration_min`; **NO** `branches`/`verticals` — eso es admin) |
| `GET` | `/me/availability?from=&to=` | `MY_AVAILABILITY_READ` |
| `POST` | `/me/availability` | `MY_AVAILABILITY_WRITE` |
| `PUT` | `/me/availability/{block_id}` | `MY_AVAILABILITY_WRITE` |
| `DELETE` | `/me/availability/{block_id}` | `MY_AVAILABILITY_WRITE` |

> **Endpoints `/me/...`**: el service resuelve el `doctor` desde `CurrentAuth.user.id` vía `doctor_repository.get_by_user_id(...)`. Si el user logueado no tiene perfil de doctor → `403 ForbiddenException(code="NOT_A_DOCTOR")`. Esto separa "editar mi propia disponibilidad" (role `DOCTOR`) de "editar la disponibilidad de cualquier doctor" (role `ADMIN`).

> **Códigos de error de dominio** (mensajes `detail` en **español**, `code` en inglés): `DOCTOR_NOT_FOUND` (404), `AVAILABILITY_NOT_FOUND` (404, también cubre el caso de un block que no pertenece al doctor — ownership), `EMAIL_TAKEN` (409, email del user nested ya existe), `OFFICE_NOT_IN_BRANCH` (400), `DOCTOR_NOT_IN_BRANCH` (400), `AVAILABILITY_OVERLAP` (400, dos bloques del mismo doctor en la misma `date` se solapan), `NOT_A_DOCTOR` (403, `/me/*` sin perfil). Los mensajes de los validators Pydantic van en inglés (el front re-valida con Zod). Mismo criterio que clinic.

## Permisos seed

11 permisos. Ya consolidados en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md).

```python
# Module: staff
("MENU-STAFF",                "Menu Staff",                    "STAFF"),
("DOCTORS_READ",              "Read doctors",                  "STAFF"),
("DOCTORS_CREATE",           "Create doctors",                "STAFF"),
("DOCTORS_UPDATE",            "Update doctors",                "STAFF"),
("DOCTORS_DELETE",            "Delete doctors",                "STAFF"),
("DOCTOR_AVAILABILITY_READ",  "Read any doctor availability",  "STAFF"),
("DOCTOR_AVAILABILITY_WRITE", "Write any doctor availability", "STAFF"),
("MY_DOCTOR_PROFILE_READ",    "Read my doctor profile",        "STAFF"),
("MY_DOCTOR_PROFILE_WRITE",   "Write my doctor profile",       "STAFF"),
("MY_AVAILABILITY_READ",      "Read my availability",          "STAFF"),
("MY_AVAILABILITY_WRITE",     "Write my availability",         "STAFF"),
```

**Roles seed** (F0 introduce el helper genérico `_seed_role` + los roles `DOCTOR` y `ASESOR`; `SYSTEM` se difiere):

- `ADMIN` — **todos** los permisos (incluidos los de staff).
- `DOCTOR` — subset **disponible hoy** (de `_seed-and-roles.md`): `MENU-HOME`, `MENU-CATALOG` + `*_READ` de catálogo, `*_READ` de clinic, `MENU-STAFF`, `DOCTORS_READ`, `MY_DOCTOR_PROFILE_*`, `MY_AVAILABILITY_*`. Los de `scheduling`/`crm` se suman cuando existan esos módulos; el `_seed_role` filtra los códigos inexistentes. **No** edita disponibilidad ni perfil de otros doctores (`DOCTOR_AVAILABILITY_WRITE` queda fuera).
- `ASESOR` — subset **disponible hoy**: `MENU-HOME`, `MENU-CATALOG` + `*_READ` de catálogo, `MENU-CLINIC` + `BRANCHES_READ` + `OFFICES_READ`, `DOCTORS_READ`, `DOCTOR_AVAILABILITY_READ` (necesita ver agenda para agendar leads). Crece al sumar `crm`/`conversations`/`scheduling`/`marketing`.

El helper genérico `_seed_role(db, actor_id, name, description, permission_codes, all_permissions)` filtra `[p for p in all_permissions if p.code in codes]` — los códigos faltantes se **omiten** (idempotente y a prueba de módulos futuros), de modo que el subset de `DOCTOR`/`ASESOR` se puede declarar con su forma final (incluyendo permisos de módulos aún no implementados) sin romper el seed. Reemplaza al `_seed_admin_role` único del template, que se generaliza a este helper. El role `SYSTEM` (user técnico no autenticable, `active=false`, usado como `created_by` de operaciones automáticas) se **difiere** a una fase posterior.

## Decisiones de diseño (no obvias)

### Modelo de disponibilidad: bloques concretos por fecha, en vez de patrón semanal + excepciones

**Cambio vs lo documentado.** El overview viejo ([`docs/modules/staff.md`](../staff.md), que este README reemplaza) y [ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md) asumían un **patrón semanal recurrente** (`DoctorAvailabilityPattern` con `day_of_week`) + **excepciones ad-hoc** (`DoctorAvailabilityOverride` con `is_available`). **Se reemplaza** por una sola entidad `DoctorAvailability` de **bloques concretos por fecha** — sin recurrencia, sin flag `is_available`, sin la tabla de overrides.

**Por qué** (confirmado por el usuario): los doctores **no tienen horario fijo**. Cada mes (re)definen sus horarios concretos y cambian. Modelar un patrón recurrente que casi nunca se cumple, y luego pisarlo con overrides constantes, es más complejo que simplemente declarar los bloques reales de cada fecha. Con bloques concretos: "no disponible" = no hay bloque; "disponibilidad extra" = agregar bloque; "vacaciones" = sin bloques en el rango. El cierre del consultorio sigue en `clinic.OfficeClosure` (que `scheduling` resta).

**Implicancia para `scheduling`**: `compute_available_slots` se **simplifica** a `bloques_del_doctor ∩ horario_del_office − office_closures − citas_activas` (más los pre-filtros tabulares de vertical/office apto y el grano de slot). Ya no hay que combinar pattern + override por día.

**Estado de los ADR**: [ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md) (doctor 1:1 con user) **sigue válido sin cambios**. [ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md) **se actualizará/supersedirá aparte** para reflejar bloques concretos en vez de pattern+override; el resto del ADR-006 (solo persiste `Appointment`, disponibilidad on-the-fly, cache TTL cuando aplique) sigue intacto. Estas fichas asumen el **modelo nuevo**.

### Creación de Doctor anidada (nested user + doctor)

**Confirmado por usuario.** `DoctorCreate` lleva un payload **anidado** `user` (no un `user_id` de un user existente). El service crea el `User` (asignándole el role `DOCTOR`) **y** el `Doctor` en una sola transacción.

- `DoctorCreate { user: DoctorUserCreate, cmp_code?, bio?, photo_url?, signature_url?, slot_duration_min=30, branch_ids: list[str], vertical_ids: list[str] }`.
- `DoctorUserCreate` es el espejo del `UserCreate` del admin (`email`, `first_name`, `last_name`, `second_last_name?`, `document_type?`, `document_number?`, `phone?`, `password?`). El `password` es **opcional**: si falta, se genera uno temporal (igual que `admin.user.create`).
- `DoctorCreatedResponse { data: DoctorDetail, generated_password: str | None }` — devuelve la contraseña temporal **solo si se generó** (igual que `UserCreatedResponse`).
- Validaciones: email único (`409 EMAIL_TAKEN`); `branch_ids`/`vertical_ids` deben existir y estar vivos (`400` si no); el doctor queda con el role `DOCTOR`.

**Por qué nested y no `user_id`**: el flujo real es "dar de alta a un doctor", no "convertir un user existente en doctor". Forzar a crear primero el user en `admin` y luego vincularlo duplicaría pasos. El service cubre la consistencia de [ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md) ("user con role `DOCTOR` ↔ existe `Doctor`") en una sola operación atómica.

### El doctor reserva consultorio (disponibilidad a nivel `(doctor, branch, office)`)

**Confirmado por usuario.** Cada `DoctorAvailability` es `(doctor, branch, office, date, horas)` — el doctor **declara** en qué consultorio se atiende. No hay "te asigno el office que esté libre". Esto hace a `scheduling` determinista: dado un bloque del doctor, ya se sabe en qué office se atiende, y se valida que ese office sea apto para la vertical del producto (`office_vertical` M:N).

**Invariantes validados en el service** (no en CHECK, porque cruzan tablas; cada uno con su `code`):

1. `office_id` pertenece a `branch_id` → `400 OFFICE_NOT_IN_BRANCH`.
2. El doctor está asignado a `branch_id` (via `doctor_branch`) → `400 DOCTOR_NOT_IN_BRANCH`.
3. **No-solapamiento**: dos bloques del **mismo doctor** en la **misma `date`** no pueden solaparse en `[opens_at, closes_at)` (el doctor no puede estar en dos lugares a la vez); adyacentes OK → `400 AVAILABILITY_OVERLAP`. Se valida el set entrante contra los existentes en esa fecha **y**, en alta masiva, también entre los bloques del propio body.
4. **(Suave / scheduling)** el bloque idealmente cabe en el `OfficeOperatingHours` del office para el weekday de `date`; **NO** se valida como hard-block en `staff`. `scheduling` intersecta con el horario del office, así que la porción del bloque fuera de horario simplemente no genera slots. Se documenta, no se bloquea.

### `slot_duration_min` en `Doctor` (no por `(doctor, product)`)

**Confirmado por usuario.** El slot del doctor es la unidad temporal mínima de su agenda — el **grano** del calendario, no la duración de una atención concreta. Al agendar, `scheduling` cruza dos valores:

- `product.duration_min` = duración real esperada de la atención.
- `doctor.slot_duration_min` = grano del calendario del doctor.

**Reglas de cómputo** (para el módulo `scheduling`): si `product.duration_min` es `NULL` o `≤ doctor.slot_duration_min` → 1 slot; si es mayor → `ceil(product.duration_min / doctor.slot_duration_min)` slots **contiguos** (si no hay contiguos suficientes, `scheduling` rechaza con `NO_CONTIGUOUS_SLOTS`). Esto evita inventar una tabla `doctor_product_duration` antes de tiempo; si el negocio quiere durations específicas por `(doctor, product)`, se agrega después de forma aditiva.

### Soft-delete del doctor no toca el `User`

**De [ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md).** `DELETE /doctors/{id}` hace soft-delete del `doctor` y deja el `User` intacto. Para "bloquear el acceso del doctor a la plataforma" hay que tocar `user.active = false` desde `admin`. El service lo documenta. Consecuencia simétrica: quitar el role `DOCTOR` a un user con perfil de doctor activo debe coordinarse en `admin` (`BadRequestException(code="USER_HAS_ACTIVE_DOCTOR_PROFILE")`).

### Cross-module: consistencia de soft-delete y roles

**De [ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md) + patrón de clinic.** El M:N `doctor_branch`/`doctor_vertical` apunta a `clinic.branch`/`catalog.vertical`. Al exponer sedes/verticales del doctor (`DoctorDetail.branches`/`.verticals`, dropdowns del form) se **filtran las soft-deleted** vía join (`deleted_at IS NULL`); **no** se extiende el delete guard de `clinic`/`catalog` para mirar las asociaciones de `staff` (eso acoplaría esos módulos a `staff`). El backstop ante un **hard-delete** del padre es la FK `ON DELETE RESTRICT` en las tablas de asociación. Así `staff` tolera el soft-delete (lo oculta) sin que `clinic`/`catalog` tengan que conocer a `staff`. La consistencia "User con role `DOCTOR` ↔ existe `Doctor`" es responsabilidad de los services (`staff.doctor` al crear/borrar; `admin.user` al quitar el role).

### Asesor / Admin sin tabla propia

**De [ADR-002](../../decisions/ADR-002-doctor-entity-extends-user.md), confirmado por usuario.** Estos roles **no necesitan datos profesionales** ni relaciones M:N propias en el MVP. `admin.user` con su `Role` basta. Si el negocio pide más (capacity por asesor, métricas de cierre, cuotas), se agrega `advisor` 1:1 con `User` de forma aditiva.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `admin` | `doctor.user_id` (FK 1:1, inmutable). Creación **nested** crea el `User` con role `DOCTOR`. Audit users vía FK lógica a `user.id` en `created_by`/`updated_by`. |
| `clinic` | `doctor_branch` (M:N) → `clinic.branch`; `doctor_availability.branch_id` y `.office_id` (FKs). El cierre del consultorio (`clinic.OfficeClosure`) y el horario (`clinic.OfficeOperatingHours`) NO se duplican aquí — los consume `scheduling`. FKs `ON DELETE RESTRICT`. |
| `catalog` | `doctor_vertical` (M:N) → `catalog.vertical`. Define qué verticales cubre el doctor. FK `ON DELETE RESTRICT`. |
| `scheduling` | Consume `DoctorAvailability` + `slot_duration_min` + `doctor_branch`/`doctor_vertical` para calcular slots libres ([ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md)). NO escribe en `staff`. |

`staff` depende de `admin` (1:1 con user), `clinic` (M:N con branch + FKs de availability) y `catalog` (M:N con vertical). No depende de `scheduling` ni de los demás módulos de dominio.

## Diagramas

- ER: [`docs/diagrams/er-staff.puml`](../../diagrams/er-staff.puml)
- Class diagram (modelos + repos + services): [`docs/diagrams/class-backend-staff.puml`](../../diagrams/class-backend-staff.puml)

> Los diagramas se actualizan aparte tras las fichas (lo hace el implementador): quitar `Pattern`/`Override`, dejar `Doctor` + `DoctorAvailability` + las 2 M:N.

## Implementación por fases

Igual que `clinic`, `staff` se implementa por fases que mapean al ciclo de vida del módulo. Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist que referencia estas fases.

| Fase | Alcance |
|---|---|
| **F0 — Prep** | 11 permisos `STAFF` en `seed.py`; helper genérico `_seed_role` + roles `DOCTOR`/`ASESOR` (subset disponible hoy; `SYSTEM` diferido); navegación "Staff" → "Doctores" (`MENU-STAFF`) + ícono de sidebar; `endpoints.ts` (doctores + availability + me); `types/staff.types.ts` (todas las interfaces); skeleton del paquete `staff` en backend. |
| **F1 — Doctor (+ M:N `doctor_branch`/`doctor_vertical`)** | Modelo + schemas + repo + service + router CRUD; creación **nested** (user + doctor); `branches_count`/`verticals_count` denormalizados (batch como en clinic); página de detalle `/staff/doctors/{id}` con tabs (**Perfil** + **Auditoría** funcionales; **Disponibilidad** placeholder de F2); lista con drawer de creación. Reusa `SearchableOptionList` para `branch_ids`/`vertical_ids`. Migración `0009_staff_doctor`. |
| **F2 — DoctorAvailability (calendario)** | Modelo + schemas + repo + service (invariantes 1-3) + router (`GET` rango, `POST` bulk, `PUT`, `DELETE`); tab "Disponibilidad" = **grilla semanal tipo calendario** (ver [`ui.md`](ui.md)). El frontend más pesado del proyecto. Migración `0010_staff_doctor_availability`. |
| **F3 — self-service `/me`** | Endpoints `/me/doctor` + `/me/availability/*`; UI "Mi perfil" + "Mi agenda" para el doctor logueado (reusa el calendario de F2 en modo self). |

> **Migraciones**: revision id ≤ 32 chars (límite `alembic_version varchar(32)`). La siguiente libre tras clinic (`0008`) es `0009`. Sugeridas: `0009_staff_doctor` (F1) y `0010_staff_doctor_availability` (F2). Encadenar `down_revision`.

## Próximos pasos / TODOs deliberados

- [ ] Al implementar F2, validar que la grilla semanal de disponibilidad refleje los invariantes de backend inline (`closes_at > opens_at`, no-solapamiento por fecha) y muestre `OfficeOperatingHours` como banda guía + `OfficeClosure` hachurado (solo lectura, vienen de clinic).
- [x] Modelo de disponibilidad documentado como bloques concretos ([ADR-007](../../decisions/ADR-007-doctor-availability-concrete-blocks.md)); [ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md) lleva nota de actualización (entradas = bloques concretos). Al implementar `scheduling`, verificar que `compute_available_slots` use `(doctor_id, date)` para las queries por rango.
- [x] Overview viejo `docs/modules/staff.md` borrado y consolidado en este README; diagramas `er-staff`/`class-backend-staff` regenerados al modelo nuevo.
- [ ] Cuando se diseñe `scheduling`, verificar que el cálculo de slots filtre offices aptos por `office_vertical` (respetando `vertical.deleted_at IS NULL`) y aplique el grano `slot_duration_min` con la regla de N slots contiguos para productos largos.
- [ ] Considerar `DoctorVerticalCertification` si en el futuro la clínica quiere registrar certificaciones específicas por vertical. Por ahora `doctor_vertical` basta.
- [ ] Coordinar con `admin` el guard `USER_HAS_ACTIVE_DOCTOR_PROFILE` al quitar el role `DOCTOR` de un user con perfil de doctor activo.
