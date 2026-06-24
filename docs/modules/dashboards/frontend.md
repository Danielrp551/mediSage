# Módulo `dashboards` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-06-24
> **Audiencia**: developer implementando `frontend/src/.../dashboard/` (el panel + los reportes) + las extensiones de `endpoints.ts`/`navigation.ts` (que reemplazan el welcome placeholder de `/dashboard`).
> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), el [`design.md`](./design.md) y el [ADR-015](../../decisions/ADR-015-dashboards-materialized-aggregation.md). Como moldes de referencia: el frontend de [`../marketing/frontend.md`](../marketing/frontend.md) (el **endpoint de métrica agregada no-paginada** `usage_summary` = `SingleResponse[X]` que se lee con `.data`, sin `useTableQuery`) y [`../calendar/frontend.md`](../calendar/frontend.md) (la **lectura live sin tag de mutación** + el patrón de `actions` que sólo lee).

> **Contrato autoritativo**: este doc respeta la [SPEC compartida](../../../C:/tmp/dashboards_spec.md) (consolidada con [`README.md`](./README.md)) — nombres de schemas, campos, endpoints, permisos, códigos de error y **fases** son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, **manda la spec** (y por encima, el código real ya mapeado). Los **tipos TS siguen el RUNTIME** descrito en [`backend.md`](./backend.md) (lección §12 scheduling: el espejo se hace contra los schemas Pydantic reales, no contra el diseño).

> **Naturaleza del módulo (no re-litigar)**: el módulo es **100% lectura/agregación** (read-only). **No muta ni una fila de negocio** → los actions de lectura llevan `tags: ['dashboards']` pero **NO hay `revalidateTag` de mutación** (no hay create/update/delete). La única "escritura" del sistema es el job de refresco del rollup, que dispara el **Cloud Scheduler con shared-secret** (NO el frontend — ver [`backend.md`](./backend.md) y [ADR-012](../../decisions/ADR-012-cloud-tasks-bot-dispatch.md)); `/dashboards/internal/refresh` **nunca** se llama desde el front.

> **Convenciones heredadas de catalog/clinic/staff/crm/conversations/bots/scheduling/marketing/calendar shipped** (presentes desde ya):
> 1. **Respuestas no-paginadas** `SingleResponse[X]` (molde `marketing.usage_summary`) → se lee `.data`. NO se usa `useTableQuery` (no es un listado paginado; no hay `QueryRequest`, ni `ALLOWED_FIELDS`, ni `between` en el request). El request es un body dedicado `DashboardFilter`.
> 2. **TZ** (lección recurrente staff/crm/scheduling): cualquier `new Date()`/now que afecte el render = **client-only**. El badge "Actualizado hace N min" (de `last_refreshed_at`) y cualquier render de fecha relativa van en componentes cliente. El eje X de la línea son **fechas-puro** (`metric_date`, sin hora) → se formatean sin TZ (no son instantes absolutos; no necesitan `timeZone` fijo). Ver la nota de clases de tiempo en los tipos.
> 3. **Numeric/Decimal serializa como STRING en el wire** (contrato cross-cutting del template) → `bot_cost_usd: string`. El front lo formatea para mostrar (no opera aritmética sobre el string sin parsear).
> 4. **Estados configurables (ADR-008)** → los colores y labels de segmentos (estados de lead / estados de cita) vienen de los **catálogos** (`/meta`: `lead_statuses[].color`, `appointment_statuses[].color`), **nunca** hardcodeados por id. El front sólo resuelve `code → {label,color}` con lo que `/meta` entrega.
> 5. **Mensajes en Firestore (ADR-011)** → "nº de mensajes" **NO existe** en este módulo; los proxies son nº de conversaciones + turnos del bot. No se inventa una métrica de mensajes.

---

## Alcance del frontend por fase (LOCKED)

El frontend de `dashboards` se construye en **dos fases** (F2 y F3); F0 es sólo andamiaje compartido (types + endpoints + nav). El backend (F1) entrega los endpoints de lectura antes de F2.

- **F0 (Prep)** — andamiaje inerte: `types/dashboards.types.ts` (espejo), bloque `DASHBOARDS` en `endpoints.ts`, re-gateo del item `home`→`/dashboard` por `DASHBOARD_VIEW` + child `reportes`→`/dashboard/reportes` por `REPORTS_EXPORT`, íconos nuevos en el `iconMap` del `Sidebar`. **NO** hay pantalla nueva todavía (la página `/dashboard` sigue mostrando el welcome placeholder hasta F2). Las rutas backend `/dashboards/*` → 404 (módulo no registrado).
- **F2 (Panel)** — frontend-only: `actions/dashboards.actions.ts` (reads), `app/(main)/dashboard/page.tsx` (RSC, reemplaza el welcome), `DashboardClient` + componentes locales (charts Fluent + KPI cards + filtros + React Query con `refetchInterval`). Auditar Lighthouse (RNF-05).
- **F3 (Reportes)** — `generateReport` (action de descarga binaria) + `app/(main)/dashboard/reportes/page.tsx` + `ReportForm`. **No** hay migración ni charts nuevos.

> **NO se construye** (diferido D1–D4, documentado como roadmap en `design.md` §14, **NO codear**): dashboard por-doctor, métricas de mensajes desde Firestore, caché distribuida (Redis), real-time estricto del día en curso + forecast/tendencias. La interfaz de tipos no necesita reescritura para admitirlos.

---

## Estructura de archivos a crear / modificar

```
frontend/src/
├── types/
│   └── dashboards.types.ts                  ← NUEVO (F0). Espejo EXACTO de los schemas de backend.md/spec §5:
│                                                DashboardFilter, FunnelStage, FunnelSummary,
│                                                TimeSeriesPoint, TimeSeries, DistributionBucket,
│                                                DistributionSummary, KpiSummary, DashboardMeta,
│                                                RefreshResult, ReportFormat, ReportRequest
│                                                (sin entidades de negocio; NO reusa nada de otros módulos)
├── lib/
│   └── constants/
│       ├── endpoints.ts                      ← EXTEND (F0) con el bloque DASHBOARDS (FUNNEL, LEADS_EVOLUTION,
│       │                                        APPOINTMENTS_DISTRIBUTION, SUMMARY, META, REPORT;
│       │                                        todos POST salvo META = GET. /internal/refresh NO va acá:
│       │                                        lo invoca Cloud Scheduler, no el front — referencia muerta)
│       └── navigation.ts                     ← MOD (F0): item `home` → gated DASHBOARD_VIEW (reemplaza
│                                                MENU-HOME); + child `reportes` → /dashboard/reportes gated
│                                                REPORTS_EXPORT. (Sidebar.tsx: registrar íconos nuevos.)
├── actions/
│   └── dashboards.actions.ts                 ← NUEVO (F2 reads; F3 report). getFunnel, getLeadsEvolution,
│                                                getAppointmentsDistribution, getSummary (POST + DashboardFilter,
│                                                tags ['dashboards'], devuelven .data), getMeta (GET, .data);
│                                                generateReport (POST /report → binario para descargar).
│                                                SIN revalidateTag (módulo read-only).
└── app/(main)/dashboard/
    ├── page.tsx                              ← MOD (F2): reemplaza el welcome placeholder. RSC:
    │                                            requirePermission("DASHBOARD_VIEW") + prefetch
    │                                            (getSummary + getFunnel + getMeta) → initialData a DashboardClient.
    │                                            Para usuarios sin DASHBOARD_VIEW: welcome mínimo (sin redirect loop).
    ├── _components/
    │   ├── DashboardClient.tsx               ← NUEVO (F2). Orquesta filtros + React Query (initialData del
    │   │                                        prefetch, staleTime≈refetchInterval≈intervalo) + layout del panel.
    │   ├── DashboardFilters.tsx              ← NUEVO. Rango (fechas) + Sede (Dropdown) + Origen (Dropdown) +
    │   │                                        badge "Actualizado hace N min" (client-only) + refrescar.
    │   ├── KpiCards.tsx                       ← NUEVO. Fila de Card+Text con los escalares de KpiSummary.
    │   ├── FunnelChart.tsx                    ← NUEVO ("use client" + dynamic ssr:false). FunnelChart nativo
    │   │                                        si la versión lo trae / ConversionFunnel bespoke (fallback).
    │   ├── LeadsLineChart.tsx                 ← NUEVO ("use client" + dynamic ssr:false). LineChart/AreaChart.
    │   ├── AppointmentsDonut.tsx              ← NUEVO ("use client" + dynamic ssr:false). DonutChart.
    │   └── BotMiniPanel.tsx                   ← NUEVO. Mini-panel chatbot (conversaciones bot, turnos, costo, tokens).
    └── reportes/                             ← NUEVO (F3)
        ├── page.tsx                          ← RSC. requirePermission("REPORTS_EXPORT") + getMeta (sedes para el filtro).
        └── _components/
            └── ReportForm.tsx                ← NUEVO. Rango + Sede + formato (PDF/Excel) + checkboxes de
                                                 secciones + "Generar y descargar" (dispara generateReport).
```

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas.

