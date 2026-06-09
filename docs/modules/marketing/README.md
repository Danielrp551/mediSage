# Módulo `marketing`

> **Última actualización**: 2026-06-08
> **Propósito**: gestión de **campañas** (atribución comercial: de dónde vino un lead/cliente) y **promociones** (descuentos aplicables a productos), más la **traza inmutable de uso** (`PromotionUsage`: quién recibió qué descuento, en qué producto y a qué cita). Es el **módulo #8 — el último** del MVP: cierra los tres FKs forward que `crm` y `conversations` dejaron diferidos ([ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md)) y engancha el descuento en el flujo de reserva de `scheduling` y en el bot.
> **Path del código**: `backend/app/modules/marketing/` (backend) · `frontend/src/app/(main)/marketing/` (frontend).

> **Este documento es el overview**. Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts (request/response/errores), lógica de service (`apply`/`eligible_for`/`validate`/`compute_price`, helper `_compute_discount`), draft de migraciones.
> - 🎨 [`ui.md`](ui.md) — mockups por pantalla (campañas, promociones, usos), drawers con tabs, estados, componentes Fluent UI, UX writing en español.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod (descuento discriminado), navegación, types espejo.

## Resumen

`marketing` resuelve **dos preguntas de negocio independientes** que comparten un mismo techo de módulo:

1. **Atribución** — ¿de qué **campaña** vino esta persona? `Campaign` es la entidad que `crm` (`source_campaign_id` en `person_lead_status` / `lead_status_history`) y `conversations` (`default_campaign_id` en `channel_account`) referencian para etiquetar el origen de un lead. **El ingest de la atribución YA vive en crm/conversations** (la columna y el `LeadActivity(CAMPAIGN_ATTRIBUTION)` ya existen); marketing solo aporta la entidad `Campaign` y **cierra las tres FKs forward** vía `ALTER` aditivo.
2. **Descuento** — ¿qué **promoción** aplica a este producto, para esta persona, y cuánto se descuenta? `Promotion` define el descuento (porcentaje o monto fijo, con vigencia y topes de uso); `PromotionUsage` registra cada redención como **audit inmutable** (snapshot de `original_amount` / `discount_amount` / `final_amount`).

```
                 campaign_promotion (M:N)
   Campaign ◀───────────────────────────▶ Promotion
   (atribución)                            (descuento: percentage | fixed_amount)
       │                                       │
       │ campaign_id (nullable)                │ promotion_product (M:N) ─▶ Product (catalog, sin tocar)
       │ motiva el uso                         │ o applies_to_all_products=true
       ▼                                       ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ PromotionUsage  (audit inmutable, SIN SoftDelete)                      │
   │  promotion_id · person_id · product_id · appointment_id? · campaign_id?│
   │  original_amount · discount_amount · final_amount · currency           │
   │  UNIQUE PARCIAL appointment_id (no-stacking: 1 promo por cita)         │
   └──────────────────────────────────────────────────────────────────────┘
              ▲                          ▲                       ▲
       crm.person              scheduling.appointment      catalog.product
```

El módulo **no calcula atribución** (eso lo hace crm al crear el lead) ni **cobra** nada (no hay módulo de pagos en el MVP): solo **define** campañas/promociones y **registra** el efecto de un descuento cuando se aplica. El cómputo del descuento es puro `Decimal` (`ROUND_HALF_UP`, **cap a `base_price`** — un descuento nunca supera el precio), y la aplicación es **atómica** dentro de la transacción que la dispara (reserva de cita en scheduling, o `POST /promotion-usages` directo).

`marketing` se construye **después** de `catalog`, `crm`, `conversations` y `scheduling` (todos en producción) y **toca** `scheduling`+`bots` en su última fase (F4) para enganchar el descuento en la reserva. **No modifica** catalog/crm/conversations en código — solo el `ALTER` aditivo de la migración F1 cierra los FKs forward.

## Entidades

5 entidades. Mixins: `PK`=`PrimaryKeyMixin` (`String(36)` uuid4), `A`=`ActiveMixin`, `SD`=`SoftDeleteMixin`, `T`=`TimestampMixin`. **`PromotionUsage` NO lleva `SD`** (audit inmutable, mismo criterio que los historiales de crm/scheduling). Las dos M:N son **associations puras** (`Table` en `models/associations.py`, sin identidad propia).

