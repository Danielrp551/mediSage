# Módulo `crm`

> **Última actualización**: 2026-05-28
> **Propósito**: contactos (`Person`) y su ciclo de vida lead/cliente, incluyendo identificadores multicanal, asignación de owner, historial de estados y timeline de actividad.
> **Path del código**: `backend/app/modules/crm/`

## Resumen

`Person` es la entidad raíz del contacto comercial. Su ciclo de vida en la clínica tiene **dos hilos paralelos**:

```
                ┌─────────────────────────────┐
                │  PersonLeadStatus (activo)  │  ← un solo lead activo por Person
                │  + LeadStatusHistory        │  ← traza completa de transiciones
                │  + LeadAssignment (owner)   │  ← asesor responsable
                └─────────────────────────────┘
   Person ──┤
                ┌─────────────────────────────┐
                │  PersonCustomerStatus       │  ← cliente actual de la clínica
                │  + CustomerStatusHistory    │
                └─────────────────────────────┘
```

Una persona puede tener **uno o ambos** estados activos simultáneamente: ya es cliente (`CustomerStatus`) **y** está siendo cultivada como lead de otra campaña (`LeadStatus`). Esto motiva la separación en tablas hijas. Decisión documentada en [ADR-003](../decisions/ADR-003-person-with-separated-lifecycle-statuses.md).

