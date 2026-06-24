# ADR-015: Módulo de Dashboards y Reportes — agregación materializada (daily rollup), reportes server-side, Fluent UI Charts

> **Status**: Proposed
> **Date**: 2026-06-24
> **Deciders**: @daniel, @marco

## Context

La tesis tiene el **OE3 (Módulo de Dashboards y Reportes)** y las **HU26/HU27 (épica E07) PENDIENTE** en el backlog, pero el Cap.6 los describe como "desplegado y funcionando" con **figuras (17/18/19) de un sistema anterior que ya no existe**. Hay que construir el módulo de verdad para cerrar OE3 + HU26/HU27 + el **RNF-05** real (panel ≤ 3 s, LCP ≤ 2.5 s) y eliminar esa incoherencia.

La tesis pide un panel **en tiempo real** centrado en un **embudo de conversión** (del primer contacto a la cita confirmada) + **evolución de leads** (línea) + **distribución de citas** (donut) + **reportes exportables a PDF/Excel**. **La data del embudo ya existe en producción** (crm, scheduling, conversations, bots, marketing) — no hay que crear fuentes, solo **agregarlas y visualizarlas**.

### Investigación (no se asumió nada)

Se corrió un Workflow de mapeo del código real (6 agentes en paralelo, 2026-06-24, todas las afirmaciones con cita `path:línea`). Hallazgos que dirigen la decisión:

- **El embudo se une enteramente por `person_id`**. Las etapas de lead son un **catálogo configurable** ([ADR-008](ADR-008-configurable-status-transition-matrix.md)): `NUEVO → INTENTANDO_CONTACTAR → CONTACTADO → INTERESADO → EVALUANDO → CITA_AGENDADA` (único `is_won`) / `NO_INTERESADO`. Las de cita son 8 (`SCHEDULED…ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED`). ⇒ **resolver por `code`/flags, nunca por id hardcodeado**.
- **No existe ningún endpoint de agregación/dashboard hoy** (solo `func.count()` para totales de paginación). El único precedente de un endpoint de **métrica agregada no-paginada** es `marketing.usage_summary` (`SingleResponse[PromotionUsageSummary]`) — es el molde.
- **Los mensajes viven en Firestore** ([ADR-011](ADR-011-firestore-message-stream-cqrs.md), CQRS) → "nº de mensajes" **NO es consultable en SQL**; sí lo son las conversaciones, los turnos del bot (`bot_event`), las citas y los estados.
- **`person_lead_status` se soft-deletea al entrar a un estado `is_final`** → el "stock vivo" no contiene ganados/perdidos; los conteos de embudo por flujo se sacan de `lead_status_history` (append-only).
- **`APPOINTMENT_BOOKED`/`CANCELLED` están en el enum pero NUNCA se emiten** → el embudo se cuenta por `status` + filas de `appointment`, no por el timeline.
- **Solo `appointment` tiene `branch_id`** (denorm, con índice `(branch_id, scheduled_for, status_id)`) → el filtro por sede es exacto de la etapa "cita" en adelante.
- **Infra**: ni Recharts ni Fluent Charts están instalados (la "contradicción de la tesis" es un punto abierto, no un hecho); ninguna lib de PDF/Excel; **no hay Redis** (confirmado: `config.py` sin `REDIS`; el único uso de "cache" es `lru_cache` de settings + slowapi in-memory).

### Decisiones de alcance del usuario (AskUserQuestion, 2026-06-24) — NO re-litigar

1. **Embudo COMPLETO cross-módulo** (6 etapas: Conversaciones → Leads → Contactados/Interesados → Citas agendadas → Citas confirmadas → Clientes).
2. **Agregación MATERIALIZADA / precomputada + caché** (sobre on-the-fly).
3. **Gráficos = Fluent UI Charts** (`@fluentui/react-charts`).
4. **Reportes = SERVER-SIDE** (el backend genera el binario PDF/Excel).

## Decision

Construir un módulo nuevo **`dashboards`** **read-only** (no crea entidades de negocio; agrega lo que ya existe) con:

- **Una capa de agregación MATERIALIZADA**: una *fact table* de rollup diario **`dashboard_daily_metric`** (`metric_date × branch_id × metric × segment → count/value`) + un singleton **`dashboard_refresh_state`** (observabilidad). El rollup lo **recalcula un job programado** (Cloud Scheduler → `POST /dashboards/internal/refresh`, **auth shared-secret** con `hmac.compare_digest`, molde [ADR-012](ADR-012-cloud-tasks-bot-dispatch.md)) sobre una **ventana móvil** (default 90 días + el día en curso) cada N minutos (default 10). El **plano de lectura** (endpoints del panel) solo **suma el rollup** sobre el rango+filtros → constante y sub-segundo (RNF-05). Sin Redis (materialización nativa en Postgres).
- **Reconciliación con "tiempo real"**: el rollup refresca el día en curso cada ciclo → staleness ≤ intervalo; el panel muestra **"Actualizado hace N min"** (de `dashboard_refresh_state`) + `refetchInterval` de React Query ≈ intervalo (la "caché TTL por caducidad de KPIs" que nombra la tesis). El cómputo on-the-fly del día en curso para freshness estricta queda **diferido** (aditivo).
- **Endpoints de lectura no-paginados** (`SingleResponse[X]`, molde `usage_summary`): `/dashboards/funnel`, `/leads-evolution`, `/appointments-distribution`, `/summary`, `/meta`; request dedicado `DashboardFilter(date_from, date_to, branch_id?, source?, campaign_id?)` (NO `QueryRequest`).
- **Reportes server-side**: `POST /dashboards/report` (gated `REPORTS_EXPORT`) genera **PDF** (con figuras, p.ej. `reportlab`/`weasyprint`) y **Excel** (`openpyxl`) leyendo el rollup; el front solo dispara una Server Action que descarga el binario (coherente con "el browser nunca habla con FastAPI directo").
- **Gráficos Fluent UI Charts** (`@fluentui/react-charts`): `DonutChart` (distribución de citas), `LineChart`/`AreaChart` (evolución de leads), embudo con `FunnelChart` nativo si la versión lo trae o un `ConversionFunnel` bespoke con tokens Fluent (precedente bespoke = `CalendarGrid`). Charts client-only con `next/dynamic({ssr:false})` (fuera del critical path → LCP).
- **3 permisos** (`MENU-DASHBOARDS` reservado + `DASHBOARD_VIEW` + `REPORTS_EXPORT`); ADMIN+ASESOR (HU26); DOCTOR fuera del dashboard comercial. **Scope por sede = filtro** (single-tenant), exacto de la etapa "cita" en adelante; etapas previas a nivel clínica.

**Migración**: `0026_dashboard_metric` crea las 2 tablas derivadas + **índices aditivos** en tablas fuente (`lead_status_history.changed_at`, `conversation.opened_at`, `person.created_on`, `person_customer_status.became_customer_at`) para acelerar el job de refresco. No crea entidades de negocio ni constraints sobre datos existentes.

## Alternatives Considered

### Agregación: ON-THE-FLY (no elegida)
- **Pros**: la más simple; cero infra nueva (sin job, sin tablas, sin scheduler); estrictamente en tiempo real (cada request ve el dato vivo); el volumen de una clínica lo soporta con los índices existentes; molde directo `usage_summary`.
- **Cons**: recomputa las agregaciones en cada carga del panel; depende de índices nuevos en las tablas fuente para sostener RNF-05; menos "defensable" como historia de optimización en la tesis.
- **No elegida**: el usuario eligió **materializada** para garantizar RNF-05 por construcción y por la narrativa de "optimización de consultas de agregación" que HU26 motiva. (Era una opción válida y más liviana; se documenta como el camino de simplificación si el rollup resulta sobre-ingeniería.)

### Caché distribuida (Redis/Memorystore) (diferida)
- Una caché de resultados compartida entre instancias optimizaría aún más, pero **suma infra** (Memorystore) que el template no tiene y que HARDENING §1 prevé solo para rate-limit distribuido. El rollup en Postgres + el caché TTL de React Query ya cumplen RNF-05 → **diferida** a una fase de escala.