> **Por qué `home` → `/dashboard` y no una ruta nueva** (decisión spec §10 / design §10): el panel **reemplaza** el welcome placeholder que hoy vive en `/dashboard` (un `<h1>Bienvenido</h1>` gateado por `MENU-HOME`). No se crea una ruta nueva; se re-gatea el item existente y se reescribe el `page.tsx`. Los **reportes** sí son una sub-ruta nueva (`/dashboard/reportes`).

> **Sobre `loading.tsx`**: igual que clinic/scheduling/calendar shipped — **no** se crea. El panel no es una `DataTable`; el `DashboardClient` renderiza sus propios skeletons (de KPI cards y de cada chart) mientras hidrata/refetcha. Cada widget tiene su propio estado loading/empty/error (aislado — un widget que falla no rompe el panel).

> **NO se crean** (diferido, **NO codear**): vistas per-doctor, paneles de mensajes Firestore, tendencias/forecast, real-time estricto. La spec los lista como D1–D4.

---

## Tipos TS — `types/dashboards.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic) y la spec §5). Importable desde server actions y client components. **No reusa** tipos de otros módulos (el módulo no tiene entidades de negocio); los catálogos (estados/sedes/orígenes) llegan **inline** dentro de `DashboardMeta` (no se importan los `Option` de crm/scheduling/clinic — el dashboard sólo necesita `{code,name,color,display_order}` / `{id,name}`, que `/meta` ya entrega con esa forma mínima).

```ts
// ── Request: el filtro de todos los endpoints POST (NO QueryRequest) ───────────
// date_from/date_to son fechas-puro ISO ("YYYY-MM-DD"), NO instantes (el rollup es por día UTC).
// El backend valida: date_to >= date_from y rango <= 366 días (→ DASHBOARD_INVALID_DATE_RANGE, 400).
export interface DashboardFilter {
  date_from: string; // "YYYY-MM-DD"
  date_to: string; // "YYYY-MM-DD"
  branch_id?: string | null; // null/ausente = todas las sedes
  source?: string | null; // ej. "bot" | "advisor" | … (atribución de origen de cita)
  campaign_id?: string | null; // FK lógica a marketing.campaign (sin constraint; ADR-009)
}

// ── Embudo (6 etapas) — /dashboards/funnel ────────────────────────────────────
// Una etapa del embudo. rate_from_prev = conteo_esta / conteo_anterior (null en la 1ª etapa).
// color = el color del catálogo (cuando la etapa mapea a un estado) o null (etapas escalares).
export interface FunnelStage {
  key: string; // "conversations" | "leads" | "contacted" | "appointments" | "confirmed" | "customers"
  label: string; // etiqueta ES ya resuelta por el backend ("Conversaciones", "Leads", …)
  count: number;
  rate_from_prev: number | null; // tasa etapa-a-etapa (0..1); null en la 1ª etapa
  color: string | null; // color del catálogo o null
}

export interface FunnelSummary {
  stages: FunnelStage[]; // 6 etapas en orden
  conversion_rate: number; // KPI HU26 = lead_stage[CITA_AGENDADA] / leads_created (0..1)
  total_leads: number;
  total_appointments: number;
  total_customers: number;
  chatbot_share: number; // % de citas con source='bot' (0..1)
}

// ── Serie temporal (línea de evolución de leads) — /dashboards/leads-evolution ─
// Un punto = un día + un dict de valores (una clave por serie, ej. por lead_status_code).
export interface TimeSeriesPoint {
  date: string; // "YYYY-MM-DD" (fecha-puro; NO instante)
  values: Record<string, number>; // { [seriesKey]: count }
}

// Definición de cada serie (para la leyenda + color del trazo). key empareja con TimeSeriesPoint.values[key].
export interface TimeSeries {
  series: { key: string; label: string; color: string | null }[]; // color del catálogo lead_status
  points: TimeSeriesPoint[];
}

// ── Distribución (donut de citas) — /dashboards/appointments-distribution ──────
export interface DistributionBucket {
  code: string; // appointment_status_code (resuelto por code, ADR-008)
  label: string; // etiqueta ES del catálogo
  color: string | null; // appointment_status.color del catálogo
  count: number;
}

export interface DistributionSummary {
  buckets: DistributionBucket[];
  total: number; // centro del donut
}

// ── KPIs escalares + chatbot — /dashboards/summary ─────────────────────────────
// Tasas en 0..1 (el front formatea a %). bot_cost_usd es Decimal → STRING en el wire.
export interface KpiSummary {
  // tasas (float 0..1)
  conversion_rate: number;
  lead_to_appt_rate: number;
  confirmation_rate: number;
  show_rate: number;
  no_show_rate: number;
  customer_rate: number;
  // conteos (int)
  total_conversations: number;
  conversations_bot: number;
  total_leads: number;
  total_appointments: number;
  total_confirmed: number;
  total_attended: number;
  total_customers: number;
  bot_turns: number;
  // monto (Decimal → string; NO number — contrato cross-cutting del template)
  bot_cost_usd: string;
}

// ── Meta (catálogos + freshness) — GET /dashboards/meta ────────────────────────
// Puebla los selects de los filtros (sedes/orígenes) + los colores/labels de los charts
// (estados de lead/cita) + el badge "Actualizado hace N min" (last_refreshed_at).
export interface DashboardMeta {
  last_refreshed_at: string | null; // timestamptz ISO; null = nunca refrescado. "hace N min" = client-only
  lead_statuses: { code: string; name: string; color: string | null; display_order: number }[];
  appointment_statuses: { code: string; name: string; color: string | null; display_order: number }[];
  branches: { id: string; name: string }[];
  sources: string[]; // orígenes de cita distintos vistos en el rollup (para el Dropdown de origen)
}

// ── Refresh (observabilidad del job; NO lo invoca el front) ────────────────────
// Lo devuelve /dashboards/internal/refresh al Cloud Scheduler. Se tipa para completar el
// espejo de backend.md, pero el frontend NUNCA llama ese endpoint (shared-secret, no JWT).
export interface RefreshResult {
  refreshed_at: string; // ISO
  window_days: number;
  rows_written: number;
  status: string; // "ok" | "running" | "error"
}

// ── Reportes (F3) ──────────────────────────────────────────────────────────────
export type ReportFormat = "pdf" | "excel";

// Body de POST /dashboards/report: el filtro + formato + secciones a incluir.
// sections = ["kpis","funnel","distribution","evolution"] (las que estén tildadas).
export interface ReportRequest extends DashboardFilter {
  format: ReportFormat;
  sections: string[];
}
```