Sobre este módulo se asientan:
- `conversations` (busca Person por `PersonContactIdentifier` al recibir un mensaje entrante);
- `bots` (decide preventa/postventa según si hay `PersonCustomerStatus` activo);
- `scheduling` (`appointment.person_id` FK a `person`).

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Person` | `person` | Identidad + contacto. Sin datos médicos en MVP. |
| `PersonContactIdentifier` | `person_contact_identifier` | M:N de identifiers multicanal (whatsapp, telegram, web, phone, email). |
| `LeadStatus` | `lead_status` | Catálogo configurable de estados de lead. |
| `CustomerStatus` | `customer_status` | Catálogo configurable de estados de cliente. |
| `PersonLeadStatus` | `person_lead_status` | Estado lead **actual** de un Person. UNIQUE por person — un solo lead activo. |
| `PersonCustomerStatus` | `person_customer_status` | Estado cliente **actual** de un Person. UNIQUE por person. |
| `LeadStatusHistory` | `lead_status_history` | Timeline inmutable de transiciones de estado lead. |
| `CustomerStatusHistory` | `customer_status_history` | Timeline inmutable de transiciones de estado cliente. |
| `LeadAssignment` | `lead_assignment` | Owner (asesor) del lead activo. UNIQUE por person. |
| `LeadActivity` | `lead_activity` | Timeline polimórfico de actividad del asesor sobre el lead. |

### `Person`

Identidad + contacto. Confirmado: **sin datos médicos** en MVP. Si en el futuro se agregue historia clínica, será módulo aparte (`medical_record` 1:1 con Person).

- `first_name: varchar(80)`.
- `last_name: varchar(80)`.
- `second_last_name: varchar(80)` `<<nullable>>`.
- `document_type: varchar(20)` `<<nullable>>` — DNI / RUC / CE (consistente con `admin.User`).
- `document_number: varchar(40)` `<<nullable, indexed>>`.
- `birth_date: date` `<<nullable>>`.
- `gender: varchar(20)` `<<nullable>>` — texto libre normalizado en frontend (M, F, X, prefer-not-to-say). Sin enum para inclusividad y porque no afecta lógica de negocio.
- `address: varchar(255)` `<<nullable>>`.
- `notes: text` `<<nullable>>` — notas administrativas libres (el asesor puede pegar contexto general).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Nota sobre `phone`/`email`**: NO viven como columnas de Person. Viven en `PersonContactIdentifier`, que permite multicanal sin migración futura.

### `PersonContactIdentifier`

M:N de identifiers por canal. Una persona puede tener varios numeros de WhatsApp, un email, un handle de Telegram, etc.

- `person_id: varchar(36)` `<<FK→person>>`.
- `channel_type: varchar(40)` — uno de `{whatsapp, telegram, web, phone, email, instagram, facebook, ...}`. Validado en Pydantic con enum cerrado. **No** es FK a un catálogo en BD: es un slug estable que cruza con `conversations.ChannelAccount.channel_type`.
- `identifier: varchar(255)` — el valor: phone normalizado E.164 (`+51999111222`), email (`name@x.com`), Telegram chat_id, etc.
- `is_primary: bool` `default false` — uno marcado como principal por `(person_id, channel_type)`. Validado en service (no constraint, porque cambiar "el principal" requiere update de dos filas).
- `verified: bool` `default false` — si fue verificado (ej. el lead respondió al opt-in del bot). Opcional, default `false`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.
- **UNIQUE `(channel_type, identifier)`** — el mismo phone WhatsApp no puede pertenecer a dos personas. Filtrado por `deleted_at IS NULL` vía partial unique index para soportar reasignación post soft-delete.

### `LeadStatus` (catálogo configurable)

Catálogo en BD para que admin pueda renombrar o agregar estados sin tocar código.

- `code: varchar(40)` `<<unique>>` — slug estable (`NUEVO`, `INTERESADO`). Usado por el código y por los bots para reaccionar a estados específicos.
- `name: varchar(120)` — nombre visible en UI.
- `description: varchar(500)` `<<nullable>>`.
- `color: varchar(20)` `<<nullable>>` — hex para badges.
- `is_initial: bool` `default false` — flag "es el estado por defecto al crear un lead nuevo". **Exactamente uno** debe tener este flag (validado en service al crear/editar).
- `is_final: bool` `default false` — terminal: si el lead llega aquí, ya no se trabaja.
- `is_won: bool` `default false` — terminal positivo (lead convertido). Sólo aplica si `is_final=true`.
- `display_order: int` `default 0`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Estados seed (granular: 7)**:

```python
LEAD_STATUSES_SEED = [
    # code, name, color, is_initial, is_final, is_won, display_order
    ("NUEVO",                 "Nuevo",                 "#9CA3AF", True,  False, False, 10),
    ("INTENTANDO_CONTACTAR",  "Intentando contactar",  "#F59E0B", False, False, False, 20),
    ("CONTACTADO",            "Contactado",            "#3B82F6", False, False, False, 30),
    ("INTERESADO",            "Interesado",            "#06B6D4", False, False, False, 40),
    ("EVALUANDO",             "Evaluando",             "#8B5CF6", False, False, False, 50),
    ("CITA_AGENDADA",         "Cita agendada",         "#22C55E", False, True,  True,  60),
    ("NO_INTERESADO",         "No interesado",         "#EF4444", False, True,  False, 70),
]
```

### `CustomerStatus` (catálogo configurable)

Análogo a `LeadStatus`. No tiene `is_won` (el cliente ya está ganado al ser cliente). Sí tiene `is_initial` (estado por defecto al convertir lead → cliente) e `is_final` (terminal: cliente perdido, no se vuelve a trabajar).

**Estados seed (granular: 5)**:

```python
CUSTOMER_STATUSES_SEED = [
    # code, name, color, is_initial, is_final, display_order
    ("ACTIVO",         "Activo",         "#22C55E", True,  False, 10),
    ("EN_TRATAMIENTO", "En tratamiento", "#06B6D4", False, False, 20),
    ("COMPLETADO",     "Completado",     "#8B5CF6", False, False, 30),
    ("INACTIVO",       "Inactivo",       "#9CA3AF", False, False, 40),
    ("PERDIDO",        "Perdido",        "#EF4444", False, True,  50),
]
```

### `PersonLeadStatus`

Estado lead actual del Person. **UNIQUE por person_id** — un único lead activo a la vez. Confirmado en respuesta del usuario.

- `person_id: varchar(36)` `<<unique, FK→person>>`.
- `lead_status_id: varchar(36)` `<<FK→lead_status>>`.
- `source_campaign_id: varchar(36)` `<<nullable, FK→campaign>>` — de qué campaña vino este lead (módulo `marketing`).
- `entered_status_at: timestamptz` — cuándo entró al estado actual.
- `last_activity_at: timestamptz` `<<nullable>>` — denormalizado para listados sin join a `LeadActivity`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Flujo de cierre**: cuando el lead se cierra (transición a estado con `is_final=true`), la fila se borra (`DELETE`) y se mantiene la traza en `LeadStatusHistory`. Si la persona vuelve a ser lead, se crea una **nueva** fila. Esto deja `PersonLeadStatus` siempre representando "el lead activo del momento".

### `PersonCustomerStatus`

Análogo a `PersonLeadStatus`. Sin `source_campaign_id` (el customer no viene de campaña directamente — viene de una conversión desde lead, trazada en `LeadStatusHistory`).

- `person_id: varchar(36)` `<<unique, FK→person>>`.
- `customer_status_id: varchar(36)` `<<FK→customer_status>>`.
- `became_customer_at: timestamptz` — cuándo se hizo cliente por primera vez.
- `entered_status_at: timestamptz` — cuándo entró al estado **actual** (si pasa de ACTIVO a INACTIVO, esto se actualiza).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `LeadStatusHistory` / `CustomerStatusHistory`

Historial inmutable de transiciones. **No se borra nunca** (audit trail honesto). Cada fila representa un cambio.

`LeadStatusHistory`:
- `person_id: varchar(36)` `<<FK→person>>`.
- `from_lead_status_id: varchar(36)` `<<nullable, FK→lead_status>>` — `NULL` cuando se crea el lead.
- `to_lead_status_id: varchar(36)` `<<FK→lead_status>>`.
- `source_campaign_id: varchar(36)` `<<nullable, FK→campaign>>` — solo se llena al crear el lead (transición desde NULL).
- `changed_at: timestamptz`.
- `changed_by: varchar(36)` `<<nullable>>` — `user.id` del actor; `NULL` si la transición fue automática (bot, sistema).
- `reason: varchar(255)` `<<nullable>>` — texto libre opcional.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — historial no se borra ni soft-deletea.

`CustomerStatusHistory`: análogo (`from_customer_status_id`, `to_customer_status_id`, sin `source_campaign_id`).

### `LeadAssignment`

Owner actual del lead. **UNIQUE por person_id** — un solo asesor responsable a la vez.

- `person_id: varchar(36)` `<<unique, FK→person>>`.
- `advisor_user_id: varchar(36)` `<<FK→user>>`.
- `assigned_at: timestamptz`.
- `assigned_by: varchar(36)` `<<nullable>>` — `user.id` del actor; `NULL` si fue round-robin automático.
- `reason: varchar(255)` `<<nullable>>` — texto libre ("rotación", "reasignación manual por XYZ").
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Round-robin** (cómo se implementa, sin tabla extra de estado):

```sql
-- "Siguiente asesor para el lead nuevo": el que tenga menos leads activos.
-- Empate → el que recibió hace más tiempo (justo).
SELECT u.id
FROM "user" u
JOIN user_role ur ON ur.user_id = u.id
JOIN role r ON r.id = ur.role_id
LEFT JOIN lead_assignment la ON la.advisor_user_id = u.id AND la.deleted_at IS NULL
WHERE r.name = 'ASESOR' AND u.active = true AND u.deleted_at IS NULL
GROUP BY u.id
ORDER BY COUNT(la.id) ASC, MAX(la.assigned_at) ASC NULLS FIRST
LIMIT 1;
```

Esto evita una tabla `RoundRobinState` y mantiene la equidad por carga real, no por orden circular ciego. Documentado como decisión inline (no ADR — es implementación trivial).

**Reasignación**: cuando un admin/asesor reasigna manualmente, el service `update`:
1. Marca la fila actual como `deleted_at = now()` (soft delete).
2. Inserta nueva fila con el nuevo `advisor_user_id` y `assigned_by = actor`.
3. Registra una entrada en `LeadActivity` con `activity_type = REASSIGNED`.

### `LeadActivity` (timeline polimórfico)

Timeline unificado de cualquier evento del asesor sobre el lead. **Tipo polimórfico** con `payload: JSONB` libre por tipo.

- `person_id: varchar(36)` `<<FK→person>>`.
- `advisor_user_id: varchar(36)` `<<nullable, FK→user>>` — actor; `NULL` para actividades de sistema.
- `activity_type: varchar(40)` — enum cerrado (no catálogo). Ver lista abajo.
- `content: text` `<<nullable>>` — texto libre (nota del asesor, resumen).
- `scheduled_for: timestamptz` `<<nullable>>` — solo para `FOLLOW_UP_SCHEDULED`.
- `completed_at: timestamptz` `<<nullable>>` — para activities con concepto de "completado" (call_attempt, follow_up).
- `outcome: varchar(40)` `<<nullable>>` — `successful / no_answer / busy / wrong_number / not_interested / interested` etc.
- `payload: jsonb` `<<nullable>>` — datos específicos del tipo.
- `related_appointment_id: varchar(36)` `<<nullable, FK→appointment>>` — si aplica.
- `related_conversation_id: varchar(36)` `<<nullable, FK→conversation>>` — si aplica.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — actividades no se borran (auditoría); si fueron error, se marca `active=false` o se agrega una nueva activity `CORRECTION` referenciándola.

**Tipos de activity (enum cerrado en código)**:

| `activity_type` | Quién crea | Campos clave del payload |
|---|---|---|
| `CALL_ATTEMPT` | asesor | `phone, duration_sec?, audio_url?` |
| `NOTE` | asesor | `content` |
| `STATUS_CHANGE` | sistema/asesor | `from_status, to_status` (también queda en `LeadStatusHistory` — esta entry es para que aparezca en el timeline unificado) |
| `FOLLOW_UP_SCHEDULED` | asesor | `scheduled_for`, `reminder_channel ∈ {whatsapp, email}` |
| `FOLLOW_UP_COMPLETED` | asesor | referencia a la activity scheduled previa via `payload.followup_id` |
| `MESSAGE_SENT` | asesor | `channel, message_id` (FK a `conversations.message`) |
| `CONVERSATION_TAKEN` | sistema | `conversation_id`, `taken_by` |
| `CONVERSATION_RELEASED` | sistema/asesor | `conversation_id`, `released_to` |
| `APPOINTMENT_BOOKED` | sistema | `appointment_id` |
| `APPOINTMENT_CANCELLED` | sistema | `appointment_id`, `reason` |
| `REASSIGNED` | sistema | `from_advisor_id, to_advisor_id, by_actor_id` |
| `CAMPAIGN_ATTRIBUTION` | sistema | `campaign_id` — registrada al crear el lead |

El frontend muestra el timeline ordenado por `created_on DESC`. La UX puede filtrar por `activity_type` o agrupar por día.

## Esquemas (Pydantic v2)

Variantes habituales (`Create / Update / Item / Detail / Option`). Específicos del módulo:

- `PersonDetail` extiende `PersonItem` con `identifiers: list[PersonContactIdentifierItem]`, `lead_status: LeadStatusOption?`, `customer_status: CustomerStatusOption?`, `assignment: LeadAssignmentItem?`.
- `LeadActivityItem` lleva el `advisor` resuelto a `UserAuditInfo` (patrón audit users del template) además de los campos base.
- `LeadStatusTransitionRequest { to_lead_status_id, reason? }` — body para `POST /persons/{id}/lead-status/transition`. El service valida la transición permitida, persiste el nuevo `PersonLeadStatus` o lo cierra (si es final), y agrega entries en `LeadStatusHistory` + `LeadActivity`.

## Endpoints

Bajo `/api/v1/crm/`.

### Person

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/persons/list` | `PERSONS_READ` |
| `POST` | `/persons` | `PERSONS_CREATE` |
| `GET` | `/persons/{id}` | `PERSONS_READ` |
| `PATCH` | `/persons/{id}` | `PERSONS_UPDATE` |
| `DELETE` | `/persons/{id}` | `PERSONS_DELETE` |
| `GET` | `/persons/options` | `PERSONS_READ` |
| `GET` | `/persons/search?q=&channel_type=&identifier=` | `PERSONS_READ` | búsqueda por nombre/doc/identifier — usada por bot/conversations al recibir mensaje |

