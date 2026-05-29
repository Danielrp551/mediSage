# Módulo `clinic`

> **Última actualización**: 2026-05-29
> **Propósito**: estructura física donde se opera la clínica — sedes, consultorios, verticales aptas por consultorio, horarios de operación recurrentes y excepciones ad-hoc.
> **Path del código**: `backend/app/modules/clinic/` (backend) · `frontend/src/app/(main)/clinic/` (frontend).

> **Este documento es el overview**. Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts, lógica.
> - 🎨 [`ui.md`](ui.md) — mockups, estados, componentes Fluent UI.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación.

## Resumen

La clínica de Medisage es **single-tenant** pero **multi-sede**. Este módulo modela el "dónde" y el "cuándo" físico de la operación, en una jerarquía de dos niveles más dos hijos de configuración del consultorio.

```
Branch (sede física)
   └─ Office (consultorio)
         ├─ office_vertical (M:N → catalog.Vertical)   verticales que puede acoger
         ├─ OfficeOperatingHours (patrón semanal)       horario recurrente por día
         └─ OfficeClosure (excepciones ad-hoc)          cierre o apertura extra puntual
```

Cada consultorio (`Office`) pertenece a una sede (`Branch`), declara qué **verticales** del catálogo es apto para atender (M:N con `catalog.Vertical`), define su propio **horario semanal** recurrente (`OfficeOperatingHours`) y puede tener **excepciones ad-hoc** (`OfficeClosure`) para feriados, mantenimiento o aperturas extraordinarias.