> **Nota sobre clases de tiempo** (regla del template; ver clinic/scheduling/calendar):
> - `date_from`/`date_to` (request) y `TimeSeriesPoint.date` / `metric_date` → **fechas-puro** `"YYYY-MM-DD"` (sin hora, sin TZ). El rollup es por **día UTC**; el eje X de la línea se formatea **sin** conversión de TZ (no es un instante absoluto → no se le aplica `timeZone` fijo ni `localDateIsoOf`). Formatear con un helper de fecha-puro (`new Date("2026-06-01T00:00:00")` o `Intl.DateTimeFormat` con la fecha tal cual), **no** `new Date(isoDate)` que la interpretaría como medianoche UTC y la correría un día en husos negativos.
> - `last_refreshed_at` / `refreshed_at` → `timestamptz` ISO 8601 con offset (instante absoluto). El "hace N min" es relativo-a-`new Date()` → **client-only** (igual que la salud de calendar). El render formateado del instante, si se mostrara, usa `timeZone` fijo o client-only (lección §22).
> - **No hay** campos de hora-de-pared (`time` sin TZ) en este módulo.

> **`bot_cost_usd` es `string`, no `number`** (Decimal/Numeric serializa como string en el wire — contrato cross-cutting). Mostrarlo formateado (`$ 12.34`); si se necesita comparar/sumar en cliente, `Number(bot_cost_usd)` explícito. (Si el backend lo manda como number, es un drift del schema — reportar.)

> **El front no reconstruye las fórmulas del embudo/KPIs**: las tasas (`conversion_rate`, `show_rate`, etc.) y los conteos de etapa los **compone el backend** sumando el rollup (ver `design.md` §4/§7). El front sólo **dibuja** lo que llega; no recalcula nada a partir de los conteos crudos (evita drift de fórmula front↔back).

---

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque `DASHBOARDS` completo. **Orden de rutas backend**: las estáticas van antes que cualquier param (la spec §6 lo exige; aquí no hay rutas con `{id}`, así que el orden es trivial — todas estáticas). En el front sólo importan las URLs. **Todos POST salvo `META` (GET)**.

```ts
const DASHBOARDS = "/api/v1/dashboards"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, …, MARKETING, CALENDAR (existentes) …

  // ── Dashboards module (#10, ADR-015) ─────────────────────
  // Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún (la página /dashboard
  // sigue con el welcome placeholder hasta F2). Las rutas backend se montan en F1 (lectura)
  // y F3 (report). El endpoint /dashboards/internal/refresh (target del Cloud Scheduler,
  // shared-secret, sin JWT) NO va acá: lo invoca Cloud Scheduler contra el backend, el
  // frontend nunca lo llama (igual que el dispatch de bots / los webhooks de conversations).
  // Todos POST (reciben DashboardFilter en el body) salvo META (GET).
  DASHBOARDS: {
    FUNNEL: `${DASHBOARDS}/funnel`, // POST + DashboardFilter → SingleResponse[FunnelSummary]
    LEADS_EVOLUTION: `${DASHBOARDS}/leads-evolution`, // POST + DashboardFilter → SingleResponse[TimeSeries]
    APPOINTMENTS_DISTRIBUTION: `${DASHBOARDS}/appointments-distribution`, // POST + DashboardFilter → SingleResponse[DistributionSummary]
    SUMMARY: `${DASHBOARDS}/summary`, // POST + DashboardFilter → SingleResponse[KpiSummary]
    META: `${DASHBOARDS}/meta`, // GET → SingleResponse[DashboardMeta] (catálogos + last_refreshed_at)
    REPORT: `${DASHBOARDS}/report`, // POST + ReportRequest → binario (application/pdf | xlsx) + Content-Disposition
  },
} as const;
```

> **Matiz de envelopes en este módulo** (todo es `SingleResponse`, NUNCA paginado):
> - `FUNNEL` / `LEADS_EVOLUTION` / `APPOINTMENTS_DISTRIBUTION` / `SUMMARY` → `SingleResponse[X]` → `.data` (molde `usage_summary`). **No** son `PaginatedResponse` → **no** se usa `useTableQuery`.
> - `META` → `SingleResponse[DashboardMeta]` → `.data` (es el único **GET**; sin body).
> - `REPORT` → **NO es JSON**: devuelve un binario (`application/pdf` o el mime de xlsx) + `Content-Disposition`. **El `backendClient` actual NO sabe leer binarios** (siempre hace `res.json()`) → `generateReport` **no** usa `backendClient`; hace su propio `fetch` server-side con el `Bearer`. Ver la sección de actions (gotcha de descarga).
> - `/internal/refresh` no figura en `ENDPOINTS` (referencia muerta — lo invoca Cloud Scheduler, no el front; igual criterio que `BOT_ENGINE.dispatch` y los webhooks de conversations que tampoco van en `ENDPOINTS`).

---

## Navigation — modificar `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

El item `home` (→ `/dashboard`) ya existe (hoy gateado por `MENU-HOME`, label "Inicio"). La MOD de F0: **re-gatear por `DASHBOARD_VIEW`** (el panel reemplaza el welcome) + **agregar un grupo/child de reportes**. Dos formas (la spec dice "item `home`→/dashboard pasa a gatearse por DASHBOARD_VIEW + child `reportes`"); el patrón consistente con el resto del nav (grupos con children) es convertir `home` en un grupo "Panel" con dos children:

```ts
// MOD del item existente "home": pasa a ser un grupo con 2 children (Panel + Reportes).
// (Alternativa mínima: dejar `home` como item simple gateado DASHBOARD_VIEW y agregar
//  "reportes" como item hermano de nivel superior — pero el grupo es más consistente.)
{
  key: "home",
  label: "Panel", // antes "Inicio"; el panel de conversión es ahora la home real
  icon: "DataTrendingRegular", // NUEVO ícono (registrar en el iconMap del Sidebar)
  children: [
    {
      key: "dashboard",
      label: "Panel de conversión",
      icon: "DataFunnelRegular", // NUEVO (verificar; fallback DataBarVerticalRegular)
      url: "/dashboard",
      // Re-gateo: antes MENU-HOME → ahora el permiso fino DASHBOARD_VIEW (lo tienen ADMIN
      // y ASESOR; el DOCTOR NO → no ve el item, y /dashboard le muestra el welcome mínimo).
      permissions: ["DASHBOARD_VIEW"],
    },
    {
      key: "reportes",
      label: "Reportes",
      icon: "DocumentTableRegular", // NUEVO (verificar; fallback DocumentRegular)
      url: "/dashboard/reportes",
      permissions: ["REPORTS_EXPORT"], // ADMIN + ASESOR (HU27)
    },
  ],
},
```

> **Gating de los items**: `dashboard` lleva `permissions: ["DASHBOARD_VIEW"]` y `reportes` lleva `["REPORTS_EXPORT"]` (ambos los tienen ADMIN y ASESOR — spec §7). El **DOCTOR** no tiene ninguno de los dos → **no** ve el grupo "Panel". `MENU-DASHBOARDS` existe en el set de permisos (lo introduce backend F0) pero, igual que `MENU-SCHEDULING`/`MENU-CALENDAR`, el item del nav se gatea con el **permiso fino** (`DASHBOARD_VIEW`/`REPORTS_EXPORT`), no con `MENU-DASHBOARDS` (que queda como permiso "de menú" reservado). El page RSC reconfirma con `requirePermission("DASHBOARD_VIEW")` / `requirePermission("REPORTS_EXPORT")`.

> **`MENU-HOME` desaparece como gate del item** (pero no se borra el permiso — backend decide). Hoy `home` se gatea por `MENU-HOME`; tras F0 se gatea por `DASHBOARD_VIEW`. Para usuarios sin `DASHBOARD_VIEW` (ej. DOCTOR), `/dashboard` no aparece en el sidebar; si navegan a la URL directa, el RSC les muestra un **welcome mínimo** (sin redirect loop — ver page.tsx) en vez de redirigir, para que `/dashboard` siga siendo una landing válida tras login.

> **Íconos nuevos en el `iconMap` del `Sidebar.tsx`** (hoy NO hay íconos de gráfico registrados): registrar `DataFunnelRegular` / `DataPieRegular` / `DataTrendingRegular` / `DocumentTableRegular` de `@fluentui/react-icons` (ya instalado). **Verificar que cada nombre exista en la versión instalada** (los nombres de `@fluentui/react-icons` cambian entre versiones — lección Next 16 del template); si alguno no existe, **fallback a `DataBarVerticalRegular`** (gráfico de barras, casi seguro presente) para el genérico y `DocumentRegular` para reportes. **No** introducir una librería de íconos nueva.
> - El registro es doble: (1) importar el ícono en `Sidebar.tsx` y (2) agregar la línea `NombreRegular: <NombreRegular />` al `const ICONS`. Si falta el segundo paso, el item se renderiza sin ícono (no crashea, pero queda feo).

