# Módulo `marketing`

> **Última actualización**: 2026-05-28
> **Propósito**: campañas (atribución de leads) y promociones (descuentos sobre productos) — con traza de aplicación.
> **Path del código**: `backend/app/modules/marketing/`

## Resumen

`marketing` modela dos cosas relacionadas pero distintas:

- **`Campaign`** — la unidad de **marketing** (con qué iniciativa atrajimos al lead). Se usa para atribución: `ChannelAccount.default_campaign_id`, `PersonLeadStatus.source_campaign_id`, `LeadStatusHistory.source_campaign_id`. No carga lógica de precio.
- **`Promotion`** — la unidad de **precio** (qué descuento se aplica a qué productos). Carga la lógica de descuento (porcentaje o monto fijo) y los límites de uso (`max_uses_total`, `max_uses_per_person`).

Las dos entidades se relacionan M:N (`campaign_promotion`): una campaña puede usar varias promociones, y la misma promoción puede pertenecer a varias campañas (ej. "20% off" se usa en "Lanzamiento Verano" y "Aniversario").

Cada aplicación de una promoción a una cita genera una fila en `PromotionUsage`, que es la **fuente de verdad de descuentos efectivamente aplicados**.

```
Campaign  ⟷ campaign_promotion ⟷  Promotion
                                    ↓
                              promotion_product (M:N a productos)
                                    ↓
                              PromotionUsage  →  Appointment (FK opcional)
                                    ↓
                              Person  (quién la usó, para max_uses_per_person)
```

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Campaign` | `campaign` | Iniciativa de marketing con fechas y status workflow. |
| `Promotion` | `promotion` | Descuento sobre productos con límites de uso. |
| `PromotionUsage` | `promotion_usage` | Cada aplicación de una promo a una cita / persona. |
| _(M:N)_ `campaign_promotion` | `campaign_promotion` | Qué promociones están en cada campaña. |
| _(M:N)_ `promotion_product` | `promotion_product` | Qué productos cubre cada promoción (si `applies_to_all_products=false`). |

### `Campaign`

Iniciativa de marketing. **Sin UTM, sin budget en MVP** — solo identidad + fechas + status. Si el negocio pide ROI tracking más adelante, se agregan columnas aditivas.

- `code: varchar(40)` `<<unique>>` — slug estable (`lanzamiento_verano_2026`).
- `name: varchar(120)`.
- `description: text` `<<nullable>>`.
- `start_date: date`.
- `end_date: date` `<<nullable>>` — `NULL` = sin fecha de cierre conocida.
- `status: varchar(20)` — enum cerrado: `draft / active / paused / ended`. **`draft`** = en planeación, no produce atribución; **`active`** = atribuye y promociones activas se pueden aplicar; **`paused`** = atribuye históricamente pero no se aplica nada nuevo; **`ended`** = histórica, solo lectura.
- `target_vertical_id: varchar(36)` `<<nullable, FK→vertical>>` — si la campaña apunta a una vertical específica. `NULL` = transversal.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Invariantes validados en service**:
- `start_date <= end_date` si `end_date` no es `NULL`.
- Transición de status: `draft → active → paused → active → ended`. No se permite `ended → *` (terminal).

### `Promotion`

Descuento aplicable a productos. Tipo discriminado: porcentaje o monto fijo.

- `code: varchar(40)` `<<unique>>` — slug estable (`20_off_brackets`).
- `name: varchar(120)`.
- `description: text` `<<nullable>>`.
- `discount_type: varchar(20)` — enum cerrado: `percentage / fixed_amount`.
- `discount_value: numeric(10,2)` — el número. **Validación cruzada**: si `percentage` → `0 < value <= 100`; si `fixed_amount` → `value > 0`.
- `currency: varchar(3)` `default 'PEN'` — ISO 4217. Solo aplica si `discount_type='fixed_amount'`. Ignorada si `percentage`.
- `start_date: date`.
- `end_date: date` `<<nullable>>`.
- `max_uses_total: int` `<<nullable>>` — límite global de aplicaciones. `NULL` = sin límite.
- `max_uses_per_person: int` `<<nullable>>` — límite por contacto. `NULL` = sin límite.
- `applies_to_all_products: bool` `default false` — `true` = aplicable a cualquier producto. `false` = solo a productos en `promotion_product` M:N.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

**Invariantes validados en service**:
- Validación cruzada `discount_type` ↔ `discount_value` (rango).
- `start_date <= end_date` si no es `NULL`.
- Si `applies_to_all_products=true`, ignora `promotion_product` (el service no necesita leerla).
- Si `applies_to_all_products=false` y no hay filas en `promotion_product`, la promoción no aplica a nada (estado inconsistente — se valida al activarla).

### `PromotionUsage`

Fuente de verdad de aplicaciones de promociones. Inmutable.

- `promotion_id: varchar(36)` `<<FK→promotion>>`.
- `person_id: varchar(36)` `<<FK→person>>` — a quién se le aplicó.
- `appointment_id: varchar(36)` `<<nullable, FK→appointment>>` — la cita afectada. `NULL` permite "registrar una redención" sin cita asociada (caso raro: venta de producto sin cita, registrada manualmente). En la práctica casi siempre tiene FK.
- `campaign_id: varchar(36)` `<<nullable, FK→campaign>>` — denormalizado: qué campaña dio origen al uso (puede haber promos que existen en varias campañas; aquí se trackea cuál motivó la aplicación específica). `NULL` si la promo se aplicó fuera de una campaña.
- `applied_at: timestamptz`.
- `applied_by: varchar(36)` `<<nullable, FK→user>>` — actor; `NULL` si fue automático (bot, sistema).
- `original_amount: numeric(10,2)` — precio sin descuento al momento de aplicar.
- `discount_amount: numeric(10,2)` — monto descontado.
- `final_amount: numeric(10,2)` — `original_amount - discount_amount`. Denormalizado para reportes.
- `currency: varchar(3)` — coherente con el producto al momento de aplicar.
- `notes: varchar(500)` `<<nullable>>`.
- Mixins: `PrimaryKey`, `Active`, `Timestamp`. **Sin `SoftDeleteMixin`** — audit trail inmutable.

**Invariantes en service**:
- Al insertar, validar:
  - `promotion.active = true` y `now() ∈ [start_date, end_date]` (o `end_date IS NULL`).
  - Si `applies_to_all_products=false`, el `appointment.product_id` debe estar en `promotion_product`.
  - Si `max_uses_total NOT NULL`: `COUNT(promotion_usage WHERE promotion_id = ?) < max_uses_total`.
  - Si `max_uses_per_person NOT NULL`: `COUNT(promotion_usage WHERE promotion_id = ? AND person_id = ?) < max_uses_per_person`.
  - **No stacking**: si la `appointment_id` ya tiene `PromotionUsage`, falla con `BadRequestException(code="PROMOTION_ALREADY_APPLIED")`. Confirmado por usuario.
- `final_amount == original_amount - discount_amount` (validación de coherencia).

### `campaign_promotion` (M:N)

- `campaign_id: varchar(36)` `<<PK, FK→campaign>>`.
- `promotion_id: varchar(36)` `<<PK, FK→promotion>>`.
- `ON DELETE CASCADE`.

### `promotion_product` (M:N)

- `promotion_id: varchar(36)` `<<PK, FK→promotion>>`.
- `product_id: varchar(36)` `<<PK, FK→product>>`.
- `ON DELETE CASCADE`.

## Esquemas (Pydantic v2)

Variantes habituales. Específicos del módulo:

- `CampaignDetail` lleva `promotions: list[PromotionOption]` y `target_vertical: VerticalOption?`.
- `PromotionDetail` lleva `products: list[ProductOption]` (vacío si `applies_to_all_products=true`) y `campaigns: list[CampaignOption]`.
- `PromotionEligibilityRequest { product_id, person_id }` — body para validar si una promo aplica.
- `PromotionEligibilityResponse { promotion_id, is_eligible: bool, reason?: str, discount_amount, final_amount }`.
- `ComputePriceRequest { product_id, person_id, promotion_id? }`.
- `ComputePriceResponse { original_amount, discount_amount, final_amount, currency, promotion_applied?: PromotionOption }`.
- `ApplyPromotionRequest { promotion_id, person_id, appointment_id, campaign_id? }` — body del service de aplicación (usado por scheduling al crear cita).

## Endpoints

Bajo `/api/v1/marketing/`.

### Campaign

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/campaigns/list` | `CAMPAIGNS_READ` |
| `POST` | `/campaigns` | `CAMPAIGNS_CREATE` |
| `GET` | `/campaigns/{id}` | `CAMPAIGNS_READ` |
| `PATCH` | `/campaigns/{id}` | `CAMPAIGNS_UPDATE` |
| `DELETE` | `/campaigns/{id}` | `CAMPAIGNS_DELETE` |
| `GET` | `/campaigns/options?status=` | `CAMPAIGNS_READ` |
| `POST` | `/campaigns/{id}/transition` | `CAMPAIGNS_UPDATE` | cambia status (draft→active→paused→ended) |
| `GET` | `/campaigns/{id}/promotions` | `CAMPAIGNS_READ` |
| `PUT` | `/campaigns/{id}/promotions` | `CAMPAIGNS_UPDATE` | bulk replace M:N (body: `{promotion_ids}`) |