### PersonContactIdentifier

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/persons/{id}/identifiers` | `PERSONS_READ` |
| `POST` | `/persons/{id}/identifiers` | `PERSONS_UPDATE` |
| `PATCH` | `/persons/{id}/identifiers/{ident_id}` | `PERSONS_UPDATE` |
| `DELETE` | `/persons/{id}/identifiers/{ident_id}` | `PERSONS_UPDATE` |

### Catálogos LeadStatus / CustomerStatus

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/lead-statuses/list` | `LEAD_STATUSES_READ` |
| `POST` | `/lead-statuses` | `LEAD_STATUSES_WRITE` |
| `PATCH` | `/lead-statuses/{id}` | `LEAD_STATUSES_WRITE` |
| `DELETE` | `/lead-statuses/{id}` | `LEAD_STATUSES_WRITE` |
| `GET` | `/lead-statuses/options` | `LEAD_STATUSES_READ` |
| _(idem)_ | `/customer-statuses/...` | `CUSTOMER_STATUSES_*` |

### Estado de un Person (lead/customer)

| Método | Ruta | Permiso | Descripción |
|---|---|---|---|
| `GET` | `/persons/{id}/lead-status` | `PERSONS_READ` | estado actual |
| `POST` | `/persons/{id}/lead-status/transition` | `LEAD_ACTIVITIES_WRITE` | transicionar al siguiente estado |
| `POST` | `/persons/{id}/lead-status/close` | `LEAD_ACTIVITIES_WRITE` | cerrar lead (final state) |
| `GET` | `/persons/{id}/lead-status/history` | `LEAD_STATUS_HISTORY_READ` | timeline de cambios |
| `POST` | `/persons/{id}/promote-to-customer` | `LEAD_ACTIVITIES_WRITE` | crea `PersonCustomerStatus`, cierra `PersonLeadStatus` con `is_won=true` si aplica |
| _(idem)_ | `/persons/{id}/customer-status/...` | `CUSTOMER_*` | análogos para customer |

