# Módulo `marketing` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-06-08
> **Audiencia**: developer implementando `frontend/src/.../marketing/`.
> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), y como moldes de referencia el frontend de [`../crm/frontend.md`](../crm/frontend.md) (editor M:N + Zod con `superRefine` + tags por-recurso) y [`../scheduling/frontend.md`](../scheduling/frontend.md) (wire `apply_promotion_id` en el wizard de citas + reuse de catálogos cross-módulo), más el `ProductDrawer` de [`../catalog/frontend.md`](../catalog/frontend.md) (form discriminado por watch + Decimal-como-string) y el `BotToolsAssignment` de [`../bots/frontend.md`](../bots/frontend.md) (editor M:N bulk-replace con `SearchableOptionList`).

> **Contrato autoritativo**: este doc respeta la spec compartida de marketing (consolidada en [`README.md`](./README.md)) — nombres de entidades, campos, endpoints, permisos, códigos de error y **fases** son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, manda la spec.

> **Modelo confirmado** (spec §0, decisiones 2026-06-08 — NO re-litigar): **5 entidades** — `Campaign` (status ENUM FIJO `draft/active/paused/ended`, transiciones en el SERVICE, **NO** catálogo configurable ni matriz a diferencia de crm/scheduling), `Promotion` (descuento **discriminado** `percentage`/`fixed_amount`), `PromotionUsage` (audit **inmutable**, sin SoftDelete), M:N `campaign_promotion`, M:N `promotion_product`. **No-stacking**: una promo por cita (UNIQUE parcial en `promotion_usage.appointment_id`). **Integración cross-módulo TOTAL**: marketing **cierra** las 3 FKs forward (ADR-009) vía ALTER; en F4 scheduling gana `apply_promotion_id` (aplicación atómica de promo al agendar) y bots gana la tool `list_eligible_promotions` + `book_appointment` extendido. Marketing **LEE** catalog/crm sin tocarlos (`product_repository.get_by_id`, join propio para el M:N de productos, `vertical_repository.get_by_ids`, `person_option_map`); sólo F4 toca scheduling+bots.

> **Convenciones heredadas de catalog/clinic/staff/crm/conversations/bots/scheduling shipped** (el lector debe tenerlas presentes desde ya):
> 1. **Verbos HTTP**: los updates completos usan **`PUT`** (no `PATCH`). Los M:N bulk-replace son `PUT` (`/campaigns/{id}/promotions`, `/promotions/{id}/products`). La transición de campaña y la validación/aplicación de promociones son `POST` sub-recursos.
> 2. **Dropdowns**: los endpoints de "lista plana de activos" se llaman **`/active`** (no `/options`) y devuelven **lista cruda** (`response_model=list[...]`, sin envelope `SingleResponse`; no se lee `.data`). Reconciliación del doc flat viejo: `/campaigns/options` → **`/campaigns/active`**.
> 3. **Decimal = `string` en el wire** (lección catalog `base_price`): `discount_value` (cuando es `fixed_amount`), `original_amount`/`discount_amount`/`final_amount` viajan como **`string`** en TS. El `Input` usa `inputMode="decimal"`, no `type="number"`. El `percentage` puede modelarse como `number` 0–100 (ver Zod). Aritmética en el backend siempre `Decimal` ROUND_HALF_UP, descuento cap a `base_price`.
> 4. **Lección hotfix `cd10c78` de staff** (aplica a `PromotionUsageItem`, que denormaliza mucho): `defaultSort`, columnas `isSortable` y `searchFields` **SOLO** sobre columnas reales de `ALLOWED_FIELDS`. Ordenar/filtrar server-side por un denormalizado (`promotion_name`, `person_name`, `product_name`, `campaign_name`) devuelve **400 → error boundary del RSC**. El `defaultSort` del client y el `sorting` del prefetch RSC **DEBEN coincidir** (si difieren, el primer paint pide una página y el client otra → flash + refetch). Filtrar por promo/persona/fecha = **deep-link traducido a `FilterCondition` sobre columnas reales** (`promotion_id`, `person_id`, `created_on` — reales en el `promotion_usage`), NO order-by de denormalizados.

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── marketing.types.ts                  ← Campaign*, Promotion*, PromotionUsage*,
│                                              PromotionEligibility/ComputePrice*, PromotionUsageSummary,
│                                              enums (CampaignStatus, DiscountType)
│                                              (reusa UserAuditInfo de audit.types; VerticalOption de catalog,
│                                               ProductOption de catalog)
├── lib/
│   ├── schemas/
│   │   ├── campaign.schema.ts              ← campaignCreate/Update (code slug inmutable; fechas;
│   │   │                                       campaignPromotionsReplace; campaignTransition)
│   │   ├── promotion.schema.ts            ← promotionCreate/Update (DISCOUNT DISCRIMINADO vía
│   │   │                                       base+superRefine — NO discriminatedUnion, por .partial();
│   │   │                                       promotionProductsReplace)
│   │   └── promotion-usage.schema.ts      ← applyPromotion, eligibilityRequest, computePriceRequest
│   └── constants/
│       ├── endpoints.ts                   ← EXTEND con bloque MARKETING (CAMPAIGNS, PROMOTIONS con
│       │                                       nested promotions/products M:N, PROMOTION_USAGES + validación)
│       ├── navigation.ts                  ← EXTEND con grupo 'marketing' (MENU-MARKETING)
│       └── marketing.ts                   ← NUEVO: CAMPAIGN_STATUS_META (label ES + color por estado),
│                                              CAMPAIGN_TRANSITIONS (matriz de shortcuts §2),
│                                              DISCOUNT_TYPE_META (label ES por tipo),
│                                              SUPPORTED_CURRENCIES, formatDiscount helper
├── actions/
│   ├── campaign.actions.ts                ← list/active/get/create/update/delete + transition +
│   │                                          getCampaignPromotions/setCampaignPromotions (M:N)
│   ├── promotion.actions.ts              ← list/active/get/create/update/delete +
│   │                                          getPromotionProducts/setPromotionProducts (M:N) + usageSummary
│   └── promotion-usage.actions.ts        ← eligibleFor/validatePromotion/computePrice (lecturas) +
│                                              applyPromotion (POST) + listPromotionUsages
└── app/(main)/marketing/
    ├── campanas/
    │   ├── page.tsx                       ← LISTA de campañas (drawer create/edit) + deep-link ?status=
    │   └── _components/
    │       ├── CampaignsClient.tsx
    │       └── CampaignDrawer.tsx         ← tabs Datos / Promociones (editor M:N) / Auditoría +
    │                                          badge status + control "Cambiar estado" (shortcuts por matriz)
    ├── promociones/
    │   ├── page.tsx                       ← LISTA de promociones (drawer create/edit)
    │   └── _components/
    │       ├── PromotionsClient.tsx
    │       └── PromotionDrawer.tsx        ← tabs Datos / Descuento (DISCRIMINADO por watch) /
    │                                          Vigencia y límites / Productos (M:N + applies_to_all toggle) /
    │                                          Campañas (read-only chips) / Auditoría
    └── usos/
        ├── page.tsx                       ← read-only; reportes de uso (deep-link ?promotion_id=&person_id=)
        └── _components/PromotionUsagesClient.tsx
```

> **Por qué no hay `marketing/layout.tsx`**: igual que catalog/clinic/staff/crm/scheduling — `campanas`, `promociones`, `usos` son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El detalle de campaña/promoción es un **drawer** (no una sub-ruta), montado desde la lista; la cita tiene menos sub-recursos que Person/Office y se opera in-context (mismo criterio que el detalle de cita en scheduling).

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas. Mantiene componentes locales colocados con su page.

> **Sobre `loading.tsx`**: catalog/clinic/staff/crm/scheduling shipped **no** incluyeron `loading.tsx` (el `DataTable` ya renderiza su skeleton vía `isLoading`). `marketing` sigue ese criterio. No se crean `loading.tsx`.

> **`usos` es read-only** (spec §10): sin drawer ni mutaciones. La página de usos es un reporte (DataTable + filtros) gated `PROMOTION_USAGES_READ`. La aplicación de una promoción (`POST /promotion-usages`) **no** tiene UI directa de creación en el MVP — se dispara desde scheduling (F4, `apply_promotion_id` en el wizard de citas) o desde el bot. La validación (`eligible-for`/`validate`/`compute-price`) la consume el wizard de citas y, opcionalmente, una herramienta de "verificar promoción" embebida (nice-to-have).

## Tipos TS — `types/marketing.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic) y spec §4). Importable desde server actions y client components. **Reusa** `UserAuditInfo` de `audit.types.ts`; **reusa** `VerticalOption` (catalog) y `ProductOption` (catalog) — no se redefinen. **Decimales → `string`** (lección `base_price` de catalog; `discount_value` cuando `fixed_amount`, y todos los `*_amount` de usage/eligibility/compute). El `percentage` se modela como `string` en el wire por consistencia con el `Numeric(10,2)` del backend; el form lo edita como `number` (ver Zod). Las 6 columnas de audit (`created_by_user`/`updated_by_user: UserAuditInfo | null`, etc.) van en `Item`; `PromotionUsageItem` lleva **sólo 3** (`created_on`/`created_by`/`created_by_user`) porque la entidad es **PK·A·T sin updated_** (audit inmutable, spec §3.3).