### Promotion

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/promotions/list` | `PROMOTIONS_READ` |
| `POST` | `/promotions` | `PROMOTIONS_CREATE` |
| `GET` | `/promotions/{id}` | `PROMOTIONS_READ` |
| `PATCH` | `/promotions/{id}` | `PROMOTIONS_UPDATE` |
| `DELETE` | `/promotions/{id}` | `PROMOTIONS_DELETE` |
| `GET` | `/promotions/options?active_only=` | `PROMOTIONS_READ` |
| `GET` | `/promotions/{id}/products` | `PROMOTIONS_READ` |
| `PUT` | `/promotions/{id}/products` | `PROMOTIONS_UPDATE` | bulk replace M:N |
| `GET` | `/promotions/{id}/usage-summary` | `PROMOTION_USAGES_READ` | total_uses, total_discount, etc. |

### Validación y aplicación (usado por `scheduling` y por los bots)

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/promotions/eligible-for` | `PROMOTION_VALIDATE` | body `{product_id, person_id}`; devuelve lista de promos elegibles |
| `POST` | `/promotions/{id}/validate` | `PROMOTION_VALIDATE` | body `PromotionEligibilityRequest`; valida si esa promo aplica |
| `POST` | `/compute-price` | `PROMOTION_VALIDATE` | body `ComputePriceRequest`; devuelve precio final |
| `POST` | `/promotion-usages` | `PROMOTION_APPLY` | aplica la promo (crea `PromotionUsage`). Invocado típicamente por el service de scheduling al persistir la cita, no por endpoint público. Expuesto para casos manuales y para tools del bot. |
| `POST` | `/promotion-usages/list` | `PROMOTION_USAGES_READ` |