### Owner del lead

| Método | Ruta | Permiso |
|---|---|---|
| `GET` | `/persons/{id}/assignment` | `LEAD_ASSIGNMENTS_READ` |
| `PUT` | `/persons/{id}/assignment` | `LEAD_ASSIGNMENTS_WRITE` | reasignación manual (body: `{advisor_user_id, reason?}`) |
| `POST` | `/persons/{id}/assignment/auto` | `LEAD_ASSIGNMENTS_WRITE` | trigger round-robin auto (idempotente: si ya tiene owner, no-op o re-rota según body) |
| `GET` | `/me/leads/list` | `MY_LEADS_READ` | leads asignados al asesor logueado |

### LeadActivity (timeline)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/persons/{id}/activities/list` | `LEAD_ACTIVITIES_READ` |
| `POST` | `/persons/{id}/activities` | `LEAD_ACTIVITIES_WRITE` |
| `PATCH` | `/persons/{id}/activities/{act_id}` | `LEAD_ACTIVITIES_WRITE` | solo content/outcome editables |
| `DELETE` | `/persons/{id}/activities/{act_id}` | `LEAD_ACTIVITIES_WRITE` | marca `active=false`, no borra |

## Permisos seed

```python
# Module: crm
("MENU-CRM", "Ver menú CRM", "Gestión de contactos y leads", "crm"),
("PERSONS_READ", "Ver contactos", "Listar y consultar personas", "crm"),
("PERSONS_CREATE", "Crear contactos", "Crear nuevas personas", "crm"),
("PERSONS_UPDATE", "Editar contactos", "Editar datos y identifiers", "crm"),
("PERSONS_DELETE", "Eliminar contactos", "Soft-delete de personas", "crm"),
("LEAD_STATUSES_READ", "Ver catálogo lead-status", "Consultar estados de lead", "crm"),
("LEAD_STATUSES_WRITE", "Editar catálogo lead-status", "Crear/editar estados de lead", "crm"),
("CUSTOMER_STATUSES_READ", "Ver catálogo customer-status", "Consultar estados de cliente", "crm"),
("CUSTOMER_STATUSES_WRITE", "Editar catálogo customer-status", "Crear/editar estados de cliente", "crm"),
("LEAD_ASSIGNMENTS_READ", "Ver asignaciones de leads", "Consultar quién atiende qué lead", "crm"),
("LEAD_ASSIGNMENTS_WRITE", "Reasignar leads", "Reasignar manualmente / disparar round-robin", "crm"),
("LEAD_ACTIVITIES_READ", "Ver actividades del lead", "Consultar timeline del lead", "crm"),
("LEAD_ACTIVITIES_WRITE", "Registrar actividad", "Crear/editar entries del timeline", "crm"),
("LEAD_STATUS_HISTORY_READ", "Ver historial de estados", "Consultar transiciones histórico", "crm"),
("MY_LEADS_READ", "Ver mis leads", "Listar leads asignados al asesor logueado", "crm"),
```

