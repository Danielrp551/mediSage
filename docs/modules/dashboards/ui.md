# Módulo `dashboards` — UI design

> **Última actualización**: 2026-06-24
> **Audiencia**: developer implementando las pantallas de `dashboards` en `frontend/src/app/(main)/dashboard/` (el Panel `/dashboard` que **reemplaza** el placeholder de bienvenida) y `frontend/src/app/(main)/dashboard/reportes/` (Reportes).
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts de `FunnelSummary`/`TimeSeries`/`DistributionSummary`/`KpiSummary`/`DashboardMeta`/`DashboardFilter`), la **spec autoritativa** (`C:/tmp/dashboards_spec.md` §11) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). Decisión de arquitectura en [ADR-015](../../decisions/ADR-015-dashboards-materialized-aggregation.md); diseño consolidado (mockups base + cómputo del embudo) en [`design.md`](./design.md) (§8 visualizaciones, §11 UI).

> **Alineación con clinic/staff/crm/scheduling/marketing/calendar (módulos gold-standard ya en prod)**: `dashboards` reutiliza directamente los patrones que esos módulos dejaron como precedente del template y **no inventa un estilo nuevo** (regla de la metodología: consistencia con lo shippeado **>** estilo nuevo). En concreto:
> - **El panel NO es una lista con DataTable** (no hay entidad de negocio que paginar): es una **página de visualización** (KPI cards + charts) servida por RSC con prefetch + React Query, espejo de cómo `scheduling/calendario` monta su grilla bespoke (no usa `useTableQuery`, usa `useQuery` directo — lección §12 scheduling y spec §10).
> - **Los charts** son **client-only** (`"use client"`, miden el DOM) cargados con `next/dynamic({ ssr: false })` + `<Skeleton>` Fluent como fallback, **exactamente** como `CalendarGrid` de scheduling sacó su JS pesado del critical path. Heredan el theming Griffel del `FluentProvider` (cero mapeo de colores).
> - **El header con filtros** (Rango / Sede / Origen) reusa el lenguaje de toolbar de `clinic`/`scheduling` (`<Dropdown>` de sede de `GET /clinic/branches/active`, mismo que el wizard de scheduling y el mapeo de calendar) + un **badge de frescura** "Actualizado hace N min" (relativo, **client-only**) que clona el "Última revisión: hace N" de las cards de `calendar`.
> - **El embudo** (`ConversionFunnel`) es un componente **bespoke con tokens Fluent** (barras horizontales decrecientes) — precedente "bespoke dentro de Fluent" = `CalendarGrid` de scheduling — usado **solo si** `@fluentui/react-charts` no expone un `FunnelChart` nativo en la versión instalada (a verificar en F2).
> - **Los colores de los segmentos** del donut (estados de cita) y de la línea (estados de lead) salen de los **catálogos** (`appointment_status.color`, `lead_status.color`) vía `GET /dashboards/meta`, **no** hardcodeados — misma regla que los badges de `crm`/`scheduling` que leen `color` del catálogo (ADR-008). El embudo y las KPI cards, que no mapean a un solo estado, usan tokens neutrales/de marca.
> - **El aislamiento por widget** (cada chart/card falla solo con su propio `MessageBar` sin romper el panel) clona la regla **best-effort §23** que `calendar` aplicó al overlay (un fallo externo nunca rompe la grilla). Acá: un endpoint de un widget caído nunca tumba el panel entero.

