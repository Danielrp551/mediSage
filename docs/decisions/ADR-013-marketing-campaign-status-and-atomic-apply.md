# ADR-013: marketing — status de campaña como enum fijo (no matriz ADR-008) + aplicación de promoción atómica cross-módulo

> **Status**: Accepted
> **Date**: 2026-06-08
> **Deciders**: @daniel, @marco
> **Relacionado**: cierra el patrón forward-FK de [ADR-009](ADR-009-forward-fk-deferred-cross-module.md); diverge deliberadamente de [ADR-008](ADR-008-configurable-status-transition-matrix.md); consume `scheduling` ([ADR-006](ADR-006-hybrid-calendar-slots.md)) y `catalog`/`crm`.

## Context

`marketing` (#8, último módulo) modela **campañas** (atribución de leads) y **promociones** (descuentos sobre productos del catálogo) con una tabla de **uso** inmutable (`promotion_usage`). Dos decisiones de diseño no-obvias surgieron al especificarlo y fueron **confirmadas por el usuario** (AskUserQuestion, 2026-06-08); ambas merecen ADR porque alguien va a preguntar "¿por qué no se hizo como crm/scheduling?".

1. **¿`Campaign.status` debe ser un catálogo configurable con matriz de transiciones (como `lead_status`/`customer_status`/`appointment_status`, [ADR-008](ADR-008-configurable-status-transition-matrix.md)) o un enum fijo en código?** Los tres módulos previos con estados (crm, scheduling) usan tablas-catálogo + una matriz `*_transition` editable sin deploy. Aplicar el mismo patrón a campaña sería consistente pero agrega 1 entidad-catálogo + su CRUD + UI de matriz + seed.

2. **Cuando se agenda una cita con una promoción, ¿la aplicación de la promo (crear `PromotionUsage`) debe ser atómica con la creación de la cita, o un paso desacoplado?** El usuario eligió la integración "Todo ahora": `scheduling.create_appointment` debe poder aplicar la promo. La pregunta es **dónde** vive esa llamada y con qué garantía transaccional.

## Decision

### D1 — `Campaign.status` es un **enum fijo en código** (`draft / active / paused / ended`) con transiciones validadas en el **service**, NO un catálogo configurable.

```
draft  → {active}
active → {paused, ended}
paused → {active, ended}
ended  → {}            # terminal
```

- El enum vive en `marketing/enums.py:CampaignStatus`. La matriz de transición es una constante hardcodeada en `campaign` service; una transición no permitida lanza `BadRequestException(code="CAMPAIGN_TRANSITION_NOT_ALLOWED")` (400).
- **No** hay tablas `campaign_status` / `campaign_status_transition`, ni UI de matriz, ni seed de estados. El frontend tiene una constante espejo (`CAMPAIGN_TRANSITIONS`) solo para gatear los botones-atajo; el backend re-valida.
- El color del badge es **fijo por estado en el front** (Campaign no tiene columna `color`, a diferencia de los catálogos de crm/scheduling).

### D2 — La aplicación de promoción es **atómica en la transacción del request**, inyectada in-process en `scheduling.create_appointment`.

- `AppointmentCreate` gana un campo opcional `apply_promotion_id: str | None = None`. Si está presente, `create_appointment` llama a `marketing.promotion_usage.apply(...)` **después** del `db.flush()` que materializa `appointment.id` y **antes** del return, en la **misma `AsyncSession`**.
- `apply(...)` lanza **excepciones de dominio** (`BadRequest`/`Conflict`/`NotFound`, nunca `HTTPException`). Como ningún service hace `commit` (lo hace `get_db` al final del request), si la promo es inválida/agotada la excepción propaga y **toda la transacción revierte**: la cita NO queda creada sin su promo, y no hay `PromotionUsage` sin cobertura. Cita + uso de promo se crean o fallan **juntos**.
- La misma ruta sirve para el **bot** (la tool `book_appointment` pasa `apply_promotion_id` y `source='bot'`) y para el backoffice — un solo camino.
- `marketing` referencia `appointment` por columna FK (`promotion_usage.appointment_id`) **sin** `relationship` ORM; el sentido del import es `scheduling → marketing` (no al revés), evitando ciclo.

## Alternatives Considered

### D1-B — Catálogo configurable + matriz (patrón ADR-008). **Rechazada.**
- **Pros**: consistencia total con crm/scheduling; la clínica podría renombrar/reconfigurar estados sin deploy.
- **Cons**: los 4 estados de campaña son **inherentes al ciclo de vida** de una iniciativa de marketing (planear → lanzar → pausar → terminar); no son una taxonomía de negocio que la clínica vaya a reconfigurar (a diferencia de "Interesado/Evaluando/…" de un lead). Agregar una entidad-catálogo + CRUD + UI de matriz + seed para 4 estados fijos es **complejidad sin beneficio**.
- **Rechazada porque**: ADR-008 existe para taxonomías *configurables por el negocio*; forzarlo aquí sería cargo-cult. Si en el futuro el negocio pидiera estados de campaña configurables, se migra a ADR-008 de forma aditiva (el enum se vuelve seed inicial).

### D2-B — Apply desacoplado (endpoint `POST /promotion-usages` separado, llamado tras crear la cita). **Rechazada para el flujo de booking.**
- **Pros**: marketing no obliga a tocar `scheduling`; menor acoplamiento.
- **Cons**: **pierde la atomicidad** — entre crear la cita y aplicar la promo hay una ventana donde la cita existe a precio lleno; si el segundo call falla, queda una cita sin su descuento (estado inconsistente que el cliente debe reconciliar). El usuario eligió explícitamente la integración total ("Todo ahora").
- **Nota**: el endpoint standalone `POST /promotion-usages` **sí existe** (para redenciones manuales o sin cita), pero el camino de booking usa la inyección atómica D2.

## Consequences

### Positivas
- **D1**: módulo más simple (1 entidad menos, sin UI de matriz, sin seed de estados); el ciclo de vida de campaña queda explícito y auto-documentado en el enum.
- **D2**: "todo-o-nada" real entre cita y promo, sin commit intermedio, sin estado huérfano; un solo camino para bot y backoffice; el snapshot de precio (`original_amount`) se toma del `ctx.product.base_price` ya cargado por `validate_booking_invariants` (sin re-query).

### Negativas / Trade-offs
- **D1**: cambiar el ciclo de vida de campaña requiere deploy (no es configurable). Aceptable: es un cambio raro y de producto.
- **D2**: `marketing` **toca `scheduling`** (campo en `AppointmentCreate` + llamada en `create_appointment`) y `bots` (la tool `book_appointment`) — módulos ya en prod. Mitigación: el campo es **opcional** (cero impacto si no se usa) y la llamada está guardada por `if payload.apply_promotion_id`. Se entrega en la fase F4, con su propia review adversaria + QA E2E.
- **D2**: un fallo de promo **revierte la reserva**. Es el comportamiento deseado (no querés una cita "a medias"), pero hay que comunicarlo en la UX (el wizard muestra el error de promo y el usuario reintenta sin promo si quiere).

### Lo que esto nos obliga a hacer
- `marketing` cierra además las **FK forward a `campaign`** ([ADR-009](ADR-009-forward-fk-deferred-cross-module.md)) en su migración `0022` (ver anotación de ADR-009).
- `apply(...)` debe ser **idempotente/segura bajo concurrencia**: no-stacking por **UNIQUE parcial** real en `promotion_usage(appointment_id) WHERE appointment_id IS NOT NULL` + `SELECT … FOR UPDATE` sobre la fila `promotion` para los límites `max_uses_total`.

## Referencias

- [ADR-008](ADR-008-configurable-status-transition-matrix.md) — el patrón de matriz configurable del que D1 diverge deliberadamente.
- [ADR-009](ADR-009-forward-fk-deferred-cross-module.md) — forward-FK que marketing cierra.
- [ADR-006](ADR-006-hybrid-calendar-slots.md) — `scheduling`, consumido por D2.
- Fichas del módulo: [`marketing/README.md`](../modules/marketing/README.md), [`marketing/backend.md`](../modules/marketing/backend.md) (apply 10 pasos + migraciones), [`marketing/ui.md`](../modules/marketing/ui.md), [`marketing/frontend.md`](../modules/marketing/frontend.md).
