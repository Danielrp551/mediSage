# ADR-003: Modelar Person con estados lead/customer separados en tablas hijas

> **Status**: Accepted
> **Date**: 2026-05-28
> **Deciders**: @daniel, @marco

## Context

En Medisage los contactos de la clínica recorren **dos hilos de vida** que pueden coexistir:

- **Hilo lead** — desde que la persona llega como prospecto (via WhatsApp, web, campaña) hasta que se cierra (cita agendada / no interesado / perdido).
- **Hilo customer** — desde que la persona se convierte en cliente activo (atendido en consulta) hasta que se vuelve inactivo o perdido.

El usuario confirmó:
- Una persona ya cliente **puede volver a ser lead** de otra campaña (ej. el cliente activo en estética se acerca por dental). Lead nuevo + cliente vigente conviven.
- Un único **LeadStatus activo por person** (la operación quiere una respuesta inequívoca a "¿en qué estado está su lead?").
- Estados (LeadStatus / CustomerStatus) son **catálogo configurable en BD**, no enum en código.
- Historial completo de transiciones debe quedar trazado (`LeadStatusHistory`, `CustomerStatusHistory`).
- Owner del lead (`LeadAssignment`), identifiers multicanal y timeline polimórfico (`LeadActivity`) cuelgan de la persona, no de un "lead aislado".

Necesitamos decidir **cómo modelar la estructura de Person + estados** porque afecta:
- FKs desde otros módulos (`conversations.person_id`, `appointment.person_id`).
- Lógica del bot (decide preventa/postventa según el "estado actual").
- Reporting (¿cuántos leads activos hay? ¿cuántos clientes nuevos este mes?).
- Operación del asesor (su panel filtra por estado y owner).

Esta decisión es **estructural** — revertirla obligaría a migrar datos masivamente y rehacer FKs en varios módulos.

## Decision

**`Person` es la entidad raíz**, y los estados lead/customer viven en **tablas hijas separadas**:

- `PersonLeadStatus` (UNIQUE `person_id`) — estado lead **activo actual** (si existe).
- `PersonCustomerStatus` (UNIQUE `person_id`) — estado cliente **activo actual** (si existe).
- `LeadStatusHistory` y `CustomerStatusHistory` — timelines inmutables de transiciones.
- `LeadAssignment` (UNIQUE `person_id`) — owner asesor del lead activo.
- `LeadActivity` — timeline polimórfico (notas, intentos, follow-ups, system events).
- `PersonContactIdentifier` — M:N de identifiers por canal.

Una persona en cualquier momento puede:
- tener `PersonLeadStatus` y `PersonCustomerStatus` simultáneos (cliente activo + lead nuevo de otra campaña);
- tener solo `PersonLeadStatus` (lead puro, todavía no es cliente);
- tener solo `PersonCustomerStatus` (cliente activo sin lead en curso);
- no tener ninguno (Person creado a mano sin tracking comercial — caso raro pero posible).

Estados como **catálogos en BD** con flags `is_initial` / `is_final` / `is_won` para que el código no hardcodee codes.

## Alternatives Considered

### Opción A — `Person.stage` enum/varchar

Una sola columna `stage ∈ {lead, customer, lead_and_customer, lost, ...}` en `Person`. Las transiciones se trackean con `created_on`/`updated_on` o tabla `PersonHistory` única.

- **Pros**:
  - Una sola tabla, simple de leer.
  - Filtros "dame todos los leads" son `WHERE stage IN (...)` sin join.
- **Cons**:
  - No representa el caso "cliente activo + lead nuevo simultáneos" sin estados frankenstein como `lead_and_customer`. La explosión combinatoria crece a medida que aparecen casos.
  - Historial por hilo (lead vs customer) se enreda en una sola traza. Para "¿cuántas veces fue lead esta persona?" hay que parsear la traza y filtrar por sub-estados.
  - El owner del lead, la campaña de origen, etc. no tienen casa natural — se vuelven columnas en Person que solo aplican cuando `stage IN (lead, lead_and_customer)`, otra vez con `NULL` por todos lados.
- **Rechazada porque**: el dominio tiene dos hilos paralelos genuinos. Aplastarlos en una sola dimensión obliga a inventar estados híbridos o duplicar columnas nullables.

### Opción B — Dos entidades raíz separadas: `Lead` y `Patient`

`Lead` tiene su tabla con sus columnas (status, campaign, owner, contact data). Cuando se convierte, se crea `Patient` con datos copiados.

- **Pros**:
  - Cada hilo en su tabla con sus columnas — sin nullables sospechosos.
  - Modelo clásico de CRM (HubSpot, Pipedrive).
- **Cons**:
  - **Duplicación de identidad**: nombres, phone, email viven en `Lead` y se copian a `Patient`. ¿Qué pasa cuando el cliente actualiza su teléfono? ¿Se actualiza en ambos? ¿Cuál es la fuente de verdad?
  - El caso "cliente que vuelve a ser lead" obliga a crear un nuevo `Lead` referenciando al `Patient` — la traza histórica entre múltiples leads del mismo Patient es awkward (¿FK `lead.patient_id` opcional?).
  - `conversations.person_id` tendría que ser polimórfico (`lead_id | patient_id`) — anti-pattern en SQL relacional.
  - **Búsqueda unificada por phone se complica**: ¿busco en `lead.phone` o `patient.phone`? El bot al recibir mensaje no sabe si es lead nuevo o cliente recurrente.
- **Rechazada porque**: introduce duplicación de identidad y FKs polimórficas en otros módulos para resolver el caso del "mismo humano".