**Roles seed que tocan `crm`**:
- `ADMIN` — todos.
- `ASESOR` — `MENU-CRM`, `PERSONS_{READ,CREATE,UPDATE}` (no delete), `LEAD_ACTIVITIES_{READ,WRITE}`, `LEAD_STATUS_HISTORY_READ`, `LEAD_ASSIGNMENTS_{READ,WRITE}`, `MY_LEADS_READ`, `LEAD_STATUSES_READ`, `CUSTOMER_STATUSES_READ`.
- `DOCTOR` — `PERSONS_READ` (al atender la cita ve datos del paciente).

## Decisiones de diseño

### Person + estados separados — ver [ADR-003](../decisions/ADR-003-person-with-separated-lifecycle-statuses.md)
Alternativas (stage enum, dos entidades Lead/Patient) y razones de rechazo en el ADR.

### Un único LeadStatus activo por Person (`UNIQUE person_id`)
Confirmado por usuario. Razón: simplifica el reporting ("¿en qué estado está el lead?" no admite ambigüedad), evita decisiones operativas ambiguas ("¿a cuál de los dos leads aplico la acción?") y mantiene el flow conceptual lineal. Si una persona ya cliente vuelve a interesarse, se cierra y se reabre — la traza queda en `LeadStatusHistory.source_campaign_id`.

