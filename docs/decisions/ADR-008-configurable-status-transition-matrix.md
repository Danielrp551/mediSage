# ADR-008: Matriz de transiciones de estado configurable (lead/customer)

> **Status**: Accepted
> **Date**: 2026-05-31
> **Deciders**: @daniel, @marco
> **Relacionado**: **supersede** la nota "futura ADR" de [ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) sobre las reglas de transición; no toca el resto de ADR-003 (que sigue vigente).

## Context

[ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) modeló el ciclo de vida de un `Person` con estados de **lead** y **customer** en tablas hijas separadas (`PersonLeadStatus` / `PersonCustomerStatus`), apoyados en catálogos configurables (`LeadStatus` / `CustomerStatus`) con flags `is_initial` / `is_final` / `is_won`. Pero **dejó abierta** la cuestión de **qué transiciones entre estados son válidas** — textualmente: *"`transition()` valida transiciones (matriz de transiciones permitidas — futura ADR si el negocio define reglas estrictas)"*.

Al detallar el módulo `crm` (fase de documentación), el usuario decidió (pregunta Q3 de diseño): **sí queremos una matriz de transiciones que rechace saltos inválidos**, pero **las reglas exactas todavía no están cerradas** — *"habría que definir una base y luego la actualizaríamos"*. Es decir, necesitamos:

1. **Enforcement**: el service debe rechazar una transición que no esté permitida.
2. **Editable sin deploy**: las reglas cambiarán con la operación; cambiarlas no puede requerir un release (igual que los propios estados, que ya son catálogo en BD).
3. **Una base sensata desde el día uno**: el seed debe traer una matriz inicial razonable sobre los 7 estados de lead y 5 de customer.

La decisión es no-obvia y costosa de revertir: condiciona el modelo de datos (¿una tabla nueva?), el contrato del endpoint de transición y la UI de administración de catálogos.

## Decision

**Las transiciones permitidas se modelan como filas configurables en dos tablas nuevas — `lead_status_transition` y `customer_status_transition` — que representan las aristas `from → to` del grafo de estados.**

- `lead_status_transition { from_lead_status_id (FK→lead_status), to_lead_status_id (FK→lead_status) }`, **UNIQUE `(from, to)`**. Análoga `customer_status_transition`. Mixins `PrimaryKey` · `Active` · `Timestamp` — **sin `SoftDelete`**: son configuración, no dato de negocio; deshabilitar una arista = `active=false` (conserva la fila) o `DELETE` real.
- **Enforcement en el service**: `person_lead_status.transition(to_id, …)` verifica que exista una arista `(estado_actual → to_id)` activa; si no, lanza `BadRequestException(code="LEAD_TRANSITION_NOT_ALLOWED")` (400, `detail` en español). El estado inicial al crear el lead sigue siendo el `is_initial` del catálogo (no es una arista); transicionar a un estado `is_final` cierra el lead (soft-delete de `PersonLeadStatus`).
- **Editable por admin** sin deploy: `GET /lead-statuses/{id}/transitions` (destinos permitidos) y `PUT /lead-statuses/{id}/transitions` (body `{to_ids: [...]}` reemplaza las aristas de salida de ese estado), gated `LEAD_STATUSES_WRITE`. Idem customer.
- **Base seedeada** (`_seed_lead_transition_matrix` / `_seed_customer_transition_matrix`, idempotentes), sobre los estados seed:

  **Lead** (7 estados):
  ```
  NUEVO                → INTENTANDO_CONTACTAR, NO_INTERESADO
  INTENTANDO_CONTACTAR → CONTACTADO, NO_INTERESADO
  CONTACTADO           → INTERESADO, INTENTANDO_CONTACTAR (re-contacto), NO_INTERESADO
  INTERESADO           → EVALUANDO, NO_INTERESADO
  EVALUANDO            → CITA_AGENDADA, INTERESADO, NO_INTERESADO
  CITA_AGENDADA  (is_final/is_won) → (terminal)
  NO_INTERESADO  (is_final)        → (terminal)
  ```
  **Customer** (5 estados, permisiva): las no-finales (`ACTIVO`, `EN_TRATAMIENTO`, `COMPLETADO`) transicionan libremente entre sí y hacia las finales (`INACTIVO`, `PERDIDO`); `INACTIVO → ACTIVO` (reactivar); `PERDIDO` (is_final) terminal.

El catálogo de estados (`LeadStatus`/`CustomerStatus`) sigue siendo configurable (codes, flags, color, orden); la matriz es una **capa de configuración aparte** encima del catálogo.

## Alternatives Considered

### Opción A — Transiciones libres (cualquier estado activo → cualquiera)
- **Pros**: cero modelo extra; el asesor mueve el lead a donde quiera; flexibilidad total.
- **Cons**: no hay proceso enforced; permite saltos sin sentido (p.ej. `NUEVO → CITA_AGENDADA` sin pasar por contacto), ensuciando el reporting del embudo.
- **Rechazada porque**: el usuario eligió explícitamente tener control sobre las transiciones (Q3).