```ts
import type { UserAuditInfo } from "./audit.types";
import type { VerticalOption, ProductOption } from "./catalog.types";

// ── Enums (espejo de marketing/enums.py; valores EXACTOS) ─────────

// Ciclo de vida de la campaña. ENUM FIJO (NO catálogo configurable). Las
// transiciones permitidas están hardcodeadas en el SERVICE (spec §2), NO en BD.
export type CampaignStatus = "draft" | "active" | "paused" | "ended";

export const CAMPAIGN_STATUSES: readonly CampaignStatus[] = [
  "draft",
  "active",
  "paused",
  "ended",
] as const;

// Tipo de descuento de la promoción. INMUTABLE post-create (el update NO lo incluye).
export type DiscountType = "percentage" | "fixed_amount";

export const DISCOUNT_TYPES: readonly DiscountType[] = [
  "percentage",
  "fixed_amount",
] as const;

// ── Campaign ──────────────────────────────────────────────

// Para selects/M:N/atribución (lista cruda en /campaigns/active). Subset estable.
export interface CampaignOption {
  id: string;
  code: string;
  name: string;
  status: CampaignStatus;
}

// Fila de listado. El backend DENORMALIZA target_vertical_name (batch via
// vertical_repository.get_by_ids) y promotions_count (count_promotions_map). NINGUNO
// está en ALLOWED_FIELDS de campaña salvo las columnas reales — NO ordenar por el
// vertical_name/promotions_count (lección cd10c78). Filtro por status = columna real.
export interface CampaignItem {
  id: string;
  code: string; // slug minúsculas, inmutable post-create
  name: string;
  description: string | null;
  start_date: string; // "YYYY-MM-DD" (date sin TZ)
  end_date: string | null; // null = sin cierre conocido
  status: CampaignStatus;
  target_vertical_id: string | null; // null = transversal
  target_vertical_name: string | null; // denormalizado para mostrar sin join
  promotions_count: number; // tamaño del M:N campaign_promotion
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle: identidad completa + vertical resuelto + las promos del M:N. Un solo GET
// puebla el drawer (tab Datos + tab Promociones leen de aquí; el editor M:N refetcha
// la lista de asignados aparte para evitar stale tras un set).
export interface CampaignDetail extends CampaignItem {
  target_vertical: VerticalOption | null; // resuelto via VerticalOption.model_validate
  promotions: PromotionOption[]; // las promos vinculadas (M:N) — [] en F1, pobladas en F2
}

// code y status NO van en el create (status nace 'draft'; code es obligatorio aquí
// pero inmutable luego). target_vertical_id opcional (transversal si null).
export interface CampaignCreatePayload {
  code: string; // slug minúsculas (regex), min2 max40
  name: string; // min1 max120
  description?: string | null; // max500
  start_date: string; // "YYYY-MM-DD"
  end_date?: string | null;
  target_vertical_id?: string | null;
}

// Update: NO incluye code ni status (inmutables vía update; el status cambia por
// /transition). active toggle de negocio.
export interface CampaignUpdatePayload {
  name?: string;
  description?: string | null;
  start_date?: string;
  end_date?: string | null;
  target_vertical_id?: string | null;
  active?: boolean;
}

// Body de POST /campaigns/{id}/transition (valida la matriz §2 en el service).
export interface CampaignTransitionPayload {
  to_status: CampaignStatus;
}

// Body de PUT /campaigns/{id}/promotions — REEMPLAZA el set completo del M:N.
export interface CampaignPromotionsReplacePayload {
  promotion_ids: string[];
}

// ── Promotion ─────────────────────────────────────────────

// Para selects/M:N/atribución (lista cruda en /promotions/active). Trae el descuento
// listo para mostrar (molde ProductOption). discount_value = string (Decimal).
export interface PromotionOption {
  id: string;
  code: string;
  name: string;
  discount_type: DiscountType;
  discount_value: string; // Decimal serializado (porcentaje 0-100 o monto fijo)
  currency: string; // ISO 4217; sólo aplica si fixed_amount
}

// Fila de listado. Denormaliza products_count (count_products_map) y campaigns_count
// (count_campaigns_map) — NO sortables (cd10c78). Filtro por discount_type/currency/
// active = columnas reales de ALLOWED_FIELDS.
export interface PromotionItem {
  id: string;
  code: string; // slug minúsculas, inmutable
  name: string;
  description: string | null;
  discount_type: DiscountType; // INMUTABLE post-create
  discount_value: string; // Decimal serializado
  currency: string;
  start_date: string; // "YYYY-MM-DD"
  end_date: string | null;
  max_uses_total: number | null; // null = ilimitado
  max_uses_per_person: number | null; // null = ilimitado
  applies_to_all_products: boolean; // true = ignora el M:N de productos
  products_count: number; // tamaño del M:N promotion_product (0 si applies_to_all)
  campaigns_count: number; // campañas que la incluyen
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle: + productos cubiertos (vacío si applies_to_all_products=true) + campañas
// (read-only) + total de usos. El tab Productos lee `products`; el tab Campañas
// muestra `campaigns` como chips de solo lectura.
export interface PromotionDetail extends PromotionItem {
  products: ProductOption[]; // [] si applies_to_all_products=true
  campaigns: CampaignOption[]; // read-only (se gestiona desde el lado Campaña)
  total_uses: number; // count de PromotionUsage para esta promo
}

// Create: discount_type + discount_value (Decimal). El RANGO discount_type↔value se
// valida en el SERVICE (no Pydantic), para que el update lo imponga uniforme. currency
// default 'PEN' (ISO ^[A-Z]{3}$). code slug obligatorio aquí, inmutable luego.
export interface PromotionCreatePayload {
  code: string; // slug minúsculas
  name: string;
  description?: string | null;
  discount_type: DiscountType;
  discount_value: string; // Decimal serializado (percentage 0-100 o fixed >0)
  currency?: string; // default "PEN"
  start_date: string; // "YYYY-MM-DD"
  end_date?: string | null;
  max_uses_total?: number | null; // ge=1 o null
  max_uses_per_person?: number | null; // ge=1 o null
  applies_to_all_products?: boolean; // default false
}

// Update: NO incluye code ni discount_type (ambos INMUTABLES). discount_value sí
// (re-validado en el service contra el discount_type existente de la fila).
export interface PromotionUpdatePayload {
  name?: string;
  description?: string | null;
  discount_value?: string;
  currency?: string;
  start_date?: string;
  end_date?: string | null;
  max_uses_total?: number | null;
  max_uses_per_person?: number | null;
  applies_to_all_products?: boolean;
  active?: boolean;
}

// Body de PUT /promotions/{id}/products — REEMPLAZA el set completo del M:N.
export interface PromotionProductsReplacePayload {
  product_ids: string[];
}

// ── PromotionUsage (audit inmutable — PK·A·T, SIN updated_) ──────

// Fila de listado del reporte de usos. Denormaliza promotion_name/person_name/
// product_name/campaign_name (batch maps; person via person_option_map). Audit de
// SOLO 3 columnas (sin updated_*): la entidad es inmutable (spec §3.3). Los *_name NO
// son sortables; filtrar por promotion_id/person_id/created_on (columnas reales).
export interface PromotionUsageItem {
  id: string;
  promotion_id: string;
  promotion_name: string; // denormalizado
  person_id: string;
  person_name: string; // denormalizado (full_name via person_option_map)
  product_id: string;
  product_name: string; // denormalizado
  appointment_id: string | null; // null = redención sin cita
  campaign_id: string | null;
  campaign_name: string | null; // denormalizado (null si sin campaña)
  original_amount: string; // Decimal serializado (snapshot base_price)
  discount_amount: string; // Decimal serializado (monto descontado)
  final_amount: string; // Decimal serializado (original - discount)
  currency: string; // snapshot del product.currency
  notes: string | null;
  created_on: string; // = applied_at (TimestampMixin; aplicación auto → SYSTEM)
  created_by: string; // = applied_by (SYSTEM_USER_ID si bot/scheduling)
  created_by_user: UserAuditInfo | null; // null si SYSTEM
}

// Detalle = Item (sin extras hoy). Se tipa aparte por simetría con los demás módulos.
export type PromotionUsageDetail = PromotionUsageItem;

// Body de POST /promotion-usages (crea PromotionUsage). Lo arma scheduling (F4) o el
// bot; el front no tiene un form de creación directo en el MVP (la página de usos es
// read-only). Se documenta el shape por completitud y para el wire de scheduling.
export interface ApplyPromotionPayload {
  promotion_id: string;
  person_id: string;
  product_id: string;
  appointment_id?: string | null;
  campaign_id?: string | null;
  notes?: string | null;
}

// ── Validación / precio (read-only; no insertan) ────────

// Body de POST /promotions/eligible-for (lista las promos elegibles para producto+persona).
export interface PromotionEligibilityRequest {
  product_id: string;
  person_id: string;
}

// Una promo evaluada: is_eligible + razón + montos calculados (sin insertar). La usa
// el selector de promo del wizard de citas (F4) y el panel de "verificar promoción".
export interface PromotionEligibility {
  promotion_id: string;
  code: string;
  name: string;
  is_eligible: boolean;
  reason: string | null; // motivo de NO elegibilidad (expirada/límite/per_person/no cubre)
  original_amount: string; // Decimal serializado
  discount_amount: string; // Decimal serializado
  final_amount: string; // Decimal serializado
  currency: string;
}

// Body de POST /compute-price (precio con o sin una promo puntual).
export interface ComputePriceRequest {
  product_id: string;
  person_id: string;
  promotion_id?: string | null; // null = sin descuento (original=final)
}

export interface ComputePriceResponse {
  original_amount: string; // Decimal serializado
  discount_amount: string; // Decimal serializado (0 si sin promo)
  final_amount: string; // Decimal serializado
  currency: string;
  promotion: PromotionOption | null; // null si promotion_id ausente
}

// Resumen de uso de UNA promo (GET /promotions/{id}/usage-summary). Lo muestra el
// tab/panel de métricas del PromotionDrawer.
export interface PromotionUsageSummary {
  promotion_id: string;
  total_uses: number;
  total_original_amount: string; // Decimal serializado
  total_discount_amount: string; // Decimal serializado
  total_final_amount: string; // Decimal serializado
}
```

> **Nota sobre las clases de tiempo** (igual que catalog/clinic/crm):
> - `Campaign.start_date`/`end_date`, `Promotion.start_date`/`end_date` → `Date` **sin TZ**, viajan como `"YYYY-MM-DD"`. **No** se construyen con `new Date(start_date)` para comparar contra "hoy" sin cuidar el desfase de medianoche (parsear como local: `new Date(\`${d}T00:00:00\`)`). La vigencia ("¿está activa hoy?") la decide el **backend** en `apply` (`PROMOTION_NOT_ACTIVE`/`PROMOTION_EXPIRED`); el front sólo la pinta como hint.
> - `PromotionUsage.created_on` es `timestamptz` ISO 8601 con offset → se formatea con `lib/utils/date.ts` (`formatDate`). Cualquier "hoy/ayer" o agrupación por día que afecte el render del reporte = **client-only** (`new Date()` en SSR corre en UTC y desfasa el día en Lima `-05:00`).