### `LeadStatus` y `CustomerStatus` como catálogo en BD, pero `LeadActivity.activity_type` como enum cerrado
Trade-off intencional:
- **Estados de lead/cliente cambian con la operación** (la clínica puede querer "INVESTIGANDO_PRESUPUESTO" como sub-estado de "EVALUANDO"). Catálogo en BD habilita evolución sin deploy.
- **Tipos de activity son contratos con el sistema** (`MESSAGE_SENT` lo emite el módulo `conversations`, `APPOINTMENT_BOOKED` lo emite `scheduling`). Agregar uno nuevo requiere cambios en el código que lo emite y consume — un enum en código mantiene la coherencia.

### `is_initial` / `is_final` / `is_won` como flags en el catálogo
Permiten al código encontrar "el estado por defecto al crear" y "los estados terminales" sin hardcodear codes. Si el admin renombra `NUEVO` a `RECIEN_LLEGADO`, el código sigue funcionando — busca el que tenga `is_initial=true`. Validación en service: exactamente una fila con `is_initial=true` por catálogo.

### Round-robin sin tabla de estado
Documentado arriba. El query `SELECT advisor ORDER BY (active_leads ASC, last_assigned_at ASC) LIMIT 1` reparte equitativamente y se auto-balancea cuando un asesor entra/sale. **Concurrencia**: dos leads que llegan al mismo tiempo podrían recibir el mismo asesor. Mitigación: el service envuelve en una transacción con `SELECT ... FOR UPDATE` sobre la fila del candidate user — si ya cambió el conteo, recalcula. Documentar al implementar.

### `LeadActivity` polimórfica con `payload: JSONB`
Confirmado por usuario. Razón: el timeline crece con tipos heterogéneos que comparten 80% de columnas (actor, fecha, content). Columnas comunes tipadas + `payload` libre para lo específico balancea estructura y flexibilidad. Si un tipo crece en uso y merece columnas propias, se promueven con migración (Postgres puede indexar campos JSONB con `GIN`).

