# Módulo `clinic`

> **Última actualización**: 2026-05-28
> **Propósito**: estructura física donde se opera la clínica — sedes, consultorios, verticales aptas por consultorio y horarios de operación.
> **Path del código**: `backend/app/modules/clinic/`

## Resumen

La clínica de Medisage es **single-tenant** pero **multi-sede**. Cada sede (`Branch`) tiene uno o más consultorios (`Office`). Cada consultorio:

- declara qué **verticales** del catálogo es apto para atender (M:N con `catalog.Vertical`);
- define su propio **horario semanal** recurrente (`OfficeOperatingHours`);
- puede tener **excepciones ad-hoc** (`OfficeClosure`) para feriados, mantenimiento o apertura extraordinaria.

Es la base sobre la que `staff` declara dónde puede atender un doctor (`doctor_branch` M:N) y sobre la que `scheduling` calcula slots disponibles cruzando: patrón del doctor × horarios del office × excepciones × verticales aptas × citas existentes.

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Branch` | `branch` | Sede física: dirección estructurada, geo, contacto, timezone IANA. |
| `Office` | `office` | Consultorio: pertenece a una `Branch`, M:N con verticales aptas. |
| `OfficeOperatingHours` | `office_operating_hours` | Patrón semanal recurrente de apertura por día (puede haber varios bloques: mañana + tarde). |
| `OfficeClosure` | `office_closure` | Excepción ad-hoc: cierre o apertura extraordinaria sobre un rango de tiempo concreto. |
| _(M:N)_ `office_vertical` | `office_vertical` | Tabla de asociación office ↔ vertical apta. |

### `Branch`

Sede física. Lleva dirección estructurada (no free-text) para habilitar a futuro: filtros "sede más cercana" en el bot, integración con mapas, autocomplete en formularios.

- `code: varchar(40)` `<<unique>>` — slug estable (`lima_centro`, `trujillo`). Usado en URLs internas y por bots.
- `name: varchar(120)` — nombre comercial ("Sede Lima Centro").
- `address_line: varchar(255)` — calle y número ("Av. Larco 1234").
- `district: varchar(120)` `<<nullable>>` — distrito ("Miraflores").
- `city: varchar(120)` — ciudad ("Lima").
- `region: varchar(120)` `<<nullable>>` — región/departamento ("Lima").
- `country: varchar(2)` `default 'PE'` — ISO 3166-1 alpha-2.
- `postal_code: varchar(20)` `<<nullable>>`.
- `latitude: numeric(9,6)` `<<nullable>>` — geo opcional.
- `longitude: numeric(9,6)` `<<nullable>>`.
- `phone: varchar(40)` `<<nullable>>` — teléfono de la sede.
- `email: varchar(255)` `<<nullable>>` — correo de la sede.
- `timezone: varchar(60)` `default 'America/Lima'` — IANA (`America/Lima`, `America/Mexico_City`). **Ver sección "Timezone & datetimes" abajo**.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `Office`

Consultorio dentro de una sede. Cada uno declara qué verticales del catálogo puede acoger — al agendar, `scheduling` filtra offices aptos para el producto solicitado.

- `branch_id: varchar(36)` `<<FK→branch>>`.
- `code: varchar(40)` — identificador legible único por sede ("C-03", "ESTETICA-01"). UNIQUE `(branch_id, code)`.
- `name: varchar(120)` — nombre interno o número visible ("Consultorio 3 — Dental").
- `room_number: varchar(20)` `<<nullable>>` — número de habitación si es distinto del code (ej. piso).
- `floor: varchar(20)` `<<nullable>>` — piso ("2", "PB").
- `description: varchar(500)` `<<nullable>>`.
- M:N con `catalog.Vertical` via `office_vertical` — verticales que puede acoger.
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

## Esquemas (Pydantic v2)

Por entidad las variantes son `Create / Update / Item / Detail / Option`.

**Decisión específica para `OfficeOperatingHours`**: no se gestiona como CRUD individual. Se expone un **endpoint bulk** `PUT /offices/{id}/operating-hours` que recibe la **lista completa** del patrón semanal y reemplaza atómicamente. Esto evita estados intermedios inconsistentes (ej. borrar el bloque de tarde antes de crear el nuevo) y simplifica la UI ("guardar todos los horarios" como una sola acción).

Schemas:
- `OfficeOperatingHoursItem { day_of_week, opens_at, closes_at }`
- `OfficeOperatingHoursReplace { hours: list[OfficeOperatingHoursItem] }` — el body del bulk PUT.

**Para `OfficeClosure`**: sí es CRUD individual (cada excepción es una unidad atómica con razón propia).

## Endpoints

Todos bajo `/api/v1/clinic/`. Listado paginado con `POST /list` + `QueryRequest`.

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `POST` | `/branches/list` | `BRANCHES_READ` | listado paginado |
| `POST` | `/branches` | `BRANCHES_CREATE` | crear |
| `GET` | `/branches/{id}` | `BRANCHES_READ` | detalle |
| `PATCH` | `/branches/{id}` | `BRANCHES_UPDATE` | actualizar |
| `DELETE` | `/branches/{id}` | `BRANCHES_DELETE` | soft delete |
| `GET` | `/branches/options` | `BRANCHES_READ` | dropdown |
| `POST` | `/offices/list` | `OFFICES_READ` | listado paginado |
| `POST` | `/offices` | `OFFICES_CREATE` | crear |
| `GET` | `/offices/{id}` | `OFFICES_READ` | detalle (incluye `branch`, `verticals`) |
| `PATCH` | `/offices/{id}` | `OFFICES_UPDATE` | actualizar (incluye `vertical_ids` para reasignar M:N) |
| `DELETE` | `/offices/{id}` | `OFFICES_DELETE` | soft delete |
| `GET` | `/offices/options?branch_id=&vertical_id=` | `OFFICES_READ` | dropdown filtrable |
| `GET` | `/offices/{id}/operating-hours` | `OFFICE_HOURS_READ` | listar bloques del patrón |
| `PUT` | `/offices/{id}/operating-hours` | `OFFICE_HOURS_WRITE` | reemplazar atómicamente todo el patrón |
| `GET` | `/offices/{id}/closures?from=&to=` | `OFFICE_CLOSURES_READ` | listar excepciones en rango |
| `POST` | `/offices/{id}/closures` | `OFFICE_CLOSURES_WRITE` | agregar excepción |
| `DELETE` | `/offices/{id}/closures/{closure_id}` | `OFFICE_CLOSURES_WRITE` | eliminar excepción |

## Permisos seed

Agregar a `app/core/seed.py:SEED_PERMISSIONS`:

```python
# Module: clinic
("MENU-CLINIC", "Ver menú clínica", "Gestión de sedes y consultorios", "clinic"),
("BRANCHES_READ", "Ver sedes", "Listar y consultar sedes", "clinic"),
("BRANCHES_CREATE", "Crear sedes", "Crear nuevas sedes", "clinic"),
("BRANCHES_UPDATE", "Editar sedes", "Editar sedes existentes", "clinic"),
("BRANCHES_DELETE", "Eliminar sedes", "Soft-delete de sedes", "clinic"),
("OFFICES_READ", "Ver consultorios", "Listar y consultar consultorios", "clinic"),
("OFFICES_CREATE", "Crear consultorios", "Crear nuevos consultorios", "clinic"),
("OFFICES_UPDATE", "Editar consultorios", "Editar consultorios existentes", "clinic"),
("OFFICES_DELETE", "Eliminar consultorios", "Soft-delete de consultorios", "clinic"),
("OFFICE_HOURS_READ", "Ver horarios de consultorios", "Consultar el patrón semanal", "clinic"),
("OFFICE_HOURS_WRITE", "Editar horarios de consultorios", "Reemplazar el patrón semanal", "clinic"),
("OFFICE_CLOSURES_READ", "Ver cierres/aperturas extra", "Consultar excepciones ad-hoc", "clinic"),
("OFFICE_CLOSURES_WRITE", "Editar cierres/aperturas extra", "Crear/eliminar excepciones", "clinic"),
```

**Roles seed que tocan `clinic`** (validar al consolidar permisos al final):
- `ADMIN` — todos.
- `DOCTOR` — `BRANCHES_READ`, `OFFICES_READ`, `OFFICE_HOURS_READ`, `OFFICE_CLOSURES_READ` (necesita saber dónde y cuándo puede atender, no editar la infraestructura).
- `ASESOR` — `MENU-CLINIC` + `BRANCHES_READ`, `OFFICES_READ` (para responder al lead "¿en qué sedes están?").

## Decisiones de diseño (no obvias)

### Horarios viven en `Office`, no en `Branch`

Confirmado por usuario: un consultorio puede tener horario distinto del de la sede ("Consultorio 3 atiende L-V 8-14 aunque la sede esté abierta hasta las 20"). Modelar el horario en `Office` es la granularidad operativa real. La sede no necesita su horario propio en BD — si se quiere mostrar "Horario de la sede" en marketing, se deriva del max/min de sus offices o se agrega como `Branch.public_hours` (texto descriptivo libre) en el futuro sin migración compleja.

### `OfficeClosure` cubre cierres y aperturas extra con un solo modelo (`is_closed: bool`)

Alternativa rechazada: dos tablas separadas (`closure` y `extra_opening`). Misma semántica (rango de tiempo + razón + auditoría) → una tabla con flag boolean es más simple, menos código, y permite mostrar el calendario completo de excepciones en una sola query. El consumidor (`scheduling`) interpreta el flag al combinar con el patrón.

### `Office` M:N con `Vertical` en lugar de "office_type" enum

Confirmado por usuario. Razón: un consultorio puede ser apto para múltiples verticales (ej. estética facial Y dermatología clínica). Un `OfficeType` enum/catálogo forzaría 1:1 y obligaría a duplicar offices "iguales pero de otro tipo". La M:N es la representación natural.

### `day_of_week`: convención Python (0=lunes), no Postgres (0=domingo)

`EXTRACT(DOW FROM date)` en Postgres devuelve 0 = domingo. `datetime.weekday()` en Python devuelve 0 = lunes. El código de scheduling es Python; usar la convención del lenguaje host evita conversiones repetidas y bugs off-by-one. Documentado en el modelo y validado en Pydantic.

### `OfficeOperatingHours` se gestiona con bulk `PUT` (reemplazo atómico)

Razón: un patrón semanal coherente es un agregado. Editar bloques individuales abre la puerta a estados intermedios inválidos ("borré tarde antes de crear nueva"). El bulk replace simplifica UI y mantiene invariantes (todos los bloques de un día son coherentes entre sí). Trade-off: no hay traza fina de "qué bloque cambió" — si llega a importarse, se puede agregar un `OfficeOperatingHoursHistory` snapshot por update.

### Timezone & datetimes — cómo se resuelve la representación de horas

Hay **tres clases distintas** de "tiempo" en este módulo, cada una con regla propia. Importante porque mezclar las convenciones causa bugs sutiles.

| Tipo de dato | Columna(s) | Convención | UI |
|---|---|---|---|
| Hora local del office (patrón) | `OfficeOperatingHours.opens_at`, `closes_at` | `time` sin TZ. Se interpreta en `office.branch.timezone`. | UI muestra tal cual ("8:00") porque el doctor/asesor está en esa sede. |
| Instante de excepción | `OfficeClosure.starts_at`, `ends_at` | `timestamptz` (UTC en BD, ISO 8601 con offset en JSON). | Browser convierte al timezone del usuario con `new Date()` (estándar del template). En la práctica coincide con el TZ de la sede. |
| Instante de cita | `Appointment.scheduled_for` (módulo `scheduling`) | `timestamptz` | Igual: browser hace la conversión. |

**Por qué timezone en Branch y no en Clinic singleton**: el usuario confirmó timezone por Branch para tener el camino abierto a sedes multi-país. Como el grueso de instantes (`OfficeClosure`, `Appointment`) viaja como `timestamptz`, la conversión a UI es automática vía browser y no requiere lógica server-side para el path principal. La columna `branch.timezone` solo se usa cuando hay que **resolver una hora local del patrón** (ej. "Lunes 9:00 en Sede Lima") a un instante concreto en UTC — eso lo hace `scheduling` al construir/comparar slots.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `catalog` | `office_vertical` M:N → `catalog.vertical`. Define qué offices son aptos para qué verticales. |
| `staff` | `doctor_branch` M:N entre `staff.doctor` y `clinic.branch` (definido en `staff`, no aquí). |
| `scheduling` | `appointment.office_id` y `appointment.branch_id` FKs. Scheduling lee patrón + closures + verticales aptas + capacity. |

`clinic` solo depende de `admin` (audit users) y `catalog` (M:N con Vertical).

## Diagramas

- ER: [`docs/diagrams/er-clinic.puml`](../diagrams/er-clinic.puml)
- Class diagram: [`docs/diagrams/class-backend-clinic.puml`](../diagrams/class-backend-clinic.puml)

## Próximos pasos / TODOs deliberados

- [ ] Validar al diseñar `scheduling` que la query "slots disponibles del Dr X esta semana" usa `office_vertical` para filtrar offices aptos para el producto solicitado.
- [ ] Si el bot pide "sede más cercana", agregar índice GIN/geo sobre `(latitude, longitude)` (Postgres PostGIS o `earthdistance`). Postergado al MVP del bot.
- [ ] Si el negocio quiere mostrar horario público en marketing, agregar `Branch.public_hours` (texto libre) o vista materializada que agregue por sede.
- [ ] Considerar `BranchClosure` (cierre completo de sede) si pasa de ser excepcional a recurrente. Por ahora, cerrar una sede = `Branch.active = false`.