> **Por qué `discount_value` y los `*_amount` son `string`** (no `number`): el backend los serializa como **Decimal-string** (`Numeric(10,2)`, lección `base_price` de catalog). Tipar como `number` perdería precisión y rompería el contrato. El form de `Promotion` edita el `discount_value` como `number` (porcentaje) o como `string` decimal (fijo) según `discount_type` — ver [Zod](#zod-schemas) — y serializa a string al enviar. Los reportes de usos formatean los `*_amount` con `currency` (`formatCurrency(value, currency)`, util a crear si no existe).

> **Por qué `PromotionUsageItem` lleva sólo 3 columnas de audit** (no 6): la entidad `PromotionUsage` es **PK·A·T sin SoftDelete y sin updated_** (audit inmutable, spec §3.3) — no hay `updated_on`/`updated_by`/`updated_by_user`. El `created_by_user` puede ser `null` cuando la aplicación fue automática (bot/scheduling → `created_by = SYSTEM_USER_ID`). El render muestra "Sistema" en ese caso.

## Zod schemas

> **Regla del template** ([frontend/CLAUDE.md](../../../frontend/CLAUDE.md)): los Zod viven en `src/lib/schemas/` y los importan **tanto el form (cliente) como el Server Action (server)** → drift imposible. Los mensajes visibles van en **español** (el usuario los lee); los `path` y nombres de campo en inglés.

### `lib/schemas/campaign.schema.ts`

`code` es un **slug minúsculas inmutable** (sólo en el create; el update no lo incluye, igual que el backend). El `superRefine` espeja la validación de fechas del service (`CAMPAIGN_INVALID_DATES`: `end_date >= start_date`). El status **no** se valida aquí (nace `draft`, cambia por `/transition`). El M:N de promociones y la transición tienen sus propios schemas pequeños.

```ts
import { z } from "zod";

// code = slug en MINÚSCULAS (patrón catalog). Inmutable post-create (el update no lo
// incluye, espeja el backend). min2 max40.
const CODE_SLUG_REGEX = /^[a-z][a-z0-9_]{1,38}[a-z0-9]$/;

const campaignBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD"),
  end_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD")
    .nullable()
    .optional()
    .or(z.literal("")),
  target_vertical_id: z.string().nullable().optional(), // null = transversal
});

// end_date >= start_date (comparación lexicográfica válida para YYYY-MM-DD). Sólo
// corre cuando ambas fechas están presentes.
function refineCampaignDates(
  data: { start_date?: string; end_date?: string | null },
  ctx: z.RefinementCtx,
) {
  if (data.start_date && data.end_date && data.end_date !== "" && data.end_date < data.start_date) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["end_date"],
      message: "La fecha de fin no puede ser anterior a la de inicio.",
    });
  }
}

export const campaignCreateSchema = campaignBase
  .extend({
    code: z
      .string()
      .min(2, "Mínimo 2 caracteres")
      .max(40, "Máximo 40 caracteres")
      .regex(CODE_SLUG_REGEX, "Minúsculas, números y guion bajo (ej. verano_2026)"),
  })
  .superRefine(refineCampaignDates);

export const campaignUpdateSchema = campaignBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineCampaignDates);

// Body de POST /campaigns/{id}/transition (la validez de la arista la impone el service).
export const campaignTransitionSchema = z.object({
  to_status: z.enum(CAMPAIGN_STATUSES),
});

// Body de PUT /campaigns/{id}/promotions (reemplaza el set completo del M:N).
export const campaignPromotionsReplaceSchema = z.object({
  promotion_ids: z.array(z.string()),
});

export type CampaignCreateInput = z.infer<typeof campaignCreateSchema>;
export type CampaignUpdateInput = z.infer<typeof campaignUpdateSchema>;
export type CampaignTransitionInput = z.infer<typeof campaignTransitionSchema>;
export type CampaignPromotionsReplaceInput = z.infer<typeof campaignPromotionsReplaceSchema>;
```

> **`CAMPAIGN_STATUSES` se importa de `@/types/marketing.types`** (la const array de la union). El `z.enum(CAMPAIGN_STATUSES)` valida el `to_status` contra los 4 valores. La **validez de la transición** (`CAMPAIGN_TRANSITION_NOT_ALLOWED`, 400) **no** se valida en Zod — la conoce la matriz §2 del backend; la UI la mitiga ofreciendo en el control "Cambiar estado" **sólo** los destinos permitidos (ver `CAMPAIGN_TRANSITIONS` en [marketing.ts](#constantes-de-presentación--libconstantsmarketingts)).

### `lib/schemas/promotion.schema.ts`

El punto delicado del módulo: **el descuento es discriminado** por `discount_type`. **NO** se usa `z.discriminatedUnion` porque el `update` aplica `.partial()` (omite `discount_type`, que es inmutable) y `discriminatedUnion` exige el discriminante presente. En su lugar: un **objeto base + un `refineDiscount(data, ctx)`** aplicado con `.superRefine()` a create **Y** update (patrón crm `refineWonRequiresFinal`). Reglas: `percentage` → `discount_value` numérico `0 < v <= 100`; `fixed_amount` → `discount_value` decimal-string `^\d+(\.\d{1,2})?$` con `v > 0` **y** `currency` ISO. `code` slug inmutable (sólo create). `discount_type` inmutable (sólo create; el update no lo lleva).

```ts
import { z } from "zod";

import { DISCOUNT_TYPES } from "@/types/marketing.types";

// code = slug MINÚSCULAS (patrón catalog), inmutable post-create.
const CODE_SLUG_REGEX = /^[a-z][a-z0-9_]{1,38}[a-z0-9]$/;
// discount_value como monto fijo = decimal-string con ≤2 decimales (espeja Numeric(10,2)).
const DECIMAL_2_REGEX = /^\d+(\.\d{1,2})?$/;
// Monedas soportadas (ISO 4217). Mantener sincronizado con SUPPORTED_CURRENCIES de marketing.ts.
export const SUPPORTED_CURRENCIES = ["PEN", "USD", "EUR"] as const;

// Base SIN discount_type/discount_value (van en create con superRefine; en update
// discount_value es opcional y discount_type NO va). El discount_value se modela como
// string en el wire — el form lo edita como number (percentage) o string (fixed) y
// serializa a string antes de enviar; aquí lo aceptamos como string|number y refinamos.
const promotionBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  currency: z.enum(SUPPORTED_CURRENCIES).optional(),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD"),
  end_date: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Fecha como AAAA-MM-DD")
    .nullable()
    .optional()
    .or(z.literal("")),
  max_uses_total: z
    .number({ invalid_type_error: "Número entero" })
    .int("Entero")
    .min(1, "Mínimo 1")
    .nullable()
    .optional(),
  max_uses_per_person: z
    .number({ invalid_type_error: "Número entero" })
    .int("Entero")
    .min(1, "Mínimo 1")
    .nullable()
    .optional(),
  applies_to_all_products: z.boolean().optional().default(false),
  // discount_value viaja como string (Decimal). El form lo arma según discount_type.
  discount_value: z.string().min(1, "Obligatorio"),
});

// Discriminación SIN discriminatedUnion (para que el update con .partial() funcione):
// percentage → número 0<v<=100; fixed_amount → decimal-string >0 + currency obligatoria.
// En el update, discount_type NO viaja en el body → el refine lo recibe por separado
// (el form lo conoce de la fila existente y lo pasa como contexto vía .superRefine
// sobre un objeto que incluye un campo efímero `_discount_type` NO enviado al backend,
// o el caller valida el discount_value contra el tipo conocido antes de submit).
function refineDiscount(
  data: { discount_type?: DiscountType; discount_value?: string },
  ctx: z.RefinementCtx,
) {
  if (!data.discount_value) return; // opcional en update; si ausente, no refinar
  const raw = data.discount_value.trim();
  if (data.discount_type === "percentage") {
    const n = Number(raw);
    if (!Number.isFinite(n) || n <= 0 || n > 100) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["discount_value"],
        message: "El porcentaje debe ser mayor que 0 y como máximo 100.",
      });
    }
  } else if (data.discount_type === "fixed_amount") {
    if (!DECIMAL_2_REGEX.test(raw) || Number(raw) <= 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["discount_value"],
        message: "El monto debe ser mayor que 0 (hasta 2 decimales).",
      });
    }
    if (!data.currency) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["currency"],
        message: "Elige la moneda del descuento fijo.",
      });
    }
  }
}

export const promotionCreateSchema = promotionBase
  .extend({
    code: z
      .string()
      .min(2, "Mínimo 2 caracteres")
      .max(40, "Máximo 40 caracteres")
      .regex(CODE_SLUG_REGEX, "Minúsculas, números y guion bajo (ej. dscto_10)"),
    discount_type: z.enum(DISCOUNT_TYPES),
  })
  .superRefine((data, ctx) => refineDiscount(data, ctx));

// Update: discount_type INMUTABLE → NO va en el body. discount_value opcional. El form
// conoce el discount_type de la fila existente y lo inyecta como `_discount_type`
// (campo NO enviado al backend) sólo para que el refine valide el rango; el action lo
// descarta antes del PUT. code tampoco va (inmutable).
export const promotionUpdateSchema = promotionBase
  .partial()
  .extend({
    active: z.boolean().optional(),
    _discount_type: z.enum(DISCOUNT_TYPES).optional(), // efímero, sólo para el refine
  })
  .superRefine((data, ctx) =>
    refineDiscount({ discount_type: data._discount_type, discount_value: data.discount_value }, ctx),
  );

// Body de PUT /promotions/{id}/products (reemplaza el set completo del M:N).
export const promotionProductsReplaceSchema = z.object({
  product_ids: z.array(z.string()),
});

export type PromotionCreateInput = z.infer<typeof promotionCreateSchema>;
export type PromotionUpdateInput = z.infer<typeof promotionUpdateSchema>;
export type PromotionProductsReplaceInput = z.infer<typeof promotionProductsReplaceSchema>;
```

> **Por qué `base + superRefine` y NO `z.discriminatedUnion`** (decisión clave del módulo): el `update` usa `.partial()` y **omite** `discount_type` (inmutable post-create, spec §4.2). `z.discriminatedUnion` exige el campo discriminante presente en el objeto → incompatible con `.partial()`. El patrón base+refine (espeja `refineWonRequiresFinal` de crm `lead-status.schema`) permite reusar la lógica de validación de rango en **ambos** schemas. En el update, el `discount_type` se inyecta como `_discount_type` efímero (lo conoce el form de la fila existente) **sólo** para que el refine valide el `discount_value`; el action **lo descarta** antes del `PUT` (el backend no lo acepta). Alternativa equivalente: validar el `discount_value` en el componente con el `discount_type` en mano y dejar el Zod del update sin el refine — pero inyectar `_discount_type` mantiene la regla en el schema compartido.

> **El rango discount_type↔discount_value se valida también en el SERVICE** (spec §6.2, `PROMOTION_INVALID_DISCOUNT`, 400): el Zod es UX (feedback inline en español); el backend es la fuente de verdad (en el update, el service usa el `discount_type` **existente** de la fila — el front no puede cambiarlo). Si el Zod del front y el del service divergen, gana el backend (el `MessageBar` muestra el `detail` en español).

> **`SUPPORTED_CURRENCIES` se exporta de aquí Y de `marketing.ts`** (no duplicar la fuente): definirlo una vez (en `marketing.ts` como const de presentación) e importarlo en el schema, o viceversa. La spec lo lista en ambos contextos; la implementación escoge un único origen y lo reusa (evitar drift). El backend valida `currency` con `^[A-Z]{3}$` (cualquier ISO 4217); el front lo acota al subconjunto soportado por la UI.

### `lib/schemas/promotion-usage.schema.ts`

La validación/aplicación. `applyPromotionSchema` arma el body de `POST /promotion-usages` (lo usa scheduling F4 / el bot; el front no tiene form de creación directo). `eligibilityRequestSchema`/`computePriceRequestSchema` validan los requests de las lecturas (las consume el wizard de citas y el panel de verificación).

```ts
import { z } from "zod";

// Body de POST /promotion-usages (crea PromotionUsage). Sin form directo en el MVP;
// se documenta para el wire de scheduling/bot y por completitud del contrato.
export const applyPromotionSchema = z.object({
  promotion_id: z.string().min(1, "Elige la promoción"),
  person_id: z.string().min(1, "Elige a la persona"),
  product_id: z.string().min(1, "Elige el producto"),
  appointment_id: z.string().nullable().optional(),
  campaign_id: z.string().nullable().optional(),
  notes: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
});

// Body de POST /promotions/eligible-for.
export const eligibilityRequestSchema = z.object({
  product_id: z.string().min(1, "Elige el producto"),
  person_id: z.string().min(1, "Elige a la persona"),
});

// Body de POST /compute-price (promotion_id opcional → sin descuento).
export const computePriceRequestSchema = z.object({
  product_id: z.string().min(1, "Elige el producto"),
  person_id: z.string().min(1, "Elige a la persona"),
  promotion_id: z.string().nullable().optional(),
});

export type ApplyPromotionInput = z.infer<typeof applyPromotionSchema>;
export type EligibilityRequestInput = z.infer<typeof eligibilityRequestSchema>;
export type ComputePriceRequestInput = z.infer<typeof computePriceRequestSchema>;
```

> **Lo que Zod NO puede validar** (queda como error de servidor en español, `MessageBar`): toda la lógica de elegibilidad/aplicación — `PROMOTION_NOT_ACTIVE`, `PROMOTION_EXPIRED`, `PROMOTION_PRODUCT_NOT_COVERED`, `PROMOTION_ALREADY_APPLIED` (no-stacking), `PROMOTION_LIMIT_REACHED`, `PROMOTION_PERSON_LIMIT_REACHED`, `PRODUCT_NOT_FOUND`, `PERSON_NOT_FOUND`. La UI los **mitiga** mostrando sólo promos que `eligible-for` ya marcó `is_eligible=true` (con su `reason` para las no elegibles), pero el backend es la fuente de verdad (concurrencia: dos citas usan la última unidad de una promo con `max_uses_total` → la 2ª recibe `PROMOTION_LIMIT_REACHED`).

## Constantes de presentación — `lib/constants/marketing.ts`

Metadata de presentación del módulo: label ES + color por estado de campaña, la matriz de transiciones de status (espejo §2, para gatear los shortcuts del control "Cambiar estado"), label ES por tipo de descuento, monedas soportadas y un helper de formato de descuento. **Nuevo** (marketing necesita su propia tabla; el color de los estados es FIJO en el front — a diferencia de crm/scheduling cuyo color viene del catálogo en BD, aquí el status es un ENUM cerrado).

```ts
import type { CampaignStatus, DiscountType, PromotionOption } from "@/types/marketing.types";

// ── Estado de campaña (ENUM fijo) ────────────────────────
// Label ES + color (token Fluent semántico, NO brandPalette.accent que no existe).
// El color del badge es FIJO por estado (no configurable en BD, a diferencia de crm).
export const CAMPAIGN_STATUS_META: Record<
  CampaignStatus,
  { label: string; color: string }
> = {
  draft: { label: "Borrador", color: "tokens.colorNeutralForeground3" },
  active: { label: "Activa", color: "tokens.colorPaletteGreenForeground1" },
  paused: { label: "Pausada", color: "tokens.colorPaletteMarigoldForeground2" },
  ended: { label: "Finalizada", color: "tokens.colorNeutralForeground4" },
};

// Matriz de transiciones permitidas (espejo EXACTO de spec §2; hardcodeada en el
// service). El control "Cambiar estado" ofrece SOLO los destinos de aquí → previene
// CAMPAIGN_TRANSITION_NOT_ALLOWED (400). 'ended' es terminal (sin destinos).
export const CAMPAIGN_TRANSITIONS: Record<CampaignStatus, CampaignStatus[]> = {
  draft: ["active"],
  active: ["paused", "ended"],
  paused: ["active", "ended"],
  ended: [], // terminal
};

// ── Tipo de descuento ────────────────────────────────────
export const DISCOUNT_TYPE_META: Record<DiscountType, { label: string }> = {
  percentage: { label: "Porcentaje" },
  fixed_amount: { label: "Monto fijo" },
};

// Monedas soportadas por la UI (ISO 4217). El backend acepta cualquier ^[A-Z]{3}$;
// el front lo acota. Reusado por el Zod de promotion (single source).
export const SUPPORTED_CURRENCIES = ["PEN", "USD", "EUR"] as const;

// Formato de descuento para badges/columnas: "10%" o "S/ 25.00" según el tipo.
export function formatDiscount(p: Pick<PromotionOption, "discount_type" | "discount_value" | "currency">): string {
  if (p.discount_type === "percentage") return `${p.discount_value}%`;
  // fixed_amount: prefijo de moneda + monto (Decimal-string, ya con 2 decimales).
  const symbol = p.currency === "PEN" ? "S/" : p.currency === "USD" ? "$" : p.currency === "EUR" ? "€" : p.currency;
  return `${symbol} ${p.discount_value}`;
}
```

> **El color de los badges de estado es FIJO** (token Fluent por `CampaignStatus`), **no** del catálogo: a diferencia de crm `LeadStatus`/scheduling `AppointmentStatus` (color hex configurable en BD), `CampaignStatus` es un **ENUM cerrado** (spec §0.2) → el color vive en `CAMPAIGN_STATUS_META`. Usar **tokens Fluent semánticos** (`tokens.colorPaletteGreenForeground2`, etc.), nunca `brandPalette.accent` (no existe — lección operativa transversal). El snippet arriba muestra los nombres de token como strings ilustrativos; en el código real se importan de `@fluentui/react-components` (`tokens`).

> **`formatDiscount`/`formatCurrency`**: `formatDiscount` arma el texto del badge de descuento. Para los `*_amount` de los reportes de usos crear/reusar `formatCurrency(value: string, currency: string)` en `lib/utils/` (si no existe ya una util de moneda) — los montos vienen como Decimal-string y se muestran con prefijo de moneda. No usar `Intl.NumberFormat` sobre un `Number(value)` si eso perdería precisión; el string ya viene con 2 decimales del backend.

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque MARKETING completo (todas las URLs de la spec §7). `/active` antes de `/{id}` en el backend; verbos `PUT` para updates y para los M:N bulk-replace; transición/validación/aplicación como `POST` sub-recursos. Los M:N llevan el id en una **función** (`PROMOTIONS_LIST(id)`/`PROMOTIONS_UPDATE(id)`, `PRODUCTS_LIST(id)`/`PRODUCTS_UPDATE(id)`).

```ts
const MARKETING = "/api/v1/marketing"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, VERTICALS, SERVICES, PRODUCTS,
  //   BRANCHES, OFFICES, DOCTORS, ME (staff), CRM, SCHEDULING (existentes) …

  // ── Marketing module ──────────────────────────────────────
  CAMPAIGNS: {
    LIST: `${MARKETING}/campaigns/list`,
    CREATE: `${MARKETING}/campaigns`,
    GET: (id: string) => `${MARKETING}/campaigns/${id}`,
    UPDATE: (id: string) => `${MARKETING}/campaigns/${id}`, // ← PUT
    DELETE: (id: string) => `${MARKETING}/campaigns/${id}`, // soft delete
    ACTIVE: `${MARKETING}/campaigns/active`, // raw CampaignOption list
    TRANSITION: (id: string) => `${MARKETING}/campaigns/${id}/transition`, // POST (valida matriz §2)
    // M:N campaign_promotion (las promos de la campaña).
    PROMOTIONS_LIST: (id: string) => `${MARKETING}/campaigns/${id}/promotions`, // GET (SingleResponse[list[PromotionOption]])
    PROMOTIONS_UPDATE: (id: string) => `${MARKETING}/campaigns/${id}/promotions`, // ← PUT (reemplaza set)
  },
  PROMOTIONS: {
    LIST: `${MARKETING}/promotions/list`,
    CREATE: `${MARKETING}/promotions`,
    GET: (id: string) => `${MARKETING}/promotions/${id}`,
    UPDATE: (id: string) => `${MARKETING}/promotions/${id}`, // ← PUT
    DELETE: (id: string) => `${MARKETING}/promotions/${id}`, // soft delete
    ACTIVE: `${MARKETING}/promotions/active`, // raw PromotionOption list
    // M:N promotion_product (los productos cubiertos).
    PRODUCTS_LIST: (id: string) => `${MARKETING}/promotions/${id}/products`, // GET (SingleResponse[list[ProductOption]])
    PRODUCTS_UPDATE: (id: string) => `${MARKETING}/promotions/${id}/products`, // ← PUT (reemplaza set)
    USAGE_SUMMARY: (id: string) => `${MARKETING}/promotions/${id}/usage-summary`, // GET (PROMOTION_USAGES_READ)
    // Validación de UNA promo puntual.
    VALIDATE: (id: string) => `${MARKETING}/promotions/${id}/validate`, // POST (PROMOTION_VALIDATE)
  },
  PROMOTION_USAGES: {
    LIST: `${MARKETING}/promotion-usages/list`, // POST + QueryRequest (PROMOTION_USAGES_READ)
    APPLY: `${MARKETING}/promotion-usages`, // POST (201, PROMOTION_APPLY) — crea PromotionUsage
    ELIGIBLE_FOR: `${MARKETING}/promotions/eligible-for`, // POST (PROMOTION_VALIDATE)
    COMPUTE_PRICE: `${MARKETING}/compute-price`, // POST (PROMOTION_VALIDATE)
  },
} as const;
```

> **Orden de rutas en el backend** (no afecta al front, pero lo documenta): `/campaigns/active` y `/promotions/active` se declaran **antes** de `/{id}` (evita captura de ruta); `/promotions/eligible-for` (literal) antes de `/promotions/{id}/validate`. El aggregator agrupa `eligible-for`/`validate`/`usage-summary` por permiso (pueden vivir en `promotion_usage.py` o `promotion.py`).

> **`/active` devuelve lista CRUDA** (`response_model=list[...]`, sin envelope) — no se lee `.data`. El **M:N GET** (`/campaigns/{id}/promotions`, `/promotions/{id}/products`) devuelve `SingleResponse[list[Option]]` → **sí** se lee `.data` (el editor M:N lee `res.data` para preseleccionar). El resto (`/list`, `GET /{id}`, `POST`, `PUT`, transición, validación, compute, usage-summary) usa los envelopes del template y se lee con `.data`.

> **`PROMOTION_USAGES.APPLY` NO se llama desde la UI del módulo marketing** en el MVP (la página de usos es read-only). Lo consume **scheduling** (F4, vía `apply_promotion_id` en el body de `POST /appointments` — el backend de scheduling llama a `marketing.promotion_usage.apply` en la misma sesión, atómico) y el **bot**. Se lista en el `ENDPOINTS` por completitud y para un eventual panel de aplicación manual (TODO diferido).

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `marketing` (módulo #8, último) después de `scheduling` (antes de `admin`):

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … */ },
  { key: "catalog", /* … */ },
  { key: "clinic", /* … */ },
  { key: "staff", /* … */ },
  { key: "crm", /* … */ },
  { key: "scheduling", /* … */ },

  // ── NEW ───────────────────────────────────────────
  {
    key: "marketing",
    label: "Marketing",
    icon: "MegaphoneRegular",
    permissions: ["MENU-MARKETING"], // gate del grupo (ASESOR/ADMIN lo tienen)
    children: [
      {
        key: "campaigns",
        label: "Campañas",
        icon: "MegaphoneRegular",
        url: "/marketing/campanas",
        permissions: ["CAMPAIGNS_READ"],
      },
      {
        key: "promotions",
        label: "Promociones",
        icon: "TicketDiamondRegular",
        url: "/marketing/promociones",
        permissions: ["PROMOTIONS_READ"],
      },
      {
        key: "promotion-usages",
        label: "Usos de promoción",
        icon: "ReceiptRegular",
        url: "/marketing/usos",
        permissions: ["PROMOTION_USAGES_READ"],
      },
    ],
  },

  { key: "admin", /* … */ },
];
```

> **Gating del grupo vs items**: la spec pide el grupo **gated `MENU-MARKETING`** (lo tienen ADMIN/ASESOR — el ASESOR ya forward-declara 6 perms de marketing, spec §11). Cada item lleva su permiso fino (`CAMPAIGNS_READ`, `PROMOTIONS_READ`, `PROMOTION_USAGES_READ`) y el page RSC valida con `requirePermission(...)`. El grupo se muestra si ≥1 child pasa el filtro. **No** redefinir los permisos aquí — los 12 ya son canónicos en `seed.py` (los crea backend F0, spec §11; HOY 6 de ellos sólo viven en el set `ASESOR_PERMISSION_CODES`, no como filas — F0 los materializa).

> **Íconos** (verificar que existan en `@fluentui/react-icons` v9 — **lección catalog: 4 íconos no existían**; fallback si no): grupo Marketing `MegaphoneRegular`, Campañas `MegaphoneRegular`, Promociones `TicketDiamondRegular` (alternativa: `TagRegular`), Usos de promoción `ReceiptRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que catalog/clinic/staff/crm/scheduling). Alternativas verificadas: `TicketDiamondRegular` → `TagRegular`; `ReceiptRegular` → `DocumentRegular`/`ReceiptMoneyRegular`. **No** introducir librerías de íconos nuevas. `MegaphoneRegular` ya lo usa crm (`CAMPAIGN_ATTRIBUTION` en `ACTIVITY_TYPE_META`) → confirmado que resuelve.

## Server Actions

Mismo molde que catalog/clinic/staff/crm/scheduling: validar con Zod en el action → llamar backend client → `revalidateTag(TAG, "max")`. Reusa el `MutationResult<T>` exportado por `user.actions.ts` (**NO** está en `api.types`). **Next 16 exige el 2º argumento de `revalidateTag`** (`"max"`); omitirlo es error de tipos/runtime.

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `marketing:campaigns` | listas y detalle de campañas, `/campaigns/active` | crear/editar/borrar campaña; transición; **set de promociones** (cambia `promotions_count` denormalizado) |
| `marketing:promotions` | listas y detalle de promociones, `/promotions/active` | crear/editar/borrar promoción; **set de productos** (cambia `products_count`); cambia `campaigns_count` si se la asigna/desasigna desde una campaña |
| `marketing:promotion-usages` | reporte de usos (`/promotion-usages/list`), usage-summary | aplicar una promo (crea PromotionUsage) — lo dispara scheduling/bot; también renombrar promo/persona/producto/campaña deja stale los denormalizados |

> **Cross-tag**: (1) `setCampaignPromotions` invalida `marketing:campaigns` (el `promotions_count` y el detalle de esa campaña) **y** `marketing:promotions` (el `campaigns_count` de las promos afectadas, que es read-only desde el lado promo pero se muestra). (2) `setPromotionProducts` invalida `marketing:promotions` (el `products_count`/detalle). (3) Renombrar una `Campaign`/`Promotion`/`Product`/`Person` deja stale el `*_name` denormalizado de un reporte de usos cacheado → el tag `marketing:promotion-usages` se invalida en el rename **si** el módulo dueño coopera; como marketing no controla el rename de Product/Person (otros módulos), el reporte de usos se refresca por TTL/navegación (aceptable: es un reporte histórico). (4) `applyPromotion` (lo llama scheduling F4) invalida `marketing:promotion-usages` **y** `marketing:promotions` (el `total_uses`/`usage-summary` de esa promo) — ver nota cross-módulo en [scheduling/frontend.md](../scheduling/frontend.md) (el wire F4).

> **No hay tag por-recurso (`marketing:campaign:{id}`)** como en crm/scheduling: el detalle de campaña/promoción se opera en un **drawer** que refetcha al abrir (`getCampaign(id)`/`getPromotion(id)` en cliente), y el M:N refetcha su lista de asignados aparte tras un set. El grano global por-entidad (`marketing:campaigns`/`marketing:promotions`) basta para el MVP (volumen bajo de campañas/promos). Si crece, taggear por-id (mismo criterio que `scheduling:appointment:{id}`) es la evolución.

### `actions/campaign.actions.ts`

Molde directo de `vertical.actions` (CRUD) + el M:N bulk-replace de `bot-configuration.actions` (`getBotTools`/`setBotTools`).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  campaignCreateSchema,
  campaignUpdateSchema,
  campaignTransitionSchema,
  campaignPromotionsReplaceSchema,
} from "@/lib/schemas/campaign.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  CampaignDetail,
  CampaignItem,
  CampaignOption,
  PromotionOption,
} from "@/types/marketing.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions"; // ← NO está en api.types