### `PersonContactIdentifier` con UNIQUE `(channel_type, identifier)`
Garantiza que un phone WhatsApp pertenezca a una sola persona — base del matching de `conversations` al recibir mensaje entrante. Validado como partial index (`WHERE deleted_at IS NULL`) para permitir reasignar identifiers después de soft-delete.

### Historiales sin SoftDelete
`LeadStatusHistory`, `CustomerStatusHistory` y `LeadActivity` **no** llevan `SoftDeleteMixin` — la auditoría es honesta o no es. Si una activity fue por error, se marca `active=false` (visible solo a admin) o se crea una correctiva referenciando la original.

## Flujo end-to-end típico

1. **Mensaje WhatsApp entra** → `conversations` matchea `PersonContactIdentifier` por `(channel_type='whatsapp', identifier=phone)`.
2. **No existe** → `conversations.services` llama `crm.services.person.create_from_inbound_contact(channel_type, identifier, first_message_preview)`. Esto:
   - Crea `Person` con campos mínimos (first_name puede venir de WhatsApp profile, last_name puede quedar vacío).
   - Crea `PersonContactIdentifier`.
   - Crea `PersonLeadStatus` con `lead_status_id = (el que tiene is_initial=true)`.
   - Registra `LeadStatusHistory` (transición NULL → NUEVO).
   - Llama `lead_assignment.assign_round_robin(person_id)`.
   - Registra `LeadActivity` con `activity_type=CAMPAIGN_ATTRIBUTION` si la conversación viene de una `ChannelAccount` con `campaign_id` (lo discutimos al diseñar `conversations`).
3. **Existe** → `bots` decide preventa vs postventa según `PersonCustomerStatus` activa o no.
4. **Asesor toma conversación** → `conversations` cambia `assignee_type=advisor`; emite `LeadActivity(CONVERSATION_TAKEN)`.
5. **Asesor transiciona estado** → `POST /persons/{id}/lead-status/transition`. Service valida transición, persiste, registra `LeadStatusHistory` + `LeadActivity(STATUS_CHANGE)`.
6. **Se agenda cita** → `scheduling.services.appointment.create` registra cita; emite `LeadActivity(APPOINTMENT_BOOKED)`. Cuando el paciente asiste y el doctor completa la atención, se llama `crm.promote_to_customer(person_id)` — cierra LeadStatus (CITA_AGENDADA → is_won=true), crea `PersonCustomerStatus(ACTIVO)`.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `admin` | `LeadAssignment.advisor_user_id`, `LeadActivity.advisor_user_id`, audit users por mixin. |
| `marketing` | `PersonLeadStatus.source_campaign_id`, `LeadStatusHistory.source_campaign_id` (FKs nullable a `campaign`). |
| `conversations` | Busca Person por `PersonContactIdentifier`; emite `LeadActivity` por cambios de assignee. `LeadActivity.related_conversation_id` FK opcional. |
| `bots` | Lee `PersonCustomerStatus` para decidir bot preventa/postventa. |
| `scheduling` | `appointment.person_id` (FK). Emite `LeadActivity(APPOINTMENT_*)`. |

## Diagramas

- ER: [`docs/diagrams/er-crm.puml`](../diagrams/er-crm.puml)
- Class: [`docs/diagrams/class-backend-crm.puml`](../diagrams/class-backend-crm.puml)

## Próximos pasos / TODOs deliberados

- [ ] Cuando se diseñe `conversations`, validar el contrato `crm.services.person.find_by_identifier_or_create(channel_type, identifier, profile_data)`.
- [ ] Implementar el round-robin con `SELECT ... FOR UPDATE` para evitar race condition. Documentar en service.
- [ ] Considerar agregar `MedicalRecord` 1:1 con Person cuando el negocio requiera historia clínica (postergado al MVP).
- [ ] Si los reportes de "leads por fuente" se vuelven dominantes, considerar denormalizar `source_campaign_id` también en `PersonCustomerStatus` para reportes de conversión rápidos.
- [ ] Evaluar índice GIN sobre `LeadActivity.payload` si emergen queries frecuentes sobre campos del JSONB.