## Permisos seed

```python
# Module: marketing
("MENU-MARKETING", "Ver menú marketing", "Campañas y promociones", "marketing"),
("CAMPAIGNS_READ", "Ver campañas", "Listar y consultar campañas", "marketing"),
("CAMPAIGNS_CREATE", "Crear campañas", "Crear nuevas campañas", "marketing"),
("CAMPAIGNS_UPDATE", "Editar campañas", "Editar campañas y M:N de promociones", "marketing"),
("CAMPAIGNS_DELETE", "Eliminar campañas", "Soft-delete de campañas", "marketing"),
("PROMOTIONS_READ", "Ver promociones", "Listar y consultar promociones", "marketing"),
("PROMOTIONS_CREATE", "Crear promociones", "Crear nuevas promociones", "marketing"),
("PROMOTIONS_UPDATE", "Editar promociones", "Editar promociones y M:N de productos", "marketing"),
("PROMOTIONS_DELETE", "Eliminar promociones", "Soft-delete de promociones", "marketing"),
("PROMOTION_VALIDATE", "Validar promoción", "Consultar elegibilidad y precio con promo", "marketing"),
("PROMOTION_APPLY", "Aplicar promoción", "Crear PromotionUsage al agendar/atender", "marketing"),
("PROMOTION_USAGES_READ", "Ver usos de promoción", "Reportes de aplicaciones de promociones", "marketing"),
```