| Entidad | Tabla | Mixins | Propósito |
|---|---|---|---|
| `Campaign` | `campaign` | PK·A·SD·T | Campaña comercial = unidad de atribución. `status` enum-fijo (`draft/active/paused/ended`). `target_vertical_id?` (FK real a catalog). |
| `Promotion` | `promotion` | PK·A·SD·T | Descuento discriminado por `discount_type` (`percentage` 0<v≤100 \| `fixed_amount` v>0). Vigencia + topes de uso. |
| `PromotionUsage` | `promotion_usage` | **PK·A·T** (sin SD) | Audit inmutable de una redención: snapshot de montos + a qué cita/campaña/producto. |
| `campaign_promotion` | `campaign_promotion` | — (M:N) | Asocia campañas ↔ promociones (PK compuesta, FK CASCADE). |
| `promotion_product` | `promotion_product` | — (M:N) | Asocia promociones ↔ productos cubiertos (PK compuesta, FK CASCADE a catalog). |

### `Campaign` (atribución)

- `code: varchar(40)` UNIQUE NOT NULL, indexado — slug minúsculas (patrón catalog `vertical.code`). Índice `uq_campaign_code` **no-parcial**. Inmutable vía `update`.
- `name: varchar(120)` NOT NULL · `description: varchar(500)` nullable.
- `start_date: date` NOT NULL · `end_date: date` nullable (NULL = sin cierre conocido).
- `status: varchar(20)` NOT NULL default `'draft'` — `CampaignStatus.value`, **enum fijo** con transiciones validadas en el SERVICE (ver [Decisiones](#campaignstatus-enum-fijo-no-catálogo-configurable)). NO se cambia vía `update`, solo vía `/transition`.
- `target_vertical_id: varchar(36)` nullable, **FK real a `vertical.id`** (catalog en prod), indexado — NULL = campaña transversal.
- Relationship `promotions` (M:N `campaign_promotion`, `back_populates="campaigns"`, `lazy="raise"`). **NO** relationship a `Vertical` (`target_vertical_name` se resuelve por `vertical_repository.get_by_ids` batch / `VerticalOption`).

### `Promotion` (descuento)

- `code: varchar(40)` UNIQUE NOT NULL, indexado — slug minúsculas. Índice `uq_promotion_code`. Inmutable.
- `name: varchar(120)` NOT NULL · `description: varchar(500)` nullable.
- `discount_type: varchar(20)` NOT NULL — `DiscountType.value` (`percentage` \| `fixed_amount`). **INMUTABLE** post-create (no va en `update`).
- `discount_value: Numeric(10,2)` NOT NULL — `percentage`: `0 < v ≤ 100`; `fixed_amount`: `v > 0`. **Serializa como STRING** en el wire. Validado en el SERVICE (no Pydantic), para que `update` (sin `discount_type`) lo imponga uniforme.
- `currency: varchar(3)` NOT NULL default `'PEN'` — ISO 4217 (`^[A-Z]{3}$`); solo aplica cuando `fixed_amount`.
- `start_date: date` NOT NULL · `end_date: date` nullable.
- `max_uses_total: int` nullable (NULL = ilimitado) · `max_uses_per_person: int` nullable (NULL = ilimitado).
- `applies_to_all_products: bool` NOT NULL default `false` — `true` ignora el M:N `promotion_product`.
- Relationship `campaigns` (M:N, `back_populates="promotions"`, `lazy="raise"`). **NO** relationship a `Product`: el M:N `promotion_product` se resuelve por **query propia** en `PromotionProductRepository` (join a `catalog.Product`), sin tocar el módulo catalog.

### `PromotionUsage` (audit inmutable)

Registro append-only de una redención. **Sin `SoftDeleteMixin`** (la auditoría es honesta o no es).

- `promotion_id: varchar(36)` FK→`promotion` NOT NULL, indexado.
- `person_id: varchar(36)` FK→`person` NOT NULL, indexado (crm en prod → FK real).
- `product_id: varchar(36)` FK→`product` NOT NULL, indexado — qué producto recibió el descuento.
- `appointment_id: varchar(36)` nullable FK→`appointment`, indexado (scheduling en prod → FK real; NULL = redención sin cita).
- `campaign_id: varchar(36)` nullable FK→`campaign`, indexado — qué campaña motivó el uso.
- `original_amount: Numeric(10,2)` NOT NULL — snapshot del `base_price` del producto · `discount_amount: Numeric(10,2)` NOT NULL · `final_amount: Numeric(10,2)` NOT NULL (`original − discount`) · `currency: varchar(3)` NOT NULL — snapshot del `product.currency`.
- `notes: varchar(500)` nullable.
- **No** hay `applied_at`/`applied_by` separados: se usan `created_on`/`created_by` (TimestampMixin). Aplicación automática (bot/scheduling) → `created_by = SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000002`).
- **No-stacking** → índice **UNIQUE PARCIAL** `uq_promotion_usage_appointment` sobre `appointment_id` `WHERE appointment_id IS NOT NULL`, **dialect-agnóstico** (`postgresql_where` + `sqlite_where`, lección crm F1). Sin `deleted_at` (no hay SD) → no se agrega esa cláusula al predicado.
- **NO** relationship ORM (todo por FK column + batch maps), igual que `appointment`.

### M:N (`models/associations.py`)

- `campaign_promotion` — `(campaign_id, promotion_id)` PK compuesta, ambas FK `ondelete="CASCADE"`.
- `promotion_product` — `(promotion_id, product_id)` PK compuesta, FK a `promotion` + `product` (catalog) `ondelete="CASCADE"`.

## Enums (`marketing/enums.py`)

Dos `StrEnum` **cerrados en código** (no catálogos en BD):

```python
class CampaignStatus(StrEnum):
    draft = "draft"; active = "active"; paused = "paused"; ended = "ended"

class DiscountType(StrEnum):
    percentage = "percentage"; fixed_amount = "fixed_amount"
```

**Matriz de transición de `CampaignStatus`** (hardcodeada en el service, NO en BD):

```
draft  → {active}
active → {paused, ended}
paused → {active, ended}
ended  → {}            # terminal
```

Transición no permitida → `BadRequestException(code="CAMPAIGN_TRANSITION_NOT_ALLOWED")` (400).

## Endpoints (resumen)

Todos bajo `/api/v1/marketing/`. Listado paginado con `POST /<recurso>/list` + `QueryRequest`. Convención del codebase (heredada de catalog/clinic/staff/crm/scheduling shipped): **`PUT` (no `PATCH`)** para updates; **`/active` (no `/options`) lista cruda** (`response_model=list[...]`, sin envelope); el resto usa `SingleResponse` / `PaginatedResponse`. `ALLOWED_FIELDS` solo columnas reales. El detalle de request/response/errores está en [`backend.md`](backend.md#api-contracts).

### Campaign (`routers/campaign.py`, prefix `/campaigns`)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/campaigns/list` | `CAMPAIGNS_READ` |
| `POST` | `/campaigns` (201) | `CAMPAIGNS_CREATE` |
| `GET` | `/campaigns/active` | `CAMPAIGNS_READ` (lista cruda `CampaignOption`) |
| `GET` | `/campaigns/{id}` | `CAMPAIGNS_READ` (`CampaignDetail`) |
| `PUT` | `/campaigns/{id}` | `CAMPAIGNS_UPDATE` |
| `DELETE` | `/campaigns/{id}` (204) | `CAMPAIGNS_DELETE` (soft) |
| `POST` | `/campaigns/{id}/transition` | `CAMPAIGNS_UPDATE` (valida matriz §enum) |
| `GET` | `/campaigns/{id}/promotions` | `CAMPAIGNS_READ` (promos del M:N) |
| `PUT` | `/campaigns/{id}/promotions` | `CAMPAIGNS_UPDATE` (bulk-replace `{promotion_ids}`) |

> `/campaigns/active` se declara **antes** de `/campaigns/{id}` para evitar la captura de ruta.

### Promotion (`routers/promotion.py`, prefix `/promotions`)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/promotions/list` | `PROMOTIONS_READ` |
| `POST` | `/promotions` (201) | `PROMOTIONS_CREATE` |
| `GET` | `/promotions/active` | `PROMOTIONS_READ` (lista cruda `PromotionOption`) |
| `GET` | `/promotions/{id}` | `PROMOTIONS_READ` (`PromotionDetail`) |
| `PUT` | `/promotions/{id}` | `PROMOTIONS_UPDATE` |
| `DELETE` | `/promotions/{id}` (204) | `PROMOTIONS_DELETE` (soft) |
| `GET` | `/promotions/{id}/products` | `PROMOTIONS_READ` (productos del M:N) |
| `PUT` | `/promotions/{id}/products` | `PROMOTIONS_UPDATE` (bulk-replace `{product_ids}`) |
| `GET` | `/promotions/{id}/usage-summary` | `PROMOTION_USAGES_READ` (`PromotionUsageSummary`) |

### Validación / aplicación (`routers/promotion_usage.py`)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/promotions/eligible-for` | `PROMOTION_VALIDATE` (lista `PromotionEligibility` para `{product_id, person_id}`) |
| `POST` | `/promotions/{id}/validate` | `PROMOTION_VALIDATE` (una promo puntual) |
| `POST` | `/compute-price` | `PROMOTION_VALIDATE` (precio con/sin promo, sin insertar) |
| `POST` | `/promotion-usages` (201) | `PROMOTION_APPLY` (crea `PromotionUsage` — el `apply`) |
| `POST` | `/promotion-usages/list` | `PROMOTION_USAGES_READ` |

> Orden de rutas: `/promotions/eligible-for` (literal) **antes** de `/promotions/{id}/validate`. El aggregator agrupa `eligible-for`/`validate`/`usage-summary` por permiso (pueden vivir en `promotion_usage.py` o `promotion.py`).

> **Códigos de error de dominio** (`detail` en **español**, `code` en inglés): `CAMPAIGN_NOT_FOUND` (404), `CAMPAIGN_CODE_TAKEN` (409), `CAMPAIGN_INVALID_DATES` (400), `TARGET_VERTICAL_NOT_FOUND` (400), `CAMPAIGN_TRANSITION_NOT_ALLOWED` (400), `PROMOTION_NOT_FOUND` (404), `PROMOTION_CODE_TAKEN` (409), `PROMOTION_INVALID_DISCOUNT` (400), `PROMOTION_INVALID_DATES` (400), `PRODUCT_NOT_FOUND` (404), `PERSON_NOT_FOUND` (404), `PROMOTION_PRODUCT_NOT_COVERED` (400), `PROMOTION_ALREADY_APPLIED` (409 — no-stacking), `PROMOTION_NOT_ACTIVE` (400), `PROMOTION_EXPIRED` (400), `PROMOTION_LIMIT_REACHED` (400), `PROMOTION_PERSON_LIMIT_REACHED` (400). La tabla completa con el "cuándo" exacto está en [`backend.md`](backend.md).

## Permisos seed

12 permisos, `module="MARKETING"`. Se consolidan en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md) — aquí se referencian:

```
MENU-MARKETING ·
CAMPAIGNS_{READ,CREATE,UPDATE,DELETE} ·
PROMOTIONS_{READ,CREATE,UPDATE,DELETE} ·
PROMOTION_VALIDATE · PROMOTION_APPLY · PROMOTION_USAGES_READ
```

> ⚠ **Forward-declaración existente**: hoy 6 de estos codes (`MENU-MARKETING`, `CAMPAIGNS_READ`, `PROMOTIONS_READ`, `PROMOTION_VALIDATE`, `PROMOTION_APPLY`, `PROMOTION_USAGES_READ`) viven **solo** en el `set` `ASESOR_PERMISSION_CODES` — **NO** como filas en `SEED_PERMISSIONS`. F0 crea las 12 filas; al hacerlo, esos 6 se auto-activan para ASESOR.

**Roles seed**:

- `ADMIN` — los **12** permisos.
- `ASESOR` — los **6** forward-declarados: `MENU-MARKETING`, `CAMPAIGNS_READ`, `PROMOTIONS_READ`, `PROMOTION_VALIDATE`, `PROMOTION_APPLY`, `PROMOTION_USAGES_READ`. (Lee campañas/promos, valida y aplica descuentos, ve usos; **no** crea/edita/borra campañas ni promociones — eso es admin.)
- `DOCTOR` — **ninguno**.

## Decisiones de diseño (confirmadas con el usuario 2026-06-08 — no se re-litiga)

### Superficie MVP COMPLETA

El MVP incluye **toda** la superficie de descuento, no un subconjunto: `eligible-for` (qué promos aplican a un producto/persona) + `validate` (una promo puntual) + `compute-price` (precio final con/sin promo) + `apply` (crea `PromotionUsage`) + reportes de uso (list + summary). Razón: el descuento sin la traza de uso no sirve para reportar, y el `apply` sin `validate`/`compute-price` deja al cliente sin forma de previsualizar el precio.

### `CampaignStatus` = enum FIJO (no catálogo configurable)

A diferencia de `crm.LeadStatus` y `scheduling.AppointmentStatus` (catálogos en BD + matriz configurable, [ADR-008](../../decisions/ADR-008-configurable-status-transition-matrix.md)), `Campaign.status` es un **`StrEnum` de 4 valores** (`draft/active/paused/ended`) con la **matriz de transición hardcodeada en el SERVICE**. Razón confirmada: los 4 estados son **inherentes al ciclo de vida** de una campaña (un borrador se activa, se pausa, se cierra); la clínica no los reconfigura ni agrega estados nuevos. Modelarlos como catálogo+matriz sería sobre-ingeniería. Endpoint genérico `/transition` (sin side-effects ricos).

### Integración cross-módulo TOTAL ("Todo ahora")

Marketing **no** difiere su integración: en el mismo MVP (a) **cierra los 3 FKs forward** que crm/conversations dejaron (ADR-009), (b) **engancha el descuento atómicamente** en la reserva de cita de scheduling, y (c) **expone el descuento al bot** (tool read-only + extensión de `book_appointment`). Razón: el valor de las promociones se materializa al aplicarlas en una cita real; dejar la integración para "después" entregaría una entidad muerta.

### No-stacking: una promoción por cita

Una cita admite **a lo sumo una** `PromotionUsage` — backstop a nivel de BD con el índice **UNIQUE PARCIAL** sobre `appointment_id`, y pre-check en el service (`PROMOTION_ALREADY_APPLIED`, 409). El descuento no se acumula con otro descuento en la misma cita.

### `discount_type` inmutable post-create

Cambiar el tipo de descuento de una promoción ya usada invalidaría los snapshots de `PromotionUsage`. Por eso `discount_type` **no** va en `PromotionUpdate`; el rango de `discount_value` se valida en el SERVICE (`_validate_discount`) tomando el `discount_type` de la fila existente, para que create y update impongan la misma regla.

### Cómputo del descuento: `Decimal`, `ROUND_HALF_UP`, cap a `base_price`

`_compute_discount(promo, base_price)` es un helper puro y testeable: `percentage` → `base_price * value/100` redondeado a 2 decimales, **capado a `base_price`**; `fixed_amount` → `min(value, base_price)`. Un descuento **nunca** supera el precio (`final_amount ≥ 0`). Aritmética siempre en `Decimal` (nunca float); el wire serializa los montos como **string**.

> **Sin ADR nuevo de diseño de datos** salvo: marketing **CIERRA** ADR-009 (los forward FKs) → se anota ADR-009 como "cerrado por marketing"; opcionalmente un ADR-013 "marketing: enum-status vs matriz + apply atómico cross-módulo" (a decidir en la consolidación post-fichas).

## Integración cross-módulo (cierre de los FKs forward + wire atómico)

### Cierre de los 3 FKs forward — ADR-009

`crm` y `conversations` declararon columnas `varchar(36)` indexadas **sin FK física** apuntando a `campaign` (que no existía). La migración **F1 de marketing** (`0022_marketing_campaign`), una vez creada la tabla `campaign`, las cierra con `create_foreign_key` en la misma migración:

| Columna | Tabla | Módulo dueño | FK que agrega marketing |
|---|---|---|---|
| `source_campaign_id` | `person_lead_status` | crm | `fk_person_lead_status_campaign` |
| `source_campaign_id` | `lead_status_history` | crm | `fk_lead_status_history_campaign` |
| `default_campaign_id` | `channel_account` | conversations | `fk_channel_account_campaign` |

> Los índices de esas columnas **ya existen** (`ix_person_lead_status_campaign` [nombre a mano], `ix_lead_status_history_source_campaign_id`, `ix_channel_account_default_campaign_id`) — **NO** se recrean, solo `create_foreign_key`. Seguro hoy: todos los valores son `NULL`. El `downgrade` dropea los 3 FK antes de `drop_table campaign`.

### Wire atómico en scheduling (F4)

`scheduling.AppointmentCreate` gana `apply_promotion_id: str | None = None`. En `services/appointment.py:create_appointment`, tras el `db.flush()` de la cita (y el del history) y **antes** del return, si `payload.apply_promotion_id` está presente, llama a `marketing.promotion_usage.apply(...)` con `appointment_id=appt.id` en la **misma sesión** (sin commit intermedio). Si la promo es inválida, `apply` lanza una excepción de dominio → el rollback global **revierte la cita**. Import: scheduling → marketing (OK; marketing **no** importa scheduling a nivel módulo — su `appointment_id` es column, sin relationship). **Reschedule** NO re-aplica la promo (queda en la cita vieja; el usuario re-aplica si quiere).

### Bot (F4)

- Tool read-only `list_eligible_promotions` (`tools/marketing.py`, `@register_tool`): toma `product_id` de args, usa `ctx.person_id` como sujeto (guard `no_person` si None). Target service `marketing.promotion_usage.eligible_for`. Captura solo `DomainException`. Import en `tools/__init__.py` (al final) o no se registra.
- `book_appointment` (`tools/scheduling.py`): lee `args.get("apply_promotion_id")` y lo pasa al `AppointmentCreate`; captura las excepciones de dominio de marketing en el mismo `except DomainException`.
- **seed** `BotTool`: 4ª tuple en `BOT_TOOL_SEED` (`"list_eligible_promotions"`, `requires_confirmation=False`, target `"marketing.promotion_usage.eligible_for"`) + extender el `parameters_schema` de `book_appointment` con `apply_promotion_id` opcional.

> **Pre-requisito de orden**: la firma de `apply`/`eligible_for` debe existir y estar estable **antes** de tocar bots (el import de `tools/` al boot dispara `@register_tool`; un `ImportError` tumba el arranque). Por eso F4 va **después** de F3.

## Dependencias entre módulos

| Módulo | Relación | Naturaleza |
|---|---|---|
| `catalog` | Lee `Product` (`product_repository.get_by_id`: `base_price` + `currency`) para el cómputo; M:N `promotion_product` → `product` (join propio, sin relationship en Product); `target_vertical_id → vertical` (FK real) + `vertical_repository.get_by_ids` / `VerticalOption` para `target_vertical_name`. | LEE + 2 FK reales |
| `crm` | `promotion_usage.person_id → person` (FK real); hidrata `person_name` en reportes vía `person_repository` + `person_option_map`. **Cierra** `person_lead_status.source_campaign_id` y `lead_status_history.source_campaign_id → campaign` (FK aditiva, ADR-009). | FK aditiva (cierra forward) |
| `conversations` | **Cierra** `channel_account.default_campaign_id → campaign` (FK aditiva, ADR-009). El ingest de atribución ya vive en conversations; marketing solo provee `Campaign`. | FK aditiva (cierra forward) |
| `scheduling` | `promotion_usage.appointment_id → appointment` (FK real, nullable). F4: `create_appointment` llama a `apply` atómicamente vía `apply_promotion_id`. scheduling importa marketing; marketing NO importa scheduling (column, sin relationship). | FK real + wire atómico (F4) |
| `bots` | F4: tool `list_eligible_promotions` (read-only) + `book_appointment` extendido + seed `BotTool`. | aditivo (F4) |
| `admin` | Audit users (`created_by`/`updated_by` → `user.id`) vía `user_repository.get_audit_info_map`; `SYSTEM` user (`…0002`) como actor de las aplicaciones automáticas (bot/scheduling). | audit |

`marketing` **no modifica** catalog/crm/conversations en código (solo el `ALTER` aditivo de la migración F1). F4 **sí** toca scheduling+bots (aprobado). Es el último módulo: cierra los forwards que crm/conversations dejaron diferidos.

## Diagramas

- ER: [`docs/diagrams/er-marketing.puml`](../../diagrams/er-marketing.puml)
- Class diagram (modelos + repos + services): [`docs/diagrams/class-backend-marketing.puml`](../../diagrams/class-backend-marketing.puml)

> Ambos reflejan el **modelo viejo flat** (`docs/modules/marketing.md`, 2026-05-28, idealizado). Se **regeneran al modelo de esta spec** en la consolidación post-fichas: 5 entidades, `discount_type` discriminado, `PromotionUsage` sin SD con UNIQUE parcial, las 2 M:N, los FKs forward marcados como "cerrados por marketing", `PUT`/`/active`.

## Implementación por fases

`marketing` se implementa en fases de padre a hijo; cada fase = 1 commit (molde metodología). La última migración aplicada es `0021_scheduling_appointment`, así que marketing arranca en `0022`. Cada deep-dive ([`backend.md`](backend.md), [`ui.md`](ui.md), [`frontend.md`](frontend.md)) cierra con un checklist mapeado a estas fases.

| Fase | Alcance | Migración (revid ≤32) |
|---|---|---|
| **F0 — Prep** | 12 permisos → `SEED_PERMISSIONS` (auto-activa los 6 de ASESOR); nav grupo "Marketing" + iconos Fluent; `endpoints.ts`; `types/marketing.types.ts` (espejo completo); skeleton inerte del paquete backend (`__init__.py` con docstring, **NO registrado**). RO: login admin + assert 12 perms en JWT + rutas marketing → 404. | ninguna (solo seed) |
| **F1 — Campaign** | modelo+schemas+repo+service+router `Campaign` + matriz de transición en service. **Registrar el módulo** (modules/__init__ + main.py + aggregator). Migración `0022` crea `campaign` + **cierra los 3 FKs forward** (ALTER). UI `/marketing/campanas`. ⚠ subset F1: Campaign **NO** declara el relationship `promotions` (Promotion aún no existe) → se difiere a F2; `promotions_count`=0, `CampaignDetail.promotions`=`[]`; el endpoint `/campaigns/{id}/promotions` y `set_promotions` llegan en F2. | `0022_marketing_campaign` |
| **F2 — Promotion** | modelo+schemas+repo+service+router `Promotion` + M:N `campaign_promotion` (ahora ambos existen → wire relationship Campaign.promotions ↔ Promotion.campaigns + `set_promotions` + count) + M:N `promotion_product` (repo con join propio). Migración `0023` (promotion + 2 M:N). Activar `promotions_count` en Campaign + `products_count`/`campaigns_count` en Promotion. UI `/marketing/promociones` (form discriminado por `discount_type`). | `0023_marketing_promotion` |
| **F3 — PromotionUsage** | modelo+schemas+repo+service + `apply`/`validate`/`eligible-for`/`compute-price` + usage list/summary + no-stacking + concurrencia (`get_for_update` + UNIQUE parcial). Migración `0024`. UI `/marketing/usos` (read-only). | `0024_marketing_promotion_usage` |
| **F4 — Integración** | scheduling `apply_promotion_id` atómico en `create_appointment` + bot tool `list_eligible_promotions` + `book_appointment` extendido + seed `BotTool`. (Toca scheduling+bots.) | ninguna |

> **Migraciones**: revision id ≤ 32 chars (`alembic_version varchar(32)`). Verificadas: `0022_marketing_campaign` (23) · `0023_marketing_promotion` (25) · `0024_marketing_promotion_usage` (30). Encadenar `down_revision` (`0022` baja a `0021_scheduling_appointment`). Los FKs forward se cierran con `create_foreign_key` en F1 (el smoke sqlite no los ejercita; los valida el QA E2E en Postgres).

## Próximos pasos / TODOs deliberados

- [ ] **Consolidación post-fichas**: regenerar `er-marketing.puml` + `class-backend-marketing.puml` al modelo final (5 entidades, descuento discriminado, UNIQUE parcial, M:N, FKs forward cerrados); **anotar [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) como "cerrado por marketing"**; decidir si se redacta un ADR-013 (enum-status vs matriz + apply atómico cross-módulo); borrar el overview plano viejo `docs/modules/marketing.md` y repuntar sus links a este README; actualizar `docs/decisions/README.md` si hace falta.
- [ ] **Selector de promo elegible en el wizard de reserva** (consume `eligible-for`): nice-to-have del MVP; mínimo es el campo opcional `apply_promotion_id` en el `AppointmentCreate` del wizard.
- [ ] **Reschedule re-aplica promo**: hoy la promo queda en la cita vieja al reagendar; si el negocio lo requiere, propagar el descuento a la cita nueva (postergado).

---

> **Las otras 3 fichas del módulo**: [`backend.md`](backend.md) (modelo de datos + API contracts + service `apply`/`eligible_for` + migraciones) · [`ui.md`](ui.md) (mockups, drawers con tabs, UX writing en español) · [`frontend.md`](frontend.md) (Next.js, server actions, Zod discriminado, types espejo). Este README es el **overview autoritativo**; ante cualquier choque cross-ficha, prevalece el contenido de esta página.