const CAMPAIGNS_TAG = "marketing:campaigns";
const PROMOTIONS_TAG = "marketing:promotions";

export async function listCampaigns(query: QueryRequest): Promise<ApiPaginated<CampaignItem>> {
  return backendClient.post<ApiPaginated<CampaignItem>>(ENDPOINTS.CAMPAIGNS.LIST, query, {
    tags: [CAMPAIGNS_TAG],
  });
}

export async function listActiveCampaigns(): Promise<CampaignOption[]> {
  // Lista CRUDA (sin envelope) — NO se lee `.data`.
  return backendClient.get<CampaignOption[]>(ENDPOINTS.CAMPAIGNS.ACTIVE, { tags: [CAMPAIGNS_TAG] });
}

export async function getCampaign(id: string): Promise<ApiSingle<CampaignDetail>> {
  return backendClient.get<ApiSingle<CampaignDetail>>(ENDPOINTS.CAMPAIGNS.GET(id), {
    tags: [CAMPAIGNS_TAG],
  });
}

export async function createCampaign(
  input: unknown,
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.CREATE,
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 CAMPAIGN_CODE_TAKEN / 400 CAMPAIGN_INVALID_DATES / 400 TARGET_VERTICAL_NOT_FOUND.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateCampaign(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.UPDATE(id), // ← PUT
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteCampaign(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CAMPAIGNS.DELETE(id));
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Transición de estado (valida la matriz §2 en el service) ─
export async function transitionCampaign(
  id: string,
  input: unknown, // { to_status }
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignTransitionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.TRANSITION(id),
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 CAMPAIGN_TRANSITION_NOT_ALLOWED en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── M:N campaign_promotion (molde getBotTools/setBotTools) ──

export async function getCampaignPromotions(id: string): Promise<PromotionOption[]> {
  // GET enveloped SingleResponse[list[PromotionOption]] → leer .data.
  const res = await backendClient.get<ApiSingle<PromotionOption[]>>(
    ENDPOINTS.CAMPAIGNS.PROMOTIONS_LIST(id),
    { tags: [CAMPAIGNS_TAG] },
  );
  return res.data;
}

export async function setCampaignPromotions(
  id: string,
  input: unknown, // { promotion_ids: [...] } — reemplaza el set completo
): Promise<MutationResult<ApiSingle<CampaignDetail>>> {
  const parsed = campaignPromotionsReplaceSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<CampaignDetail>>(
      ENDPOINTS.CAMPAIGNS.PROMOTIONS_UPDATE(id), // ← PUT (reemplaza)
      parsed.data,
    );
    revalidateTag(CAMPAIGNS_TAG, "max"); // promotions_count + detalle de la campaña
    revalidateTag(PROMOTIONS_TAG, "max"); // campaigns_count de las promos afectadas
    return { ok: true, data };
  } catch (e) {
    // 400 PROMOTION_NOT_FOUND si algún promotion_id no existe vivo.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/promotion.actions.ts`

Análogo a `campaign.actions` (CRUD + M:N de productos). Sin transición (la promo no tiene estado de ciclo de vida). + `usage-summary` (read).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  promotionCreateSchema,
  promotionUpdateSchema,
  promotionProductsReplaceSchema,
} from "@/lib/schemas/promotion.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  PromotionDetail,
  PromotionItem,
  PromotionOption,
  PromotionUsageSummary,
} from "@/types/marketing.types";
import type { ProductOption } from "@/types/catalog.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const PROMOTIONS_TAG = "marketing:promotions";
const USAGES_TAG = "marketing:promotion-usages";

export async function listPromotions(query: QueryRequest): Promise<ApiPaginated<PromotionItem>> {
  return backendClient.post<ApiPaginated<PromotionItem>>(ENDPOINTS.PROMOTIONS.LIST, query, {
    tags: [PROMOTIONS_TAG],
  });
}

export async function listActivePromotions(): Promise<PromotionOption[]> {
  // Lista CRUDA — la consume el editor M:N de campañas (opciones) y el wizard de citas.
  return backendClient.get<PromotionOption[]>(ENDPOINTS.PROMOTIONS.ACTIVE, { tags: [PROMOTIONS_TAG] });
}

export async function getPromotion(id: string): Promise<ApiSingle<PromotionDetail>> {
  return backendClient.get<ApiSingle<PromotionDetail>>(ENDPOINTS.PROMOTIONS.GET(id), {
    tags: [PROMOTIONS_TAG],
  });
}

export async function createPromotion(
  input: unknown,
): Promise<MutationResult<ApiSingle<PromotionDetail>>> {
  const parsed = promotionCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PromotionDetail>>(
      ENDPOINTS.PROMOTIONS.CREATE,
      parsed.data,
    );
    revalidateTag(PROMOTIONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 PROMOTION_CODE_TAKEN / 400 PROMOTION_INVALID_DISCOUNT / 400 PROMOTION_INVALID_DATES.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updatePromotion(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<PromotionDetail>>> {
  const parsed = promotionUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  // Descartar el campo efímero _discount_type antes del PUT (el backend no lo acepta;
  // sólo existía para que el Zod del update valide el rango de discount_value).
  const { _discount_type, ...body } = parsed.data as Record<string, unknown>;
  try {
    const data = await backendClient.put<ApiSingle<PromotionDetail>>(
      ENDPOINTS.PROMOTIONS.UPDATE(id), // ← PUT
      body,
    );
    revalidateTag(PROMOTIONS_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deletePromotion(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.PROMOTIONS.DELETE(id));
    revalidateTag(PROMOTIONS_TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── M:N promotion_product ───────────────────────────────

export async function getPromotionProducts(id: string): Promise<ProductOption[]> {
  const res = await backendClient.get<ApiSingle<ProductOption[]>>(
    ENDPOINTS.PROMOTIONS.PRODUCTS_LIST(id),
    { tags: [PROMOTIONS_TAG] },
  );
  return res.data;
}

export async function setPromotionProducts(
  id: string,
  input: unknown, // { product_ids: [...] }
): Promise<MutationResult<ApiSingle<PromotionDetail>>> {
  const parsed = promotionProductsReplaceSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<PromotionDetail>>(
      ENDPOINTS.PROMOTIONS.PRODUCTS_UPDATE(id), // ← PUT (reemplaza)
      parsed.data,
    );
    revalidateTag(PROMOTIONS_TAG, "max"); // products_count + detalle
    return { ok: true, data };
  } catch (e) {
    // 400 PRODUCT_NOT_FOUND si algún product_id no existe vivo en catalog.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Resumen de uso (read) ───────────────────────────────
export async function getPromotionUsageSummary(id: string): Promise<PromotionUsageSummary> {
  const res = await backendClient.get<ApiSingle<PromotionUsageSummary>>(
    ENDPOINTS.PROMOTIONS.USAGE_SUMMARY(id),
    { tags: [USAGES_TAG] },
  );
  return res.data;
}
```

### `actions/promotion-usage.actions.ts`

La validación/aplicación + el reporte. `eligibleFor`/`validatePromotion`/`computePrice` son **lecturas** (no revalidan tags; las consume el wizard de citas F4 y el panel de verificación). `applyPromotion` (POST) crea el `PromotionUsage` — en el MVP **no** lo llama la UI de marketing directamente (la página de usos es read-only); se documenta para scheduling/bot.

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  applyPromotionSchema,
  eligibilityRequestSchema,
  computePriceRequestSchema,
} from "@/lib/schemas/promotion-usage.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  ComputePriceResponse,
  PromotionEligibility,
  PromotionUsageDetail,
  PromotionUsageItem,
} from "@/types/marketing.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const PROMOTIONS_TAG = "marketing:promotions";
const USAGES_TAG = "marketing:promotion-usages";

// ── Reporte de usos (read-only) ─────────────────────────
export async function listPromotionUsages(
  query: QueryRequest,
): Promise<ApiPaginated<PromotionUsageItem>> {
  return backendClient.post<ApiPaginated<PromotionUsageItem>>(
    ENDPOINTS.PROMOTION_USAGES.LIST,
    query,
    { tags: [USAGES_TAG] },
  );
}

// ── Validación (lecturas; sin revalidateTag) ────────────

export async function eligibleFor(input: unknown): Promise<PromotionEligibility[]> {
  // Valida product_id+person_id; lista las promos elegibles (con razón si no). La usa
  // el selector de promo del wizard de citas (F4) y el panel "verificar promoción".
  const parsed = eligibilityRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<PromotionEligibility[]>>(
    ENDPOINTS.PROMOTION_USAGES.ELIGIBLE_FOR,
    parsed,
    { cache: "no-store" },
  );
  return res.data;
}

export async function validatePromotion(
  promotionId: string,
  input: unknown, // { product_id, person_id }
): Promise<PromotionEligibility> {
  const parsed = eligibilityRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<PromotionEligibility>>(
    ENDPOINTS.PROMOTIONS.VALIDATE(promotionId),
    parsed,
    { cache: "no-store" },
  );
  return res.data;
}

export async function computePrice(input: unknown): Promise<ComputePriceResponse> {
  const parsed = computePriceRequestSchema.parse(input);
  const res = await backendClient.post<ApiSingle<ComputePriceResponse>>(
    ENDPOINTS.PROMOTION_USAGES.COMPUTE_PRICE,
    parsed,
    { cache: "no-store" },
  );
  return res.data;
}

// ── Aplicación (POST; crea PromotionUsage) ──────────────
// En el MVP NO la llama la UI de marketing (usos = read-only); scheduling F4 la dispara
// vía apply_promotion_id en el body de POST /appointments (atómico en el backend). Se
// documenta para un eventual panel de aplicación manual.
export async function applyPromotion(
  input: unknown,
): Promise<MutationResult<ApiSingle<PromotionUsageDetail>>> {
  const parsed = applyPromotionSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<PromotionUsageDetail>>(
      ENDPOINTS.PROMOTION_USAGES.APPLY,
      parsed.data,
    );
    revalidateTag(USAGES_TAG, "max"); // el reporte + usage-summary
    revalidateTag(PROMOTIONS_TAG, "max"); // total_uses de la promo
    return { ok: true, data };
  } catch (e) {
    // 400 PROMOTION_NOT_ACTIVE/EXPIRED/PRODUCT_NOT_COVERED/LIMIT_REACHED/PERSON_LIMIT_REACHED;
    // 409 PROMOTION_ALREADY_APPLIED (no-stacking); 404 PROMOTION/PRODUCT/PERSON_NOT_FOUND.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **`eligibleFor`/`validatePromotion`/`computePrice` validan con `.parse` (no `.safeParse`)** porque el caller (wizard de citas / panel de verificación) ya pre-valida el form; un request inválido es un bug, no input de usuario suelto. Lecturas on-the-fly → `cache: "no-store"` (la elegibilidad cambia con cada uso nuevo; el caching está diferido). Gated `PROMOTION_VALIDATE` (los 3) — coincide con la spec §7.

> **`applyPromotion` no se cablea a un botón en marketing** (MVP): la aplicación ocurre **dentro** del flujo de agendar cita (scheduling F4) o del bot. Documentado en el wire F4 abajo. Si el negocio pide aplicar una promo "suelta" (sin cita), embeber un mini-form que llame `applyPromotion` es un TODO diferido.

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/marketing/campanas/page.tsx` (LISTA)

Análoga a `catalog/verticales/page.tsx`. El create/edit vive en un **drawer**. **Deep-link**: `?status=` traducido a `FilterCondition` sobre la columna **real** `status`. El `defaultSort` del prefetch debe coincidir con el del client (si se ordena por `start_date`, pasar el MISMO `defaultSort` al `useTableQuery`).

```tsx
import { listCampaigns } from "@/actions/campaign.actions";
import { listActiveVerticals } from "@/actions/vertical.actions"; // catalog (dropdown del drawer)
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { CampaignsClient } from "./_components/CampaignsClient";

export const metadata = { title: "Campañas" };

interface PageProps {
  searchParams: Promise<{ status?: string }>;
}

export default async function CampaignsPage({ searchParams }: PageProps) {
  await requirePermission("CAMPAIGNS_READ");
  const sp = await searchParams;

  // Deep-link → FilterCondition sobre la columna REAL `status`.
  const conditions: FilterCondition[] = [];
  if (sp.status) conditions.push({ field: "status", operator: "eq", value: sp.status });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  const [initialData, verticals] = await Promise.all([
    listCampaigns({
      pagination: { skip: 0, limit: 10 },
      // defaultSort = created_on (columna real). DEBE coincidir con el client.
      sorting: { sort_by: "created_on", sort_order: "desc" },
      filters,
    }),
    listActiveVerticals(),
  ]);

  return <CampaignsClient initialData={initialData} verticals={verticals} />;
}
```

> **Por qué el filtro va sobre `status` y NO sobre `target_vertical_name`/`promotions_count`**: `status` (y `target_vertical_id`, `start_date`, `end_date`, `code`, `name`, `active`) son columnas **reales** del `campaign` (en `ALLOWED_FIELDS`, spec §5) → server-filterable/sortable sin riesgo. `target_vertical_name`/`promotions_count` son **denormalizados** (sólo render) → NO sortables (lección `cd10c78`). La tabla no los marca `isSortable`; sólo `created_on`/`start_date`/`code`/`name`/`status` (reales).

### `app/(main)/marketing/promociones/page.tsx` (LISTA)

```tsx
import { listPromotions } from "@/actions/promotion.actions";
import { listActiveProducts } from "@/actions/product.actions"; // catalog (editor M:N del drawer)
import { requirePermission } from "@/lib/auth/session";

import { PromotionsClient } from "./_components/PromotionsClient";

export const metadata = { title: "Promociones" };

export default async function PromotionsPage() {
  await requirePermission("PROMOTIONS_READ");
  const [initialData, products] = await Promise.all([
    listPromotions({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "created_on", sort_order: "desc" }, // columna real; coincide con el client
      filters: null,
    }),
    listActiveProducts(),
  ]);
  return <PromotionsClient initialData={initialData} products={products} />;
}
```

> **`listActiveProducts` se prefetcha para el editor M:N** del `PromotionDrawer` (tab Productos). El `listActivePromotions` para el editor M:N de campañas se carga en cliente desde el `CampaignDrawer` (no en el RSC de campañas, para no acoplar). El `discount_type` filtro/sort va sobre la columna real `discount_type` (en `ALLOWED_FIELDS`); `products_count`/`campaigns_count` NO son sortables.

### `app/(main)/marketing/usos/page.tsx` (REPORTE read-only)

```tsx
import { listPromotionUsages } from "@/actions/promotion-usage.actions";
import { listActivePromotions } from "@/actions/promotion.actions"; // dropdown de filtro
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { PromotionUsagesClient } from "./_components/PromotionUsagesClient";

export const metadata = { title: "Usos de promoción" };

interface PageProps {
  searchParams: Promise<{ promotion_id?: string; person_id?: string }>;
}

export default async function PromotionUsagesPage({ searchParams }: PageProps) {
  await requirePermission("PROMOTION_USAGES_READ");
  const sp = await searchParams;

  // Deep-link → FilterCondition sobre columnas REALES (promotion_id/person_id están en
  // ALLOWED_FIELDS del promotion_usage; los *_name NO).
  const conditions: FilterCondition[] = [];
  if (sp.promotion_id) conditions.push({ field: "promotion_id", operator: "eq", value: sp.promotion_id });
  if (sp.person_id) conditions.push({ field: "person_id", operator: "eq", value: sp.person_id });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  const [initialData, promotions] = await Promise.all([
    listPromotionUsages({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "created_on", sort_order: "desc" }, // columna real (= applied_at)
      filters,
    }),
    listActivePromotions(),
  ]);

  return <PromotionUsagesClient initialData={initialData} promotions={promotions} />;
}
```

> **`usos` es read-only y NO redirige a `notFound`**: si no hay usos, el `DataTable` muestra estado vacío "Aún no hay usos de promoción registrados." El filtro por persona usa `person_id` (real); la **búsqueda** por nombre de persona/promo/producto es **client-side** (denormalizados, no whitelistados). El `defaultSort = created_on` (real) coincide con el prefetch.

## Client components — esqueletos

> **No reproduzco los archivos completos** — siguen el patrón exacto de `catalog/.../VerticalsClient`/`ProductDrawer` (lista + drawer + form discriminado por watch) + el editor M:N de `bots/.../BotToolsAssignment` (`SearchableOptionList` bulk-replace). Documento las **diferencias específicas** a marketing. La UI detallada (mockups, copy) vive en [`ui.md`](./ui.md).

### `CampaignsClient.tsx`

Sigue el patrón de `VerticalsClient.tsx` (lista + drawer de creación/edición + RowActions). Diferencias:

- Recibe `verticals: VerticalOption[]` (dropdown `target_vertical_id` del drawer + chip de filtro opcional).
- `useTableQuery`: `queryKey: "marketing:campaigns"`, `fetcher: listCampaigns`, `searchFields: ["code", "name"]` (reales → server-side OK; o client-side si se prefiere), `defaultSort: { field: "created_on", order: "desc" }` (**columna real**, coincide con el prefetch RSC), `initialData`.
- State `statusFilter` sincronizado con URL (`nuqs`) + chip "Filtrado por: {estado}" con ✕. El `Dropdown` de estado usa `CAMPAIGN_STATUS_META[s].label`.
- Columns: `actions`, `code` (monoespaciado), `name`, `status` (badge color vía `CAMPAIGN_STATUS_META[status]` — **color fijo del front**, no del catálogo), `target_vertical_name` ("Transversal" si null), `promotions_count` ("{n} promos"), `start_date`/`end_date` (fechas, `formatDate` de date-puro **local**), `active`. **Sólo `code`/`name`/`status`/`created_on`/`start_date` son `isSortable`** (reales); `target_vertical_name`/`promotions_count` NO (cd10c78).
- **RowActions**: Ver/Editar (gated `CAMPAIGNS_UPDATE`) → abre `CampaignDrawer`; Eliminar (gated `CAMPAIGNS_DELETE`, danger). El detalle se opera en el mismo drawer (carga `getCampaign(id)` al abrir).
- Botón "Nueva campaña" gated `CAMPAIGNS_CREATE` → abre `CampaignDrawer` vacío.

### `CampaignDrawer.tsx`

Drawer create/edit/detalle con **tabs** (`TabId = "datos" | "promociones" | "auditoria"`). `useForm` con `campaignCreateSchema`/`campaignUpdateSchema`. Molde `VerticalDrawer` + el editor M:N. Tabs:

- **Datos**: `code` (`Input`, **solo create**, disabled en edit — inmutable), `name`, `description` (`Textarea`), `start_date`/`end_date` (`Input type="date"`), `target_vertical_id` (`Dropdown` de `verticals` + opción "Transversal" = null), `active` (`Switch`, solo edit). Badge de status arriba (`CAMPAIGN_STATUS_META`) + control **"Cambiar estado"**: botones shortcut sólo para los destinos de `CAMPAIGN_TRANSITIONS[status]` (draft→Activar; active→Pausar/Finalizar; paused→Reanudar/Finalizar; ended→sin acciones, hint "Campaña finalizada"). Cada botón llama `transitionCampaign(id, { to_status })`. Tras éxito, re-`load()` del detalle (tag invalidado).
- **Promociones** (editor M:N, **gated `CAMPAIGNS_UPDATE`**): molde `BotToolsAssignment` + `SearchableOptionList`. Carga `getCampaignPromotions(id)` → preselecciona; `listActivePromotions()` (en cliente) → opciones (cada una muestra `name` + `code` + el descuento vía `formatDiscount`). Guardar → `setCampaignPromotions(id, { promotion_ids })` (bulk-replace). Estado vacío del catálogo: "No hay promociones activas. Crea promociones en la sección Promociones." (link a `/marketing/promociones`).
- **Auditoría**: created/updated by/on (patrón shipped, `created_by_user.full_name ?? "Sistema"`).

> **El tab Promociones del create**: el M:N requiere que la campaña ya exista (necesita `id`). En el create, ocultar/deshabilitar el tab Promociones con hint "Guarda la campaña primero para asignar promociones." (mismo criterio que `BotToolsAssignment`, que requiere el `configurationId`). Tras crear, recargar el drawer en modo edit con el `id` devuelto.

### `PromotionsClient.tsx`

Sigue patrón `VerticalsClient`. Diferencias:

- Recibe `products: ProductOption[]` (editor M:N del drawer).
- `useTableQuery`: `queryKey: "marketing:promotions"`, `fetcher: listPromotions`, `searchFields: ["code", "name"]`, `defaultSort: { field: "created_on", order: "desc" }` (real), `initialData`.
- Columns: `actions`, `code`, `name`, `discount` (texto vía `formatDiscount({ discount_type, discount_value, currency })` → "10%" o "S/ 25.00"), `applies_to_all_products` (badge "Todos los productos" / "{n} productos" según `products_count`), `campaigns_count` ("{n} campañas"), `start_date`/`end_date`, `max_uses_total`/`max_uses_per_person` ("Ilimitado" si null), `active`. **Sólo `code`/`name`/`discount_type`/`currency`/`created_on`/`start_date`/`end_date`/`active` son `isSortable`** (reales); `products_count`/`campaigns_count` NO.
- **RowActions**: Editar (gated `PROMOTIONS_UPDATE`); Eliminar (gated `PROMOTIONS_DELETE`, danger).
- Botón "Nueva promoción" gated `PROMOTIONS_CREATE`.

### `PromotionDrawer.tsx` — el form discriminado

Molde **`ProductDrawer`** (form con render condicional por `form.watch`). `useForm` con `promotionCreateSchema`/`promotionUpdateSchema`. **6 tabs** (`TabId = "datos" | "descuento" | "vigencia" | "productos" | "campanas" | "auditoria"`):

- **Datos**: `code` (solo create, disabled en edit — inmutable), `name`, `description`.
- **Descuento** (el corazón discriminado): `discount_type` (`Dropdown`, **solo create**, disabled en edit — inmutable; en edit muestra el valor con `DISCOUNT_TYPE_META[type].label`). `form.watch("discount_type")` controla el render condicional:
  - `percentage` → `Input` numérico (`inputMode="decimal"`, 0–100) para `discount_value`; **sin** campo de moneda.
  - `fixed_amount` → `Input` `inputMode="decimal"` (decimal-string ≤2 decimales) para `discount_value` **+** `Dropdown` `currency` (de `SUPPORTED_CURRENCIES`).
  - En edit, inyectar `_discount_type` (el de la fila) al `form` para que el `superRefine` del update valide el rango; el action lo descarta antes del PUT.
- **Vigencia y límites**: `start_date`/`end_date` (`Input type="date"`), `max_uses_total`/`max_uses_per_person` (`Input` numérico, vacío = ilimitado → enviar `null`).
- **Productos** (editor M:N, gated `PROMOTIONS_UPDATE`): `applies_to_all_products` (`Switch`). Si **true** → ocultar el picker (la promo cubre todo el catálogo; el M:N se ignora). Si **false** → `SearchableOptionList` de `products` (molde `BotToolsAssignment`): carga `getPromotionProducts(id)` → preselecciona; guardar → `setPromotionProducts(id, { product_ids })`. Mismo gate de "guarda primero" en el create.
- **Campañas** (read-only): chips de las campañas que incluyen la promo (`promotion.campaigns`, `CampaignOption[]`) con su badge de status. **No editable desde aquí** (el M:N se gestiona desde el lado Campaña). Hint "Las campañas que incluyen esta promoción se gestionan desde Campañas."
- **Auditoría**: created/updated by/on + un mini-panel de métricas (`getPromotionUsageSummary(id)`: total de usos + montos descontados, gated `PROMOTION_USAGES_READ`).

> **Por qué `discount_type`/`code` disabled en edit**: ambos son **inmutables post-create** (spec §3.2/§4.2). El backend rechaza cambiarlos vía update; el front los muestra disabled (no los manda en el body — el `promotionUpdateSchema` ni siquiera los incluye, salvo `_discount_type` efímero que el action descarta). Cambiar el tipo de descuento implicaría re-crear la promo.

> **`applies_to_all_products=true` oculta el picker** (no lo deshabilita vacío): cuando está en true, el M:N de productos se **ignora** en el backend (`covers_product` devuelve true para todo). El picker se oculta para no confundir; al pasar a false, mostrar el `SearchableOptionList` (puede estar vacío → la promo no cubriría ningún producto hasta que se asignen). El `set` del M:N persiste aunque `applies_to_all_products=true` (se ignora), pero la UX limpia es ocultar.

### `PromotionUsagesClient.tsx`

**Read-only** (sin drawer ni mutaciones). Sigue el patrón de tabla de `VerticalsClient` pero sin RowActions de edición. Diferencias:

- Recibe `promotions: PromotionOption[]` (dropdown de filtro por promo).
- `useTableQuery`: `queryKey: "marketing:promotion-usages"`, `fetcher: listPromotionUsages`, `searchFields: ["promotion_name", "person_name", "product_name"]` (**client-side**: denormalizados), `defaultSort: { field: "created_on", order: "desc" }` (real), `initialData`.
- State `promotionFilter`/`personFilter` sincronizados con URL (`nuqs`) + chips. El `Dropdown` de promo lista `promotions`; el filtro por persona es un `Input` (o un picker de persona) → `person_id` deep-link.
- Columns: `created_on` (fecha+hora, `formatDate`, **client-only** render), `promotion_name` (Promoción), `person_name` (Persona), `product_name` (Producto), `original_amount`/`discount_amount`/`final_amount` (formateados con `currency` vía `formatCurrency`), `campaign_name` ("—" si null), `appointment_id` (badge "Con cita" / "Sin cita"), `notes`. **Ninguna columna denormalizada es `isSortable`** (cd10c78); sólo `created_on` (real). Los montos se muestran con prefijo de moneda; **no** convertir el Decimal-string a `Number` para formatear (perdería precisión — ya viene con 2 decimales).
- **Sin** botón "Nuevo" (la aplicación no se crea desde aquí). Estado vacío: "Aún no hay usos de promoción registrados."

## Wire F4 — `apply_promotion_id` en el wizard de citas (scheduling)

> **Esta sección documenta el cambio que F4 introduce en el FRONTEND de scheduling** (no en marketing). El detalle del backend está en [`backend.md`](./backend.md#f4-integración) y [`../scheduling/frontend.md`](../scheduling/frontend.md).

- `types/scheduling.types.ts` → `AppointmentCreatePayload` gana `apply_promotion_id?: string | null` (opcional). El backend de scheduling, al recibirlo, llama a `marketing.promotion_usage.apply` en la **misma sesión** (atómico): si la promo es inválida (expirada/límite/no cubre), la excepción de dominio hace **rollback global** → la cita NO se crea. El front muestra el `detail` del error de marketing en el `MessageBar` del wizard sin cerrar.
- `lib/schemas/appointment.schema.ts` → `bookingWizardSchema` gana `apply_promotion_id: z.string().nullable().optional()`.
- **Selector de promo elegible en el wizard de booking** (paso Confirmar, **nice-to-have**): tras elegir paciente+producto, llamar `eligibleFor({ product_id, person_id })` → mostrar las promos `is_eligible=true` como opciones (con su descuento calculado vía `formatDiscount` + `final_amount`); las no elegibles, atenuadas con su `reason`. Seleccionar una setea `apply_promotion_id`. **Mínimo** (MVP): el campo opcional en el schema + el body; el selector UI completo puede diferirse. Gated `PROMOTION_VALIDATE`/`PROMOTION_APPLY` (visible sólo si el actor los tiene).
- **Reschedule no re-aplica la promo** (spec §9 F4): la promo quedó en la cita vieja; la cita nueva NO la hereda. Documentar en la UI de reschedule ("La promoción de la cita original no se traslada; vuelve a aplicarla si corresponde.").

> **Por qué el selector es nice-to-have y el campo es obligatorio**: el contrato (`apply_promotion_id` opcional en `AppointmentCreate`) es lo que cierra el loop lead→bot→cita→cliente con descuento. El **bot** ya lo usa (F4 extiende `book_appointment` con `apply_promotion_id` + la tool `list_eligible_promotions`). La UI del wizard puede empezar sin el selector (el asesor agenda sin promo) y agregarlo cuando se priorice — pero el campo y el schema deben existir desde F4 para no romper el contrato.

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| `PUT` para updates y M:N bulk-replace (no `PATCH`); transición/validación/aplicación = `POST` sub-recursos | Alineación a catalog/clinic/staff/crm/scheduling shipped. `/campaigns/{id}/promotions` y `/promotions/{id}/products` son `PUT` (reemplazan el set). `/transition`, `/eligible-for`, `/validate`, `/compute-price`, `/promotion-usages` son `POST`. |
| `/active` para dropdowns (lista cruda) | Misma convención shipped; no se lee `.data`. Reconciliación: `/campaigns/options` viejo → `/campaigns/active`. |
| `revalidateTag(TAG, "max")` (2º arg) | Next 16 exige el 2º argumento; omitirlo es error. |
| **Decimal → `string` en el wire** (`discount_value` fijo, `*_amount`) | Lección `base_price` de catalog. `Input inputMode="decimal"`, no `type=number`. El `percentage` se edita como `number` y se serializa a string. No convertir a `Number` para formatear (precisión). |
| **Descuento discriminado vía base+`superRefine`, NO `z.discriminatedUnion`** | El `update` usa `.partial()` y omite `discount_type` (inmutable); `discriminatedUnion` exige el discriminante presente. El base+refine (molde `refineWonRequiresFinal` de crm) reusa la lógica en create+update. `_discount_type` efímero inyectado en edit, descartado por el action. |
| `Campaign.status` = **ENUM fijo** (badge color del front), NO catálogo configurable ni matriz | Spec §0.2: 4 estados inherentes al ciclo de vida; la clínica no los reconfigura (diverge de crm/scheduling). El color vive en `CAMPAIGN_STATUS_META` (token Fluent), no en BD. La transición usa `CAMPAIGN_TRANSITIONS` (matriz §2 hardcodeada) para gatear los shortcuts. |
| `code`/`discount_type` **disabled en edit** (inmutables) | Spec §3.2/§4.2: el backend rechaza cambiarlos vía update; el `*UpdateSchema` no los incluye. |
| Editor M:N = **bulk-replace** (PUT `{promotion_ids}`/`{product_ids}`) con `SearchableOptionList` | Molde `BotToolsAssignment`/`StatusMatrixEditor` de bots/crm. No es add/remove incremental; el front manda el array completo. El GET de asignados devuelve `SingleResponse[list[Option]]` → leer `.data`. Requiere `id` (gate "guarda primero" en el create). |
| Detalle de campaña/promoción = **drawer** (no página) | Pocos sub-recursos; se opera in-context (mismo criterio que el detalle de cita en scheduling). No hay tag por-id (el drawer refetcha al abrir). |
| `usos` = **read-only** (sin drawer/mutaciones) | La aplicación de promo ocurre en scheduling F4 / bot, no en una UI de marketing. La página es un reporte. `applyPromotion` se documenta pero no se cablea a un botón (MVP). |
| **`defaultSort`/`isSortable`/`searchFields` SOLO sobre columnas reales** | Lección `cd10c78`: ordenar por `target_vertical_name`/`promotions_count`/`products_count`/`campaigns_count`/`*_name` de usos da 400. `defaultSort = created_on` (real); el client y el prefetch deben coincidir. Filtros = `FilterCondition` sobre `status`/`promotion_id`/`person_id` (reales). |
| Búsqueda por nombre de promo/persona/producto en usos = **client-side** | Los `*_name` son denormalizados (no whitelistados). `useTableQuery.searchFields` busca sobre la página visible. |
| `eligibleFor`/`validate`/`computePrice` NO revalidan tags (lecturas on-the-fly) | No persisten; `cache: "no-store"`. La elegibilidad cambia con cada uso; caching diferido (MVP). Validan con `.parse` (caller pre-valida). |
| `applyPromotion` revalida `marketing:promotion-usages` + `marketing:promotions` | Crea PromotionUsage → afecta el reporte + el `total_uses`/`usage-summary` de la promo. Lo dispara scheduling F4 (cross-módulo). |
| `setCampaignPromotions` revalida ambos tags (`campaigns` + `promotions`) | Cambia `promotions_count` de la campaña Y `campaigns_count` de las promos afectadas. |
| Fechas-puro (`start_date`/`end_date`) se parsean como **local** | `new Date(\`${d}T00:00:00\`)`, nunca como UTC (desfase de medianoche). La vigencia "¿activa hoy?" la decide el backend; el front la pinta como hint. |
| Render de `created_on`/agrupación "hoy" del reporte = client-only | `new Date()` que afecta render = client-only (SSR en UTC desfasa el día en Lima `-05:00`). |
| `apply_promotion_id` opcional en el wizard de citas (F4) | Cierra el loop lead→bot→cita→cliente con descuento. El campo + schema son obligatorios desde F4; el selector UI de promo elegible es nice-to-have. |
| Color de badge de status = token Fluent fijo (no `brandPalette.accent`) | `CampaignStatus` es ENUM cerrado; el color es del front. `brandPalette` no tiene `accent` (lección operativa transversal). |
| Sin bulk actions, sin duplicar, sin import CSV, sin panel de aplicación manual | Postergados al MVP+1 (igual que catalog/clinic/staff/crm/scheduling). |

## Checklist de implementación (mapeado a fases F0–F4)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md#checklist-de-implementación) y la spec §12. Cada checkbox es lado frontend.

### F0 — Prep (andamiaje compartido)

- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `MARKETING` (`CAMPAIGNS` con nested `PROMOTIONS_LIST/UPDATE` + `TRANSITION`, `PROMOTIONS` con nested `PRODUCTS_LIST/UPDATE` + `USAGE_SUMMARY` + `VALIDATE`, `PROMOTION_USAGES` con `LIST`/`APPLY`/`ELIGIBLE_FOR`/`COMPUTE_PRICE`). Verbos `PUT`, rutas `/active`, sub-recursos `POST`.
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `marketing` ("Marketing" → Campañas `CAMPAIGNS_READ`, Promociones `PROMOTIONS_READ`, Usos de promoción `PROMOTION_USAGES_READ`; grupo gated `MENU-MARKETING`).
- [ ] Registrar íconos `MegaphoneRegular`/`TicketDiamondRegular`/`ReceiptRegular` en el `iconMap` del `Sidebar.tsx` (**verificar que existan** en `@fluentui/react-icons` v9 — lección catalog; fallbacks `TagRegular`/`DocumentRegular`).
- [ ] Crear `src/types/marketing.types.ts` (TODAS las interfaces: `CampaignOption/Item/Detail` + payloads/transition/promotions-replace; `PromotionOption/Item/Detail` + payloads/products-replace; `PromotionUsageItem/Detail` (3 cols audit) + `ApplyPromotionPayload`; `PromotionEligibility(Request)`/`ComputePrice(Request/Response)`/`PromotionUsageSummary`; enums `CampaignStatus`/`DiscountType` como union + const array; reusa `UserAuditInfo`/`VerticalOption`/`ProductOption`). **Decimales = `string`.**
- [ ] Crear `src/lib/constants/marketing.ts` (`CAMPAIGN_STATUS_META`, `CAMPAIGN_TRANSITIONS`, `DISCOUNT_TYPE_META`, `SUPPORTED_CURRENCIES`, `formatDiscount`). Crear/reusar `formatCurrency` en `lib/utils/`.
- [ ] Crear los skeletons inertes de las 3 páginas (placeholders) — registrar las rutas sin lógica. (Backend NO registra el módulo en F0 — sólo perms+nav+types+endpoints; las rutas marketing dan 404 hasta F1.)
- [ ] **Permisos test (F0)**: login admin → 12 perms de marketing en el JWT; el grupo "Marketing" aparece con sus 3 items; sin `MENU-MARKETING` el grupo no aparece. Las rutas `/marketing/*` (placeholders) renderizan vacías; las del backend dan 404.

### F1 — Campaign (sin el M:N de promociones todavía)

- [ ] Crear `src/lib/schemas/campaign.schema.ts` (`campaignCreate/Update` code slug inmutable + `refineCampaignDates`; `campaignTransitionSchema`; `campaignPromotionsReplaceSchema` — este último se cablea en F2).
- [ ] Crear `src/actions/campaign.actions.ts` (list/active/get/create/update/delete + transition; tag `marketing:campaigns`). `getCampaignPromotions`/`setCampaignPromotions` se cablean en F2 (la tabla `promotion` aún no existe; `promotions_count`=0, `CampaignDetail.promotions`=[]).
- [ ] Crear `src/app/(main)/marketing/campanas/page.tsx` (`metadata.title = "Campañas"`, prefetch `defaultSort = created_on`, deep-link `?status=` → `FilterCondition` columna real) + `_components/CampaignsClient.tsx` (denormalizados NO sortables, filtro status chip) + `CampaignDrawer.tsx` (tabs Datos/Auditoría; el tab Promociones llega en F2; control "Cambiar estado" con shortcuts de `CAMPAIGN_TRANSITIONS`).
- [ ] **Smoke test (F1)**: `/marketing/campanas` → "Nueva campaña" (code `verano_2026` + nombre + fechas + vertical o transversal) → aparece con badge "Borrador". Editar nombre/fechas. Cambiar estado Borrador→Activar→Pausar→Reanudar→Finalizar; en "Finalizada" no hay acciones. Eliminar una.
- [ ] **Validación test (F1)**: `code` con mayúsculas/espacios → error inline Zod en español; `end_date < start_date` → error inline; code duplicado → `CAMPAIGN_CODE_TAKEN` (409) `MessageBar`; vertical inexistente → `TARGET_VERTICAL_NOT_FOUND` (400); transición no permitida (forzada) → `CAMPAIGN_TRANSITION_NOT_ALLOWED` (400).
- [ ] **Permisos test (F1)**: con `CAMPAIGNS_READ` sin `_CREATE`/`_UPDATE`/`_DELETE`, la tabla se ve pero sin "Nueva campaña"/Editar/Eliminar ni control de estado.

### F2 — Promotion + ambos M:N

- [ ] Crear `src/lib/schemas/promotion.schema.ts` (`promotionCreate/Update` DISCRIMINADO vía base+`refineDiscount`; `_discount_type` efímero en update; `promotionProductsReplaceSchema`).
- [ ] Crear `src/actions/promotion.actions.ts` (CRUD + active + `getPromotionProducts`/`setPromotionProducts` + `getPromotionUsageSummary`; tag `marketing:promotions`). **Cablear** `getCampaignPromotions`/`setCampaignPromotions` en `campaign.actions` (la tabla `promotion` ya existe).
- [ ] Crear `src/app/(main)/marketing/promociones/page.tsx` (`metadata.title = "Promociones"`, prefetch `defaultSort = created_on`, prefetch `listActiveProducts` para el M:N) + `_components/PromotionsClient.tsx` (columna `discount` vía `formatDiscount`; denormalizados NO sortables) + `PromotionDrawer.tsx` (6 tabs; tab Descuento discriminado por `form.watch("discount_type")`; tab Productos `applies_to_all` toggle + `SearchableOptionList`; tab Campañas read-only).
- [ ] Cablear el **tab Promociones** del `CampaignDrawer` (editor M:N `getCampaignPromotions`/`setCampaignPromotions` + `listActivePromotions` opciones, molde `BotToolsAssignment`). Activar `promotions_count` en la lista de campañas.
- [ ] **Smoke test (F2)**: `/marketing/promociones` → "Nueva promoción" tipo `percentage` (valor 10) → badge "10%". Otra `fixed_amount` (valor 25.00 + PEN) → "S/ 25.00". Editar: el `discount_type` está disabled; cambiar `discount_value` valida el rango del tipo existente. Tab Productos: con `applies_to_all=false` asignar 2 productos (multiselect bulk) → recargar persiste; con `applies_to_all=true` el picker se oculta. Desde una campaña, tab Promociones → asignar las 2 promos → recargar persiste; el `promotions_count` de la campaña sube; el `campaigns_count` de las promos sube.
- [ ] **Validación discriminada test (F2)**: `percentage` con valor 0 o >100 → error inline; `fixed_amount` con valor 0 o sin moneda → error inline; `code` duplicado → `PROMOTION_CODE_TAKEN` (409); rango inválido forzado al backend → `PROMOTION_INVALID_DISCOUNT` (400). `product_id` inexistente en el set → `PRODUCT_NOT_FOUND` (400); `promotion_id` inexistente en el set de campaña → `PROMOTION_NOT_FOUND` (400).
- [ ] **Permisos test (F2)**: con `PROMOTIONS_READ` sin `_UPDATE`, el editor M:N de productos está disabled y no aparece "Nueva promoción"/Editar/Eliminar.

### F3 — PromotionUsage + validación/aplicación + reporte

- [ ] Crear `src/lib/schemas/promotion-usage.schema.ts` (`applyPromotionSchema`, `eligibilityRequestSchema`, `computePriceRequestSchema`).
- [ ] Crear `src/actions/promotion-usage.actions.ts` (`listPromotionUsages`; `eligibleFor`/`validatePromotion`/`computePrice` lecturas `cache:"no-store"` sin tags; `applyPromotion` POST revalida `marketing:promotion-usages`+`marketing:promotions`).
- [ ] Crear `src/app/(main)/marketing/usos/page.tsx` (`metadata.title = "Usos de promoción"`, read-only, `defaultSort = created_on`, deep-link `?promotion_id=&person_id=` → `FilterCondition` columnas reales) + `_components/PromotionUsagesClient.tsx` (montos formateados con moneda; búsqueda client-side; sin botón "Nuevo").
- [ ] Cablear el mini-panel de métricas en `PromotionDrawer` (tab Auditoría / Métricas → `getPromotionUsageSummary`, gated `PROMOTION_USAGES_READ`).
- [ ] **Smoke test (F3)**: tras aplicar una promo (vía scheduling F4 o un apply manual de prueba), `/marketing/usos` lista el uso con promo/persona/producto/montos formateados (`original`/`discount`/`final` + moneda) + badge "Con cita"/"Sin cita". Filtrar por promo (deep-link) + chip; ✕ limpia. El `usage-summary` de la promo muestra total de usos + montos.
- [ ] **Validación/aplicación test (F3)**: `eligibleFor(product, person)` lista las promos elegibles (con `reason` en las no elegibles: expirada/límite/no cubre); `computePrice` con/sin promo devuelve los montos correctos. Aplicar dos veces a la misma cita → `PROMOTION_ALREADY_APPLIED` (409, no-stacking); aplicar una promo con `max_uses_total` agotado → `PROMOTION_LIMIT_REACHED`; una promo que no cubre el producto → `PROMOTION_PRODUCT_NOT_COVERED`. Todos en español en el `MessageBar`.
- [ ] **Decimal test (F3)**: un descuento `percentage` 10% sobre `base_price` 99.99 → `discount` y `final` con 2 decimales (ROUND_HALF_UP, cap a base_price); un `fixed_amount` mayor que el `base_price` → descuento cap a `base_price` (final 0). Los montos se muestran como string sin perder precisión.
- [ ] **Permisos test (F3)**: sin `PROMOTION_USAGES_READ` la página de usos redirige (RSC) y el grupo no muestra el item; sin `PROMOTION_VALIDATE` el `eligibleFor`/`validate`/`compute-price` fallan 403; sin `PROMOTION_APPLY` el `applyPromotion` falla 403.

### F4 — Integración (scheduling + bot)

> **Toca scheduling+bots** (aprobado). El frontend de marketing **no** crea pantallas nuevas en F4 — el cambio es el wire `apply_promotion_id` en el wizard de citas de scheduling (ver [Wire F4](#wire-f4--apply_promotion_id-en-el-wizard-de-citas-scheduling)).

- [ ] En `types/scheduling.types.ts`: `AppointmentCreatePayload` += `apply_promotion_id?: string | null`. En `lib/schemas/appointment.schema.ts`: `bookingWizardSchema` += `apply_promotion_id` opcional.
- [ ] (Nice-to-have) Selector de promo elegible en el paso Confirmar del `BookingWizardDrawer`: tras paciente+producto, `eligibleFor({ product_id, person_id })` → opciones con descuento calculado (`formatDiscount` + `final_amount`); seleccionar setea `apply_promotion_id`. Gated `PROMOTION_VALIDATE`/`PROMOTION_APPLY`.
- [ ] **Smoke test (F4)**: agendar una cita con `apply_promotion_id` de una promo válida → la cita se crea **y** aparece un `PromotionUsage` en `/marketing/usos` con `appointment_id` (badge "Con cita") y `created_by` = "Sistema" si fue vía bot. Agendar con una promo inválida (expirada/límite) → la cita **NO** se crea (rollback atómico) y el wizard muestra el `detail` de marketing en `MessageBar`.
- [ ] **No-stacking test (F4)**: intentar aplicar una 2ª promo a una cita que ya tiene una → `PROMOTION_ALREADY_APPLIED` (409). Reagendar la cita → la promo NO se traslada (la nueva cita queda sin promo; hint en la UI de reschedule).
- [ ] **Bot/cross-módulo test (F4)**: una cita creada por el bot con `apply_promotion_id` (tool `book_appointment` extendida) genera su `PromotionUsage` con origen Sistema; la tool `list_eligible_promotions` (read-only) lista las promos elegibles para el lead. Verificable en `/marketing/usos`.

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog**. Para `marketing` no hay deuda de traducción del template — todos los strings nuevos nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Campañas", "Promociones", "Usos de promoción").
- [ ] Todos los `label` de `NAV_ITEMS.marketing` en español ("Marketing", "Campañas", "Promociones", "Usos de promoción").
- [ ] Empty states, placeholders, badges (estado de campaña Borrador/Activa/Pausada/Finalizada; tipo de descuento Porcentaje/Monto fijo; "Con cita"/"Sin cita"; "Transversal"; "Ilimitado"; "Todos los productos"), copy del control de estado ("Activar", "Pausar", "Reanudar", "Finalizar") y `MessageBar` en español (ver tabla de copy en [`ui.md`](./ui.md#texto-ux-writing)).
- [ ] Mensajes de error de dominio que vienen del backend ya en español (`CAMPAIGN_CODE_TAKEN`, `CAMPAIGN_INVALID_DATES`, `TARGET_VERTICAL_NOT_FOUND`, `CAMPAIGN_TRANSITION_NOT_ALLOWED`, `PROMOTION_CODE_TAKEN`, `PROMOTION_INVALID_DISCOUNT`, `PROMOTION_INVALID_DATES`, `PROMOTION_NOT_FOUND`, `PRODUCT_NOT_FOUND`, `PERSON_NOT_FOUND`, `PROMOTION_PRODUCT_NOT_COVERED`, `PROMOTION_ALREADY_APPLIED`, `PROMOTION_NOT_ACTIVE`, `PROMOTION_EXPIRED`, `PROMOTION_LIMIT_REACHED`, `PROMOTION_PERSON_LIMIT_REACHED`) — los `detail` se devuelven en español para mostrarse directo; el `code` queda en inglés (coordinar con [`backend.md`](./backend.md#catálogo-de-error-codes)).

## TODOs deliberados (postergados al MVP+1)

- [ ] **Panel de aplicación manual de promo** (sin cita) — el MVP aplica vía scheduling F4 / bot; `applyPromotion` está implementado pero sin botón en marketing. Embeber un mini-form (promo+persona+producto) si el negocio lo pide.
- [ ] **Selector de promo elegible completo en el wizard de citas** — F4 deja el campo `apply_promotion_id` + el body; el selector UI (con `eligibleFor` + descuento calculado) es nice-to-have.
- [ ] **Tag por-recurso** (`marketing:campaign:{id}`/`marketing:promotion:{id}`) — el MVP usa el grano global por-entidad (volumen bajo). Taggear por-id si crece el catálogo.
- [ ] **Editor M:N de campañas desde el lado promoción** — hoy el tab Campañas de `PromotionDrawer` es read-only (el M:N se gestiona desde Campaña). Hacerlo bidireccional si el negocio lo pide.
- [ ] **Resolver `currency` por catálogo configurable** — el MVP acota a `SUPPORTED_CURRENCIES` (PEN/USD); el backend acepta cualquier ISO 4217.
- [ ] **Gráficos/dashboard de uso de promociones** (tendencia de redenciones, descuento total por campaña) — el MVP es tabla + `usage-summary`. Diferir.
- [ ] **Bulk actions / duplicar campaña-promoción / import CSV** — postergados (igual que catalog/clinic/staff/crm/scheduling).
- [ ] **Vista responsive** de las tablas — el MVP asume desktop.
- [ ] **i18n framework** — por ahora strings literales en español directo (mismo criterio que los 7 módulos previos).