**Roles seed que tocan `marketing`**:
- `ADMIN` — todos.
- `ASESOR` — `MENU-MARKETING`, `CAMPAIGNS_READ`, `PROMOTIONS_READ`, `PROMOTION_VALIDATE`, `PROMOTION_APPLY`, `PROMOTION_USAGES_READ`. **No** edita catálogos.
- `DOCTOR` — sin permisos en este módulo.

## Decisiones de diseño

### Campaign y Promotion separadas (no una sola entidad)
Confirmado por usuario al validar el mapa de módulos. Razón: el ciclo de vida es distinto. Una campaña dura unas semanas y atribuye leads; una promoción puede existir varias campañas o vivir independiente. Una campaña sin promo es válida (campaña de awareness). Una promo sin campaña es válida (descuento permanente para clientes recurrentes).

### `Campaign.status` workflow (draft/active/paused/ended)
Confirmado por usuario. Razón: admin necesita planear campañas (`draft`) antes de lanzarlas (`active`), pausar sin terminar (`paused`), y terminar definitivamente (`ended`). Transiciones validadas en service.

**Trade-off explícito**: el flag `Campaign.active` (mixin) sigue existiendo y se usa para soft-disable independiente del status. En la práctica, `status='ended'` típicamente coincide con `active=false`. Documentar al implementar para evitar confusión.

### `Promotion` con `discount_type` discriminado + `discount_value`
Confirmado por usuario. Cubre los dos casos comunes (20% off vs 50 PEN off) sin combinar atributos heterogéneos en una sola columna. La validación cruzada se hace en Pydantic (`@model_validator(mode='after')`).

### `max_uses_total` + `max_uses_per_person` nullable
Confirmado. NULL = sin límite. Permite promos "ilimitadas" (20% off siempre que esté activa) y promos limitadas ("solo 100 redenciones globales"). El service valida con `SELECT COUNT(*) FROM promotion_usage WHERE ...` al aplicar.

**Concurrencia**: dos clientes intentan usar la promo número 100 simultáneamente. Mitigación: `SELECT FOR UPDATE` sobre el lock de la promo + recount. Si el segundo detecta `count >= max_uses_total` post-lock, lanza `BadRequestException(code="PROMOTION_LIMIT_REACHED")`.

### `PromotionUsage` como tabla de audit + reporte
Confirmado por usuario. Trade-off de tener una tabla más: cada aplicación deja traza con snapshot del precio original y descuento. Permite reportes ("cuánto descontamos en este mes", "qué promo mueve más volumen") sin reconstruir desde appointments. Indexes sugeridos: `(promotion_id)`, `(person_id, promotion_id)`, `(appointment_id)`, `(applied_at)`.

### Una promo por aplicación (no stack)
Confirmado por usuario. Razón: cálculo simple, UX clara para el lead ("tu descuento es X"). Validado por el constraint en service: si `appointment_id` ya tiene `PromotionUsage`, rechaza. Si el negocio quiere stacking en el futuro, se agrega `Promotion.is_stackable: bool` y se refactoriza la validación — diseño aditivo.

### `applies_to_all_products: bool` + `promotion_product` M:N
Decisión local de modelado. Razones:
- `true` evita poblar la M:N con todos los productos cuando la promo es "todo el catálogo 10% off".
- `false` exige listar los productos cubiertos.
- El service de validación lee la flag primero; si `false`, mira la M:N.

### `PromotionUsage.appointment_id` nullable, `campaign_id` nullable
- `appointment_id` nullable por si en el futuro se quiere registrar una redención sin cita (caso raro pero válido: venta directa de producto físico).
- `campaign_id` nullable porque promociones pueden aplicarse fuera de campaña (ej. "10% off recurrente para clientes activos" sin campaña asociada). Si vino de una campaña, se trackea para reportes de ROI por campaña.