Es la base sobre la que `staff` declara dónde puede atender un doctor (`doctor_branch` M:N) y sobre la que `scheduling` calcula slots disponibles cruzando: patrón del doctor × horarios del office × excepciones × verticales aptas × citas existentes.

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Branch` | `branch` | Sede física: dirección estructurada, geo, contacto, timezone IANA. |
| `Office` | `office` | Consultorio: pertenece a una `Branch`, M:N con verticales aptas. |
| `OfficeOperatingHours` | `office_operating_hours` | Patrón semanal recurrente de apertura por día (puede haber varios bloques: mañana + tarde). |
| `OfficeClosure` | `office_closure` | Excepción ad-hoc: cierre o apertura extraordinaria sobre un rango de tiempo concreto. |
| _(M:N)_ `office_vertical` | `office_vertical` | Tabla de asociación office ↔ vertical apta. Vive en `models/associations.py`. |

### `Branch`

Sede física. Es el primer nivel de la jerarquía y no tiene FK a ningún módulo de dominio (es raíz). Lleva dirección estructurada (no free-text) para habilitar a futuro: filtros "sede más cercana" en el bot, integración con mapas, autocomplete en formularios.

- `code: varchar(40)` `<<unique>>` — slug estable (`lima_centro`, `trujillo`). Usado en URLs internas y por bots.
- `name: varchar(120)` — nombre comercial ("Sede Lima Centro").
- `address_line: varchar(255)` — calle y número ("Av. Larco 1234").
- `district: varchar(120)` `<<nullable>>` — distrito ("Miraflores").
- `city: varchar(120)` — ciudad ("Lima").
- `region: varchar(120)` `<<nullable>>` — región/departamento ("Lima").
- `country: varchar(2)` `default 'PE'` — ISO 3166-1 alpha-2.
- `postal_code: varchar(20)` `<<nullable>>`.
- `latitude: numeric(9,6)` `<<nullable>>` — geo opcional.
- `longitude: numeric(9,6)` `<<nullable>>` — geo opcional.
- `phone: varchar(40)` `<<nullable>>` — teléfono de la sede.
- `email: varchar(255)` `<<nullable>>` — correo de la sede.
- `timezone: varchar(60)` `default 'America/Lima'` — IANA (`America/Lima`, `America/Mexico_City`). **Ver sección "Timezone & datetimes" abajo**.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `Office`

Consultorio dentro de una sede. Es el segundo nivel: una cita se reserva contra un producto, pero `scheduling` la ubica en un `Office` apto. Cada uno declara qué verticales del catálogo puede acoger — al agendar, `scheduling` filtra offices aptos para el producto solicitado.

- `branch_id: varchar(36)` `<<FK→branch>>`.
- `code: varchar(40)` — identificador legible **único por sede** (`(branch_id, code)`). Ej: `C-03`, `ESTETICA-01`.
- `name: varchar(120)` — nombre interno o número visible ("Consultorio 3 — Dental").
- `room_number: varchar(20)` `<<nullable>>` — número de habitación si es distinto del code.
- `floor: varchar(20)` `<<nullable>>` — piso ("2", "PB").
- `description: varchar(500)` `<<nullable>>`.
- M:N con `catalog.Vertical` via `office_vertical` — verticales que puede acoger. La FK `office_vertical.vertical_id → vertical` es `ON DELETE RESTRICT` (backstop ante hard-delete; ver [Decisiones](#cross-module-filtrar-verticales-soft-deleted-al-listar)).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `OfficeOperatingHours`

Patrón semanal recurrente del consultorio. Un office puede tener **varias filas por día** para modelar bloques (ej. mañana 8-13 y tarde 16-20 con cierre por almuerzo).

- `office_id: varchar(36)` `<<FK→office>>`.
- `day_of_week: smallint` — **convención Python `datetime.weekday()`: 0 = lunes, 6 = domingo**. Documentado en el modelo y validado por Pydantic (`int 0..6`).
- `opens_at: time` — hora local de apertura (sin TZ; ver sección "Timezone & datetimes").
- `closes_at: time` — hora local de cierre. CHECK `closes_at > opens_at` (un bloque no cruza medianoche; si fuera necesario, se modela como dos bloques en dos días).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.
- **Sin `UNIQUE` sobre `(office_id, day_of_week)`** porque hay múltiples bloques por día.

### `OfficeClosure`

Excepción ad-hoc al patrón semanal. Cubre **dos casos** con el mismo schema:

- `is_closed: true` → el office NO está disponible en ese rango (feriado, mantenimiento). Pisa al patrón.
- `is_closed: false` → el office SÍ está disponible en ese rango aunque el patrón diga lo contrario (ej. abrir un domingo por demanda).

Campos:

- `office_id: varchar(36)` `<<FK→office>>`.
- `starts_at: timestamptz` — inicio del rango (UTC en BD, ISO 8601 con offset en JSON).
- `ends_at: timestamptz` — fin. CHECK `ends_at > starts_at`.
- `is_closed: bool` — `true` = cierre, `false` = apertura extra.
- `reason: varchar(255)` — texto libre para auditoría ("Feriado 28 julio", "Mantenimiento eléctrico").
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

## Endpoints (resumen)

Todos bajo `/api/v1/clinic/`. Listado paginado con `POST /list` + `QueryRequest`. Detalle de request/response en [`backend.md`](backend.md#api-contracts).

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `POST` | `/branches/list` | `BRANCHES_READ` | listado paginado |
| `POST` | `/branches` | `BRANCHES_CREATE` | crear |
| `GET` | `/branches/{id}` | `BRANCHES_READ` | detalle |
| `PUT` | `/branches/{id}` | `BRANCHES_UPDATE` | actualizar |
| `DELETE` | `/branches/{id}` | `BRANCHES_DELETE` | soft delete (guard 409 si tiene offices activos) |
| `GET` | `/branches/active` | `BRANCHES_READ` | dropdown |
| `POST` | `/offices/list` | `OFFICES_READ` | listado paginado |
| `POST` | `/offices` | `OFFICES_CREATE` | crear (incluye `vertical_ids` para el M:N) |
| `GET` | `/offices/{id}` | `OFFICES_READ` | detalle (incluye `branch`, `verticals`) |
| `PUT` | `/offices/{id}` | `OFFICES_UPDATE` | actualizar (incluye `vertical_ids` para reasignar M:N) |
| `DELETE` | `/offices/{id}` | `OFFICES_DELETE` | soft delete |
| `GET` | `/offices/active?branch_id=&vertical_id=` | `OFFICES_READ` | dropdown filtrable |
| `GET` | `/offices/{id}/operating-hours` | `OFFICE_HOURS_READ` | listar bloques del patrón |
| `PUT` | `/offices/{id}/operating-hours` | `OFFICE_HOURS_WRITE` | reemplazar atómicamente todo el patrón (bulk) |
| `GET` | `/offices/{id}/closures?from=&to=` | `OFFICE_CLOSURES_READ` | listar excepciones en rango |
| `POST` | `/offices/{id}/closures` | `OFFICE_CLOSURES_WRITE` | agregar excepción |
| `DELETE` | `/offices/{id}/closures/{closure_id}` | `OFFICE_CLOSURES_WRITE` | eliminar excepción |

> **Alineación con el catálogo shipped (decisión confirmada).** El borrador original de `clinic.md` usaba `PATCH` para updates y `/options` para dropdowns. El catálogo ya en producción usa **`PUT`** para actualización full y **`/active`** para "lista plana de activos para dropdowns" (mismo patrón que `ENDPOINTS.ROLES.ACTIVE`, `ENDPOINTS.PERMISSIONS.ACTIVE` del template). Para no introducir dos convenciones en el mismo codebase, `clinic` adopta `PUT` + `/active`. La **única excepción** es el endpoint bulk de horarios, que se queda en `PUT /offices/{id}/operating-hours` porque ahí `PUT` es semánticamente correcto (reemplazo idempotente de toda la colección). Los `/active` devuelven una **lista cruda** (`response_model=list[...]`), sin envelope `SingleResponse`, igual que catalog.

## Permisos seed

13 permisos. Ya consolidados en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md).

```python
# Module: clinic
("MENU-CLINIC", "Menu Clinic", "CLINIC"),
("BRANCHES_READ", "Read branches", "CLINIC"),
("BRANCHES_CREATE", "Create branches", "CLINIC"),
("BRANCHES_UPDATE", "Update branches", "CLINIC"),
("BRANCHES_DELETE", "Delete branches", "CLINIC"),
("OFFICES_READ", "Read offices", "CLINIC"),
("OFFICES_CREATE", "Create offices", "CLINIC"),
("OFFICES_UPDATE", "Update offices", "CLINIC"),
("OFFICES_DELETE", "Delete offices", "CLINIC"),
("OFFICE_HOURS_READ", "Read office operating hours", "CLINIC"),
("OFFICE_HOURS_WRITE", "Write office operating hours", "CLINIC"),
("OFFICE_CLOSURES_READ", "Read office closures", "CLINIC"),
("OFFICE_CLOSURES_WRITE", "Write office closures", "CLINIC"),
```

**Roles seed**:
- `ADMIN` — todos.
- `DOCTOR` — `BRANCHES_READ`, `OFFICES_READ`, `OFFICE_HOURS_READ`, `OFFICE_CLOSURES_READ` (necesita saber dónde y cuándo puede atender, no editar la infraestructura).
- `ASESOR` — `MENU-CLINIC` + `BRANCHES_READ`, `OFFICES_READ` (para responder al lead "¿en qué sedes están?").

## Decisiones de diseño (no obvias)

### Horarios viven en `Office`, no en `Branch`

**Por qué**: un consultorio puede tener horario distinto del de la sede ("Consultorio 3 atiende L-V 8-14 aunque la sede esté abierta hasta las 20"). Modelar el horario en `Office` es la granularidad operativa real. La sede no necesita su horario propio en BD.

**Costo si cambia**: si en el futuro se quiere mostrar "Horario de la sede" en marketing, se deriva del max/min de sus offices o se agrega `Branch.public_hours` (texto descriptivo libre) sin migración compleja. Aceptable porque el dominio operativo (scheduling) razona a nivel office.

### `OfficeClosure` cubre cierres y aperturas extra con un solo modelo (`is_closed: bool`)

**Por qué**: alternativa rechazada — dos tablas separadas (`closure` y `extra_opening`). Misma semántica (rango de tiempo + razón + auditoría) → una tabla con flag boolean es más simple, menos código, y permite mostrar el calendario completo de excepciones en una sola query. El consumidor (`scheduling`) interpreta el flag al combinar con el patrón.

### `Office` M:N con `Vertical` en lugar de un enum `office_type`

**Por qué**: confirmado por usuario. Un consultorio puede ser apto para múltiples verticales (ej. estética facial Y dermatología clínica). Un `OfficeType` enum/catálogo forzaría 1:1 y obligaría a duplicar offices "iguales pero de otro tipo". La M:N es la representación natural y se reasigna en bloque desde el form del office (`vertical_ids`).

### `day_of_week`: convención Python (0=lunes), no Postgres (0=domingo)

**Por qué**: `EXTRACT(DOW FROM date)` en Postgres devuelve 0 = domingo. `datetime.weekday()` en Python devuelve 0 = lunes. El código de scheduling es Python; usar la convención del lenguaje host evita conversiones repetidas y bugs off-by-one. Documentado en el modelo y validado en Pydantic (`int 0..6`).

### `OfficeOperatingHours` se gestiona con bulk `PUT` (reemplazo atómico), no CRUD individual

**Por qué**: un patrón semanal coherente es un agregado. Editar bloques individuales abre la puerta a estados intermedios inválidos ("borré la tarde antes de crear la nueva"). El bulk replace (`PUT /offices/{id}/operating-hours` con `OfficeOperatingHoursReplace { hours: [...] }`) simplifica la UI ("guardar todos los horarios" como una sola acción) y mantiene invariantes.

**Costo si cambia**: no hay traza fina de "qué bloque cambió". Si llega a importar, se puede agregar un `OfficeOperatingHoursHistory` snapshot por update. `OfficeClosure`, en cambio, **sí es CRUD individual** (cada excepción es una unidad atómica con razón propia).

### Página dedicada para el detalle del consultorio (no drawer)

**Por qué (decisión confirmada, nueva vs catalog)**: el catálogo resolvía todo con drawers. Un `Office` tiene demasiado estado para un drawer cómodo: datos básicos + verticales + patrón semanal + calendario de excepciones + auditoría. Por eso el detalle del consultorio es una **página dedicada** `/clinic/offices/{id}` con tabs (**Detalles · Horarios · Excepciones · Auditoría**). La **lista** de consultorios (`/clinic/offices`) conserva un **drawer de creación** para nuevos offices; ver/editar uno existente **navega** a su página de detalle. Las sedes (`Branch`) siguen el patrón del catálogo (drawer-only). Este shell de "lista con drawer de creación + página de detalle con tabs" queda como patrón reusable para módulos futuros.

### Convención de endpoints alineada al catálogo shipped (`PUT` + `/active`)

**Por qué**: ver la nota bajo [Endpoints](#endpoints-resumen). En resumen: `PUT` (no `PATCH`) para updates full y `/active` (no `/options`) para dropdowns, para tener una sola convención en todo el codebase. La única excepción intencional es `PUT /offices/{id}/operating-hours`, donde `PUT` ya era lo correcto por ser reemplazo idempotente de colección.

### Cross-module: filtrar verticales soft-deleted al listar

**Por qué**: el M:N `office_vertical` apunta a `catalog.vertical`. Al exponer las verticales aptas de un office (`OfficeDetail.verticals`, dropdown del form), se **filtran las verticales soft-deleted** vía join (`vertical.deleted_at IS NULL`). NO se extiende el delete guard de `catalog.Vertical` para mirar `office_vertical` — eso acoplaría `catalog` a `clinic`. El backstop ante un **hard-delete** de vertical es la FK `office_vertical.vertical_id → vertical` con `ON DELETE RESTRICT`. Así `clinic` tolera el soft-delete (lo oculta) sin que `catalog` tenga que conocer a `clinic`.

### Timezone & datetimes — cómo se resuelve la representación de horas

Hay **tres clases distintas** de "tiempo" en este módulo, cada una con regla propia. Importante porque mezclar las convenciones causa bugs sutiles.

| Tipo de dato | Columna(s) | Convención | UI |
|---|---|---|---|
| Hora local del office (patrón) | `OfficeOperatingHours.opens_at`, `closes_at` | `time` sin TZ. Se interpreta en `office.branch.timezone`. | UI muestra tal cual ("8:00") porque el doctor/asesor está en esa sede. |
| Instante de excepción | `OfficeClosure.starts_at`, `ends_at` | `timestamptz` (UTC en BD, ISO 8601 con offset en JSON). | Browser convierte al timezone del usuario con `new Date()` (estándar del template). En la práctica coincide con el TZ de la sede. |
| Instante de cita | `Appointment.scheduled_for` (módulo `scheduling`) | `timestamptz` | Igual: browser hace la conversión. |

**Por qué timezone en `Branch` y no en un singleton `Clinic`**: el usuario confirmó timezone por `Branch` para tener el camino abierto a sedes multi-país. Como el grueso de instantes (`OfficeClosure`, `Appointment`) viaja como `timestamptz`, la conversión a UI es automática vía browser y no requiere lógica server-side para el path principal. La columna `branch.timezone` solo se usa cuando hay que **resolver una hora local del patrón** (ej. "Lunes 9:00 en Sede Lima") a un instante concreto en UTC — eso lo hace `scheduling` al construir/comparar slots.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `catalog` | `office_vertical` (M:N) → `catalog.vertical`. Define qué offices son aptos para qué verticales. FK `ON DELETE RESTRICT`. |
| `staff` | `doctor_branch` (M:N) entre `staff.doctor` y `clinic.branch` (definido en `staff`, no aquí). |
| `scheduling` | `appointment.office_id` y `appointment.branch_id` (FKs). Scheduling lee patrón + closures + verticales aptas + capacity para calcular slots. |

`clinic` solo depende de `admin` (audit users vía FK lógica a `user.id` en `created_by`/`updated_by`) y `catalog` (M:N con `Vertical`). No depende de `staff`, `scheduling` ni de los demás módulos de dominio.

## Diagramas

- ER: [`docs/diagrams/er-clinic.puml`](../../diagrams/er-clinic.puml)
- Class diagram (modelos + repos + services): [`docs/diagrams/class-backend-clinic.puml`](../../diagrams/class-backend-clinic.puml)

## Implementación por fases

A diferencia del catálogo (que se implementó por entidad de la jerarquía), `clinic` se implementa por fases que mapean al ciclo de vida del módulo. Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist que referencia estas fases.

| Fase | Alcance |
|---|---|
| **F0 — Prep** | 13 permisos en seed; navegación "Clínica" → Sedes, Consultorios (`MENU-CLINIC`); endpoints registrados; íconos de sidebar. |
| **F1 — Branch** | Modelo + schemas + repo + service + router de `Branch`; lista (drawer) + CRUD + `/active`. |
| **F2 — Office + M:N** | `Office` + `office_vertical` (M:N → vertical); activar `Branch.offices_count`; guard `409 BRANCH_HAS_ACTIVE_CHILDREN` al borrar sede con offices activos; shell de la **página de detalle** del office. |
| **F3 — OfficeOperatingHours** | Tab "Horarios"; bulk `PUT /offices/{id}/operating-hours` (reemplazo atómico). |
| **F4 — OfficeClosure** | Tab "Excepciones"; CRUD de cierres/aperturas extra anidado en `/offices/{id}/closures`. |

## Próximos pasos / TODOs deliberados

- [ ] Validar al diseñar `scheduling` que la query "slots disponibles del Dr X esta semana" usa `office_vertical` para filtrar offices aptos para el producto solicitado (y respeta `vertical.deleted_at IS NULL`).
- [ ] Si el bot pide "sede más cercana", agregar índice GIN/geo sobre `(latitude, longitude)` (Postgres PostGIS o `earthdistance`). Postergado al MVP del bot.
- [ ] Si el negocio quiere mostrar horario público en marketing, agregar `Branch.public_hours` (texto libre) o vista materializada que agregue por sede.
- [ ] Considerar `BranchClosure` (cierre completo de sede) si pasa de ser excepcional a recurrente. Por ahora, cerrar una sede = `Branch.active = false`.
- [ ] Cuando se diseñe `staff`, validar que `doctor_branch` use FK con `ON DELETE RESTRICT` (no queremos perder asignaciones por borrar sedes).