---

## Server Actions — `actions/dashboards.actions.ts`

Mismo molde que marketing (`getPromotionUsageSummary` — lee `SingleResponse` y devuelve `.data`): llamar `backendClient` → devolver `.data`. **SIN `revalidateTag` de mutación** (el módulo no muta negocio). Los reads llevan `tags: ['dashboards']` para participar de la caché de fetch de Next, pero **nada los invalida desde el front** (los datos se refrescan por el job del backend + el `refetchInterval` de React Query; ver más abajo).

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `dashboards` | todos los reads del panel (funnel/línea/donut/summary/meta) | **nunca desde el front** (read-only). El frescor lo da el `refetchInterval` de React Query + el job del backend. El tag existe sólo para deduplicar/cachear el fetch de Next dentro de un render. |

> **Una sola familia de tag** (no por-endpoint ni por-filtro): el panel es de lectura; no hay mutaciones que invalidar. El `refetchInterval` de React Query (≈ intervalo de refresco) es el que mantiene el panel "vivo". El report (`generateReport`) **no** lleva tag (es un binario on-demand).

```ts
"use server";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { serverEnv } from "@/config/env";
import { COOKIES } from "@/lib/constants/cookies";
import { cookies } from "next/headers";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type {
  DashboardFilter,
  DashboardMeta,
  DistributionSummary,
  FunnelSummary,
  KpiSummary,
  ReportRequest,
  TimeSeries,
} from "@/types/dashboards.types";
import type { MutationResult } from "./user.actions";

const DASHBOARDS_TAG = "dashboards";

// ── Reads del panel (POST + DashboardFilter; devuelven .data del SingleResponse) ──
// NO capturan el error (Server Components dejan que error.tsx lo agarre); pero como los
// consume React Query desde el cliente vía estos actions, un throw se convierte en
// query.isError → el widget muestra su propio MessageBar aislado (ver DashboardClient).

export async function getFunnel(filter: DashboardFilter): Promise<FunnelSummary> {
  const res = await backendClient.post<ApiSingle<FunnelSummary>>(ENDPOINTS.DASHBOARDS.FUNNEL, filter, {
    tags: [DASHBOARDS_TAG],
  });
  return res.data;
}

export async function getLeadsEvolution(filter: DashboardFilter): Promise<TimeSeries> {
  const res = await backendClient.post<ApiSingle<TimeSeries>>(
    ENDPOINTS.DASHBOARDS.LEADS_EVOLUTION,
    filter,
    { tags: [DASHBOARDS_TAG] },
  );
  return res.data;
}

export async function getAppointmentsDistribution(
  filter: DashboardFilter,
): Promise<DistributionSummary> {
  const res = await backendClient.post<ApiSingle<DistributionSummary>>(
    ENDPOINTS.DASHBOARDS.APPOINTMENTS_DISTRIBUTION,
    filter,
    { tags: [DASHBOARDS_TAG] },
  );
  return res.data;
}

export async function getSummary(filter: DashboardFilter): Promise<KpiSummary> {
  const res = await backendClient.post<ApiSingle<KpiSummary>>(ENDPOINTS.DASHBOARDS.SUMMARY, filter, {
    tags: [DASHBOARDS_TAG],
  });
  return res.data;
}

// META es GET (sin body) → catálogos + last_refreshed_at. Lo prefetcha el RSC y lo refresca
// React Query con el resto.
export async function getMeta(): Promise<DashboardMeta> {
  const res = await backendClient.get<ApiSingle<DashboardMeta>>(ENDPOINTS.DASHBOARDS.META, {
    tags: [DASHBOARDS_TAG],
  });
  return res.data;
}

// ── Reporte (F3): descarga del binario desde un Server Action ────────────────────
// GOTCHA: backendClient SIEMPRE hace res.json() → NO sirve para un binario. generateReport
// hace su PROPIO fetch server-side (leyendo la cookie httpOnly + Bearer), captura el
// ArrayBuffer y lo devuelve como base64 + filename + mime al cliente, que arma un Blob y
// dispara la descarga. (No se puede streamear el binario directo al navegador desde un
// Server Action; se serializa por el canal de la action.)
export async function generateReport(
  input: ReportRequest,
): Promise<MutationResult<{ filename: string; mime: string; base64: string }>> {
  try {
    const jar = await cookies();
    const token = jar.get(COOKIES.ACCESS_TOKEN)?.value;
    const res = await fetch(`${serverEnv.BACKEND_URL}${ENDPOINTS.DASHBOARDS.REPORT}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(token ? { authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(input),
      cache: "no-store",
    });
    if (!res.ok) {
      // El backend manda el error como JSON envelope (REPORT_FORMAT_NOT_SUPPORTED 400,
      // DASHBOARD_INVALID_DATE_RANGE 400) incluso para este endpoint binario.
      let body: unknown = null;
      try {
        body = await res.json();
      } catch {
        /* ignore */
      }
      throw new HttpError(res.status, body);
    }
    const mime = res.headers.get("content-type") ?? "application/octet-stream";
    // Filename del Content-Disposition (el backend lo fija: "reporte-conversion-YYYYMMDD.pdf").
    const cd = res.headers.get("content-disposition") ?? "";
    const filename = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? "reporte.bin";
    const buf = await res.arrayBuffer();
    const base64 = Buffer.from(buf).toString("base64");
    return { ok: true, data: { filename, mime, base64 } };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "No se pudo generar el reporte." };
  }
}
```

> **Por qué `generateReport` NO usa `backendClient`** (gotcha real, verificado en `services/backend.client.ts`): el `backendClient` siempre hace `res.json()` y lanza si no es JSON → **no puede** leer un PDF/xlsx. La action hace su propio `fetch` con el `Bearer` (misma cookie httpOnly que el client), captura el `ArrayBuffer`, lo pasa a base64 y lo devuelve. El cliente reconstruye un `Blob` y dispara la descarga (`URL.createObjectURL` + un `<a download>` programático). Es el patrón estándar de "descarga de binario desde Server Action" en Next 16 (el binario se serializa por el canal de la action, no se streamea). Para reportes muy grandes, una mejora futura sería un endpoint que devuelva una URL firmada de GCS; el MVP serializa el binario (los reportes agregados de una clínica son chicos).

> **`generateReport` SÍ captura el error** (a diferencia de los reads): es disparado por un gesto del usuario (botón "Generar y descargar") → devuelve `MutationResult` para que el `ReportForm` muestre el `detail` en español en un `MessageBar` (`REPORT_FORMAT_NOT_SUPPORTED` / `DASHBOARD_INVALID_DATE_RANGE`). Los reads, en cambio, propagan el throw → React Query lo convierte en `isError` por-widget.

> **Sin `revalidateTag` en TODO el archivo**: no hay mutaciones de negocio. Es la diferencia clave con marketing/scheduling (que sí revalidan tras create/update). El tag `dashboards` existe sólo para que los reads de un mismo render se cacheen/deduplliquen; nada los invalida desde el front.

---

## Charts — bespoke (sin dependencia) ⚠ ACTUALIZADO EN F2

> **Actualización F2 (2026-06-24)**: NO se agregó `@fluentui/react-charts`. Rompe el build de Next 16 App Router + Turbopack (`@fluentui/react-icons` interno → `createContext is not a function` en un chunk SSR; no lo salvan `dynamic ssr:false`/`transpilePackages`/`turbopack.root`). Los charts se hicieron **bespoke** con tokens Fluent: `ConversionFunnel` (barras `div`), `AppointmentsDonut` (CSS `conic-gradient` + leyenda), `LeadsLineChart` (SVG `viewBox`+`preserveAspectRatio="none"`+`vector-effect: non-scaling-stroke`, ejes HTML). Sin `next/dynamic` (ya no hay bundle pesado que diferir) y SSR-safe. Colores de segmento del catálogo (`bucket.color`/`series.color`, ADR-008), fallback a tokens. Ver [ADR-015 §Update](../../decisions/ADR-015-dashboards-materialized-aggregation.md). El texto de abajo describe el plan original con la librería.

El plan original (NO implementado): `@fluentui/react-charts` (v9, sucesora de `@fluentui/react-charting`) como dep nueva del front. Reglas (de `design.md` §8):

1. **Cada chart es un componente cliente** (`"use client"`): mide el DOM (ancho/alto) → no puede renderizar en server.
2. **Carga con `next/dynamic({ ssr: false })` + `<Skeleton>` Fluent como fallback** → saca el JS del chart del **critical path** (LCP/RNF-05). El RSC pinta primero los KPI cards (texto) y los esqueletos; los charts hidratan después.
3. **Theming hereda del `FluentProvider`** (Griffel; ver `AppProviders.tsx`) → **cero mapeo de colores manual** (a diferencia de Recharts, que obligaba a mapear el tema a mano — razón documentada en el ADR-015 para elegir Fluent Charts). Los colores de **segmento** (estados de lead/cita) vienen del **catálogo** (`/meta`), se pasan como prop de color a cada serie/sector.

```tsx
// _components/AppointmentsDonut.tsx (patrón replicado por LeadsLineChart y FunnelChart)
"use client";