### Reportes client-side (no elegida)
- Generar el PDF/Excel en el navegador (jspdf/exceljs) evita un endpoint, pero **pesa el bundle** y da **menor fidelidad** del PDF (las figuras del panel no salen tal cual). **No elegida**: server-side da mejor fidelidad y respeta la frontera del template.

### Gráficos con Recharts (no elegido)
- Recharts (lo que dice la Tabla 10 de la tesis) es maduro y flexible, **pero** introduce un sistema de estilos paralelo (no Griffel) y obliga a mapear los colores del tema a mano. **No elegido**: `@fluentui/react-charts` comparte tokens con todo el stack (cero fricción de theming) y resuelve la contradicción de la tesis a favor de §6.2.3 (se actualiza la Tabla 10).

### Métricas de mensajes desde Firestore (diferidas)
- "Nº de mensajes / tiempo de primera respuesta a nivel mensaje" requiere agregar Firestore (los mensajes no están en Postgres, ADR-011). **Diferido**: el embudo usa conteo de conversaciones + turnos del bot; las métricas de mensaje son un read-model aparte, futuro.

## Consequences

### Positivas
- **Aditivo y de bajo riesgo**: el módulo **solo lee** las fuentes; no muta ni una fila de negocio, no toca `compute_available_slots` ni ningún flujo → imposible introducir un bug funcional en el embudo. Una falla del job degrada con gracia (sirve el último rollup + badge "Actualizado hace N min").
- **RNF-05 por construcción**: el plano de lectura suma una tabla chica indexada → sub-segundo; prefetch SSR + `next/dynamic` de los charts → LCP. Historia de optimización fuerte para la tesis.
- **Reusa patrones en producción**: `usage_summary` (métrica agregada), shared-secret + Cloud Scheduler ([ADR-012](ADR-012-cloud-tasks-bot-dispatch.md)), catálogos configurables ([ADR-008](ADR-008-configurable-status-transition-matrix.md)), FKs forward ([ADR-009](ADR-009-forward-fk-deferred-cross-module.md)).
- **Cierra OE3 + HU26/HU27 + RNF-05** y reemplaza las figuras falsas del Cap.6 por el dashboard real.

### Negativas / Trade-offs
- **"Casi en tiempo real", no estricto**: el dato es tan fresco como el último refresco (staleness ≤ intervalo, default 10 min). Se mitiga con el badge "Actualizado hace N min" + refetch; el real-time estricto del día en curso es una mejora aditiva diferida.
- **Infra nueva**: un Cloud Scheduler + un secret (`DASHBOARD_REFRESH_SECRET`) en **ambos** workflows de deploy (lección §9/§11) + un boot-validator (`_enforce_dashboard_refresh_secret`). Deps nuevas: la lib de charts (front) + la lib PDF + `openpyxl` (back).
- **Filtro por sede parcial**: exacto de la etapa "cita" en adelante (solo `appointment` tiene `branch_id`); las etapas previas (conversaciones, leads) son a nivel clínica → se etiqueta el caveat en la UI.
- **El job escanea las fuentes**: requiere índices aditivos en columnas temporales hoy no indexadas; el `date_trunc` del bucketing es Postgres-only (en el smoke sqlite se bucketiza en Python o se gatea el SQL).

### Lo que esto nos obliga a hacer
- Settings nuevas (`DASHBOARD_REFRESH_SECRET`, `DASHBOARD_REFRESH_INTERVAL_MINUTES`, `DASHBOARD_REFRESH_WINDOW_DAYS`) en **ambos** workflows (`--set-env-vars`/`--set-secrets`) + boot-validator ruidoso si el módulo queda medio-configurado.
- Provisionar el **Cloud Scheduler** (cron → `/dashboards/internal/refresh` con el header del secret) + el secret en Secret Manager, antes del deploy que lo referencia.
- Definir permisos RBAC (`DASHBOARD_VIEW`, `REPORTS_EXPORT`, `MENU-DASHBOARDS`), nav, endpoints, types espejo — F0 inerte (molde scheduling F0).
- Diseñar el detalle por ficha (`docs/modules/dashboards/{README,backend,ui,frontend}.md`) en la fase de documentación previa a F0.

