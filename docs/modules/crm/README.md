# Módulo `crm`

> **Última actualización**: 2026-05-31
> **Propósito**: gestión de **contactos** (`Person`) y sus **dos hilos de vida comerciales** — el hilo **lead** (prospecto que se cultiva hasta cita/descarte) y el hilo **cliente** (paciente activo de la clínica), que pueden coexistir. Incluye identificadores multicanal, catálogos configurables de estados con matriz de transiciones, asignación de owner (asesor) con round-robin, historiales inmutables y un timeline polimórfico de actividad. Es el **módulo más grande** del proyecto (12 entidades) y la base sobre la que se asientan `conversations`, `bots`, `scheduling` y `marketing`.
> **Path del código**: `backend/app/modules/crm/` (backend) · `frontend/src/app/(main)/crm/` (frontend).

> **Este documento es el overview**. Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts (request/response/errores), lógica de service, draft SQL de migraciones.
> - 🎨 [`ui.md`](ui.md) — mockups por pantalla con estados (empty/loading/no-results/error), componentes Fluent UI (incl. el timeline de actividad), UX writing en español.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación, types espejo.

## Resumen

`crm` es el módulo de **personas que la clínica capta y atiende comercialmente**. La entidad raíz es `Person` — identidad + contacto, **sin datos médicos** en el MVP (si en el futuro se requiere historia clínica, será un módulo aparte, p.ej. `medical_record` 1:1 con `Person`).

Cada `Person` recorre **dos hilos de vida paralelos que pueden coexistir** ([ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md)): el **hilo lead** (prospecto) y el **hilo cliente** (paciente). Una misma persona puede ser **cliente activo de estética** y, a la vez, **lead nuevo de una campaña dental** — los dos hilos viven en tablas hijas separadas, cada una con su propio estado actual, su historial y (en el caso del lead) su owner y su origen de campaña.

```
                ┌─────────────────────────────────────────────┐
                │  PersonLeadStatus  (UNIQUE person_id)        │  ← un solo lead activo por Person
                │  + LeadStatusHistory   (traza inmutable)     │  ← cada transición queda registrada
                │  + LeadAssignment  (UNIQUE person_id, owner) │  ← asesor responsable (round-robin)
                │  + source_campaign_id  (origen, FK diferida) │
                └─────────────────────────────────────────────┘
   Person ──┤   (identidad + PersonContactIdentifier multicanal)
                ┌─────────────────────────────────────────────┐
                │  PersonCustomerStatus  (UNIQUE person_id)    │  ← cliente actual de la clínica
                │  + CustomerStatusHistory  (traza inmutable)  │
                └─────────────────────────────────────────────┘

   LeadActivity (timeline polimórfico) cuelga de Person — notas, llamadas,
   seguimientos, cambios de estado/owner, eventos de sistema y de módulos futuros.
```

Una persona en cualquier momento puede: tener `PersonLeadStatus` y `PersonCustomerStatus` simultáneos (cliente + lead nuevo); solo lead (prospecto puro); solo cliente (atendido sin lead en curso); o ninguno (Person creado a mano sin tracking comercial). La **existencia de la fila** (no borrada) en `PersonLeadStatus` / `PersonCustomerStatus` significa "tiene hilo activo"; al cerrar (transición a estado `is_final`) la fila se soft-deletea y la traza permanece en el historial. Reabrir = fila nueva.