import dynamic from "next/dynamic";
import { Skeleton, SkeletonItem } from "@fluentui/react-components";

// dynamic con ssr:false: el bundle del chart no entra en el HTML del server → fuera del LCP.
const DonutChart = dynamic(
  () => import("@fluentui/react-charts").then((m) => m.DonutChart),
  { ssr: false, loading: () => <SkeletonItem style={{ height: 240 }} /> },
);

export function AppointmentsDonut({ data }: { data: DistributionSummary }) {
  // Mapear buckets → el shape que pide el DonutChart, con el color del catálogo (no hardcodeado).
  const chartData = {
    chartTitle: "Distribución de citas",
    chartData: data.buckets.map((b) => ({
      legend: b.label,
      data: b.count,
      color: b.color ?? undefined, // del catálogo appointment_status; Fluent default si null
    })),
  };
  if (data.total === 0) return <EmptyWidget label="No hay citas en el rango seleccionado" />;
  return <DonutChart data={chartData} innerRadius={60} /* total al centro */ />;
}
```

| Visualización | Componente Fluent | Datos | Notas |
|---|---|---|---|
| **Embudo** (centro) | `FunnelChart` **si la versión instalada lo expone**; si no, un `ConversionFunnel` **bespoke** (barras horizontales decrecientes con tokens Fluent — precedente "bespoke dentro de Fluent" = `CalendarGrid` de scheduling). **Verificar en F2** qué charts trae la versión; el bespoke es el fallback seguro. | `FunnelSummary.stages` (6 conteos + `rate_from_prev`). | Cada barra muestra `label · count · (rate_from_prev %)`. |
| **Evolución de leads** (línea) | `LineChart` (o `AreaChart`) | `TimeSeries` → `points` (eje X = `date`, fechas-puro) + `series` (una por `lead_status_code`, color del catálogo). | Eje X = días; **sin** conversión de TZ (fecha-puro). |
| **Distribución de citas** (donut) | `DonutChart` | `DistributionSummary.buckets` por `appointment_status_code`. | Centro = `total`; colores del catálogo. |
| **KPIs** (tarjetas) | `Card` + `Text` de `@fluentui/react-components` (NO un chart) | escalares de `KpiSummary`. | Pintan primero (texto, sin dynamic). Tendencia vs período anterior = diferible. |
| **Mini-panel chatbot** | `Card` + cifras (+ opcional `LineChart`) | `conversations_bot`, `bot_turns`, `bot_cost_usd`, tokens. | Resalta el aporte del chatbot (eje de la tesis). |

> **`FunnelChart` nativo vs `ConversionFunnel` bespoke** (decisión abierta, se cierra al instalar en F2): si `@fluentui/react-charts` expone un `FunnelChart` usable, se usa; si no (o si no respeta los 6-niveles + tasas), se hace el bespoke (un `div` con barras `makeStyles` de ancho proporcional al conteo, tokens Fluent, igual criterio que `CalendarGrid`). En ambos casos es client-only + dynamic ssr:false.

> **Skeleton fallback obligatorio**: el `loading` del `dynamic` NO puede ser `null` (dejaría un salto de layout → CLS). Usar un `SkeletonItem` con la altura aproximada del chart (donut ≈ 240px, línea ≈ 280px, embudo ≈ 300px) para reservar el espacio.

---

## React Query — el patrón del panel (NO `useTableQuery`)

El panel **no es un listado paginado** → **no** usa `useTableQuery` (que asume `QueryRequest` + paginación + `nuqs`). Usa `useQuery` directo, uno por widget, con:
- **`initialData`** del prefetch RSC (el `page.tsx` ya trajo summary+funnel+meta) → primer render sin round-trip (LCP).
- **`staleTime` ≈ `refetchInterval` ≈ el intervalo de refresco del rollup** (`DASHBOARD_REFRESH_INTERVAL_MINUTES`, default **10 min**) → es la "caché TTL por caducidad de KPIs" que nombra la tesis. El panel se siente "vivo" sin recomputar nada (sólo lee el rollup); `refetchInterval` re-pide cada N min para que el badge "Actualizado hace N min" y los conteos avancen.

```tsx
// _components/DashboardClient.tsx — un useQuery por widget (aislamiento de error)
"use client";

const REFRESH_MS = 10 * 60_000; // ≈ DASHBOARD_REFRESH_INTERVAL_MINUTES (10 min)

const funnelQuery = useQuery({
  queryKey: ["dashboards:funnel", filter], // el filter es parte de la key → refetch al cambiarlo
  queryFn: () => getFunnel(filter),
  initialData: filterIsDefault ? initialData.funnel : undefined, // sólo si el filtro = el prefetch
  staleTime: REFRESH_MS,
  refetchInterval: REFRESH_MS, // "casi en tiempo real"
});
// idéntico para summaryQuery / distributionQuery / leadsQuery / metaQuery
```

> **`initialData` sólo cuando el filtro coincide con el prefetch**: el RSC prefetcha con el rango por defecto (ej. últimos 30 días, todas las sedes). Si el usuario cambia el filtro, la `queryKey` cambia → React Query refetcha (no usa el `initialData`). Mismo criterio que `useTableQuery` (que usa `initialData` sólo mientras la URL refleja el request default).

> **El `QueryClient` global ya tiene `staleTime: 30_000`** (`AppProviders.tsx`); el panel **sobrescribe** `staleTime`/`refetchInterval` por-query al valor del intervalo (10 min) — no se toca el default global. `refetchOnWindowFocus: false` (default global) está bien para un panel de 10 min.

> **Filtro como estado** (no necesariamente `nuqs`): el `DashboardFilter` (rango/sede/origen) puede vivir en `useState` local del `DashboardClient` (más simple que `useTableQuery`) o en `nuqs` si se quiere URL-shareable (refinamiento). El MVP usa `useState`; la spec/ui.md fijan el detalle. La `queryKey` incluye el filtro serializado → cambiar un filtro refetcha todos los widgets.

> **Aislamiento de error por widget** (estado "error" de la UI, spec §11): cada `useQuery` es independiente; si `getFunnel` falla (un widget), su `funnelQuery.isError` muestra un `MessageBar` + reintentar **sólo en el embudo**, sin romper el donut/línea/KPIs. Mismo criterio que el overlay best-effort de calendar (§23): un widget caído no tumba el panel.

---

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/dashboard/page.tsx` (MOD — reemplaza el welcome placeholder)

RSC que **reemplaza** el `<h1>Bienvenido</h1>` actual. `requirePermission("DASHBOARD_VIEW")` + prefetch en paralelo de `getSummary` + `getFunnel` + `getMeta` (los tres que pintan el "above the fold": KPI cards + embudo + freshness/catálogos) → pasa `initialData` al `DashboardClient`. La línea y el donut los pide el cliente (no bloquean el LCP).