## Update (F2, 2026-06-24): gráficos implementados **bespoke** (sin `@fluentui/react-charts`)

La decisión de alcance #3 ("Gráficos = Fluent UI Charts") se **revisó en la implementación de F2**. Se instaló `@fluentui/react-charts` (v9.3.20: expone `FunnelChart`, `DonutChart`, `LineChart`, `AreaChart`) pero **rompe el build de producción de Next 16 App Router + Turbopack**: al recolectar la página `/dashboard`, un chunk SSR evalúa `@fluentui/react-icons` (dependencia interna de react-charts) con el React restringido (react-server) → `TypeError: d.createContext is not a function`. Ni `next/dynamic({ ssr:false })`, ni `transpilePackages`, ni fijar `turbopack.root` lo resolvieron (el build sigue evaluando el módulo server-side).

**Resolución**: los tres charts se implementaron **bespoke** con divs/SVG + tokens Fluent (precedente "bespoke dentro de Fluent" = `CalendarGrid` de scheduling) y se **removió la dependencia** `@fluentui/react-charts`:
- **Embudo** (`ConversionFunnel`): barras horizontales decrecientes (ancho ∝ conteo) + `rate_from_prev`. Renderiza inmediato con el prefetch (sin bundle de charts → mejor LCP del widget protagonista).
- **Distribución de citas** (`AppointmentsDonut`): anillo con CSS `conic-gradient` + agujero central con el total + leyenda.
- **Evolución de leads** (`LeadsLineChart`): SVG `viewBox` con `preserveAspectRatio="none"` + `vector-effect: non-scaling-stroke` (responsive sin distorsión) + ejes en HTML (nítidos).

**Por qué es consistente con el espíritu del ADR**: el motivo de elegir Fluent Charts sobre Recharts era "compartir tokens Griffel → cero fricción de theming". El bespoke con tokens Fluent **cumple ese objetivo aún mejor** (cero librería de charts, cero theming foráneo), es **más liviano** (sin 38 paquetes nuevos ni JS pesado), **SSR-safe** y los colores de segmento siguen saliendo del catálogo (ADR-008). Trade-off: sin tooltips/leyendas/ejes "gratis" de la lib → se construyen a mano (leyendas + `<title>` SVG nativos + ejes HTML). La contradicción de la tesis (Recharts vs §6.2.3) se resuelve igual a favor de gráficos **nativos al design system**, ahora literalmente sin dependencia externa.

## Referencias

- **Documento de diseño**: [`docs/modules/dashboards/design.md`](../modules/dashboards/design.md) (arquitectura, cómputo del embudo, modelo del rollup, refresco, KPIs, UI, fases, diagramas mermaid).
- **ADRs reutilizados**: [ADR-008](ADR-008-configurable-status-transition-matrix.md) (estados configurables → resolver por code/flags), [ADR-009](ADR-009-forward-fk-deferred-cross-module.md) (FKs forward `source_campaign_id`/`related_*`), [ADR-011](ADR-011-firestore-message-stream-cqrs.md) (mensajes en Firestore → no agregables en SQL), [ADR-012](ADR-012-cloud-tasks-bot-dispatch.md) (shared-secret + dispatch async → molde del refresco), [ADR-013](ADR-013-marketing-campaign-status-and-atomic-apply.md) (`usage_summary` = molde de endpoint de métrica agregada).
- **Código relevante (citas exactas en `backend.md`)**: `backend/app/modules/marketing/repositories/promotion_usage.py:64-77` (`usage_summary`, molde de agregación), `backend/app/modules/scheduling/models/appointment.py:38-48` (índice `(branch_id, scheduled_for, status_id)`), `backend/app/modules/crm/models/lead_status_history.py` (eje del line chart), `backend/app/core/seed.py:343-413` (catálogos de estado sembrados), `backend/app/core/config.py` (sin Redis), `frontend/src/providers/AppProviders.tsx:50-61` (QueryClient `staleTime`).
- **Tesis**: OE3, HU26/HU27 (E07), RNF-05, RE3.2; reemplaza Figuras 17/18/19 del Cap.6. Cumplimiento: **Ley N.º 29733** (minimización de datos — los reportes son agregados, no exponen PHI individual).