Sobre `crm` se construyen los módulos posteriores: `conversations` (matchea `Person` por `PersonContactIdentifier` al recibir un mensaje y llamará a `find_by_identifier_or_create`), `bots` (decide preventa/postventa según si hay `PersonCustomerStatus` activo), `scheduling` (`appointment.person_id` será FK a `person`) y `marketing` (`PersonLeadStatus.source_campaign_id` será FK a `campaign`). `crm` se implementa **antes** que todos ellos — por eso las tres columnas que apuntan a esos módulos existen ya como `varchar(36)` indexado **sin FK física** (ver [FKs forward diferidas](#fks-forward-a-módulos-futuros-columna-ahora-constraint-después-adr-009)).

## Entidades

12 entidades. Mixins: `PK`=`PrimaryKeyMixin`, `A`=`ActiveMixin`, `SD`=`SoftDeleteMixin`, `T`=`TimestampMixin`. **Los historiales y `LeadActivity` NO llevan `SD`** (audit trail honesto — ver [Decisiones](#historiales-y-actividad-sin-softdelete)).

| Entidad | Tabla | Mixins | Propósito |
|---|---|---|---|
| `Person` | `person` | PK·A·SD·T | Identidad + contacto. Raíz del módulo. Sin datos médicos en MVP. |
| `PersonContactIdentifier` | `person_contact_identifier` | PK·A·SD·T | Identificadores multicanal por persona (whatsapp, telegram, web, phone, email, …). Dedup `UNIQUE(channel_type, identifier)` parcial. |
| `LeadStatus` | `lead_status` | PK·A·SD·T | Catálogo configurable de estados de lead. Flags `is_initial`/`is_final`/`is_won`. |
| `CustomerStatus` | `customer_status` | PK·A·SD·T | Catálogo configurable de estados de cliente. Flags `is_initial`/`is_final` (sin `is_won`). |
| `LeadStatusTransition` | `lead_status_transition` | PK·A·T | Aristas permitidas del grafo de estados de lead (matriz configurable). |
| `CustomerStatusTransition` | `customer_status_transition` | PK·A·T | Aristas permitidas del grafo de estados de cliente. |
| `PersonLeadStatus` | `person_lead_status` | PK·A·SD·T | Estado lead **actual** de un Person. `UNIQUE person_id` — un único lead activo. |
| `PersonCustomerStatus` | `person_customer_status` | PK·A·SD·T | Estado cliente **actual** de un Person. `UNIQUE person_id`. |
| `LeadStatusHistory` | `lead_status_history` | PK·A·T | Timeline inmutable de transiciones de estado lead (no se borra). |
| `CustomerStatusHistory` | `customer_status_history` | PK·A·T | Timeline inmutable de transiciones de estado cliente. |
| `LeadAssignment` | `lead_assignment` | PK·A·SD·T | Owner (asesor) del lead activo. `UNIQUE person_id`. |
| `LeadActivity` | `lead_activity` | PK·A·T | Timeline polimórfico de actividad sobre el lead, con `payload` JSONB. |

> Las dos tablas de transiciones (`lead_status_transition`, `customer_status_transition`) son **entidades de configuración**, no asociaciones M:N puras: tienen su propia identidad (`PK`), su `active` para deshabilitar una arista sin borrarla, pero **no** `SD` (config, no dato de negocio). Modelan la matriz de transiciones permitidas — ver [Matriz de transiciones configurable](#matriz-de-transiciones-configurable-adr-008).

### `Person`

Identidad + contacto. **Sin `phone`/`email` como columna** — viven en `PersonContactIdentifier` (multicanal sin migración futura).

- `first_name: varchar(80)` NOT NULL · `last_name: varchar(80)` NOT NULL · `second_last_name: varchar(80)` nullable.
- `document_type: varchar(20)` nullable (DNI/RUC/CE) · `document_number: varchar(40)` nullable, **indexado**.
- `birth_date: date` nullable · `gender: varchar(20)` nullable (texto libre, **sin enum**) · `address: varchar(255)` nullable · `notes: text` nullable.
- Relaciones (`lazy="raise"`, se cargan vía `get_full`): `identifiers` 1:N, `lead_status` 1:0..1, `customer_status` 1:0..1, `assignment` 1:0..1.

### `PersonContactIdentifier`

Identificadores multicanal. El detalle de schemas y validaciones está en [`backend.md`](backend.md).

- `person_id: varchar(36)` FK→`person` NOT NULL, indexado.
- `channel_type: varchar(40)` NOT NULL — enum Pydantic cerrado `ChannelType {whatsapp, telegram, web, phone, email, instagram, facebook, other}`. **No** es FK a un catálogo: es un slug estable que cruza con `conversations.ChannelAccount.channel_type`.
- `identifier: varchar(255)` NOT NULL — el valor (phone E.164 `+51999111222`, email, chat_id de Telegram, …).
- `is_primary: bool` default `false` — uno principal por `(person_id, channel_type)`, validado en service (marcar uno desmarca el anterior en la misma tx).
- `verified: bool` default `false`.
- **UNIQUE parcial `(channel_type, identifier) WHERE deleted_at IS NULL`** (índice parcial → permite reasignar tras soft-delete). Violación → `IDENTIFIER_TAKEN` (409).

### `LeadStatus` (catálogo configurable)

Catálogo en BD para que admin renombre o agregue estados sin deploy.

- `code: varchar(40)` UNIQUE NOT NULL (slug estable en mayúsculas, p.ej. `NUEVO`) · `name: varchar(120)` NOT NULL · `description: varchar(500)` nullable · `color: varchar(20)` nullable (hex para badges) · `display_order: int` default `0`.
- `is_initial: bool` default `false` — **exactamente uno** true por catálogo (validado en service). Es el estado por defecto al crear un lead.
- `is_final: bool` default `false` — terminal.
- `is_won: bool` default `false` — terminal positivo (lead convertido). Solo válido si `is_final=true` (`WON_REQUIRES_FINAL`).

### `CustomerStatus` (catálogo configurable)

Igual a `LeadStatus` **menos `is_won`**. `is_initial` (estado por defecto al convertir lead→cliente), `is_final` (cliente perdido).

### `LeadStatusTransition` / `CustomerStatusTransition` (matriz configurable)

Modelan las **aristas permitidas** del grafo de estados. Decisión Q3 del usuario, registrada en [ADR-008](#matriz-de-transiciones-configurable-adr-008).

- `from_lead_status_id` / `from_customer_status_id`: FK→catálogo NOT NULL.
- `to_lead_status_id` / `to_customer_status_id`: FK→catálogo NOT NULL.
- **UNIQUE `(from_*, to_*)`**.
- Editables por admin (`LEAD_STATUSES_WRITE` / `CUSTOMER_STATUSES_WRITE`) — "matriz base que luego actualizamos". Sin `SD`: deshabilitar una arista = `active=false` (conserva la fila) o `DELETE` real.

### `PersonLeadStatus`

Estado lead actual. `UNIQUE person_id` — un único lead activo a la vez ([ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md)).

- `person_id: varchar(36)` **UNIQUE** FK→`person` NOT NULL · `lead_status_id: varchar(36)` FK→`lead_status` NOT NULL.
- `source_campaign_id: varchar(36)` nullable, **indexado** — **SIN FK** ([§FKs forward](#fks-forward-a-módulos-futuros-columna-ahora-constraint-después-adr-009)).
- `entered_status_at: timestamptz` NOT NULL · `last_activity_at: timestamptz` nullable (denormalizado para listados sin join a `LeadActivity`).
- **Cierre**: al transicionar a un estado `is_final`, la fila se **soft-deletea** (la traza queda en `LeadStatusHistory`). La existencia de la fila (no borrada) ⟺ "lead activo".

### `PersonCustomerStatus`

Estado cliente actual. `UNIQUE person_id`. Sin `source_campaign_id`.

- `person_id: varchar(36)` **UNIQUE** FK→`person` NOT NULL · `customer_status_id: varchar(36)` FK→`customer_status` NOT NULL.
- `became_customer_at: timestamptz` NOT NULL (primera vez que se hizo cliente) · `entered_status_at: timestamptz` NOT NULL (estado actual).

### `LeadStatusHistory` / `CustomerStatusHistory`

Historial inmutable de transiciones. **No se borra ni soft-deletea** (audit trail honesto).

`LeadStatusHistory`: `person_id` (FK, indexado), `from_lead_status_id` nullable (NULL al crear), `to_lead_status_id` NOT NULL, `source_campaign_id: varchar(36)` nullable indexado (**SIN FK**; solo se llena al crear el lead), `changed_at: timestamptz` NOT NULL, `changed_by: varchar(36)` nullable (FK lógica→`user`; NULL/`SYSTEM` si automático), `reason: varchar(255)` nullable.

`CustomerStatusHistory`: análogo (`from_customer_status_id?`, `to_customer_status_id`), **sin** `source_campaign_id`.

### `LeadAssignment`

Owner actual del lead. `UNIQUE person_id` — un solo asesor responsable.

- `person_id: varchar(36)` **UNIQUE** FK→`person` NOT NULL · `advisor_user_id: varchar(36)` FK→`user` NOT NULL.
- `assigned_at: timestamptz` NOT NULL · `assigned_by: varchar(36)` nullable (FK→`user`; NULL/`SYSTEM` si round-robin automático) · `reason: varchar(255)` nullable.
- **Reasignación**: soft-delete de la fila actual + insert nueva + `LeadActivity(REASSIGNED)`, en una sola tx.

### `LeadActivity` (timeline polimórfico)

Timeline unificado de cualquier evento sobre el lead. Polimórfico vía `activity_type` + `payload` JSONB. **Sin `SD`**: "borrar" = `active=false` (desaparece del feed normal, pero la fila queda).

- `person_id: varchar(36)` FK→`person` NOT NULL, indexado · `advisor_user_id: varchar(36)` nullable FK→`user` (NULL/`SYSTEM` para sistema).
- `activity_type: varchar(40)` NOT NULL — enum cerrado `ActivityType` (no catálogo; ver tabla abajo).
- `content: text` nullable · `scheduled_for: timestamptz` nullable (`FOLLOW_UP_SCHEDULED`) · `completed_at: timestamptz` nullable · `outcome: varchar(40)` nullable (`successful/no_answer/busy/wrong_number/not_interested/interested`) · `payload: jsonb` nullable.
- `related_appointment_id: varchar(36)` nullable, indexado — **SIN FK**. `related_conversation_id: varchar(36)` nullable, indexado — **SIN FK**.

**Enum `ActivityType`** (declarado **completo** desde el inicio — contrato estable — pero la emisión es por etapas; ver [`backend.md`](backend.md) para el enum en código):

| `activity_type` | Emisor | Disponible en crm MVP |
|---|---|---|
| `NOTE` | asesor | ✅ (`POST /activities`) |
| `CALL_ATTEMPT` | asesor | ✅ |
| `FOLLOW_UP_SCHEDULED` | asesor | ✅ |
| `FOLLOW_UP_COMPLETED` | asesor | ✅ |
| `STATUS_CHANGE` | crm (sistema) | ✅ (lo emite el transition service) |
| `REASSIGNED` | crm (sistema) | ✅ (lo emite reassign/round-robin) |
| `CAMPAIGN_ATTRIBUTION` | crm (sistema) | ✅ (`find_by_identifier_or_create`) |
| `MESSAGE_SENT` | conversations | ⏳ enum presente, emisión diferida |
| `CONVERSATION_TAKEN` | conversations | ⏳ |
| `CONVERSATION_RELEASED` | conversations | ⏳ |
| `APPOINTMENT_BOOKED` | scheduling | ⏳ |
| `APPOINTMENT_CANCELLED` | scheduling | ⏳ |

## Endpoints (resumen)

Todos bajo `/api/v1/crm/`. Listado paginado con `POST /<recurso>/list` + `QueryRequest`. Convención del codebase (heredada de catalog/clinic/staff shipped): **`PUT` (no `PATCH`) para updates** y **`/active` (no `/options`) para dropdowns** — los `/active` devuelven **lista cruda** (`response_model=list[...]`, sin envelope); el resto usa los envelopes del template (`SingleResponse` / `PaginatedResponse`). **El overview viejo de crm usaba `PATCH` y `/options` — quedan deprecados y se reemplazan en TODAS estas fichas** (ese `docs/modules/crm.md` ya fue borrado y consolidado aquí). `/search` se conserva (endpoint funcional distinto del dropdown). El detalle de request/response/errores está en [`backend.md`](backend.md#api-contracts).

### Person + identificadores

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/persons/list` | `PERSONS_READ` |
| `POST` | `/persons` | `PERSONS_CREATE` |
| `GET` | `/persons/{id}` | `PERSONS_READ` |
| `PUT` | `/persons/{id}` | `PERSONS_UPDATE` |
| `DELETE` | `/persons/{id}` | `PERSONS_DELETE` (soft) |
| `GET` | `/persons/active` | `PERSONS_READ` (lista cruda `PersonOption`) |
| `GET` | `/persons/search?q=&channel_type=&identifier=` | `PERSONS_READ` (lo usará el bot) |
| `GET`/`POST`/`PUT`/`DELETE` | `/persons/{id}/identifiers[/{ident_id}]` | `PERSONS_READ` (GET) / `PERSONS_UPDATE` (resto) |

### Catálogos LeadStatus / CustomerStatus (+ matriz)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/lead-statuses/list` | `LEAD_STATUSES_READ` |
| `POST` · `PUT` · `DELETE` | `/lead-statuses[/{id}]` | `LEAD_STATUSES_WRITE` (DELETE → 409 `LEAD_STATUS_IN_USE` si está referenciado) |
| `GET` | `/lead-statuses/active` | `LEAD_STATUSES_READ` (lista cruda) |
| `GET` | `/lead-statuses/{id}/transitions` | `LEAD_STATUSES_READ` (estados a los que puede ir) |
| `PUT` | `/lead-statuses/{id}/transitions` | `LEAD_STATUSES_WRITE` (body `{to_ids:[...]}` reemplaza las aristas de salida) |
| _(idem)_ | `/customer-statuses/...` | `CUSTOMER_STATUSES_*` |

### Ciclo de vida (lead/customer de un Person)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `GET` | `/persons/{id}/lead-status` | `PERSONS_READ` | estado actual (o null) |
| `POST` | `/persons/{id}/lead-status` | `LEAD_ACTIVITIES_WRITE` | crear lead (nace en `is_initial`); body `{source_campaign_id?, reason?}` |
| `POST` | `/persons/{id}/lead-status/transition` | `LEAD_ACTIVITIES_WRITE` | `{to_lead_status_id, reason?}`; valida matriz; si destino `is_final` → cierra |
| `POST` | `/persons/{id}/promote-to-customer` | `LEAD_ACTIVITIES_WRITE` | crea `PersonCustomerStatus(is_initial)`, cierra lead con `is_won` si aplica |
| `GET` | `/persons/{id}/lead-status/history` | `LEAD_STATUS_HISTORY_READ` | timeline de cambios |
| `GET`/`POST` | `/persons/{id}/customer-status[/transition]` | `PERSONS_READ` (GET) / `LEAD_ACTIVITIES_WRITE` (transition) | análogo customer |
| `GET` | `/persons/{id}/customer-status/history` | `LEAD_STATUS_HISTORY_READ` | |

> El endpoint `POST /persons/{id}/lead-status/close` del overview viejo **desaparece**: cerrar un lead es la consecuencia de una `transition` a un estado `is_final`, no una operación aparte. `promote-to-customer` sí es operación aparte (no es una arista del grafo lead).

### Asignación (owner) + Mis leads

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/persons/{id}/assignment` | `LEAD_ASSIGNMENTS_READ` |
| `PUT` | `/persons/{id}/assignment` | `LEAD_ASSIGNMENTS_WRITE` (`{advisor_user_id, reason?}`; manual / "asignarme") |
| `POST` | `/persons/{id}/assignment/auto` | `LEAD_ASSIGNMENTS_WRITE` (round-robin `SELECT … FOR UPDATE`) |
| `GET` | `/advisors/active` | `LEAD_ASSIGNMENTS_READ` (lista cruda `AdvisorOption` — asesores para el dropdown de asignación; **pertenece a crm**, no a admin) |
| `POST` | `/me/leads/list` | `MY_LEADS_READ` (leads del asesor logueado; `POST` + `QueryRequest` como todos los `/list`) |

### LeadActivity (timeline)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/persons/{id}/activities/list` | `LEAD_ACTIVITIES_READ` (filtros `activity_type[]`, rango fecha) |
| `POST` | `/persons/{id}/activities` | `LEAD_ACTIVITIES_WRITE` (NOTE / CALL_ATTEMPT / FOLLOW_UP_*) |
| `PUT` | `/persons/{id}/activities/{act_id}` | `LEAD_ACTIVITIES_WRITE` (solo `content`/`outcome`/`completed_at`/`scheduled_for`) |
| `DELETE` | `/persons/{id}/activities/{act_id}` | `LEAD_ACTIVITIES_WRITE` (`active=false`, no borra) |

> **`find_by_identifier_or_create`** (orquestación que llamará `conversations`) **no** tiene endpoint público en el MVP: no hay permiso que mapee a "el bot crea contactos por su cuenta". Es una **función de service** documentada en [`backend.md`](backend.md) — ver [Flujo end-to-end](#flujo-end-to-end-típico).

> **Códigos de error de dominio** (`detail` en **español**, `code` en inglés): `PERSON_NOT_FOUND` (404), `IDENTIFIER_NOT_FOUND` (404), `IDENTIFIER_TAKEN` (409), `LEAD_STATUS_NOT_FOUND`/`CUSTOMER_STATUS_NOT_FOUND` (404), `LEAD_STATUS_IN_USE`/`CUSTOMER_STATUS_IN_USE` (409), `NO_INITIAL_LEAD_STATUS` (400), `MULTIPLE_INITIAL_STATUS` (400), `WON_REQUIRES_FINAL` (400), `LEAD_TRANSITION_NOT_ALLOWED` (400), `NO_ACTIVE_LEAD` (400), `ALREADY_HAS_ACTIVE_LEAD` (409), `ALREADY_CUSTOMER` (409), `ASSIGNMENT_NOT_FOUND` (404), `NO_ADVISOR_AVAILABLE` (400), `ADVISOR_NOT_FOUND`/`ADVISOR_NOT_ASESOR` (400), `ACTIVITY_NOT_FOUND` (404). Los validators Pydantic van en inglés (el front re-valida con Zod). La tabla completa con el "cuándo" exacto está en [`backend.md`](backend.md).

## Permisos seed

15 permisos. Ya consolidados en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md#módulo-crm) — **no se redefinen aquí, se referencian**:

```
MENU-CRM · PERSONS_{READ,CREATE,UPDATE,DELETE} ·
LEAD_STATUSES_{READ,WRITE} · CUSTOMER_STATUSES_{READ,WRITE} ·
LEAD_ASSIGNMENTS_{READ,WRITE} · LEAD_ACTIVITIES_{READ,WRITE} ·
LEAD_STATUS_HISTORY_READ · MY_LEADS_READ
```

**Roles seed que tocan `crm`** (subsets canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md#matriz-roles--permisos)):

- `ADMIN` — **todos** los permisos (incluidos los 15 de crm).
- `ASESOR` — corazón de su trabajo: `MENU-CRM`, `PERSONS_{READ,CREATE,UPDATE}` (**no** `PERSONS_DELETE`), `LEAD_STATUSES_READ`, `CUSTOMER_STATUSES_READ`, `LEAD_ASSIGNMENTS_{READ,WRITE}`, `LEAD_ACTIVITIES_{READ,WRITE}`, `LEAD_STATUS_HISTORY_READ`, `MY_LEADS_READ`. **No** edita catálogos de estado (eso es admin).
- `DOCTOR` — solo `PERSONS_READ` (lee los datos del paciente al atender la cita).

> **Nota sobre `SYSTEM` (F0)**: este módulo **introduce el user `SYSTEM` y el role `SYSTEM`**, diferidos desde `staff` (ver [staff/README.md](../staff/README.md#permisos-seed)). El user técnico (`system@medisage.internal`, `active=false`, no autenticable) se usa como `created_by`/`actor_id` de las operaciones automáticas de crm: `find_by_identifier_or_create`, transiciones y round-robin disparados por sistema. El role `SYSTEM` se seedea con **lista de permisos vacía** (`SYSTEM_PERMISSION_CODES = set()`). El backend nunca resuelve `CurrentAuth` a este user — el `active=false` lo bloquea en el login normal. Definición canónica y patch de `seed.py` en [`_seed-and-roles.md`](../_seed-and-roles.md#system).

## Decisiones de diseño (no obvias)

### Person + estados separados — [ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md)

`Person` raíz + estados lead/customer en tablas hijas separadas, cada una con `UNIQUE person_id`, coexistentes. Alternativas (columna `stage` enum, dos entidades `Lead`/`Patient`, dos columnas FK en `Person`) y razones de rechazo en el ADR. **Aceptado, firmado @daniel/@marco, no se re-litiga.** Esta ficha detalla el modelo que el ADR dejó abierto (matriz de transiciones, round-robin, FKs forward).

### Un único lead/customer activo por Person (`UNIQUE person_id`)

Confirmado por usuario. Razón: la operación quiere una respuesta inequívoca a "¿en qué estado está su lead?" — sin ambigüedad sobre "a cuál de varios leads aplico la acción". Si una persona ya cliente vuelve a interesarse, se **cierra** el lead anterior (soft-delete de `PersonLeadStatus`) y se **reabre** uno nuevo (fila nueva). La traza histórica completa queda en `LeadStatusHistory` (con su `source_campaign_id` por cada apertura).

### Matriz de transiciones configurable — ADR-008

**Decisión Q3 del usuario.** Las transiciones permitidas entre estados se modelan como filas en `lead_status_transition` / `customer_status_transition` (aristas `from→to`), **seedeadas con una base** (ver tabla abajo) y **editables por admin** ("matriz base que luego actualizamos"). El service de transición rechaza una arista ausente con `LEAD_TRANSITION_NOT_ALLOWED` (400). Esto **supersede** la nota "futura ADR" que ADR-003 dejó abierta sobre las reglas de transición. El ADR-008 formal se redacta en la consolidación post-fichas (ver [Próximos pasos](#próximos-pasos--todos-deliberados)).

**Matriz base seedeada — Lead** (sobre los 7 estados seed):

```
NUEVO                → INTENTANDO_CONTACTAR, NO_INTERESADO
INTENTANDO_CONTACTAR → CONTACTADO, NO_INTERESADO
CONTACTADO           → INTERESADO, INTENTANDO_CONTACTAR (re-contacto), NO_INTERESADO
INTERESADO           → EVALUANDO, NO_INTERESADO
EVALUANDO            → CITA_AGENDADA, INTERESADO, NO_INTERESADO
CITA_AGENDADA  (is_final/is_won) → (terminal, sin aristas de salida)
NO_INTERESADO  (is_final)        → (terminal)
```

**Matriz base seedeada — Customer** (permisiva): las no-finales (`ACTIVO`, `EN_TRATAMIENTO`, `COMPLETADO`) transicionan libremente entre sí y hacia las finales (`INACTIVO`, `PERDIDO`); `INACTIVO → ACTIVO` (reactivar); `PERDIDO` (is_final) terminal.

**Estados seed** — `LeadStatus` (7) y `CustomerStatus` (5) se seedean en `seed.py` (`_seed_lead_statuses` / `_seed_customer_statuses`, idempotentes; ver [`_seed-and-roles.md`](../_seed-and-roles.md#catálogos-configurables-seed)). Listas exactas `(code, name, color, flags, display_order)` en [`backend.md`](backend.md). `CITA_AGENDADA` es el único `is_won=true` (y `is_final=true`); `is_won ⟹ is_final` (`WON_REQUIRES_FINAL`); exactamente un `is_initial` por catálogo (`NUEVO` / `ACTIVO`).

### Round-robin de asignación (manual + automático, sin tabla de estado)

**Confirmado por usuario.** La asignación de owner admite dos vías:
- **Manual** (`PUT /persons/{id}/assignment`): el asesor se auto-asigna ("asignarme") o un admin reasigna a `advisor_user_id`. El service valida que el user exista y tenga rol `ASESOR` (`ADVISOR_NOT_ASESOR`).
- **Automática** (`POST /persons/{id}/assignment/auto`, y dentro de `find_by_identifier_or_create`): round-robin **por carga real**, no por orden circular ciego. Query: asesores (`role=ASESOR`, `active`, no borrado) `ORDER BY COUNT(leads activos) ASC, MAX(assigned_at) ASC NULLS FIRST LIMIT 1`, con `SELECT … FOR UPDATE` sobre el candidato para evitar el race de dos leads simultáneos. Sin tabla `RoundRobinState`; el balanceo se auto-corrige cuando un asesor entra/sale. `assigned_by = NULL` (auto) o `SYSTEM`. Si no hay asesor activo → `NO_ADVISOR_AVAILABLE`.

Reasignar = soft-delete fila actual + insert nueva + `LeadActivity(REASSIGNED)`, en una tx.

### FKs forward a módulos futuros: "columna ahora, constraint después" — ADR-009

`crm` se construye **antes** que `marketing`, `scheduling` y `conversations`, así que las tablas `campaign`, `appointment` y `conversation` **no existen todavía**. Las tres columnas que las referencian existen ya, pero **sin FK física** (una `ForeignKey` a una tabla inexistente rompería la migración; un `relationship()` a una clase inexistente rompería la configuración del mapper al importar):

| Columna | Tabla(s) | Tipo ahora | FK real la agrega |
|---|---|---|---|
| `source_campaign_id` | `person_lead_status`, `lead_status_history` | `varchar(36)` nullable, **indexado** | migración de `marketing` (`ALTER TABLE … ADD CONSTRAINT`) |
| `related_appointment_id` | `lead_activity` | `varchar(36)` nullable, indexado | migración de `scheduling` |
| `related_conversation_id` | `lead_activity` | `varchar(36)` nullable, indexado | migración de `conversations` |

Regla **no negociable**: en el ORM, solo `mapped_column(String(36), nullable=True, index=True)` — **nunca** `ForeignKey("campaign.id")` ni `relationship()` a `Campaign`/`Appointment`/`Conversation`. La FK constraint y el `relationship` los agrega de forma **aditiva** el módulo dueño cuando crea su tabla. Patrón reusable cross-módulo, formalizado en ADR-009 (se redacta en la consolidación post-fichas).

### `LeadActivity` polimórfica con `payload` JSONB

**De [ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md), confirmado por usuario.** El timeline crece con tipos heterogéneos que comparten ~80% de columnas (actor, fecha, content, outcome). Columnas comunes tipadas + `payload` libre por tipo balancean estructura y flexibilidad. El `activity_type` es un **enum cerrado en código** (no catálogo en BD): a diferencia de los estados de lead/cliente (que la operación cambia sin deploy), los tipos de activity son **contratos con el sistema** — `MESSAGE_SENT` lo emite `conversations`, `APPOINTMENT_BOOKED` lo emite `scheduling`; agregar uno nuevo requiere tocar el código que lo emite y lo consume. Si un tipo crece y merece columnas propias, se promueven con migración (Postgres indexa JSONB con `GIN`).

### Dedup `UNIQUE(channel_type, identifier)` parcial

Garantiza que un mismo phone de WhatsApp pertenezca a **una sola** persona — base del matching de `conversations` al recibir un mensaje entrante. Índice **parcial** (`WHERE deleted_at IS NULL`) para permitir reasignar el identifier a otra persona después de un soft-delete. Violación → `IDENTIFIER_TAKEN` (409).

### Historiales y actividad sin SoftDelete

`LeadStatusHistory`, `CustomerStatusHistory` y `LeadActivity` **no** llevan `SoftDeleteMixin` — la auditoría es honesta o no es. Los historiales no se borran nunca. En `LeadActivity`, "borrar" = `active=false` (desaparece del feed normal, pero la fila permanece para auditoría); si una actividad fue un error, se desactiva en lugar de borrarse.

### Denormalización sin N+1 (patrón staff/clinic)

Los listados llevan campos denormalizados resueltos vía **batch lookups** en el service (sin N+1, como en staff/clinic): `PersonItem` lleva `primary_identifier`, `lead_status` (code/name/color), `customer_status`, `assigned_advisor` (full_name) y `last_activity_at`; `LeadActivityItem` lleva `advisor: UserAuditInfo` (patrón audit users del template, vía `user_repository.get_audit_info_map`). **Lección hotfix `cd10c78` de staff**: el `ALLOWED_FIELDS` de `Person` **NO incluye** los campos denormalizados → filtrar/ordenar por ellos da 400; la búsqueda por nombre/identificador es **client-side**, y el deep-link por `lead_status_id`/`customer_status_id`/`advisor_user_id` se traduce a `EXISTS`/JOIN en el service (como el `?branch_id=` de staff).

## Flujo end-to-end típico

Recorrido de un lead desde un mensaje entrante hasta su conversión. Las partes ⏳ dependen de módulos futuros (la columna/enum existe en crm, pero quien las dispara aún no está construido).

1. **Mensaje entra** (WhatsApp/Telegram/web) → `conversations` ⏳ matchea `Person` por `PersonContactIdentifier (channel_type, identifier)`.
2. **No existe** → `conversations` ⏳ llamará a la función de service **`person.find_by_identifier_or_create(db, channel_type, identifier, profile, *, campaign_id=None)`**, que en **una sola tx** crea: `Person` (datos mínimos del profile) + `PersonContactIdentifier` + `PersonLeadStatus(is_initial)` + `LeadStatusHistory(NULL→initial, source_campaign_id)` + `LeadAssignment(round-robin)` + `LeadActivity(CAMPAIGN_ATTRIBUTION)` si hay `campaign_id`. `created_by = SYSTEM`. **Esta función ya existe en crm (F5)**; lo que falta hasta `conversations` es **quién la invoca**.
3. **Existe** → `bots` ⏳ decide preventa vs postventa con `SELECT EXISTS(... person_customer_status WHERE person_id=? AND deleted_at IS NULL)`.
4. **Asesor trabaja el lead** → registra `NOTE` / `CALL_ATTEMPT` / `FOLLOW_UP_SCHEDULED` (`POST /persons/{id}/activities`); el timeline los muestra agrupados por día.
5. **Asesor transiciona estado** → `POST /persons/{id}/lead-status/transition` → service valida la arista en la matriz, actualiza `PersonLeadStatus`, escribe `LeadStatusHistory` + `LeadActivity(STATUS_CHANGE)`; si el destino es `is_final`, soft-deletea la fila (lead cerrado).
6. **Conversión** → `POST /persons/{id}/promote-to-customer` → crea `PersonCustomerStatus(is_initial)` + `CustomerStatusHistory(NULL→initial)`, cierra el lead con `is_won` si aplica, emite `LeadActivity`. Más adelante, `scheduling` ⏳ podrá disparar esto al completar la atención y emitirá `LeadActivity(APPOINTMENT_BOOKED/CANCELLED)`.

## Dependencias entre módulos

| Módulo | Relación | FK aditiva esperada |
|---|---|---|
| `admin` | `LeadAssignment.advisor_user_id`, `LeadActivity.advisor_user_id`, `changed_by`/`assigned_by`, audit users (`created_by`/`updated_by`) — FKs lógicas a `user.id`. El round-robin filtra `user` con `role=ASESOR`. F0 introduce el user/role `SYSTEM`. | — (ya existe `user`) |
| `marketing` | `PersonLeadStatus.source_campaign_id`, `LeadStatusHistory.source_campaign_id` apuntan a `campaign`. | **Sí**: `marketing` agrega `FK + relationship` a esas dos columnas al crear `campaign`. |
| `conversations` | Matchea `Person` por `PersonContactIdentifier`; llamará a `find_by_identifier_or_create`; emitirá `LeadActivity(MESSAGE_SENT/CONVERSATION_*)`. `LeadActivity.related_conversation_id` apunta a `conversation`. `Conversation.person_id` será FK a `person`. | **Sí**: `conversations` agrega FK a `lead_activity.related_conversation_id`. |
| `bots` | Lee `PersonCustomerStatus` para decidir preventa/postventa. NO escribe en crm. | — (solo lectura) |
| `scheduling` | `appointment.person_id` será FK a `person`; emitirá `LeadActivity(APPOINTMENT_*)` y podrá disparar `promote-to-customer`. `LeadActivity.related_appointment_id` apunta a `appointment`. | **Sí**: `scheduling` agrega FK a `lead_activity.related_appointment_id`. |

`crm` depende solo de `admin` (audit users + asesores para el round-robin). No depende de `marketing`/`conversations`/`scheduling`/`bots` — esos llegan después y se enganchan aditivamente vía las columnas forward.

## Diagramas

- ER: [`docs/diagrams/er-crm.puml`](../../diagrams/er-crm.puml)
- Class diagram (modelos + repos + services): [`docs/diagrams/class-backend-crm.puml`](../../diagrams/class-backend-crm.puml)

> Ambos diagramas reflejan el **modelo viejo** (10 entidades, FKs directas a `campaign`/`appointment`/`conversation`, `PATCH`/`/options`). Se **regeneran al modelo de esta spec** en la consolidación post-fichas (lo hace el implementador): agregar `LeadStatusTransition`/`CustomerStatusTransition`, marcar las tres columnas forward como "sin FK aún", reflejar `PUT`/`/active`.

## Implementación por fases

`crm` es el módulo más grande: una fase por grupo cohesivo de entidades, de padre a hijo. Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist mapeado a estas fases.

| Fase | Alcance | Migración (revid ≤32) |
|---|---|---|
| **F0 — Prep** | 16 permisos CRM → `SEED_PERMISSIONS` (ya canónicos en [`_seed-and-roles.md`](../_seed-and-roles.md)); **introducir user `SYSTEM` (`active=false`) + role `SYSTEM` (perms vacíos)** (diferido desde staff); nav grupo CRM + iconos; `endpoints.ts`; `types/crm.types.ts`; skeleton del paquete backend `crm`. | ninguna (solo seed) |
| **F1 — Person + Identifiers** | `Person` CRUD + `PersonContactIdentifier` (dedup UNIQUE parcial, `is_primary`, `verified`) + `/persons/search` + `/active`; lista `/crm/personas` + drawer + detalle (tabs Datos/Identificadores/Auditoría; Lead/Cliente/Actividad placeholders). | `0011_crm_person` |
| **F2 — Catálogos + matriz** | `LeadStatus`/`CustomerStatus` CRUD + seed (7+5) + `LeadStatusTransition`/`CustomerStatusTransition` + seed matriz base + UI `/crm/estados-lead`/`/crm/estados-cliente` con editor de transiciones. | `0012_crm_status_catalogs` |
| **F3 — Lead lifecycle** | `PersonLeadStatus` + `LeadStatusHistory` + transition (valida matriz) + `LeadAssignment` (manual + round-robin auto) + `MY_LEADS` + `LeadActivity` (tabla + `STATUS_CHANGE`/`REASSIGNED`) + tab Lead + `AssignmentControl` + `/crm/mis-leads`. | `0013_crm_lead_lifecycle` |
| **F4 — Customer lifecycle** | `PersonCustomerStatus` + `CustomerStatusHistory` + `promote_to_customer` + tab Cliente. | `0014_crm_customer_lifecycle` |
| **F5 — Timeline + orquestación** | `LeadActivity` rico (NOTE/CALL_ATTEMPT/FOLLOW_UP_*) + el timeline UI pesado (composer/chips/day-groups) + `find_by_identifier_or_create` completo + enum `ActivityType` completo (tipos cross-module presentes, emisión diferida). | ninguna (tablas ya existen) |

> **Migraciones**: revision id ≤ 32 chars (límite `alembic_version varchar(32)`). La última aplicada es `0010_staff_doctor_availability`, así que crm arranca en `0011`. Sugeridas y verificadas ≤32: `0011_crm_person` (15) · `0012_crm_status_catalogs` (24) · `0013_crm_lead_lifecycle` (23) · `0014_crm_customer_lifecycle` (27). Encadenar `down_revision`. Las columnas forward se crean como `varchar(36)` indexado **sin** `ForeignKey`.

## Próximos pasos / TODOs deliberados

- [x] **Consolidación post-fichas (HECHA, 2026-05-31)**: creados [ADR-008](../../decisions/ADR-008-configurable-status-transition-matrix.md) (matriz de transiciones configurable — supersede la nota "futura ADR" de ADR-003) y [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (FKs forward diferidas, patrón reusable); [ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md) anotado (sigue Accepted, modelo ahora detallado); índice `docs/decisions/README.md` actualizado; diagramas `er-crm.puml` + `class-backend-crm.puml` regenerados al modelo final (12 entidades, transition tables, columnas forward sin FK); overview viejo `docs/modules/crm.md` borrado y sus links repuntados a este README ([ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md), [`_seed-and-roles.md`](../_seed-and-roles.md), `scheduling.md`, `docs/diagrams/README.md`).
- [ ] **FK aditivas** cuando lleguen los módulos dueños: `marketing` → FK + relationship a `person_lead_status.source_campaign_id` y `lead_status_history.source_campaign_id`; `scheduling` → FK a `lead_activity.related_appointment_id` (+ `appointment.person_id`); `conversations` → FK a `lead_activity.related_conversation_id` (+ `conversation.person_id`). Documentarlo también como TODO en los overviews de esos módulos al diseñarlos.
- [ ] **`find_by_identifier_or_create`** queda como función de service sin endpoint en el MVP; al diseñar `conversations`, validar que su firma `(db, channel_type, identifier, profile, *, campaign_id=None)` cubra los datos del profile entrante y que `conversations` la invoque con `created_by = SYSTEM`.
- [ ] **Índice GIN sobre `LeadActivity.payload`** si emergen queries frecuentes sobre campos del JSONB (no en el MVP).
- [ ] Considerar `MedicalRecord` 1:1 con `Person` cuando el negocio requiera historia clínica (postergado; `Person` no lleva datos médicos en el MVP).
- [ ] Si los reportes de "leads por fuente" se vuelven dominantes, considerar denormalizar `source_campaign_id` también en `PersonCustomerStatus` para conversiones rápidas.