```tsx
import {
  getFunnel,
  getMeta,
  getSummary,
} from "@/actions/dashboards.actions";
import { requirePermission } from "@/lib/auth/session";
import { DEFAULT_DASHBOARD_FILTER } from "./_components/DashboardFilters"; // ej. últimos 30 días

import { DashboardClient } from "./_components/DashboardClient";

export const metadata = { title: "Panel de conversión" };

export default async function DashboardPage() {
  // Re-gateo F0: antes MENU-HOME → ahora DASHBOARD_VIEW. El DOCTOR (sin el permiso) NO pasa;
  // pero NO redirigimos (sería un redirect loop si /dashboard es la landing) → mostramos un
  // welcome mínimo. Por eso NO usamos requirePermission directo arriba: chequeamos el claim.
  // (Patrón: requirePermission redirige; acá queremos degradar a welcome, no redirigir.)
  const claims = await requirePermission("DASHBOARD_VIEW", { redirectTo: "/dashboard?welcome=1" });
  // ↑ si requirePermission no soporta degradar, ver la nota: leer claims y ramificar a <Welcome/>.

  const filter = DEFAULT_DASHBOARD_FILTER; // { date_from, date_to: hoy, branch_id: null, ... }
  const [summary, funnel, meta] = await Promise.all([
    getSummary(filter),
    getFunnel(filter),
    getMeta(),
  ]);

  return (
    <DashboardClient
      initialData={{ summary, funnel, meta }}
      initialFilter={filter}
    />
  );
}
```

> **Welcome mínimo para usuarios sin `DASHBOARD_VIEW`** (sin redirect loop): `/dashboard` es la landing tras login. Si el actor no tiene `DASHBOARD_VIEW` (ej. DOCTOR), **no** se redirige (sería un loop) — se renderiza un welcome mínimo (`<h1>Bienvenido</h1>` + atajos a "Mi agenda"/"Mis leads" según permisos). Implementación: leer los claims (`requireAuth()` en vez de `requirePermission`) y **ramificar** en el server: si `claims.permissions.includes("DASHBOARD_VIEW")` → `<DashboardClient/>`; si no → `<WelcomeFallback/>`. (El pseudo-código de arriba con `{ redirectTo }` es ilustrativo; el detalle exacto lo fija `ui.md`/`backend.md` de session helpers. El criterio firme: **no redirigir desde la landing; degradar a welcome**.)

> **Prefetch de 3 (no 5)**: el RSC trae summary+funnel+meta (above-the-fold + catálogos para los selects). La línea (`getLeadsEvolution`) y el donut (`getAppointmentsDistribution`) los pide el cliente con sus `useQuery` (sin `initialData`) → no bloquean el primer render. Mismo criterio de LCP que prefetchar sólo lo crítico.

### `app/(main)/dashboard/reportes/page.tsx` (NUEVO — F3)

RSC con `requirePermission("REPORTS_EXPORT")` + `getMeta` (para poblar el Dropdown de sedes del filtro del reporte). Pasa la meta al `ReportForm`.

```tsx
import { getMeta } from "@/actions/dashboards.actions";
import { requirePermission } from "@/lib/auth/session";

import { ReportForm } from "./_components/ReportForm";

export const metadata = { title: "Reportes" };

export default async function ReportsPage() {
  await requirePermission("REPORTS_EXPORT");
  const meta = await getMeta(); // sedes para el filtro
  return <ReportForm branches={meta.branches} />;
}
```

> **`requirePermission("REPORTS_EXPORT")` SÍ redirige** (a diferencia de `/dashboard`): `/dashboard/reportes` no es la landing → un usuario sin el permiso se redirige normalmente (no hay loop). ADMIN y ASESOR pasan; DOCTOR no.

---

## Client components — esqueletos

> **No reproduzco los archivos completos** — la UI detallada (mockups ASCII, copy, estados) vive en [`ui.md`](./ui.md). Documento las diferencias específicas a `dashboards`.

### `DashboardClient.tsx`

Orquestador del panel (no es una `DataTable`). Props: `{ initialData: { summary: KpiSummary; funnel: FunnelSummary; meta: DashboardMeta }; initialFilter: DashboardFilter }`.

- **Estado**: `const [filter, setFilter] = useState(initialFilter)` (rango/sede/origen). El `filter` es parte de la `queryKey` de cada widget → cambiarlo refetcha todo.
- **Queries** (una por widget, aisladas): `summaryQuery`, `funnelQuery`, `distributionQuery`, `leadsQuery`, `metaQuery` (ver la sección React Query). `initialData` sólo en summary/funnel/meta cuando `filter === initialFilter`.
- **Layout** (spec §11 / ui.md): header (filtros + badge "Actualizado hace N min" + refrescar) → fila de KPI cards → Embudo (centro) → fila Línea + Donut → mini-panel chatbot.
- **Estados por widget**: loading = skeleton del widget (no spinner global); sin-datos = ilustración + "No hay datos en el rango seleccionado"; error = `MessageBar` + reintentar (sólo ese widget). El panel **nunca** se rompe entero.
- **Gating**: la página ya gateó `DASHBOARD_VIEW`; `REPORTS_EXPORT` (botón/enlace a reportes) se gatea con `<PermissionGuard anyOf={["REPORTS_EXPORT"]}>`.

### `DashboardFilters.tsx`

Header de filtros. Props: `{ filter, onChange, meta, lastRefreshedAt }`.
- **Rango**: un selector de fechas (presets "Últimos 7/30/90 días" + custom `date_from`/`date_to`). El backend valida `date_to >= date_from` y rango ≤ 366d → si el usuario arma un rango inválido, el `getX` devuelve 400 `DASHBOARD_INVALID_DATE_RANGE` y el widget muestra el `detail` ES. (Idealmente el front también acota el rango en el picker.)
- **Sede**: `<Dropdown>` poblado con `meta.branches` + opción "Todas las sedes" (`value=""` → `branch_id=null`). **Caveat de la UI** (design §4 caveat 4): mostrar un hint suave de que el filtro de sede es exacto **de la etapa "cita" en adelante** (conversaciones/leads son a nivel clínica) — no inventar un filtro de sede para las etapas previas.
- **Origen**: `<Dropdown>` con `meta.sources` + "Todos".
- **Badge "Actualizado hace N min"**: `lastRefreshedAt` (de `meta.last_refreshed_at`) relativo a `new Date()` → **client-only** (igual que la salud de calendar). Si `null` → "Sin datos aún". Botón refrescar = `queryClient.invalidateQueries({ queryKey: ["dashboards:*"] })` o `refetch()` de cada query (re-pide el rollup; no dispara el job del backend).
- **Exportar a constante** `DEFAULT_DASHBOARD_FILTER` (el rango por defecto del prefetch RSC) para que page.tsx y el client coincidan (mismo criterio para que `initialData` aplique).

### `KpiCards.tsx`

Fila de tarjetas (Card + Text). Props: `{ summary: KpiSummary }`. Cada card muestra una métrica:
- Tasa de conversión (`conversion_rate`, formato `%`), Leads (`total_leads`), Citas (`total_appointments`), Confirmadas (`total_confirmed`), Clientes (`total_customers`), Bot (`chatbot_share` o `conversations_bot / total_conversations`, formato `%`).
- **`bot_cost_usd` es string** → formatear como moneda (`$ {Number(bot_cost_usd).toFixed(2)}`); no operar sobre el string crudo.
- Pintan **primero** (texto, sin `dynamic`) → contribuyen al LCP. La flecha de tendencia vs período anterior es **diferible** (no MVP).

### `FunnelChart.tsx` / `LeadsLineChart.tsx` / `AppointmentsDonut.tsx`

Cada uno: `"use client"` + `next/dynamic(() => import("@fluentui/react-charts").then(m => m.X), { ssr:false, loading: <Skeleton> })`. Reciben sus datos como prop (`FunnelSummary` / `TimeSeries` / `DistributionSummary`), mapean al shape del chart Fluent **con los colores del catálogo** (no hardcodeados), y manejan el caso `total === 0` / `points.length === 0` → estado sin-datos. Ver la sección Charts.