### Opción B — Matriz hardcodeada en código (dict por `code`)
- **Pros**: sin tablas nuevas; rápido.
- **Cons**: los `code` de los estados son **editables por admin** (catálogo en BD) — hardcodear contra ellos rompe la premisa de ADR-003. Y "actualizar la matriz luego" requeriría un deploy, justo lo que el usuario quiere evitar.
- **Rechazada porque**: contradice "catálogo configurable" y "editable sin deploy".

### Opción C — Derivar las transiciones de `display_order` + flags
- **Pros**: sin tablas ni edición; "solo se avanza" según el orden.
- **Cons**: demasiado implícito; no captura ramificaciones reales (re-contacto hacia atrás, descarte desde cualquier punto, saltar EVALUANDO). El orden lineal no es el grafo real.
- **Rechazada porque**: el embudo no es lineal; la regla implícita no expresa el dominio.

### Opción D — Tabla de transiciones configurable (Aceptada)
- Aristas `from→to` en BD, seedeadas y editables. Ver Decision.

## Consequences

### Positivas
- **Proceso enforced**: el embudo solo admite los saltos definidos; el reporting queda limpio.
- **Editable sin deploy**: admin ajusta la matriz desde la UI de catálogos (multiselect "transiciones permitidas hacia…" por estado; a futuro una grilla `from×to`).
- **Base lista**: el seed trae una matriz razonable; arrancamos con reglas y las afinamos con la operación (lo que pidió el usuario).
- **Coherente con ADR-003**: los estados siguen siendo catálogo; la matriz es otra capa de config, no código.

### Negativas / Trade-offs
- **Dos tablas más** (`lead_status_transition`, `customer_status_transition`) — `crm` ya es el módulo más grande (12 entidades).
- **Mantenimiento de la matriz**: agregar/renombrar un estado obliga a **definir sus aristas** (de entrada y de salida), o ese estado queda inalcanzable / sin salida (dead-end). La UI debe hacer esto evidente al crear un estado.
- **El seed debe ser idempotente** y resolver los `from`/`to` por `code` (no por id, que cambia entre entornos).

### Lo que esto nos obliga a hacer
- `crm` crea `lead_status_transition` / `customer_status_transition` (migración `0012_crm_status_catalogs`, fase F2) y los seeds de la matriz base.
- El service de transición (`person_lead_status.transition` / `person_customer_status.transition`) consulta la matriz y lanza `LEAD_TRANSITION_NOT_ALLOWED` ante una arista ausente.
- La UI de catálogos (`/crm/estados-lead`, `/crm/estados-cliente`) incluye el editor de transiciones permitidas por estado.
- Actualizar el seed consolidado [`_seed-and-roles.md`](../modules/_seed-and-roles.md) para incluir `_seed_lead_transition_matrix` / `_seed_customer_transition_matrix` en `seed()` y en el checklist de verificación.

## Actualización (2026-06-06) — el patrón se reusa en `scheduling`

El módulo `scheduling` (#7) adopta **el mismo patrón** para el ciclo de vida de la **cita**: una tabla `appointment_status_transition (from_status_id, to_status_id; UNIQUE(from,to); Active·Timestamp, sin SoftDelete)` espeja `lead_status_transition`/`customer_status_transition`, con `repo.is_allowed(from,to)` → `APPOINTMENT_TRANSITION_NOT_ALLOWED` (400). El catálogo `AppointmentStatus` lleva `is_initial`/`is_final` + `is_active_attention` (en vez de `is_won`). Los shortcuts del service (`confirm`/`check_in`/`start`/`attend`/`no_show`/`cancel`/`reschedule`) consultan la matriz; los **side-effects** (attend→promote a cliente, cancel→`min_hours_to_cancel`, reschedule→nueva cita) viven en el service, no en la matriz. **Divergencia deliberada con crm**: alcanzar un estado `is_final` en scheduling **NO soft-deletea** la cita (la fila vive como registro histórico); en crm sí soft-deletea la fila viva del lifecycle. Detalle en [`docs/modules/scheduling/`](../modules/scheduling/README.md) (decisión confirmada con el usuario 2026-06-06).

## Referencias

- [ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) — Person + estados separados (este ADR supersede su nota abierta sobre reglas de transición; el resto sigue vigente).
- [`docs/modules/scheduling/README.md`](../modules/scheduling/README.md) — `scheduling` reusa esta matriz para `AppointmentStatus`.
- Fichas del módulo: [`crm/README.md`](../modules/crm/README.md) (sección "Matriz de transiciones configurable"), [`crm/backend.md`](../modules/crm/backend.md) (modelos `*_status_transition`, service de transición, seed), [`crm/ui.md`](../modules/crm/ui.md) (editor de matriz), [`crm/frontend.md`](../modules/crm/frontend.md).
- [ADR-009](ADR-009-forward-fk-deferred-cross-module.md) — la otra decisión nueva de `crm` (FKs forward diferidas).