> **Contexto de diseño (regla del template, no negociable)**:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Los colores que NO vienen de un catálogo (barras del embudo, fondo de KPI cards, sparkline del mini-panel chatbot, flecha de tendencia) salen de **tokens Fluent** (`tokens.colorBrandForeground1`, `tokens.colorPaletteGreenForeground1`, `tokens.colorPaletteRedForeground1`, `tokens.colorNeutralForeground2/3`, `tokens.colorNeutralStroke2`), nunca de un hex hardcodeado fuera del design system. No se introduce ninguna librería de charts fuera de **`@fluentui/react-charts`** (v9, la única dep de gráficos nueva; ADR-015 decisión #3 — resuelve la contradicción de la tesis a favor de Fluent Charts sobre Recharts).
> - **Numeric = `string` en el wire (binding, spec §1/§5)**: `KpiSummary.bot_cost_usd` y cualquier `value` monetario del rollup (`dashboard_daily_metric.value`, costo del bot, ingreso) viajan como **`string`** (Numeric(12,2) serializado). En TS se tipan `string`; el formateo con moneda/locale se hace **client-side** (`formatMoney`/`formatNumber`). Las **tasas** (`conversion_rate`, `show_rate`, …) son `float` 0-1 (o el backend ya las da en %); se formatean a `XX.X %` en el front. Los **conteos** (`count`, `total_leads`, …) son `int`. **Nunca** hacer aritmética de las tasas con `bot_cost_usd` sin parsear el string.
> - **TZ — lección recurrente de staff/crm/scheduling/marketing (binding)**: cualquier `new Date()`/`now` que afecte el render debe ser **client-only**. En dashboards esto cubre: (a) el badge **"Actualizado hace N min"** (deriva de `last_refreshed_at` con `formatRelative`, client-only — el SSR en UTC desfasaría los minutos en Lima UTC-5); (b) los **defaults de los `DatePicker`** del filtro de rango ("Últimos 30 días" = `[hoy-29, hoy]` calculado en el cliente); (c) el **eje X de la línea de evolución** — los `TimeSeriesPoint.date` son **fechas ISO sin hora** (frontera de día UTC del rollup, spec §1/§5); su label de eje se formatea **client-only** para no desfasar el día. El backend agrega por `metric_date` (frontera UTC); el front **etiqueta** en local pero **no re-bucketiza** (la agregación ya está hecha — no mezclar grano).

> **Importante (alcance, no exceder)**: el módulo es **100% lectura/agregación**. Las pantallas **NO** mutan ni una fila de negocio, no abren drawers de edición, no tienen RowActions, no tocan `compute_available_slots` ni ningún flujo de otro módulo. El panel **lee el rollup** (`dashboard_daily_metric`) vía los endpoints `/dashboards/*`; los reportes **descargan un binario** generado server-side. **Diferido** (documentado, sin pantalla aquí): dashboard por-doctor, métricas de mensajes desde Firestore, tendencia vs período anterior (flecha en las KPI cards), real-time estricto del día en curso. El **filtro por sede solo afecta de la etapa "cita" en adelante** (solo `appointment` tiene `branch_id`); las etapas previas (conversaciones, leads) son a nivel clínica → se etiqueta el caveat suave en la UI (ver más abajo, regla no-negociable).

---

## Decisión de arquitectura: dos páginas en un grupo de nav nuevo — Panel (`/dashboard`) + Reportes (`/dashboard/reportes`)

`clinic` estableció la regla, reafirmada por `scheduling`/`marketing`: **si una entidad de configuración tiene sub-recursos con interacción propia (grids editables, mapeos multi-fila, máquinas de estado), su superficie va a una página/grilla dedicada; si es ligera, va a drawer.** En `dashboards` **no hay entidad de negocio ni CRUD**: hay **dos superficies de visualización/acción**, ninguna es una lista paginada, ninguna abre drawer. El panel **reemplaza** el placeholder de bienvenida (hoy `<h1>Bienvenido</h1>` gateado por `MENU-HOME`) en `/dashboard`.

| Superficie | Dónde vive | Interacción | Patrón |
|---|---|---|---|
| **Panel de conversión** (embudo + KPIs + línea + donut + mini-panel chatbot) | **página** `/dashboard` (item de nav "Inicio"/"Panel", reemplaza el welcome) | filtros (rango/sede/origen) + refrescar; lectura pura, **sin** drawer ni mutaciones | RSC `page.tsx` (prefetch summary+funnel → `initialData`) + client con `useQuery` (NO `useTableQuery`) + charts client-only |
| **Reportes** (export PDF/Excel) | **página** `/dashboard/reportes` (child de nav, gated `REPORTS_EXPORT`) | filtros (rango/sede) + formato + secciones + "Generar y descargar"; **dispara una descarga binaria**, sin mutación de negocio | form simple (Fluent `Field`/`RadioGroup`/`Checkbox`) + Server Action que devuelve el binario |

### Por qué el Panel es una **página** (que reemplaza el welcome) y no un drawer ni un tab

El panel es la **vista raíz** de la app para Asesor/Admin (la primera pantalla útil tras el login). No es un sub-recurso de nada; es el destino del item "Inicio"/"Panel". Reemplaza el placeholder `<h1>Bienvenido</h1>` que hoy ocupa `/dashboard` (gateado por `MENU-HOME`). Tiene 5 widgets que conviven en un layout denso (KPI row + embudo central + fila línea/donut + mini-panel chatbot) — eso es una **página dedicada**, no cabe en un drawer ni en un tab. El gate de la página es `requirePermission("DASHBOARD_VIEW")` en el RSC; para usuarios **sin** `DASHBOARD_VIEW` (p.ej. DOCTOR), `/dashboard` mantiene un **welcome mínimo** (sin redirect loop — su vista operativa es "Mi agenda" en scheduling).

> Alternativas descartadas: (B) **un dashboard como drawer/modal sobre otra pantalla** — absurdo, el panel ES la pantalla raíz, no un overlay. (C) **tabs dentro de `/dashboard` (un tab por chart)** — rompe la lectura "de un vistazo" que pide HU26 (embudo + KPIs + tendencias juntos); el valor del panel es ver todo a la vez. (D) **meter los reportes como una sección más del panel** — rechazada: el export es un flujo distinto (elegir formato + secciones + generar/descargar) con su propio permiso (`REPORTS_EXPORT` ≠ `DASHBOARD_VIEW` en teoría, aunque ambos roles los tengan); va a su propia ruta `/dashboard/reportes` (mismo espíritu que `marketing` separó "Usos" del CRUD).

### Por qué Reportes es una **página hermana** y no un botón en el panel

Generar un reporte histórico (HU27) es un **flujo deliberado** (elijo rango + sede + formato + qué secciones incluir + genero) gateado por un permiso fino aparte (`REPORTS_EXPORT`). Meterlo como un botón del panel mezclaría "ver en vivo" (HU26) con "exportar histórico" (HU27) y obligaría a mostrar/ocultar el formulario de export según permiso dentro del panel. Va a `/dashboard/reportes` (child de nav gateado por `REPORTS_EXPORT`), igual que `marketing` puso "Usos" en su propia ruta. El panel **sí** puede tener un atajo `[ Exportar ]` que navega a `/dashboard/reportes` con los filtros actuales pre-cargados (diferible/opcional, no MVP).

### Por qué NO hay DataTable, drawer ni RowActions en todo el módulo

No hay entidad de negocio que listar (las únicas tablas — `dashboard_daily_metric`/`dashboard_refresh_state` — son derivadas, internas, nunca se muestran crudas). El módulo **agrega y visualiza**; no crea, edita ni borra nada de negocio. Por eso: cero `<DataTable>`, cero `<DrawerCreate/Edit>`, cero `RowActions`, cero confirmaciones destructivas. Las únicas "acciones" son **refrescar** (re-fetch del cliente, no el refresh del rollup — ese lo hace el cron) y **generar reporte** (descarga). Esto es deliberadamente más simple que cualquier módulo anterior.

## Sidebar — `NAV_ITEMS`: reemplazar el welcome por el Panel + child Reportes

> ⚠ **Textos UI en español** (ver [[feedback-medisage-spanish-ui]] en memoria global). `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

El item de nav que hoy apunta a `/dashboard` con un welcome placeholder (`key: "home"`, gateado por `MENU-HOME`) se **reapunta al Panel** y se gatea por **`DASHBOARD_VIEW`**; se le agrega un **child "Reportes"** gateado por **`REPORTS_EXPORT`**. Es el **primer** item del sidebar (la home de la app).

```ts
// reemplaza el item de bienvenida en NAV_ITEMS (primero de la lista):
{
  key: "home",                          // se mantiene el key 'home' (es la raíz); label en español
  label: "Panel",
  icon: "DataFunnelRegular",            // ← AGREGAR al iconMap del Sidebar (ver nota de íconos)
  url: "/dashboard",
  permissions: ["DASHBOARD_VIEW"],      // MENU-DASHBOARDS reservado (precedente scheduling/calendar)
  children: [
    {
      key: "reportes",
      label: "Reportes",
      icon: "DocumentTableRegular",     // ← AGREGAR al iconMap
      url: "/dashboard/reportes",
      permissions: ["REPORTS_EXPORT"],
    },
  ],
},
```

> **Gate de visibilidad (sidebar)**: igual que el precedente de `scheduling`/`calendar` (el item gatea por su **permiso fino**, no por el `MENU-*`), el item "Panel" se muestra con **`DASHBOARD_VIEW`** y el child "Reportes" con **`REPORTS_EXPORT`**; **`MENU-DASHBOARDS`** existe en el set pero queda **reservado** (no se usa para gatear, como `MENU-SCHEDULING`/`MENU-CALENDAR`). Subsets del spec §7: **ADMIN** (los 3 perms) y **ASESOR** (`DASHBOARD_VIEW` + `REPORTS_EXPORT`) ven Panel + Reportes; **DOCTOR** (ninguno del dashboard comercial) **no** ve el item — para el DOCTOR, `/dashboard` cae al welcome mínimo (sin redirect loop).
>
> Los permisos finos se chequean **dentro** de cada página: `requirePermission("DASHBOARD_VIEW")` en el RSC del panel y `requirePermission("REPORTS_EXPORT")` en el RSC de reportes (redirect/404 si falta). No hay un `<PermissionGuard>` de acción dentro del panel (no hay botones de mutación que gatear); el botón "Generar y descargar" de reportes ya está cubierto por el gate de la página entera.

> **Nota de íconos (verificación contra el iconMap de `Sidebar.tsx`)**: el iconMap **actual** del Sidebar (`components/layout/Sidebar/Sidebar.tsx`) **NO** registra ningún ícono de gráfico todavía (registra `CalendarLtrRegular`, `PlugConnectedRegular`, `BuildingMultipleRegular`, `MegaphoneRegular`, etc., pero no de charts). F0 debe **importar y agregar al iconMap** los íconos nuevos de `@fluentui/react-icons` (ya instalado): **`DataFunnelRegular`** (Panel — comunica "embudo"), **`DataPieRegular`** (distribución, por si se usa en un sub-item futuro), **`DataTrendingRegular`** (evolución/tendencia) y **`DocumentTableRegular`** (Reportes — documento tabular). Recomendado para el item raíz "Panel": `DataFunnelRegular` (el embudo es el corazón del panel); para "Reportes": `DocumentTableRegular`. Verificar que los 4 existen en la versión instalada de `@fluentui/react-icons` antes de F0 (precedente calendar: `CalendarSyncRegular` se verificó individualmente).

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / sin-datos / refetching / error / success) + tabla de componentes Fluent.

1. `/dashboard` — **Panel de conversión**: header (filtros rango/sede/origen + badge "Actualizado hace N min" + refrescar) → fila de **KPI cards** → **embudo de conversión** (centro, 6 etapas) → fila **Evolución de leads** (línea) + **Distribución de citas** (donut) → **mini-panel chatbot** (conversaciones/turnos/costo). Cada widget con estados loading/sin-datos/error **aislados**.
2. `/dashboard/reportes` — **Reportes**: filtros (rango/sede) + formato (PDF/Excel) + checkboxes de secciones + "Generar y descargar". Estado generando/error.

---

### Pantalla 1 — `/dashboard` (Panel de conversión)

Página raíz (RSC `page.tsx` con `requirePermission("DASHBOARD_VIEW")` que prefetcha `POST /dashboards/summary` + `POST /dashboards/funnel` con el filtro default ["Últimos 30 días", todas las sedes, todos los orígenes] y los pasa como `initialData` a React Query → primer render sin round-trip, ayuda al LCP/RNF-05). El client `DashboardClient` monta el header de filtros + los 5 widgets, cada uno con su propio `useQuery` (NO `useTableQuery` — no hay paginación). Los charts pesados van con `next/dynamic({ ssr:false })` + `<Skeleton>` fallback.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                              │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────────────┐  │
│ │  Sidebar   │ │  Panel de conversión                  Actualizado hace 4 min  [⟳]  │  │
│ │ ▸ Panel  █ │ │  [ Rango: Últimos 30 días ▾ ] [ Sede: Todas ▾ ] [ Origen: Todos ▾]│  │
│ │   • Report.│ │  ⓘ Conversaciones y leads son a nivel clínica; el filtro de sede   │  │
│ │ ▸ Catálogo │ │     aplica desde "Citas" en adelante.                              │  │
│ │ ▸ Clínica  │ ├──────────────────────────────────────────────────────────────────┤  │
│ │ ▸ Staff    │ │ ┌Tasa conv.┐┌ Leads ┐┌ Citas ┐┌Confirmadas┐┌Clientes┐┌Aporte bot┐│  │
│ │ ▸ Agenda   │ │ │  23.4 %  ││  412  ││  138  ││    96     ││   71   ││   58 %   ││  │
│ │ ▸ Marketing│ │ │ ▲ vs ant.││ leads ││ citas ││ confirmad.││ nuevos ││ de citas ││  │
│ │            │ │ └──────────┘└───────┘└───────┘└───────────┘└────────┘└──────────┘│  │
│ │            │ ├──────────────────────────────────────────────────────────────────┤  │
│ │            │ │  EMBUDO DE CONVERSIÓN                                              │  │
│ │            │ │  Conversaciones        ████████████████████████  412              │  │
│ │            │ │  Leads                 ██████████████████        356   86 %       │  │
│ │            │ │  Contactados/Interes.  ████████████              241   68 %       │  │
│ │            │ │  Citas agendadas       ████████                  138   57 %       │  │
│ │            │ │  Citas confirmadas     █████                      96   70 %       │  │
│ │            │ │  Clientes              ███                         71   74 %       │  │
│ │            │ ├───────────────────────────────────┬──────────────────────────────┤  │
│ │            │ │  EVOLUCIÓN DE LEADS               │  DISTRIBUCIÓN DE CITAS         │  │
│ │            │ │   leads/día                       │        ╭───────╮               │  │
│ │            │ │  60┤      ╱╲      ╱╲╱╲             │       ╱  total  ╲              │  │
│ │            │ │  40┤   ╱╲╱  ╲╱╲╱╲╱    ╲___        │      │   138    │              │  │
│ │            │ │  20┤ ╱                            │       ╲  citas  ╱               │  │
│ │            │ │   0┴────────────────────────      │        ╰───────╯               │  │
│ │            │ │   01jun        15jun       30jun  │  ● Agendada 22  ● Confirmada 18│  │
│ │            │ │   ─ Nuevos  ─ Interesados  ─ Cita │  ● Atendida 71  ● No asistió 9 │  │
│ │            │ │                                   │  ● Cancelada 12 ● Reagendada 6 │  │
│ │            │ ├───────────────────────────────────┴──────────────────────────────┤  │
│ │            │ │  CHATBOT          Conversaciones 238 · Turnos 1 204 · Costo $4.12  │  │
│ │            │ │   atención del bot   ▁▂▃▅▇▆▅▃▂▁▂▃▅   58 % de las citas vienen del bot│ │
│ └────────────┘ └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Header de la página**:
- Título = "Panel de conversión" (o "Panel" a secas en el sidebar). No lleva subtítulo descriptivo largo; el valor está en los widgets.
- **Badge de frescura** (arriba a la derecha): `"Actualizado hace {N} min"` derivado de `DashboardMeta.last_refreshed_at` (de `GET /dashboards/meta`), formateado con `formatRelative` **client-only** (reusa el helper de crm/calendar). Si `last_refreshed_at` es `null` → "Aún sin actualizar". Tooltip con la fecha/hora absoluta. Si la frescura supera con holgura el intervalo de refresco (p.ej. > 3× el intervalo, señal de job caído), el badge cambia a `tokens.colorPaletteYellowForeground1` con tooltip "El panel puede estar desactualizado." (degradación con gracia — el panel **sigue** mostrando el último rollup bueno, nunca se rompe).
- **Botón refrescar** `[⟳]` (`<Button appearance="subtle" icon={<ArrowSyncRegular />}>`): **NO** dispara el refresh del rollup (eso es el cron con shared-secret). Hace `queryClient.invalidateQueries(['dashboards'])` → re-fetch de los 5 widgets desde el rollup. Tooltip "Actualizar panel". Mientras refetchea, el ícono gira (`<Spinner size="tiny">` o el ícono animado) y los widgets entran en estado refetching (ver abajo).
- **Filtros** (fila debajo del título), todos sincronizados a la URL (`nuqs`, mismo patrón que los filtros chip de las listas) para ser deep-linkables y sobrevivir refresh:
  - **`[ Rango ▾ ]`** — `<Dropdown>` de presets ("Hoy", "Últimos 7 días", "Últimos 30 días" [default], "Este mes", "Personalizado…"). "Personalizado…" abre dos `<DatePicker>` (desde/hasta). Mapea a `DashboardFilter.date_from`/`date_to`. **Default = Últimos 30 días** calculado **client-only** (`[hoy-29, hoy]`). Validación client-side espejo del backend: `date_to >= date_from`, rango ≤ 366 días (spec §5/§8) — si el usuario excede el rango, mostrar `<MessageBar intent="error">"El rango no puede superar un año."` y no disparar la query.
  - **`[ Sede ▾ ]`** — `<Dropdown>` de `DashboardMeta.branches` (de `/meta`) + opción **"Todas"** (`branch_id = null`). Mapea a `DashboardFilter.branch_id`. **Caveat de sede** (regla no-negociable, ver nota suave abajo).
  - **`[ Origen ▾ ]`** — `<Dropdown>` de `DashboardMeta.sources` (de `/meta`: `bot`/`advisor`/…) + opción **"Todos"** (`source = null`). Mapea a `DashboardFilter.source`. Etiquetas en español ("Chatbot" para `bot`, "Asesor" para `advisor`).
- **Nota suave del caveat de sede** (binding, spec §13 / design §4 caveat 4): cuando el filtro de **Sede ≠ "Todas"**, mostrar un `<MessageBar intent="info">` (o un texto fino con ícono `<InfoRegular />`) debajo de los filtros: **"Conversaciones y leads son a nivel clínica; el filtro de sede aplica desde \"Citas\" en adelante."** Esto explica por qué las primeras etapas del embudo (Conversaciones, Leads, Contactados) **no** cambian al filtrar por sede (solo `appointment` tiene `branch_id`). Cuando Sede = "Todas", la nota puede ocultarse (no aplica). **No** es un error ni bloquea nada — es contexto honesto.

#### Widget 1 — KPI cards (`KpiCardsRow`)

Una fila de tarjetas (`<Card>` + `<Text>` de `@fluentui/react-components`), una por KPI escalar de `KpiSummary` (de `POST /dashboards/summary`). Cada card: **valor grande** (número/porcentaje) + **etiqueta** abajo (en español) + opcional **flecha de tendencia** vs período anterior (▲ verde / ▼ rojo con `tokens.colorPaletteGreen/RedForeground1` — **diferible**, default sin flecha; documentado pero no MVP).

| KPI (card) | Fuente (`KpiSummary`) | Formato | Etiqueta ES |
|---|---|---|---|
| **Tasa de conversión** | `conversion_rate` | `XX.X %` | "Tasa de conversión" |
| **Leads** | `total_leads` | entero | "Leads" |
| **Citas** | `total_appointments` | entero | "Citas" |
| **Confirmadas** | `total_confirmed` | entero | "Confirmadas" |
| **Clientes nuevos** | `total_customers` | entero | "Clientes" |
| **Aporte del bot** | `chatbot_share` (`conversations_bot/total_conversations` ó `% citas source=bot`) | `XX %` | "Aporte bot" |

> El número se formatea client-side (`formatNumber`/`Intl.NumberFormat` con locale `es-PE`); los porcentajes a `XX.X %`. `bot_cost_usd` (string) NO va en una KPI card de la fila superior — va en el mini-panel chatbot (formateado `$X.XX`). Las cards son **lectura pura**: no son clicables, no abren nada (diferible: clic → drill-down al detalle de esa métrica).

#### Widget 2 — Embudo de conversión (`ConversionFunnel`, centro)

El widget protagonista. Renderiza las **6 etapas** de `FunnelSummary.stages` (de `POST /dashboards/funnel`) como **barras horizontales decrecientes**: cada `FunnelStage { key, label, count, rate_from_prev, color }` es una barra cuyo ancho ∝ `count` (relativo a la etapa 1 = 100 %), con el **conteo** a la derecha y el **`rate_from_prev`** (% vs etapa previa) como anotación. La primera etapa no tiene `rate_from_prev` (es la base).

```
│  EMBUDO DE CONVERSIÓN                                              │
│  Conversaciones        ████████████████████████  412              │  ← etapa 1 (base, 100 %)
│  Leads                 ██████████████████        356   86 %       │  ← 356/412
│  Contactados/Interes.  ████████████              241   68 %       │  ← 241/356
│  Citas agendadas       ████████                  138   57 %       │  ← 138/241
│  Citas confirmadas     █████                      96   70 %       │  ← 96/138
│  Clientes              ███                         71   74 %       │  ← 71/96
```

- **Componente**: `FunnelChart` de `@fluentui/react-charts` **si la versión instalada lo expone**; si no, un componente **bespoke `ConversionFunnel`** (barras horizontales con `makeStyles` + tokens Fluent, ancho proporcional al `count`) — fallback seguro, precedente bespoke = `CalendarGrid`. **A decidir al instalar la dep en F2** (decisión abierta, design §15).
- **Color de las barras**: cada etapa puede traer `FunnelStage.color` del backend (p.ej. la etapa "Citas confirmadas" hereda el color del estado de cita correspondiente); si `color` es `null`, usar un degradado de `tokens.colorBrandForeground1`/`tokens.colorBrandBackground2` (las barras del embudo NO mapean 1:1 a un solo estado de catálogo, así que el default es de marca, no hardcodeado). **Nunca** un hex fuera del design system.
- **Sub-conteo chatbot** (opcional, diferible): la etapa "Conversaciones" puede mostrar un sub-segmento "(de los cuales {N} del bot)" leyendo `conversations_bot`; la etapa "Citas agendadas" un "(de los cuales {N} del bot)" leyendo el sub-conteo `source='bot'`. Default: solo el total; el sub-conteo es una anotación fina diferible.
- **Tooltip por etapa**: `<Tooltip>` con `"{label}: {count} ({rate_from_prev} % vs etapa previa)"`.
- **Tasa de conversión global** (KPI HU26 = `lead_stage[CITA_AGENDADA]/leads_created`): ya está en la KPI card "Tasa de conversión"; el embudo muestra las tasas **etapa-a-etapa**, no la global.

#### Widget 3 — Evolución de leads (`LeadsEvolutionChart`, línea)

`LineChart` (o `AreaChart`) de `@fluentui/react-charts` sobre `TimeSeries` (de `POST /dashboards/leads-evolution`). Eje X = días (`TimeSeriesPoint.date`, ISO sin hora, etiquetado **client-only** en local); una **serie por estado de lead** (`TimeSeries.series[] { key, label, color }` — los colores salen del catálogo `lead_status.color` vía `/meta`, NO hardcodeados). Cada `TimeSeriesPoint.values` es `dict[lead_status_code → count]`.

- **Series default**: "Nuevos", "Interesados/Contactados", "Cita agendada" (o las que el backend devuelva por `lead_status_code`). Leyenda debajo con los colores del catálogo.
- **Eje X**: días del rango; el label se formatea client-only (`01 jun`, `15 jun`, …) para no desfasar el día en Lima. **No** re-bucketizar en el front (el rollup ya agregó por `metric_date`).
- **Eje Y**: leads/día (entero).
- **Client-only** (`next/dynamic({ssr:false})` + `<Skeleton>` fallback).

#### Widget 4 — Distribución de citas (`AppointmentsDistributionDonut`, donut)

`DonutChart` de `@fluentui/react-charts` sobre `DistributionSummary` (de `POST /dashboards/appointments-distribution`). Cada `DistributionBucket { code, label, color, count }` es un segmento; el **centro** muestra `DistributionSummary.total` ("{total} citas"). Los **colores de los segmentos salen del catálogo `appointment_status.color`** (vía el `bucket.color`, que el backend resuelve del catálogo — ADR-008), **nunca** hardcodeados.

- **Segmentos**: los estados de cita del rango+sede (Agendada/Confirmada/Atendida/No asistió/Cancelada/Reagendada — `label` del catálogo en español). Leyenda al lado con `● {label} {count}`.
- **Centro del donut**: total de citas del rango+sede.
- **Filtro de sede**: este widget **SÍ** respeta el filtro de sede (las citas tienen `branch_id`) — al contrario de las etapas previas del embudo. (Coherente con el caveat de sede.)
- **Client-only** (`next/dynamic({ssr:false})` + `<Skeleton>` fallback).

#### Widget 5 — Mini-panel chatbot (`ChatbotMiniPanel`)

Resalta el aporte del chatbot (eje de la tesis). Una `<Card>` con cifras (`<Text>`) + un sparkline opcional (`LineChart`/`AreaChart` chico de conversaciones del bot por día):
- **Conversaciones** del bot (`KpiSummary.conversations_bot`).
- **Turnos** (`KpiSummary.bot_turns`, de `bot_event WHERE event_type='turn_completed'`).
- **Costo** estimado (`KpiSummary.bot_cost_usd`, **string** → formatear `$X.XX` client-side; nunca aritmética sin parsear).
- **Aporte** (`% de citas con source='bot'`, derivado o de `chatbot_share`).

> El "nº de mensajes" **NO** se muestra (los mensajes viven en Firestore, ADR-011, no son agregables en SQL — spec §13 / design §7). Se usan conversaciones + turnos del bot como proxies. Si en el futuro se agrega un read-model de Firestore, este panel suma "mensajes" (diferido, no MVP).

#### Estados (Pantalla 1) — **aislados por widget** (regla no-negociable, lección §23)

Cada widget (KPI row, embudo, línea, donut, mini-panel) tiene su **propio** `useQuery` y maneja sus estados **independientemente** → un endpoint caído **no rompe el panel**, solo su widget muestra error + reintentar. **Nunca** un spinner global ni un error de página completa por culpa de un widget.

- **Loading (primera carga)**: **skeletons por widget** (no spinner global). KPI cards = `<Skeleton>` con 6 `<SkeletonItem>` rectangulares; embudo = 6 barras-skeleton; línea/donut = `<Skeleton>` del tamaño del chart (el `next/dynamic` fallback). El prefetch del RSC (summary+funnel) evita ver el skeleton de esos dos en el primer load; línea/donut/meta sí pueden parpadear su skeleton (se cargan client-side).
- **Sin datos (rollup vacío en el rango)** (spec §8: lecturas con rollup vacío → conteos 0, **NO** error): cada widget muestra un **estado sin-datos** propio — `<EmptyState>` chico con ilustración + **"No hay datos en el rango seleccionado"**. El embudo muestra 6 etapas en 0; el donut un anillo gris con "0 citas"; la línea un eje vacío con la leyenda "No hay datos en el rango seleccionado". (El backend devuelve 0, no 4xx — el front distingue "0 real" de "error".)
- **Refetching (tras cambiar filtro / refrescar)**: cada widget mantiene lo visible con `opacity: 0.55` + un `<Spinner size="tiny">` en su esquina (mismo patrón que el refetching de las cards de calendar). **No** se vacía el widget mientras llega el dato nuevo (evita el flash a skeleton).
- **Error (un endpoint de widget falló)**: **solo ese widget** muestra `<MessageBar intent="error">` con un `[ Reintentar ]` que re-corre su `useQuery` (`refetch()`). Copy: "No se pudo cargar {widget}. Reintentar." El resto del panel sigue funcional. (Esto es el clon directo del aislamiento best-effort de calendar.)
- **Rango inválido (client-side)**: si el usuario arma un rango > 366 días o `date_to < date_from`, el panel **no dispara** las queries y muestra `<MessageBar intent="error">"El rango no puede superar un año."` / "La fecha final no puede ser anterior a la inicial." sobre los filtros (espejo de `DASHBOARD_INVALID_DATE_RANGE`, 400). Los widgets quedan con el último dato válido (no se vacían).
- **Sin permiso (`DASHBOARD_VIEW` ausente, p.ej. DOCTOR)**: el RSC no llega a renderizar el panel — `/dashboard` muestra el **welcome mínimo** (`<h1>Bienvenido</h1>` o similar) sin redirect loop. El item de nav "Panel" no aparece para ese usuario.

#### Componentes Fluent UI (Pantalla 1)

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Header | `<h1 className={styles.title}>` "Panel de conversión" |
| Badge "Actualizado hace N min" | `<Badge appearance="tint">` + `formatRelative(last_refreshed_at)` (client-only) + `<Tooltip>` con fecha absoluta; color `warning` si stale |
| Botón refrescar | `<Button appearance="subtle" icon={<ArrowSyncRegular />}>` → `queryClient.invalidateQueries(['dashboards'])` |
| Filtro rango | `<Dropdown>` de presets + `<DatePicker>` ×2 para "Personalizado…" (default "Últimos 30 días", client-only) |
| Filtro sede | `<Dropdown>` de `DashboardMeta.branches` + opción "Todas" (null) |
| Filtro origen | `<Dropdown>` de `DashboardMeta.sources` + opción "Todos" (null) |
| Caveat de sede | `<MessageBar intent="info">` (o texto fino + `<InfoRegular />`) cuando Sede ≠ "Todas" |
| KPI card | `<Card>` + `<Text size={700} weight="semibold">` (valor) + `<Text size={200}>` (etiqueta) |
| Flecha de tendencia (diferible) | `<ArrowUpRegular/ArrowDownRegular>` con `tokens.colorPaletteGreen/RedForeground1` |
| Embudo | `FunnelChart` (`@fluentui/react-charts`) **o** `ConversionFunnel` bespoke (`makeStyles` + tokens, barras horizontales decrecientes) — fallback |
| Línea de evolución | `LineChart`/`AreaChart` (`@fluentui/react-charts`), colores de `lead_status.color` (catálogo) — `next/dynamic({ssr:false})` |
| Donut de distribución | `DonutChart` (`@fluentui/react-charts`), colores de `appointment_status.color` (catálogo) — `next/dynamic({ssr:false})` |
| Mini-panel chatbot | `<Card>` + `<Text>` (cifras) + `LineChart`/`AreaChart` sparkline opcional |
| Tooltip de etapa/segmento | `<Tooltip>` |
| Leyenda (línea/donut) | leyenda nativa de Fluent Charts (colores del catálogo) |
| Skeleton (por widget) | `<Skeleton>` + `<SkeletonItem>` (NO spinner global) |
| Sin datos (por widget) | `<EmptyState>` chico + "No hay datos en el rango seleccionado" |
| Error (por widget aislado) | `<MessageBar intent="error">` + `<Button>` "Reintentar" (`refetch()`) |
| Refetching | `opacity: 0.55` + `<Spinner size="tiny">` por widget |
| Data fetch | `useQuery` (React Query, `staleTime`≈`refetchInterval`≈intervalo de refresco; NO `useTableQuery`) |

---

### Pantalla 2 — `/dashboard/reportes` (Reportes)

Página simple (RSC `page.tsx` con `requirePermission("REPORTS_EXPORT")`; prefetcha `GET /dashboards/meta` para los selects de sede). Un **formulario** de configuración del reporte (rango + sede + formato + secciones) con un único botón "Generar y descargar". **No** muestra datos ni charts — solo configura y dispara la descarga del binario que genera el backend (server-side, HU27).

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                              │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────────────┐  │
│ │  Sidebar   │ │  Reportes                                                         │  │
│ │ ▾ Panel    │ │  Genera un reporte histórico de conversiones y conversaciones.    │  │
│ │   • Report.█│ │                                                                   │  │
│ │ ▸ Catálogo │ │  ┌──────────────────────────────────────────────────────────────┐│  │
│ │ ▸ Clínica  │ │  │ Rango        [ 01/06/2026  –  30/06/2026  ▾ ]                  ││  │
│ │            │ │  │ Sede         [ Todas                       ▾ ]                  ││  │
│ │            │ │  │                                                                ││  │
│ │            │ │  │ Formato      ( • ) PDF      (   ) Excel                        ││  │
│ │            │ │  │                                                                ││  │
│ │            │ │  │ Incluir      ☑ KPIs                                            ││  │
│ │            │ │  │              ☑ Embudo de conversión                           ││  │
│ │            │ │  │              ☑ Distribución de citas                          ││  │
│ │            │ │  │              ☑ Evolución de leads                             ││  │
│ │            │ │  │                                                                ││  │
│ │            │ │  │                              [ Generar y descargar ⬇ ]        ││  │
│ │            │ │  └──────────────────────────────────────────────────────────────┘│  │
│ └────────────┘ └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Campos del formulario** (`<Field>` por fila):
- **Rango** — mismo control de rango del panel (`<Dropdown>` de presets + `<DatePicker>` ×2 para "Personalizado…"). Default = "Este mes" o "Últimos 30 días" (client-only). Misma validación (`date_to >= date_from`, ≤ 366 días). Mapea a `DashboardFilter.date_from`/`date_to`.
- **Sede** — `<Dropdown>` de `DashboardMeta.branches` + "Todas" (null). Mapea a `DashboardFilter.branch_id`. (El caveat de sede aplica igual: las secciones de conversaciones/leads del reporte son a nivel clínica; opcional repetir la nota suave.)
- **Formato** — `<RadioGroup>` con dos `<Radio>`: **PDF** (default) / **Excel**. Mapea a `{ format: 'pdf' | 'excel' }`. (Si el backend recibe otro valor → `REPORT_FORMAT_NOT_SUPPORTED`, 400 — pero el `RadioGroup` ya lo limita a los dos válidos.)
- **Incluir** (secciones) — 4 `<Checkbox>`: **KPIs** / **Embudo de conversión** / **Distribución de citas** / **Evolución de leads** (todos marcados por default). Mapea a `{ sections: string[] }` (códigos en inglés: `kpis`/`funnel`/`distribution`/`evolution`; etiquetas en español). Al menos una sección debe estar marcada (validación client-side: si 0 → deshabilitar "Generar" + hint "Selecciona al menos una sección.").

**Acción "Generar y descargar"** (`<Button appearance="primary" icon={<ArrowDownloadRegular />}>`):
- Dispara una **Server Action** `generateReport(filter, format, sections)` que llama `POST /dashboards/report` (Bearer JWT, gated `REPORTS_EXPORT`), recibe el **binario** (`application/pdf` | `xlsx`) + `Content-Disposition` (filename) y lo entrega como **descarga** al navegador (el front no parsea el binario, solo lo descarga — coherente con "el browser nunca habla con FastAPI directo": el binario pasa por el server de Next).
- Tras éxito: toast `"Reporte generado."` (la descarga la dispara el navegador). **No** hay `revalidateTag` (no hay mutación de negocio — es una lectura/export).

#### Estados (Pantalla 2)

- **Idle (default)**: formulario con los defaults (rango "Este mes", sede "Todas", formato PDF, las 4 secciones marcadas), botón "Generar y descargar" habilitado.
- **Generando**: botón con **spinner + deshabilitado** (`<Button disabled icon={<Spinner size="tiny" />}>` con texto **"Generando…"**); el resto del form se deshabilita para evitar cambios a mitad de la generación. (El PDF/Excel se genera server-side; puede tardar unos segundos.)
- **Éxito**: la descarga arranca (el navegador guarda el archivo); toast `"Reporte generado."`; el botón vuelve a habilitarse.
- **Error**: `<MessageBar intent="error">` arriba del form con el `detail` del backend en español (tabla abajo); el botón vuelve a habilitarse (se puede reintentar). **Nunca** deja el botón colgado en "Generando…" tras un error.
- **Rango inválido (client-side)**: mismo manejo que el panel — no dispara la action, muestra `<MessageBar intent="error">"El rango no puede superar un año."` / "La fecha final no puede ser anterior a la inicial."
- **Sin secciones**: botón deshabilitado + hint "Selecciona al menos una sección."
- **Sin permiso (`REPORTS_EXPORT` ausente)**: el RSC redirige/404 (`requirePermission`); el child "Reportes" no aparece en el sidebar.

#### Mapeo de códigos de error → mensaje en español (Reportes)

Las acciones devuelven `{ ok:false, error }` con el `detail` ya en español del backend. La UI mapea el `code` (spec §8) a copy:

| `code` (spec §8) | Copy en español (MessageBar) |
|---|---|
| `DASHBOARD_INVALID_DATE_RANGE` (400) | "El rango de fechas no es válido (la fecha final debe ser posterior a la inicial y el rango no puede superar un año)." |
| `REPORT_FORMAT_NOT_SUPPORTED` (400) | "Ese formato de reporte no está disponible." |
| (error de red genérico) | "No se pudo generar el reporte. Inténtalo de nuevo." |

> `DASHBOARD_REFRESH_SECRET_INVALID` (401) **NO** se mapea en la UI: es el error del endpoint interno `/dashboards/internal/refresh` (shared-secret, Cloud Scheduler), que **no** tiene pantalla — nunca lo dispara el navegador. Se documenta en backend.md, no en la UI.

#### Componentes Fluent UI (Pantalla 2)

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Header | `<h1 className={styles.title}>` "Reportes" + `<p className={styles.subtitle}>` "Genera un reporte histórico de conversiones y conversaciones." |
| Contenedor del form | `<Card>` (un solo bloque, no drawer) |
| Campo rango | `<Field label="Rango">` + `<Dropdown>` presets + `<DatePicker>` ×2 ("Personalizado…") |
| Campo sede | `<Field label="Sede">` + `<Dropdown>` de `DashboardMeta.branches` + "Todas" (null) |
| Campo formato | `<Field label="Formato">` + `<RadioGroup>` con `<Radio value="pdf">` / `<Radio value="excel">` |
| Campo secciones | `<Field label="Incluir">` + 4 `<Checkbox>` (KPIs/Embudo/Distribución/Evolución) |
| Generar y descargar | `<Button appearance="primary" icon={<ArrowDownloadRegular />}>` → Server Action `generateReport` (devuelve binario para descargar) |
| Estado generando | `<Button disabled icon={<Spinner size="tiny" />}>` "Generando…" + form deshabilitado |
| Éxito | `toast("Reporte generado.")` (la descarga la dispara el navegador) |
| Error | `<MessageBar intent="error">` con el `detail` en español |
| Validación (rango / secciones) | client-side espejo del backend (`date_to>=date_from`, ≤366d, ≥1 sección) |

---

## Decisiones de UI (cierres)

### El Panel reemplaza el welcome y es la home; Reportes es una página hermana

`/dashboard` deja de ser un placeholder `<h1>Bienvenido</h1>` y pasa a ser el **Panel de conversión** (la primera pantalla útil tras el login para Asesor/Admin), gateado por `DASHBOARD_VIEW`. Para usuarios sin ese permiso (DOCTOR), `/dashboard` mantiene un **welcome mínimo** (sin redirect loop — su vista operativa es "Mi agenda"). Reportes va a `/dashboard/reportes` (child de nav gateado por `REPORTS_EXPORT`), separado del panel porque es un flujo distinto (export histórico, HU27 ≠ ver en vivo HU26).

### Sin DataTable, drawer ni RowActions — es visualización, no CRUD

El módulo no tiene entidad de negocio que listar/editar/borrar. Cero `<DataTable>`, cero drawer, cero `RowActions`, cero confirmaciones destructivas. Las tablas internas (`dashboard_daily_metric`/`dashboard_refresh_state`) son derivadas y nunca se muestran crudas. Es deliberadamente más simple que cualquier módulo anterior.

### Charts = `@fluentui/react-charts`, client-only, fuera del critical path

Una sola dep de gráficos nueva (`@fluentui/react-charts`, v9 — ADR-015 #3, resuelve la contradicción de la tesis a favor de Fluent Charts sobre Recharts: comparte tokens Griffel con todo el stack → cero fricción de theming). Todos los charts son `"use client"` + `next/dynamic({ ssr:false })` + `<Skeleton>` fallback → su JS sale del critical path (ayuda al LCP/RNF-05; las KPI cards de texto pintan primero). Precedente "bespoke dentro de Fluent" para el embudo = `CalendarGrid` de scheduling.

### Colores de segmentos = catálogos, nunca hardcodeados (ADR-008)

Los colores del **donut** (estados de cita) y de la **línea** (estados de lead) salen de `appointment_status.color` / `lead_status.color` vía `GET /dashboards/meta` (que el backend resuelve del catálogo configurable). El **embudo** y las **KPI cards** —que no mapean a un solo estado— usan tokens de marca/neutrales (`tokens.colorBrandForeground1`, etc.). **Nunca** un hex fuera del design system. Si negocio cambia el color de un estado en el catálogo, el chart lo refleja sin tocar código.

### Aislamiento por widget — un fallo nunca rompe el panel (lección §23)

Cada widget tiene su propio `useQuery` y su propio ciclo loading/sin-datos/error. Un endpoint caído muestra `<MessageBar>` + "Reintentar" **solo en ese widget**; el resto del panel sigue funcional. **Nunca** un spinner global ni un error de página completa por culpa de un widget. Clon directo del aislamiento best-effort que `calendar` aplicó al overlay.

### "Sin datos" ≠ "error" — el rollup vacío devuelve 0, no 4xx

El backend (spec §8) devuelve conteos en 0 cuando el rollup está vacío en el rango (no un 4xx). El front distingue: 0 real → `<EmptyState>` "No hay datos en el rango seleccionado" por widget (embudo en 0, donut gris, línea vacía); error de red/servidor → `<MessageBar intent="error">` + reintentar. No confundir un período sin actividad con un fallo.

### Caveat de sede explícito (filtro parcial, design §4 caveat 4)

El filtro de sede solo afecta **de la etapa "cita" en adelante** (solo `appointment` tiene `branch_id`); las etapas previas (conversaciones, leads, contactados) son a nivel clínica. Cuando el usuario filtra por una sede concreta, una **nota suave** (`<MessageBar intent="info">`) lo explica: las primeras etapas del embudo no cambian al filtrar por sede. Es honestidad de producto, no un error — evita que el usuario crea que "su sede tuvo X conversaciones" cuando ese número es de toda la clínica.

### Frescura honesta — "Actualizado hace N min", no "tiempo real" mentiroso

El panel lee el rollup materializado (refrescado por cron cada ~10 min); muestra **"Actualizado hace N min"** (de `last_refreshed_at`, client-only) en vez de fingir tiempo real al segundo. El botón refrescar re-fetchea el rollup (no recomputa). Si la frescura supera con holgura el intervalo (job caído), el badge se pone amarillo pero el panel **sigue** sirviendo el último rollup bueno (degrada con gracia). Reconcilia "tiempo real" de HU26 con la arquitectura materializada (ADR-015 #2).

### Reportes server-side — el front solo descarga (HU27)

El PDF/Excel se genera en el backend (`POST /dashboards/report`, server-side, mejor fidelidad de figuras + bundle del front liviano); la página `/dashboard/reportes` solo configura (rango/sede/formato/secciones) y dispara una Server Action que entrega el binario como descarga. Coherente con "el browser nunca habla con FastAPI directo".

### Sin i18n framework por ahora

Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm/scheduling/marketing/calendar). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive

Mismo criterio que los módulos previos (template optimizado para desktop interno): sidebar colapsado por default; en pantallas angostas la **fila de KPI cards** envuelve (wrap a 2-3 por fila), la fila **línea + donut** apila vertical, y los charts heredan el comportamiento responsive de `@fluentui/react-charts` (miden su contenedor). El **embudo** (barras horizontales) escala bien en angosto. No se diseñan pantallas mobile-first separadas.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, `metric`, `segment`, slugs, `source`/`format` values, CSS classes) en inglés — solo los textos visibles van traducidos. Glosario clave: **Panel** (de conversión), **Embudo de conversión**, **Tasa de conversión**, **Leads** (masculino, "los leads"), **Citas** (femenino, "las citas"), **Confirmadas** (citas confirmadas), **Clientes**, **Conversaciones**, **Distribución de citas**, **Evolución de leads**, **Aporte del bot** / **Chatbot**, **Reporte** (masculino, "el reporte"), **Sin datos**, **Actualizado hace N min**.

### Glosario / concordancia de género

- **Panel / Embudo / Reporte / Aporte / Origen / Formato** son **masculino**: "el panel", "el embudo", "un reporte histórico", "el aporte del bot", "el origen", "el formato".
- **Tasa / Sede / Conversación / Cita / Distribución / Evolución / Sección** son **femenino**: "la tasa de conversión", "la sede", "las conversaciones", "las citas", "la distribución de citas", "la evolución de leads", "al menos una sección".
- **Lead** se trata como **masculino** ("los leads", "el lead"); **Cliente** masculino genérico ("los clientes nuevos").
- **Conversaciones confirmadas/agendadas/atendidas** → concordancia femenina con "citas": "Citas **confirmadas**", "Citas **agendadas**", "Citas **atendidas**".

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Sidebar — | |
| Item raíz | "Panel" |
| Child | "Reportes" |
| — Panel (Pantalla 1) — | |
| Page title | "Panel de conversión" |
| Badge frescura | "Actualizado hace {N} min" |
| Frescura nula | "Aún sin actualizar" |
| Tooltip refrescar | "Actualizar panel" |
| Filtro rango (presets) | "Hoy" / "Últimos 7 días" / "Últimos 30 días" / "Este mes" / "Personalizado…" |
| Filtro rango (labels) | "Desde" / "Hasta" |
| Filtro sede | "Sede" + opción "Todas" |
| Filtro origen | "Origen" + opciones "Todos" / "Chatbot" / "Asesor" |
| Caveat de sede | "Conversaciones y leads son a nivel clínica; el filtro de sede aplica desde \"Citas\" en adelante." |
| KPI etiquetas | "Tasa de conversión" / "Leads" / "Citas" / "Confirmadas" / "Clientes" / "Aporte bot" |
| Sub-etiqueta KPI (opcional) | "vs. período anterior" |
| Título embudo | "Embudo de conversión" |
| Etiquetas etapas | "Conversaciones" / "Leads" / "Contactados/Interesados" / "Citas agendadas" / "Citas confirmadas" / "Clientes" |
| Tooltip etapa | "{etapa}: {conteo} ({tasa} % vs etapa previa)" |
| Título línea | "Evolución de leads" |
| Eje Y línea | "leads/día" |
| Título donut | "Distribución de citas" |
| Centro donut | "{total} citas" |
| Leyenda donut | "● {estado} {conteo}" |
| Título mini-panel | "Chatbot" / "Atención del bot" |
| Cifras chatbot | "Conversaciones {N} · Turnos {N} · Costo {$X.XX}" |
| Aporte chatbot | "{N} % de las citas vienen del bot" |
| — Estados (panel) — | |
| Sin datos (por widget) | "No hay datos en el rango seleccionado" |
| Error (por widget) | "No se pudo cargar {widget}. Reintentar." |
| Botón reintentar | "Reintentar" |
| Rango muy largo | "El rango no puede superar un año." |
| Fecha final inválida | "La fecha final no puede ser anterior a la inicial." |
| Panel desactualizado (badge amarillo) | "El panel puede estar desactualizado." |
| — Reportes (Pantalla 2) — | |
| Page title | "Reportes" |
| Page subtitle | "Genera un reporte histórico de conversiones y conversaciones." |
| Campo rango | "Rango" |
| Campo sede | "Sede" |
| Campo formato | "Formato" + "PDF" / "Excel" |
| Campo secciones | "Incluir" |
| Secciones | "KPIs" / "Embudo de conversión" / "Distribución de citas" / "Evolución de leads" |
| Botón generar | "Generar y descargar" |
| Botón generando | "Generando…" |
| Hint sin secciones | "Selecciona al menos una sección." |
| Toast éxito | "Reporte generado." |
| Error formato | "Ese formato de reporte no está disponible." |
| Error rango | "El rango de fechas no es válido (la fecha final debe ser posterior a la inicial y el rango no puede superar un año)." |
| Error genérico | "No se pudo generar el reporte. Inténtalo de nuevo." |
| — Común — | |
| Loading placeholder | "Cargando…" |
| Error de red genérico | "No se pudo cargar la información. Intenta de nuevo." |

### Etiquetas de origen (`source`) y formato (`format`)

`value` (enum) en inglés, etiqueta visible en español/comercial:

| `value` | Etiqueta | Contexto |
|---|---|---|
| `bot` | "Chatbot" | filtro Origen, atribución del embudo, mini-panel |
| `advisor` | "Asesor" | filtro Origen |
| `pdf` | "PDF" | formato de reporte |
| `excel` | "Excel" | formato de reporte |

### Etiquetas de estado (segmentos de los charts) — del catálogo, no fijas

Las etiquetas de los **estados de cita** (donut) y **estados de lead** (línea) salen del **catálogo** (`appointment_status.name`/`color`, `lead_status.name`/`color` vía `/meta`) — el módulo **no** las hardcodea (ADR-008). Ejemplos visibles hoy (en español, del seed): citas = "Agendada / Confirmada / Atendida / No asistió / Cancelada / Reagendada"; leads = "Nuevo / Intentando contactar / Contactado / Interesado / Evaluando / Cita agendada / No interesado". Si el catálogo cambia un nombre o color, el chart lo refleja sin tocar la UI.

### Sin i18n framework por ahora

Los textos están **directos como strings en cada componente**. Si negocio pide soporte multilingüe, introducir `next-intl` o similar después. Postergado (misma decisión que catalog/clinic/staff/crm/scheduling/marketing/calendar).

## Mapeo a fases de implementación (checklist de UI F0–F3)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md), [`design.md`](./design.md) §14 y la spec §12 F0–F3; diferidas D1–D4 = roadmap, sin UI).

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: reapuntar el item raíz `home` → "Panel" (`/dashboard`, gate `["DASHBOARD_VIEW"]`, `MENU-DASHBOARDS` reservado) + child "Reportes" (`/dashboard/reportes`, gate `["REPORTS_EXPORT"]`); **registrar `DataFunnelRegular`/`DataPieRegular`/`DataTrendingRegular`/`DocumentTableRegular` en el iconMap de `Sidebar.tsx`** (importarlos de `@fluentui/react-icons`; verificar que existen en la versión instalada).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.DASHBOARDS` (FUNNEL, LEADS_EVOLUTION, APPOINTMENTS_DISTRIBUTION, SUMMARY, META, REPORT).
- [ ] `types/dashboards.types.ts`: interfaces espejo de Pydantic (`DashboardFilter`, `FunnelStage`/`FunnelSummary`, `TimeSeriesPoint`/`TimeSeries`, `DistributionBucket`/`DistributionSummary`, `KpiSummary`, `DashboardMeta`, `RefreshResult`). Numeric → `string`; tasas → `number`; conteos → `number`.
- [ ] Reusar `formatRelative` (client-only) de crm/calendar para "Actualizado hace N min"; reusar `<EmptyState>`/`<MessageBar>`/`<Skeleton>` del template; reusar `<Dropdown>` de sede de `clinic` (`GET /clinic/branches/active`, o de `/meta`).
- [ ] Las páginas `/dashboard` (panel) y `/dashboard/reportes` **NO** se construyen aún (paquete frontend inerte salvo nav/types/endpoints). El welcome placeholder de `/dashboard` se mantiene hasta F2. QA E2E/PROD RO F0 = login admin + assert perm count (120→123) + ver "Panel"/"Reportes" en el sidebar + rutas `/dashboards/*` → 404 (módulo backend no registrado).

### F1 — Capa de agregación + lectura (backend-only, sin pantallas)
- [ ] Sin UI (es la capa de agregación: tablas + refresh service + endpoints de lectura + `/internal/refresh` + Cloud Scheduler + migr 0026). El panel todavía no consume nada. QA E2E real = refrescar el rollup + leer los endpoints en Postgres.

### F2 — Panel (frontend)
- [ ] **Pantalla 1** `/dashboard`: `DashboardClient` (header de filtros rango/sede/origen + badge "Actualizado hace N min" client-only + botón refrescar) prefetcheado por el RSC con `requirePermission("DASHBOARD_VIEW")` (summary+funnel → `initialData`) — **reemplaza** el welcome placeholder.
- [ ] Widgets: `KpiCardsRow` (`useQuery` summary) + `ConversionFunnel` (`FunnelChart` nativo **o** bespoke — decidir al instalar la dep) + `LeadsEvolutionChart` (`LineChart`/`AreaChart`, colores catálogo) + `AppointmentsDistributionDonut` (`DonutChart`, colores catálogo) + `ChatbotMiniPanel`. **Cada uno con su `useQuery` + estados loading/sin-datos/error aislados.**
- [ ] Dep nueva front: `@fluentui/react-charts`. Charts client-only `next/dynamic({ssr:false})` + `<Skeleton>` fallback. React Query `staleTime`≈`refetchInterval`≈intervalo de refresco.
- [ ] Caveat de sede (`<MessageBar intent="info">` cuando Sede ≠ "Todas"). Filtros sincronizados a URL (`nuqs`).
- [ ] Welcome mínimo para usuarios sin `DASHBOARD_VIEW` (sin redirect loop). Auditar **Lighthouse** (RNF-05: panel ≤ 3 s, LCP ≤ 2.5 s).
- [ ] Sin migración (F2 es frontend-only).

### F3 — Reportes (frontend + backend server-side)
- [ ] **Pantalla 2** `/dashboard/reportes`: form (rango + sede + formato PDF/Excel + checkboxes de secciones) + botón "Generar y descargar" → Server Action `generateReport` (devuelve binario para descargar) + estados generando/éxito/error. RSC `requirePermission("REPORTS_EXPORT")`.
- [ ] Backend genera el binario server-side (PDF `reportlab`/`weasyprint` + Excel `openpyxl`, lazy import) — `POST /dashboards/report`. (Ver backend.md.)
- [ ] Sin migración (F3 no crea tablas).

### Diferidas (D1–D4) — sin UI
- [ ] Documentadas como roadmap en README/design (dashboard por-doctor/clínico, métricas de mensajes desde Firestore, caché distribuida Redis/Memorystore, real-time estricto del día en curso + tendencias/forecast). **No se diseñan pantallas aquí.** La **flecha de tendencia** de las KPI cards (vs período anterior) es diferible dentro de F2 (default sin flecha).