### Opción C — `Person` con `lead_status_id` y `customer_status_id` como columnas

Person tiene dos columnas FK directas: `current_lead_status_id` y `current_customer_status_id`. Historial en tablas aparte.

- **Pros**:
  - Una sola tabla raíz con dos punteros, sin join para saber estados.
- **Cons**:
  - El owner del lead (`LeadAssignment`), la campaña fuente, `entered_status_at`, `last_activity_at` son atributos del **lead actual**, no de Person. O bien viven como columnas en Person (vuelve la inflación con NULL cuando no hay lead activo), o se crean tablas aparte que pueden quedar huérfanas (¿qué pasa si el lead se cierra: el `entered_status_at` queda colgando?).
  - Cerrar un lead = poner `current_lead_status_id = NULL` y "perder" la metadata asociada. Reabrir = inventar campaign y assigned_at otra vez — pero la operación quiere que sea trivial.
  - Soft-delete del lead se mezcla con soft-delete de Person.
- **Rechazada porque**: la diferencia con la opción aceptada es que los atributos del "lead actual" no tienen casa propia. Una tabla hija (`PersonLeadStatus`) los aglutina con su ciclo de vida limpio.

### Opción D — Aceptada: `Person` + tablas hijas para estados, historial y assignment

- Person tiene **solo identidad y contacto** (sin metadata operacional).
- `PersonLeadStatus` es una **fila opcional con UNIQUE person_id** — su existencia significa "este Person tiene lead activo". Se borra cuando se cierra el lead.
- Cuando vuelve a ser lead, se inserta **nueva fila**. La traza queda en `LeadStatusHistory.source_campaign_id`.
- Igual para `PersonCustomerStatus`.
- Todos los atributos del lead actual (campaña, fechas, owner) viven en su tabla, no en Person.

## Consequences

### Positivas

- **Modelo refleja el dominio**: dos hilos paralelos coexistentes con vida propia.
- **`conversations.person_id` es una FK simple a `person`** — el matching multicanal funciona sin acoplarse al estado lead/customer.
- **Bot decide preventa/postventa con un query trivial**: "¿existe `PersonCustomerStatus` activa para este `person_id`?".
- **Identidad es única**: nombre, phone, identifiers viven en un solo lugar (`Person` + `PersonContactIdentifier`). Actualizar el teléfono toca una fila, no dos.
- **Historial por hilo es independiente y limpio**: `LeadStatusHistory` y `CustomerStatusHistory` no comparten filas con semánticas distintas.
- **Reportes son directos**:
  - Leads activos: `SELECT COUNT(*) FROM person_lead_status WHERE deleted_at IS NULL`.
  - Conversiones del mes: `SELECT COUNT(*) FROM person_customer_status WHERE became_customer_at >= ...`.
- **Catálogos editables**: la clínica puede agregar estados sin deploy (`is_initial`/`is_final`/`is_won` permiten al código encontrar los relevantes sin hardcodear codes).

### Negativas / Trade-offs

- **Más tablas** (10 entidades en `crm`). El módulo es notablemente más grande que `catalog` o `clinic`.
- **Joins frecuentes**: listar "leads con su asesor y último estado" requiere 3-4 joins. Mitigado con `selectinload` y campos denormalizados (`last_activity_at` en `PersonLeadStatus`).
- **Coordinación al cerrar/reabrir un lead**: el service de transición tiene que:
  1. Validar transición permitida.
  2. Si el nuevo estado es `is_final`, borrar `PersonLeadStatus` y registrar en `LeadStatusHistory`.
  3. Si es `is_won` y debe convertirse a cliente, llamar `promote_to_customer`.
  4. Emitir `LeadActivity(STATUS_CHANGE)`.
  Estos pasos deben quedar en una sola transacción para no dejar estados intermedios.
- **El `UNIQUE person_id` sobre `PersonLeadStatus` requiere disciplina al crear**: si dos procesos intentan crear lead activo simultáneamente, el segundo falla. Aceptable: el round-robin de assignment y la creación del lead corren en la misma transacción.

### Lo que esto nos obliga a hacer

- **En `crm.services.person_lead_status`**:
  - `transition()` valida transiciones (matriz de transiciones permitidas — futura ADR si el negocio define reglas estrictas).
  - `close()` borra la fila y registra el historial atómicamente.
- **En `crm.services.person`** `find_by_identifier_or_create` orquesta:
  - Buscar Person por `PersonContactIdentifier`.
  - Si no existe: crear `Person` + `PersonContactIdentifier` + `PersonLeadStatus(NUEVO)` + `LeadAssignment(round_robin)` + `LeadStatusHistory` + `LeadActivity(CAMPAIGN_ATTRIBUTION)` — todo en una transacción.
- **En `conversations`**: `Conversation.person_id` es FK a `person`, no a `lead` ni a `customer`. La conversación pertenece al humano, no al hilo comercial.
- **En `bots`**: la decisión preventa/postventa es `query: SELECT EXISTS(... FROM person_customer_status WHERE person_id = ? AND deleted_at IS NULL)`.
- **En `seed.py`**: poblar `LeadStatus` (7) y `CustomerStatus` (5) con los códigos seed iniciales (lista exacta en [`docs/modules/crm.md`](../modules/crm.md)).

## Referencias

- Código futuro: `backend/app/modules/crm/models/`, `backend/app/modules/crm/services/`.
- Ficha del módulo: [`docs/modules/crm.md`](../modules/crm.md).
- ADR relacionado: [ADR-002](ADR-002-doctor-entity-extends-user.md) — patrón análogo "extender User" vs "Person + tablas hijas" para el ciclo de vida del contacto.