### `BotMiniPanel.tsx`

Card con las cifras del chatbot (de `KpiSummary`): `conversations_bot`, `bot_turns`, `bot_cost_usd` (string formateado), tokens (si el schema los expone). Resalta el aporte del bot (eje de la tesis). Sin chart obligatorio (cifras + opcional una mini-línea).

### `ReportForm.tsx` (F3)

Form de generación de reporte. Props: `{ branches: { id: string; name: string }[] }`.
- **Campos**: rango (`date_from`/`date_to`) + sede (`<Dropdown>` + "Todas") + formato (`<RadioGroup>` PDF/Excel) + checkboxes de secciones (KPIs / Embudo / Distribución / Evolución).
- **"Generar y descargar"**: arma el `ReportRequest` (filtro + `format` + `sections` tildadas) → `generateReport(input)`. En éxito (`{ filename, mime, base64 }`): reconstruir el `Blob` y disparar la descarga en cliente:
  ```ts
  const onDownload = async () => {
    const res = await generateReport(buildReportRequest());
    if (!res.ok) { setError(res.error ?? "No se pudo generar el reporte."); return; }
    const { filename, mime, base64 } = res.data;
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };
  ```
- **Estados**: generando = botón con `<Spinner>` + deshabilitado (usar `useState` de pending; **no** hay un form Zod obligatorio acá — el body es simple y el backend valida el formato/rango); error = `MessageBar` con el `detail` ES (`REPORT_FORMAT_NOT_SUPPORTED` / `DASHBOARD_INVALID_DATE_RANGE`).
- **Sin Zod compartido obligatorio**: a diferencia de los forms CRUD del template (que comparten Zod cliente/servidor), el `ReportRequest` es un body simple y el `generateReport` no valida con Zod (el backend es la autoridad del formato/rango). Si se quiere defensa en profundidad, un `reportRequestSchema` chico es opcional (no bloqueante).

---

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| **`SingleResponse[X]` + `.data`, NO `useTableQuery`** | El panel no es un listado paginado; el request es `DashboardFilter` (no `QueryRequest`). Molde `marketing.usage_summary`. Se usa `useQuery` directo por widget. |
| **SIN `revalidateTag` en los actions** | El módulo es 100% lectura/agregación; no muta negocio. El frescor lo dan el `refetchInterval` (≈ intervalo del rollup) + el job del backend. El tag `dashboards` sólo deduplica el fetch de Next dentro de un render. |
| **`/internal/refresh` NO se llama desde el front** | Lo dispara el Cloud Scheduler con shared-secret (sin JWT, ADR-012). No figura en `ENDPOINTS` (referencia muerta, igual que el dispatch de bots / webhooks). |
| **`refetchInterval ≈ staleTime ≈ DASHBOARD_REFRESH_INTERVAL_MINUTES`** | La "caché TTL por caducidad de KPIs" de la tesis: el panel se siente "casi en tiempo real" leyendo el rollup, sin websockets/SSE (sobre-ingeniería). |
| **`initialData` del prefetch RSC (summary+funnel+meta)** | Primer render sin round-trip → LCP/RNF-05. Sólo aplica mientras `filter === DEFAULT_DASHBOARD_FILTER` (al cambiar el filtro, la `queryKey` cambia y React Query refetcha). |
| **Charts client-only + `next/dynamic({ssr:false})` + Skeleton fallback** | Saca el JS de los charts del critical path → LCP. KPI cards (texto) pintan primero. El Skeleton reserva el alto (sin CLS). |
| **Theming hereda del `FluentProvider` (Griffel); colores de segmento del catálogo** | `@fluentui/react-charts` comparte tokens con el stack → cero mapeo manual (razón del ADR-015 para elegir Fluent sobre Recharts). Los colores de estado vienen de `/meta` (ADR-008), no hardcodeados. |
| **`FunnelChart` nativo si existe / `ConversionFunnel` bespoke (fallback)** | Se decide al instalar en F2 según lo que exponga la versión; el bespoke (barras `makeStyles`, precedente `CalendarGrid`) es el fallback seguro. |
| **El front NO recalcula fórmulas del embudo/KPIs** | El backend compone las tasas/conteos sumando el rollup; el front sólo dibuja → sin drift de fórmula front↔back. |
| **`generateReport` hace su PROPIO `fetch` (no `backendClient`)** | `backendClient` siempre hace `res.json()` → no lee binarios. La action captura el `ArrayBuffer`, lo pasa a base64 y lo devuelve; el cliente arma el `Blob` y descarga. Patrón estándar Next 16. |
| **`generateReport` captura el error (los reads no)** | Es un gesto del usuario → `MutationResult` para `MessageBar` ES. Los reads propagan el throw → React Query lo hace `isError` por-widget. |
| **`/dashboard` sin `DASHBOARD_VIEW` → welcome mínimo, NO redirect** | `/dashboard` es la landing tras login; redirigir sería un loop. Se degrada a welcome (atajos según permisos). `/dashboard/reportes` sí redirige (no es landing). |
| **Item `home` re-gateado por `DASHBOARD_VIEW` (no `MENU-HOME`); reportes por `REPORTS_EXPORT`** | `MENU-DASHBOARDS` queda reservado (patrón scheduling/calendar); el nav se gatea con el permiso fino. |
| **Numeric (`bot_cost_usd`) es `string`** | Contrato cross-cutting del template; el front formatea, no opera sobre el string crudo. |
| **Eje X de la línea = fecha-puro (sin TZ); badge "hace N min" = client-only** | `metric_date` es por día UTC (no instante) → se formatea sin conversión de TZ. `last_refreshed_at` sí es instante → relativo client-only (lección §22). |
| **Íconos Fluent nuevos en el `iconMap`, con verificación + fallback** | `DataFunnelRegular`/`DataPieRegular`/`DataTrendingRegular`/`DocumentTableRegular`; verificar existencia en la versión instalada (los nombres cambian entre versiones — lección Next 16); fallback `DataBarVerticalRegular`/`DocumentRegular`. No introducir librería de íconos nueva. |

---

## Gotchas Next 16 / Fluent (recap operativo)

- **Charts client-only**: `@fluentui/react-charts` mide el DOM → `"use client"` + `next/dynamic({ssr:false})` obligatorio. Renderizar un chart en server tira (no hay `window`).
- **`dynamic` con `loading` ≠ null**: dar un `Skeleton` con altura aproximada (evita CLS / salto de layout durante la hidratación del chart).
- **StrictMode efectos 2x**: `reactStrictMode: true` en `next.config.ts` → los efectos (y el primer fetch de `useQuery` en dev) corren dos veces en desarrollo. Es esperado; no "arreglar" con flags.
- **`next lint` roto en Next 16 = NO es gate**: el gate de CI es `tsc --noEmit` + el build de Vercel (lección del template). No bloquear por `next lint`.
- **Prettier sólo sobre archivos nuevos**: correr `prettier --write` sólo sobre los archivos creados/tocados del módulo (no reformatear el repo).
- **Nombres de `@fluentui/react-icons` cambian entre versiones**: verificar cada ícono nuevo en la versión instalada antes de importarlo en `Sidebar.tsx`; si no existe, fallback a uno presente. (Mismo gotcha que calendar tuvo con `CalendarSyncRegular`.)
- **`backendClient` no lee binarios**: confirmado en `services/backend.client.ts` (`res.json()` siempre). El report usa `fetch` propio (ver `generateReport`).
- **Server Action no streamea binarios**: el binario se serializa por el canal de la action (base64) → el cliente reconstruye el `Blob`. Para reportes grandes, URL firmada de GCS = mejora futura (no MVP).

---

## Checklist de implementación (mapeado a fases F0 / F2 / F3)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Cada checkbox es lado frontend. (La capa de agregación + endpoints de lectura es **F1**, backend-only — no tiene checkboxes de frontend.)

### F0 — Prep (andamiaje compartido, sin pantalla nueva)