### Sin ADR
Las decisiones son razonablemente obvias dadas las respuestas del usuario. Las alternativas (Campaign+Promotion fusionados, una sola moneda, sin tabla PromotionUsage) ya se discutieron en preguntas dirigidas y se rechazaron. No hay una decisión costosa de revertir que justifique ADR aparte. Si en el futuro se quiere stacking, retención por tier, vouchers individuales o cupones únicos, eso sí amerita ADR.

## Flujo de aplicación end-to-end (asesor agenda cita con promo)

1. Asesor consulta `POST /marketing/promotions/eligible-for` con `{product_id, person_id}`.
2. Sistema devuelve `[promo_a, promo_b, promo_c]` con `is_eligible=true`.
3. Asesor elige (UI muestra cuál da más descuento).
4. Asesor llama `POST /scheduling/appointments` con `payload = {..., apply_promotion_id: promo_a.id}`.
5. Service `scheduling.appointment.create`:
   1. Valida invariantes 1-8 de scheduling.
   2. Crea `Appointment`.
   3. Llama `marketing.services.promotion_usage.apply(promotion_id=promo_a, person_id, appointment_id=new_appt.id, applied_by=actor.id, campaign_id?)`.
   4. `apply` valida elegibilidad (active, fechas, max_uses, no stacking) y persiste `PromotionUsage`.
   5. Si falla por algún motivo, rollback de la transacción (la `Appointment` no se persiste sin la promo).
6. Confirma al asesor con precio final.

## Flujo bot (tool `apply_promotion` opcional)

El bot puede ofrecer promociones al lead durante la conversación. La tool `list_eligible_promotions(product_id, person_id)` retorna las elegibles; el LLM elige cuál ofrecer; al confirmar el lead, el bot invoca `book_appointment` con `apply_promotion_id` en los args. El flujo es el mismo que el del asesor.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `catalog` | `Promotion ↔ Product` via `promotion_product` M:N. `Campaign.target_vertical_id` FK opcional. |
| `crm` | `PromotionUsage.person_id` (FK). `PersonLeadStatus.source_campaign_id`, `LeadStatusHistory.source_campaign_id` apuntan a `campaign`. |
| `conversations` | `ChannelAccount.default_campaign_id` (FK opcional) para atribución automática del lead que entra por un canal. |
| `scheduling` | `PromotionUsage.appointment_id` (FK opcional). Service de scheduling invoca `marketing.promotion_usage.apply` al crear cita con promo. |
| `admin` | `applied_by` FK, audit users via mixins. |

## Diagramas

- ER: [`docs/diagrams/er-marketing.puml`](../diagrams/er-marketing.puml)
- Class: [`docs/diagrams/class-backend-marketing.puml`](../diagrams/class-backend-marketing.puml)

## Próximos pasos / TODOs deliberados

- [ ] Implementar el `SELECT FOR UPDATE` sobre `promotion` al aplicar para evitar race en `max_uses_total`. Test obligatorio.
- [ ] Si el negocio pide tracking de **UTM/source desde URL**, agregar columnas a `Campaign`: `utm_source, utm_medium, utm_campaign, utm_content?, utm_term?`. Es aditivo, no rompe nada.
- [ ] Si llega caso de **vouchers/cupones únicos** (códigos canjeables individuales), modelar como nueva entidad `Voucher` (1:N con Promotion). Fuera del MVP.
- [ ] Si el negocio quiere **stacking de promociones**, agregar `Promotion.is_stackable: bool` y refactorizar la validación de no-stack. Postergado por decisión del usuario.
- [ ] Si el negocio quiere **A/B testing de promociones** (ofrecer promo A al 50% de leads, B al 50%), modelar como nueva entidad `PromotionExperiment` con asignación por hash de `person_id`. Postergado.
- [ ] Considerar **vista materializada** `mv_promotion_usage_summary` para reportes rápidos cuando `PromotionUsage` crezca. Postergado hasta tener carga real.
