/**
 * Espejo de los Pydantic schemas de `marketing` (backend) — ver
 * `docs/modules/marketing/backend.md` y la spec §4.
 *
 * Convención del template: identificadores en inglés; los decimales del backend
 * (`Numeric(10,2)`) viajan como **string** en el wire (lección `base_price` de
 * catalog) → `discount_value` y todos los `*_amount` son `string`. Reusa
 * `UserAuditInfo` (audit) y `VerticalOption`/`ProductOption` (catalog).
 *
 * ⚠ Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún (el backend de
 * marketing no está montado hasta F1). Cada fase cablea su parte.
 */

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

export const DISCOUNT_TYPES: readonly DiscountType[] = ["percentage", "fixed_amount"] as const;

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