- [ ] Crear `src/types/dashboards.types.ts` (TODAS las interfaces espejo de spec §5 / backend.md: `DashboardFilter`, `FunnelStage`, `FunnelSummary`, `TimeSeriesPoint`, `TimeSeries`, `DistributionBucket`, `DistributionSummary`, `KpiSummary`, `DashboardMeta`, `RefreshResult`, `ReportFormat`, `ReportRequest`). `bot_cost_usd: string`. NO reusa tipos de otros módulos.
- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `DASHBOARDS` (FUNNEL, LEADS_EVOLUTION, APPOINTMENTS_DISTRIBUTION, SUMMARY = POST; META = GET; REPORT = POST binario). `/internal/refresh` NO va (referencia muerta).
- [ ] MOD `src/lib/constants/navigation.ts`: item `home` → grupo "Panel" con children `dashboard` (gated `DASHBOARD_VIEW`) + `reportes` (gated `REPORTS_EXPORT`); íconos `DataTrendingRegular`/`DataFunnelRegular`/`DocumentTableRegular`.
- [ ] Registrar los íconos nuevos en el `iconMap` (`const ICONS`) del `Sidebar.tsx` (import + entrada) — **verificar nombres** en la versión instalada de `@fluentui/react-icons`; fallback `DataBarVerticalRegular`/`DocumentRegular`.
- [ ] **Permisos test (F0)**: el grupo "Panel" aparece para ADMIN y ASESOR (tienen `DASHBOARD_VIEW`/`REPORTS_EXPORT`), NO para DOCTOR. Rutas backend `/dashboards/*` → 404 (módulo no registrado). La página `/dashboard` sigue mostrando el welcome placeholder (sin cambios hasta F2). (Los 3 permisos + roles ya en `seed.py` — los introduce backend F0.)

### F2 — Panel (frontend, tras F1 que entrega los endpoints de lectura)

- [ ] Instalar la dep nueva `@fluentui/react-charts` (front).
- [ ] Crear `src/actions/dashboards.actions.ts` (`getFunnel`, `getLeadsEvolution`, `getAppointmentsDistribution`, `getSummary`, `getMeta`; reads con `tags: ['dashboards']`, devuelven `.data`; **sin** `revalidateTag`). (`generateReport` se crea en F3 pero puede ir acá.)
- [ ] MOD `app/(main)/dashboard/page.tsx`: reemplazar el welcome por el RSC que gatea `DASHBOARD_VIEW` (degradando a welcome mínimo si falta — sin redirect loop) + prefetch `getSummary`+`getFunnel`+`getMeta` → `DashboardClient`.
- [ ] Crear `_components/DashboardClient.tsx` (filtros + 5 `useQuery` aislados con `initialData` + `staleTime`/`refetchInterval` ≈ 10 min + layout del panel + estados por widget).
- [ ] Crear `_components/DashboardFilters.tsx` (rango/sede/origen + badge "Actualizado hace N min" client-only + refrescar; caveat de sede a nivel clínica en etapas previas; export `DEFAULT_DASHBOARD_FILTER`).
- [ ] Crear `_components/KpiCards.tsx` (Card+Text de `KpiSummary`; `bot_cost_usd` formateado; sin dynamic — pintan primero).
- [ ] Crear `_components/FunnelChart.tsx` (FunnelChart nativo si existe / ConversionFunnel bespoke; client-only + dynamic ssr:false + Skeleton).
- [ ] Crear `_components/LeadsLineChart.tsx` (LineChart/AreaChart; eje X fecha-puro sin TZ; colores del catálogo lead_status; client-only + dynamic + Skeleton).
- [ ] Crear `_components/AppointmentsDonut.tsx` (DonutChart; colores del catálogo appointment_status; total al centro; client-only + dynamic + Skeleton).
- [ ] Crear `_components/BotMiniPanel.tsx` (cifras del chatbot de `KpiSummary`).
- [ ] **Smoke test (F2)**: login ADMIN/ASESOR → `/dashboard` muestra KPI cards + embudo (6 etapas) + línea + donut + mini-panel bot; cambiar el rango/sede refetcha todos los widgets; el badge "Actualizado hace N min" refleja `last_refreshed_at`.
- [ ] **Estado sin-datos test (F2)**: rango sin datos → cada widget muestra "No hay datos en el rango seleccionado" (no error, no crash) — el rollup vacío devuelve conteos 0 (spec §8).
- [ ] **Aislamiento de error test (F2)**: si un endpoint falla, sólo ese widget muestra `MessageBar` + reintentar; el resto del panel pinta normal (no se rompe entero).
- [ ] **TZ test (F2)**: el eje X de la línea muestra los días correctos (fecha-puro, sin correrse por TZ en husos negativos); el badge "hace N min" es relativo client-only.
- [ ] **Permisos test (F2)**: DOCTOR (sin `DASHBOARD_VIEW`) en `/dashboard` → welcome mínimo (no redirect loop, no crash); no ve el grupo "Panel" en el sidebar.
- [ ] **Lighthouse (F2)**: auditar `/dashboard` (RNF-05: LCP ≤ 2.5 s; panel ≤ 3 s p95). Evidencia para la tesis (reemplaza la Figura del "Lighthouse 95" del sistema viejo).

### F3 — Reportes (sin migración)

- [ ] Crear `generateReport` en `src/actions/dashboards.actions.ts` (fetch propio server-side con `Bearer`; captura `ArrayBuffer` → base64 + filename + mime; captura el error → `MutationResult`).
- [ ] Crear `app/(main)/dashboard/reportes/page.tsx` (RSC, `requirePermission("REPORTS_EXPORT")` — SÍ redirige; `getMeta` para las sedes del filtro) + `_components/ReportForm.tsx` (rango/sede/formato/secciones + "Generar y descargar" → reconstruye Blob + descarga).
- [ ] Enlazar a `/dashboard/reportes` desde el `DashboardClient` (gated `<PermissionGuard anyOf={["REPORTS_EXPORT"]}>`).
- [ ] **Smoke test (F3)**: `/dashboard/reportes` → elegir rango + sede + PDF + secciones → "Generar y descargar" → descarga un PDF con portada + KPIs + embudo + distribución + evolución. Repetir con Excel → descarga un .xlsx con una hoja de KPIs + una hoja por dataset.
- [ ] **Error test (F3)**: formato no soportado / rango inválido → `MessageBar` ES (`REPORT_FORMAT_NOT_SUPPORTED` / `DASHBOARD_INVALID_DATE_RANGE`); botón "generando" deshabilitado mientras corre.
- [ ] **Permisos test (F3)**: usuario sin `REPORTS_EXPORT` → `/dashboard/reportes` redirige (no es landing); el enlace a reportes no aparece en el panel.

### Diferidas (D1–D4) — documentar, NO codear

- [ ] **D1 dashboard por-doctor / clínico**: NO se construye; sólo roadmap.
- [ ] **D2 métricas de mensajes desde Firestore** (read-model): NO se construye (mensajes en Firestore, ADR-011; el panel usa conversaciones + bot_turns).
- [ ] **D3 caché distribuida (Redis/Memorystore) + particionado del rollup**: NO se construye.
- [ ] **D4 real-time estricto del día en curso + tendencias/forecast** (flecha de tendencia de los KPI cards): NO se construye; la flecha vs período anterior queda como refinamiento.

## TODOs deliberados (postergados al MVP+1 / fases diferidas)

- [ ] **Flecha de tendencia vs período anterior** en los KPI cards — el MVP muestra el valor del período, sin comparación.
- [ ] **Filtro `nuqs` URL-shareable** del `DashboardFilter` — el MVP usa `useState` local; `nuqs` (link comparable, sobrevive refresh) es refinamiento.
- [ ] **URL firmada de GCS para reportes grandes** — el MVP serializa el binario por el canal de la action (base64); para reportes pesados, una URL firmada evitaría la serialización.
- [ ] **Real-time estricto del día en curso** (cómputo on-the-fly de los escalares de "hoy") — el MVP refresca por ventana móvil cada N min (badge "Actualizado hace N min").
- [ ] **i18n framework** — strings literales en español directo (mismo criterio que el resto de los módulos).
