# Módulo `marketing` — UI design

> **Última actualización**: 2026-06-08
> **Audiencia**: developer implementando las pantallas de `marketing` en `frontend/src/app/(main)/marketing/`.
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). `Campaign.status` es **enum fijo** (`draft/active/paused/ended`) con la matriz de transición hardcodeada en el service (spec §2) — **NO** es un catálogo configurable ni una matriz editable como crm/scheduling (decisión confirmada §0.2). Forward-FKs cerradas por este módulo en [ADR-009](../../decisions/ADR-009-forward-fk-deferred-cross-module.md) (a consolidar).

> **Alineación con catalog/crm/scheduling (módulos gold-standard ya en prod)**: `marketing` reutiliza directamente los patrones que esos módulos dejaron como precedente del template y **no inventa un estilo nuevo** (regla de la metodología: consistencia con lo shippeado **>** estilo nuevo). En concreto:
> - **Campañas** y **Promociones** son **listas + drawer multi-tab**: la lista espeja `OfficesClient`/`DoctorsClient` (DataTable + filtro chip + deep-link), el drawer espeja el `ProductDrawer`/`DoctorCreateDrawer` (multi-sección/tab) y los editores M:N reutilizan `SearchableOptionList` + bulk-replace PUT (molde `BotToolsTab` de bots y el editor M:N de doctores).
> - **El badge de estado de campaña** clona el `StatusBadge` de scheduling/crm, pero el color **no** sale de un catálogo (no hay `Campaign.color`): se mapea el enum `CampaignStatus` → token Fluent fijo (ver Decisiones de UI). Es la única diferencia de fondo con los badges de crm/scheduling (que sí leen `color` hex de su catálogo).
> - **El control de cambio de estado de la campaña** clona el lenguaje del `TransitionControl` + atajos de scheduling: **solo muestra los estados a los que la matriz §2 permite ir** desde el estado actual (no hay un dropdown de "todos los estados" que rebote). La diferencia: la matriz es **fija en el frontend** (constante `CAMPAIGN_TRANSITIONS`), no se consulta a un endpoint de transiciones (no existe — el backend re-valida en el service).
> - **Usos de promoción** es un **reporte read-only** (DataTable + filtros, sin drawer ni mutaciones), molde directo de un listado simple gateado (estilo `DoctorsClient` read-only / `mis-leads` de crm), pero **sin RowActions** porque la entidad `PromotionUsage` es audit inmutable (PK·A·T, sin SoftDelete; spec §3.3).

> **Contexto de diseño (regla del template, no negociable)**:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Los colores de los badges de estado de campaña salen de **tokens Fluent** (`tokens.colorPalette*Foreground*`), mapeados por enum (no hay color hex en `Campaign`). El resto usa tokens Fluent (`tokens.colorPaletteRedForeground1`, `tokens.colorPaletteGreenForeground1`, etc.). No introducir librería externa de UI.
> - **Decimales = `string` en el wire (binding, spec §1/§10)**: `discount_value`, `original_amount`, `discount_amount`, `final_amount` viajan como **`string`** (Numeric(10,2) serializado). En TS se tipan `string`; los inputs de montos van `inputMode="decimal"` (no `type=number`); el `percentage` puede ser `number` 0-100. El formateo con moneda se hace client-side (`formatMoney(value, currency)`).
> - **TZ — lección recurrente de staff/crm/scheduling (binding)**: cualquier `new Date()`/`now` que afecte el render debe ser **client-only**. En marketing esto cubre: la **vigencia** de campañas/promos ("vigente / por iniciar / vencida", resaltado en la lista) y el default de los `DatePicker` de fechas. Las fechas de marketing son `Date` (sin hora, sin TZ — `start_date`/`end_date` son `date`, no `datetime`), así que el riesgo es menor que en scheduling, pero el cómputo de "¿hoy cae dentro de la vigencia?" sigue siendo **client-only** (el SSR en UTC desfasaría el día en Lima UTC-5).

---

## Decisión de arquitectura: 3 listas en sidebar — Campañas (drawer-tabs) + Promociones (drawer-tabs) + Usos (reporte read-only)

`clinic` estableció la regla, reafirmada por `staff`/`crm`/`scheduling`: **si una entidad tiene sub-recursos con interacción propia (timelines, grids editables, listas CRUD anidadas, máquinas de estado), su superficie va a una página/grilla dedicada; si es ligera, va a drawer.** En `marketing` ninguna de las 3 entidades llega al umbral de "página con tabs" (no hay timelines pesados ni multi-superficie editable densa): Campaign y Promotion son entidades con metadata + **uno o dos editores M:N + un control de estado** que caben cómodos en un **drawer con tabs internas** (más liviano que el `Person`/`Office` de página), y PromotionUsage es audit inmutable → **reporte read-only**.

| Recurso | Lista / superficie | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **Campaign** (Campaña) | `/marketing/campanas` (sidebar, tabla + filtro por status chip + deep-link) | **drawer multi-tab** (Datos) | **drawer multi-tab** `size=medium` (Datos · Promociones [M:N] · Auditoría) + **control de cambio de estado** | tabla = `OfficesClient`; drawer = `ProductDrawer`; M:N = `SearchableOptionList` |
| **Promotion** (Promoción) | `/marketing/promociones` (sidebar, tabla + filtros chip + deep-link) | **drawer multi-tab** (Datos + Descuento + Vigencia) | **drawer multi-tab** `size=medium` (Datos · Descuento · Vigencia y límites · Productos [M:N] · Campañas [read-only] · Auditoría) | drawer = `ProductDrawer` (form **discriminado** por `discount_type`) |
| **PromotionUsage** (Uso de promoción) | `/marketing/usos` (sidebar, tabla **read-only** + filtros) | — (lo crea el service: apply / scheduling / bot) | — (audit inmutable, sin drawer ni mutaciones) | reporte read-only (molde `mis-leads`/`DoctorsClient` read) |
| `campaign_promotion` (M:N) | — | dentro del **tab Promociones** de Campaña **y** el **tab Campañas** de Promoción (read-only ahí) | editor M:N (bulk-replace `PUT`) | `SearchableOptionList` + `PUT {promotion_ids}` |
| `promotion_product` (M:N) | — | dentro del **tab Productos** de Promoción | editor M:N (toggle `applies_to_all_products` + `SearchableOptionList`) | `SearchableOptionList` + `PUT {product_ids}` |
| `eligible-for` / `validate` / `compute-price` | — | — (servicios consumidos por scheduling/bot; sin pantalla propia en marketing MVP) | — | (F4: el wizard de citas de scheduling consume `eligibleFor`; no es pantalla de marketing) |

### Por qué Campaña y Promoción van a **drawer con tabs** y no a página con tabs

Misma justificación-precedente que clinic/staff/crm/scheduling (el peso del sub-recurso manda la forma), pero acá el veredicto cae del lado del **drawer**:

| Opción | Veredicto |
|---|---|
| **A. Drawer `size="medium"` con tabs internas** (Datos / M:N / Auditoría para Campaña; + Descuento/Vigencia/Productos/Campañas para Promoción) — la entidad tiene metadata + 1–2 editores M:N + (Campaña) un control de estado; ninguno necesita ancho completo ni URL bookmarkable por tab; reusa el patrón de `ProductDrawer` (form con secciones) y los editores M:N de doctores/bot-tools; el flujo "veo la tabla → abro el drawer → edito/cambio estado → vuelvo" no pierde el contexto de la lista. | **Elegida** |
| B. Página `/marketing/campanas/{id}` con tabs (estilo `Person`/`Office`) | Rechazada — sobra. Campaña/Promoción no tienen un timeline pesado ni 5–6 superficies densas que justifiquen una página + URL por tab; forzar la página rompe el flujo de catálogo ligero (mismo veredicto que scheduling tomó para los catálogos y la cita). |
| C. Drawer plano (sin tabs, todo en un scroll) | Rechazada para Promoción — el form **discriminado** por `discount_type` + vigencia/límites + dos M:N (productos + campañas read-only) + auditoría es demasiado para un solo scroll; las tabs internas aíslan cada superficie. Para Campaña (más liviana) el límite es menor, pero por consistencia con Promoción ambas usan tabs internas. |
| D. Dialog modal | Rechazada — los editores M:N con `SearchableOptionList` y el control de estado con confirmaciones sobre un modal = z-index frágil; el drawer lateral es el patrón del template para "editar/actuar sin perder la lista". |

> El drawer de Campaña/Promoción **sincroniza** un `?campaign_id=` / `?promotion_id=` en la URL de la lista para ser deep-linkable y sobrevivir refresh (mismo espíritu que `?appointment_id=` de scheduling y `?tab=` de clinic). El tab activo dentro del drawer es estado local del drawer (no va a la URL — el drawer es liviano).

### Por qué Usos de promoción es un **reporte read-only** y no un CRUD

`PromotionUsage` es **audit inmutable** (PK·A·T, **sin SoftDelete**; spec §3.3): sus filas las crea el `apply` del service (manual vía `POST /promotion-usages`, o automático desde scheduling/bot con `created_by = SYSTEM_USER_ID`), y **nunca se editan ni se borran** desde la UI. Por eso `/marketing/usos` es una **tabla read-only** (promo · persona · producto · montos · fecha) con **filtros** (promo, persona, fecha) y **sin RowActions de mutación** — es la vista de "quién redimió qué y cuánto se descontó", consumida para reportería. No hay drawer de detalle (el `PromotionUsageDetail` = `Item` hoy, spec §4.3, sin extras); como mucho, un drawer de solo-lectura es **diferible/opcional** (no MVP). La "aplicación" de una promo no se hace desde acá (se hace al reservar una cita en scheduling, o desde el bot) — esta pantalla solo **reporta**.

## Sidebar — extensión de `NAV_ITEMS` (grupo "Marketing", gated `MENU-MARKETING`)

> ⚠ **Textos UI en español**. `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un parent item `marketing` con 3 children, **después de `scheduling`** (es el módulo #8, el último; cierra el loop campaña → promo → descuento aplicado en cita/bot):

```ts
{
  key: "marketing",
  label: "Marketing",
  icon: "MegaphoneRegular",                 // verificar en la versión de Fluent; fallback "BroadActivityFeedRegular"
  children: [
    { key: "campanas", label: "Campañas",            icon: "MegaphoneRegular",     url: "/marketing/campanas", permissions: ["CAMPAIGNS_READ"] },
    { key: "promociones", label: "Promociones",      icon: "TicketDiamondRegular", url: "/marketing/promociones", permissions: ["PROMOTIONS_READ"] },
    { key: "usos", label: "Usos de promoción",       icon: "ReceiptRegular",       url: "/marketing/usos",     permissions: ["PROMOTION_USAGES_READ"] },
  ],
},
```

> El parent usa `MENU-MARKETING` como gate de visibilidad del grupo (se muestra si ≥1 child pasa el filtro). Cada child gatea por **su** permiso de lectura:
> - **ASESOR** ya forward-declara 6 permisos del módulo (`MENU-MARKETING`, `CAMPAIGNS_READ`, `PROMOTIONS_READ`, `PROMOTION_VALIDATE`, `PROMOTION_APPLY`, `PROMOTION_USAGES_READ` — spec §11) → ve **Campañas** (read-only, sin `_CREATE/_UPDATE/_DELETE`), **Promociones** (read-only) y **Usos de promoción** (read). No puede crear/editar campañas/promos (no tiene los permisos finos), pero **sí** puede validar/aplicar promos (lo usa al reservar citas / desde el flujo de bot).
> - **ADMIN** recibe los 12 permisos → ve todo y administra.
> - **DOCTOR** no tiene ningún permiso de marketing → **no** ve el grupo.
> Los permisos finos (`CAMPAIGNS_CREATE`/`_UPDATE`/`_DELETE`, `PROMOTIONS_CREATE`/`_UPDATE`/`_DELETE`) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>` / `usePermissions()`.

> Iconos Fluent (verificar que existan en la versión instalada; usar fallback si no — **lección catalog**: 4 íconos no existían): `MegaphoneRegular` (campañas/grupo), `TicketDiamondRegular` o `TagRegular` (promociones), `ReceiptRegular` (usos). Mismo criterio de verificación que `staff` con `DoctorRegular` y `crm` con `PeopleRegular`.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error / success) + tabla de componentes Fluent.

1. `/marketing/campanas` — tabla de campañas (filtro por status chip + deep-link) + **drawer multi-tab** (Datos · Promociones [M:N] · Auditoría) + **control de cambio de estado** (atajos según la matriz §2).
2. `/marketing/promociones` — tabla de promociones (filtros chip + deep-link) + **drawer multi-tab** (Datos · Descuento [discriminado] · Vigencia y límites · Productos [M:N] · Campañas [read-only] · Auditoría).
3. `/marketing/usos` — reporte **read-only** de usos de promoción (DataTable + filtros, sin drawer/mutaciones).

---

### Pantalla 1 — `/marketing/campanas` (tabla de campañas + drawer multi-tab + control de estado)

Tabla estructura `OfficesClient`/`DoctorsClient`, con **un filtro** deep-linkable (status), con chip y ×, espejando el patrón shipped. El botón primario abre el **drawer de campaña** (create); ver/editar abre el mismo drawer en su entidad.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                      │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │   Campañas                                                 │ │
│ │ ▸ Agenda   │ │   Gestiona las campañas de marketing y sus promociones.    │ │
│ │ ▾ Marketing│ │                          ┌────────────┐┌────────────────┐  │ │
│ │   • Campañ█│ │                          │Estado:Todos▾││+ Nueva campaña │  │ │
│ │   • Promo. │ │                          └────────────┘└────────────────┘  │ │
│ │   • Usos   │ │  ┌──────────────────────┐                                  │ │
│ │ ▸ Admin    │ │  │ Estado: Activa      ✕│  ← chip                          │ │
│ │            │ │  └──────────────────────┘                                  │ │
│ │            │ │  ╭─ DataTable ──────────────────────────────────────────╮ │ │
│ │            │ │  │ ⋯ │ Código   │ Nombre        │Estado │ Vigencia      │Promos│ │
│ │            │ │  ├───┼──────────┼───────────────┼───────┼───────────────┼──────┤ │
│ │            │ │  │ ⋯ │ verano26 │ Campaña Verano│●Activa│01 ene–31 mar  │  3   │ │
│ │            │ │  │ ⋯ │ blackfri │ Black Friday  │○Borra.│28 nov–30 nov  │  0   │ │
│ │            │ │  │ ⋯ │ navidad25│ Navidad 2025  │●Finali│01–31 dic 2025 │  5   │ │
│ │            │ │  ├──────────────────────────────────────────────────────┤ │ │
│ │            │ │  │ Mostrando 1–3 de 3      ‹  Página 1 de 1  ›          │ │ │
│ │            │ │  ╰──────────────────────────────────────────────────────╯ │ │
│ └────────────┘ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (mapean a `CampaignItem`, spec §4.1; `key` inglés / `header` español):

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `actions` | `""` | RowActions | — | menú `…`: Ver / Editar / Eliminar (gated por permisos) |
| `code` | Código | text (mono) | ✅ (server, columna real en `ALLOWED_FIELDS`) | `<code>` slug minúsculas |
| `name` | Nombre | text (truncate) | ✅ (server) | `name` |
| `status` | Estado | badge | ❌ (deep-link por status) | `<CampaignStatusBadge status={c.status} />` (Borrador/Activa/Pausada/Finalizada, color por enum) |
| `vigencia` | Vigencia | rango de fechas | ❌ (derivado de `start_date`/`end_date`) | `{start_date} – {end_date \|\| "sin cierre"}`; resaltado "vigente/por iniciar/vencida" **client-only** |
| `target_vertical_name` | Vertical | text (truncate) | ❌ (denorm) | nombre de la vertical objetivo; "Todas" si NULL (transversal) |
| `promotions_count` | Promos | número | ✅ (no — denorm; ver nota) | conteo de promos vinculadas (`promotions_count`); chip pequeño |

> **Denormalización sin N+1** (spec §6.1): `target_vertical_name` (vía `vertical_repository.get_by_ids` batch) y `promotions_count` (vía `count_promotions_map` batch) se hidratan en el service. **Lección hotfix `cd10c78` de staff (binding)**: estas columnas son denormalizadas, NO están en `ALLOWED_FIELDS` (`{'code','name','status','start_date','end_date','target_vertical_id','active','created_on','updated_on'}`, spec §5) → **no son server-sortable por su texto/valor**. Por eso `target_vertical_name`/`promotions_count`/`vigencia` tienen `isSortable: false`. Server-sortable: `code`, `name`, `start_date`/`end_date` (columnas reales). El filtro por estado **no** filtra por el texto del badge sino por el valor `status` (`?status=active`), que el backend aplica como filtro real (`status` ∈ `ALLOWED_FIELDS`). `defaultSort = { field: "start_date", order: "desc" }`. **Gotcha del molde**: si el prefetch del `page.tsx` ordena por `start_date`, pasar **el mismo** `defaultSort` al `useTableQuery` (sino descarta `initialData`).

**Filtro por status (Dropdown + chip + deep-link)** — espejo de `OfficesClient`:
- **Estado**: `<Dropdown>` con las 4 opciones del enum `CampaignStatus` (Borrador / Activa / Pausada / Finalizada). `null` = "Todos los estados". Sincronizado con `?status=draft|active|paused|ended` vía `nuqs useQueryState`. Chip "Estado: {etiqueta} ✕". El backend lo aplica como filtro sobre `status` (columna real).

> Deep-link de entrada: desde un dashboard ("3 campañas activas") se llega con `/marketing/campanas?status=active` y el chip aparece pre-poblado.

**RowActions** (gated por `usePermissions()`):
- 👁 **Ver** — siempre visible (asume `CAMPAIGNS_READ`). Abre el drawer en modo `view` (todo disabled) + setea `?campaign_id=`.
- ✏ **Editar** — gated `CAMPAIGNS_UPDATE`. Abre el drawer en modo `edit`.
- 🗑 **Eliminar** — gated `CAMPAIGNS_DELETE`. `<ConfirmDialog destructive>` → `DELETE /campaigns/{id}` (soft-delete; las `PromotionUsage` que la referencian conservan el `campaign_id` — la fila campaign queda viva soft-deleted, el FK no se rompe; spec §6.1: soft-delete libre, sin guard de hijos).

**Botón "+ Nueva campaña"**: gated `<PermissionGuard anyOf={["CAMPAIGNS_CREATE"]}>`. Abre el drawer en modo `create`.

#### Drawer de campaña (`CampaignDrawer`, create/edit/view) — tabs internas

`<Drawer size="medium">` con tabs internas. **Create**: solo el tab **Datos** (la campaña nace `draft`; las promos y la auditoría no aplican aún). **Edit/View**: 3 tabs — **Datos** · **Promociones** (editor M:N) · **Auditoría** — más el **control de cambio de estado** en la cabecera del drawer.

```
                  ┌─────────────────────────────────────────────────┐
                  │  Campaña Verano                    [●Activa]  ✕ │
                  │  Cambiar estado:  [ Pausar ] [ Finalizar ]      │ ← atajos según matriz
                  ├─────────────────────────────────────────────────┤
                  │ ╭[ Datos ][ Promociones ][ Auditoría ]╮          │
                  │ │                                                │
                  │ │ Código *      (minúsculas, sin espacios)       │
                  │ │ [ verano26                          ] (bloq.)  │ ← inmutable en edit
                  │ │ Nombre *                                       │
                  │ │ [ Campaña Verano                            ]  │
                  │ │ Descripción                                    │
                  │ │ [ ……………………………………………………………………………………… ]    │
                  │ │ Vertical objetivo (opcional)                   │
                  │ │ [ Todas las verticales                    ▾ ]  │
                  │ │ Inicio *          Fin (opcional)               │
                  │ │ [ 2026-01-01 📅 ] [ 2026-03-31 📅 ]            │
                  │ │ El estado se gestiona arriba (no aquí).        │
                  │ ╰────────────────────────────────────────────────│
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Guardar ]│
                  └─────────────────────────────────────────────────┘
```

**Tab Datos** — campos + validación (Zod `campaignCreateSchema`/`campaignUpdateSchema`, espejo de `CampaignCreate`/`CampaignUpdate`, spec §4.1):
- `code` requerido (slug minúsculas, regex, 2–40); **inmutable en edit** (input disabled con hint "El código no se puede cambiar."). En create es editable.
- `name` requerido (1–120). `description` opcional (≤500, `<Textarea>`).
- `target_vertical_id` opcional (`<Dropdown>` de `GET /catalog/verticals/active` → `VerticalOption[]`; opción "Todas las verticales" = NULL/transversal).
- `start_date` requerido (`<DatePicker>`); `end_date` opcional. Validación cruzada Zod: `end_date >= start_date` (backend re-valida `CAMPAIGN_INVALID_DATES` 400).
- **`status` NO está en el form** (la campaña nace `draft`; el estado se cambia solo por el control de transición, no por update — spec §4.1: `CampaignUpdate` no lleva `status`). El campo `active` (toggle habilitado/deshabilitado) va en edit como `<Switch>` "Campaña habilitada" (distinto del status — soft-disable de negocio).

**Control de cambio de estado** (cabecera del drawer, gated `CAMPAIGNS_UPDATE`) — clon del lenguaje de scheduling:
- **Atajos** (`<Button>` por transición permitida): se renderizan **solo los destinos que la matriz §2 permite** desde el estado actual (constante `CAMPAIGN_TRANSITIONS`, fija en el front):
  - `draft` → **[ Activar ]** (→active)
  - `active` → **[ Pausar ]** (→paused) · **[ Finalizar ]** (→ended)
  - `paused` → **[ Reanudar ]** (→active) · **[ Finalizar ]** (→ended)
  - `ended` → (terminal — sin atajos; el control muestra "Estado finalizado — no admite cambios.")
- Al confirmar un atajo → `POST /campaigns/{id}/transition { to_status }`. El backend re-valida la matriz (`CAMPAIGN_TRANSITION_NOT_ALLOWED` 400 como defensa en profundidad). Tras éxito, el drawer re-fetcha y el badge + los atajos se recalculan. Un `<ConfirmDialog>` ligero para "Finalizar" (acción terminal): "¿Finalizar la campaña '{nombre}'? No podrá reactivarse."
- **NO** hay dropdown "todos los estados" (la matriz tiene a lo sumo 2 destinos por estado → atajos directos bastan, no se necesita el `TransitionControl` de dropdown de crm/scheduling). El badge de estado vive en la cabecera.

**Tab Promociones** (editor M:N `campaign_promotion`, solo edit/view; gated `CAMPAIGNS_UPDATE` para editar) — molde `BotToolsTab` + `SearchableOptionList`:

```
                  │ ╭[ Datos ][ Promociones ][ Auditoría ]╮          │
                  │ │ Promociones de esta campaña                    │
                  │ │ ┌──────────────────────────────────────────┐  │
                  │ │ │ 🔍 Buscar promociones…                    │  │
                  │ │ │ ☑ 2x1 Limpieza (15% · activa)             │  │
                  │ │ │ ☑ Descuento Botox (S/ 50.00 · activa)     │  │
                  │ │ │ ☐ Verano Facial (20% · borrador)          │  │
                  │ │ │ ☐ Promo Septiembre (10%)                  │  │
                  │ │ └──────────────────────────────────────────┘  │
                  │ │ Marca las promociones que pertenecen a esta    │
                  │ │ campaña. Una promoción puede estar en varias.  │
                  │ │                            [ Guardar promos ]  │
```

- Opciones de `GET /promotions/active` → `PromotionOption[]` (cada opción muestra nombre + el descuento listo: "15%" o "S/ 50.00" según `discount_type`/`discount_value`/`currency`, spec §4.2). El estado asignado se carga de `GET /campaigns/{id}/promotions` → `ApiSingle<PromotionOption[]>` (leer `.data`).
- Editor controlado (`SearchableOptionList`, la caller es dueña de `selected[]`); al guardar → bulk-replace `PUT /campaigns/{id}/promotions { promotion_ids: [...] }` (reemplaza el set; el backend valida cada `promotion_id` vivo → `PROMOTION_NOT_FOUND` 400). Tras éxito, `revalidateTag("marketing:campaigns")` + re-fetch (el `promotions_count` de la lista se actualiza).
- Si el viewer no tiene `CAMPAIGNS_UPDATE`, el editor es read-only (lista de promos sin checkboxes editables, sin botón "Guardar promos").

**Tab Auditoría** (solo edit/view): grid Estado (`active`) · ID de la campaña · Creado el/por · Actualizado el/por. `created_by`/`updated_by` hidratados vía `UserAuditInfo` (`created_by_user`/`updated_by_user`, spec §4.1), batch sin N+1, igual que los catálogos de crm/scheduling.

**Modos del drawer**: `create` ("Nueva campaña", solo tab Datos, footer `[ Cancelar ] [ Crear ]`) / `edit` ("Editar campaña", 3 tabs + control de estado, footer `[ Cancelar ] [ Guardar ]`) / `view` ("Detalle de campaña", todo disabled, footer `[ Cerrar ]`).

#### Estados (Pantalla 1)

- **Empty (sin campañas, sin filtro)**: ícono `MegaphoneRegular` + "Aún no hay campañas. Crea la primera para agrupar tus promociones." (el botón "Nueva campaña" del toolbar cumple la función; no va dentro del EmptyState — consistencia con catalog/clinic/staff/scheduling).
- **Empty con filtro status sin matches**: "Ninguna campaña está en este estado." (ej. `?status=ended` sin finalizadas).
- **Loading (primera carga)**: DataTable con 8 skeleton rows; toolbar normal (el server-prefetch del `page.tsx` evita verlo en el primer load).
- **No-results (búsqueda client-side sin matches)**: variante automática de `DataTable` → "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía."
- **Refetching (background)**: tabla `opacity: 0.55` + spinner top-right (overlay `shadow4`), igual que clinic/staff/scheduling.
- **Error (5xx)**: por `error.tsx` global. Soft-errors del create/edit/transition inline en el drawer (`<MessageBar intent="error">`): `CAMPAIGN_CODE_TAKEN` (409, "Ya existe una campaña con este código."), `CAMPAIGN_INVALID_DATES` (400), `TARGET_VERTICAL_NOT_FOUND` (400), `CAMPAIGN_TRANSITION_NOT_ALLOWED` (400, "Esa transición de estado no está permitida.").

#### Componentes Fluent UI / del template (campañas)

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Sidebar | `Sidebar` (auto-renderiza `NAV_ITEMS` filtrados por permisos) |
| Header | `<h1 className={styles.title}>` + `<p className={styles.subtitle}>` |
| Filtro estado | `<Dropdown>` + `nuqs useQueryState("status")` (patrón `OfficesClient`) — opciones del enum `CampaignStatus` |
| Chip filtro | `styles.chip` + `<Button icon={<DismissRegular />} />` (patrón `OfficesClient`) |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Permission gate | `<PermissionGuard anyOf={["CAMPAIGNS_CREATE"]}>` |
| Tabla | `<DataTable<CampaignItem>>` + `useTableQuery({ queryKey: "marketing:campaigns", defaultSort: { field: "start_date", order: "desc" } })` |
| Badge de estado | `<CampaignStatusBadge status={c.status} />` (custom, color por enum vía token — ver Decisiones de UI) |
| Chip de conteo de promos | `<Badge appearance="outline">{n}</Badge>` |
| Resaltado de vigencia | clase aplicada **client-only** ("vigente/por iniciar/vencida" según `start_date`/`end_date` vs hoy) |
| Row menu | `<RowActions item={c} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive ... />` |
| Drawer | `<Drawer size="medium">` + tabs internas (`<TabList>`) + `nuqs useQueryState("campaign_id")` |
| Tab Datos | `<FormField>` + `<Input>`/`<Textarea>`/`<Dropdown>` (vertical) /`<DatePicker>` + `<Switch>` (active) |
| Control de estado (atajos) | `<Button>` por transición permitida (matriz `CAMPAIGN_TRANSITIONS` fija) + `<ConfirmDialog>` para "Finalizar" |
| Editor M:N promociones | `SearchableOptionList` (controlado) → `PUT /campaigns/{id}/promotions { promotion_ids }` |
| Auditoría | grid `styles.audit` (reusado de los catálogos de crm/scheduling) |
| Error inline | `<MessageBar intent="error">` arriba del form/control |

---

### Pantalla 2 — `/marketing/promociones` (tabla de promociones + drawer multi-tab discriminado)

Tabla estructura `OfficesClient`/`DoctorsClient`, con **dos filtros** deep-linkables (tipo de descuento, estado activo), con chip y ×. El botón primario abre el **drawer de promoción** (create) — un form **discriminado por `discount_type`** (molde `ProductDrawer`).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Promociones                                                                  │
│   Define los descuentos y a qué productos y campañas aplican.                  │
│  ┌──────────────┐┌──────────────┐                       ┌──────────────────┐  │
│  │Tipo: Todos  ▾││Estado: Todas▾│                       │+ Nueva promoción │  │
│  └──────────────┘└──────────────┘                       └──────────────────┘  │
│  ┌──────────────────────┐                                                      │
│  │ Tipo: Porcentaje    ✕│  ← chip                                             │
│  └──────────────────────┘                                                      │
│  ╭─ DataTable ──────────────────────────────────────────────────────────────╮ │
│  │ ⋯ │ Código    │ Nombre        │ Descuento  │ Vigencia      │Prods│Camps│Usos│ │
│  ├───┼───────────┼───────────────┼────────────┼───────────────┼─────┼─────┼────┤ │
│  │ ⋯ │ limp_2x1  │ 2x1 Limpieza  │ 15 %       │01 ene–31 mar  │  4  │  1  │ 12 │ │
│  │ ⋯ │ botox_50  │ Descuento Botox│ S/ 50.00  │01 ene–sin cier│Todos│  2  │  3 │ │
│  │ ⋯ │ facial_20 │ Verano Facial │ 20 %       │01–28 feb 2026 │  2  │  0  │  0 │ │
│  ╰──────────────────────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (mapean a `PromotionItem`, spec §4.2):

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `actions` | `""` | RowActions | — | menú `…`: Ver / Editar / Eliminar (gated) |
| `code` | Código | text (mono) | ✅ (server) | `<code>` slug minúsculas |
| `name` | Nombre | text (truncate) | ✅ (server) | `name` |
| `discount` | Descuento | text discriminado | ❌ (derivado) | percentage → `"{discount_value} %"`; fixed → `formatMoney(discount_value, currency)` ("S/ 50.00") |
| `vigencia` | Vigencia | rango de fechas | ❌ (derivado) | `{start_date} – {end_date \|\| "sin cierre"}`; resaltado vigente/vencida **client-only** |
| `products_count` | Productos | número / "Todos" | ❌ (denorm) | "Todos" si `applies_to_all_products`; si no, `products_count` |
| `campaigns_count` | Campañas | número | ❌ (denorm) | `campaigns_count` (chip) |
| `total_uses` | Usos | número | ❌ (denorm) | `total_uses` (link suave a `/marketing/usos?promotion_id={id}`) |

> **Denormalización sin N+1** (spec §6.2): `products_count` (`count_products_map`), `campaigns_count` (`count_campaigns_map`) y `total_uses` (`usage` count) se hidratan en el service por batch. **Lección `cd10c78`**: denormalizadas → NO en `ALLOWED_FIELDS` (`{'code','name','discount_type','currency','start_date','end_date','applies_to_all_products','active','created_on','updated_on'}`, spec §5) → `isSortable: false`. Server-sortable: `code`, `name`, `start_date`/`end_date`. El filtro por **tipo** va sobre `discount_type` (columna real, `?discount_type=percentage|fixed_amount`); el filtro por **estado activo** va sobre `active` (`?active=true|false`). `defaultSort = { field: "created_on", order: "desc" }` (default del `useTableQuery`).

**Filtros (Dropdown + chip + deep-link)** — espejo de `OfficesClient`:
- **Tipo de descuento**: `<Dropdown>` con `DiscountType` (Porcentaje / Monto fijo). `null` = "Todos los tipos". `?discount_type=percentage|fixed_amount`. Chip "Tipo: {etiqueta} ✕".
- **Estado activo**: `<Dropdown>` (Activas / Inactivas / Todas) sobre `active`. `?active=true|false`. Chip "Estado: {etiqueta} ✕".

**RowActions** (gated): 👁 **Ver** (`PROMOTIONS_READ`, drawer `view` + `?promotion_id=`), ✏ **Editar** (`PROMOTIONS_UPDATE`, drawer `edit`), 🗑 **Eliminar** (`PROMOTIONS_DELETE`, `DELETE /promotions/{id}` soft-delete).
**Botón "+ Nueva promoción"**: gated `<PermissionGuard anyOf={["PROMOTIONS_CREATE"]}>`.

#### Drawer de promoción (`PromotionDrawer`, create/edit/view) — tabs internas + form discriminado

`<Drawer size="medium">` con tabs internas. **Create**: tabs **Datos** · **Descuento** · **Vigencia y límites** · **Productos** (los M:N de campañas y la auditoría aparecen en edit). **Edit/View**: 6 tabs — **Datos** · **Descuento** · **Vigencia y límites** · **Productos** (M:N) · **Campañas** (read-only) · **Auditoría**.

**Tab Datos** — `code` (slug minúsculas 2–40, **inmutable en edit**), `name` (1–120), `description` (≤500), `active` toggle (en edit). Espejo de los campos comunes de `PromotionCreate`/`PromotionUpdate`.

**Tab Descuento — DISCRIMINADO por `discount_type`** (el corazón del drawer; molde del `ProductDrawer` con `form.watch`):

```
                  │ ╭[ Datos ][ Descuento ][ Vigencia ][ Productos ]…╮│
                  │ │ Tipo de descuento *                            │
                  │ │ ( ) Porcentaje    (•) Monto fijo               │ ← Dropdown/Radio
                  │ │ ┄┄┄┄┄┄┄┄┄┄┄ percentage ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
                  │ │ Porcentaje *      (0–100)                       │
                  │ │ [ 15        ] %                                 │
                  │ │ Se descuenta el 15 % del precio del producto.  │
                  │ │ ┄┄┄┄┄┄┄┄┄┄┄ fixed_amount ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
                  │ │ Monto *           Moneda *                      │
                  │ │ [ 50.00     ]     [ PEN ▾ ]                     │
                  │ │ Se descuentan S/ 50.00 (tope: precio del prod.)│
                  │ │ ⓘ El tipo de descuento no se puede cambiar     │
                  │ │   después de crear la promoción.               │
```

- **Selector `discount_type`**: `<Dropdown>` (o `<RadioGroup>`) con "Porcentaje" / "Monto fijo". **Inmutable en edit** (disabled + hint "El tipo de descuento no se puede cambiar." — spec §3.2/§4.2: `discount_type` inmutable post-create). `form.watch("discount_type")` controla el render condicional de abajo.
- **Si `percentage`**: `<Input inputMode="decimal">` (o number) **Porcentaje** con sufijo "%"; validación 0 < v ≤ 100 (Zod `superRefine` + backend `PROMOTION_INVALID_DISCOUNT`). El campo `currency` se **oculta** (no aplica). Copy dinámico "Se descuenta el {v} % del precio del producto."
- **Si `fixed_amount`**: `<Input inputMode="decimal">` **Monto** (decimal-string `^\d+(\.\d{1,2})?$`, **`string` en el wire**, no number) + `<Dropdown>` **Moneda** (`currency`, `SUPPORTED_CURRENCIES`, default "PEN"); validación v > 0 (Zod + backend `PROMOTION_INVALID_DISCOUNT`). Copy dinámico "Se descuentan {formatMoney} (tope: precio del producto)" (el descuento se capa al `base_price`, spec §6.3).
- **Zod**: NO `z.discriminatedUnion` (por el `.partial()` del update) → base + `refineDiscount(data, ctx)` aplicado con `.superRefine()` a create Y update (spec §10): `percentage` = number 0-100; `fixed_amount` = decimal-string + currency `z.enum(SUPPORTED_CURRENCIES)`. La validación de rango la impone también el SERVICE (uniforme entre create/update, spec §6.2).

**Tab Vigencia y límites** — `start_date` requerido (`<DatePicker>`), `end_date` opcional; validación `end_date >= start_date` (backend `PROMOTION_INVALID_DATES`). `max_uses_total` opcional (`<Input>` ge=1; vacío = "ilimitado"), `max_uses_per_person` opcional (ge=1; vacío = "ilimitado"). Hints: "Déjalo vacío para usos ilimitados."

**Tab Productos** (editor M:N `promotion_product`, gated `PROMOTIONS_UPDATE`):

```
                  │ │ ☑ Aplica a todos los productos                 │ ← toggle
                  │ │   (cuando está activo, ignora la lista)        │
                  │ │ ┄┄┄┄┄┄┄ si el toggle está APAGADO ┄┄┄┄┄┄┄┄┄┄┄┄ │
                  │ │ Productos cubiertos                            │
                  │ │ ┌──────────────────────────────────────────┐  │
                  │ │ │ 🔍 Buscar productos…                      │  │
                  │ │ │ ☑ Limpieza dental                         │  │
                  │ │ │ ☑ Consulta general                        │  │
                  │ │ │ ☐ Botox facial                            │  │
                  │ │ └──────────────────────────────────────────┘  │
                  │ │                          [ Guardar productos ] │
```

- `applies_to_all_products` `<Switch>` "Aplica a todos los productos": cuando está **ON**, oculta el `SearchableOptionList` (el M:N se ignora; spec §3.2 `true = ignora M:N`). El toggle es parte del `PromotionUpdate` (se guarda con el form de Datos/Descuento o con un PUT del propio drawer).
- Cuando está **OFF**: `SearchableOptionList` de productos (`GET /catalog/products/active` → `ProductOption[]`; asignados de `GET /promotions/{id}/products` → `ApiSingle<ProductOption[]>`, leer `.data`). Bulk-replace `PUT /promotions/{id}/products { product_ids: [...] }` (backend valida cada product vivo → `PRODUCT_NOT_FOUND` 400).

**Tab Campañas (read-only)** — chips con las campañas que incluyen esta promoción (`PromotionDetail.campaigns: list[CampaignOption]`, spec §4.2; cada chip = `<CampaignStatusBadge>` + nombre). **No editable desde acá** (el M:N se administra desde el lado de la campaña, tab Promociones). Hint: "Las campañas se gestionan desde cada campaña." Si vacío: "Esta promoción no está en ninguna campaña."

**Tab Auditoría** (edit/view): grid Estado · ID de la promoción · Creado el/por · Actualizado el/por + **conteo total de usos** (`total_uses`, link a `/marketing/usos?promotion_id={id}`). `created_by`/`updated_by` vía `UserAuditInfo`.

**Modos del drawer**: `create` ("Nueva promoción") / `edit` ("Editar promoción") / `view` ("Detalle de promoción", disabled, footer `[ Cerrar ]`).

#### Estados (Pantalla 2)

- **Empty (sin promociones)**: ícono `TicketDiamondRegular` + "Aún no hay promociones. Crea la primera para ofrecer descuentos."
- **Empty con filtro tipo/estado sin matches**: "Ninguna promoción es de este tipo." / "Ninguna promoción está en este estado."
- **Loading**: DataTable con 8 skeleton rows.
- **No-results (búsqueda client-side)**: genérico de `DataTable`.
- **Refetching**: tabla `opacity: 0.55` + spinner top-right.
- **Error**: 5xx por `error.tsx`. Soft-errors inline en el drawer (`<MessageBar intent="error">`): `PROMOTION_CODE_TAKEN` (409, "Ya existe una promoción con este código."), `PROMOTION_INVALID_DISCOUNT` (400, "El valor del descuento no es válido para el tipo elegido."), `PROMOTION_INVALID_DATES` (400), `PRODUCT_NOT_FOUND` (400 al asignar un producto inexistente).

#### Componentes Fluent UI (promociones)

| Concepto UI | Componente |
|---|---|
| Filtros | `<Dropdown>` + `nuqs useQueryState("discount_type"/"active")` + chip |
| Tabla | `<DataTable<PromotionItem>>` + `useTableQuery({ queryKey: "marketing:promotions", defaultSort: { field: "created_on", order: "desc" } })` |
| Columna descuento | render discriminado (percentage → "{v} %"; fixed → `formatMoney(v, currency)`) |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Drawer | `<Drawer size="medium">` + tabs internas (`<TabList>`) + `nuqs useQueryState("promotion_id")` |
| Tab Datos | `<FormField>` + `<Input>` (code disabled en edit) /`<Textarea>` + `<Switch>` (active) |
| Selector tipo descuento | `<Dropdown>`/`<RadioGroup>` (disabled en edit) + `form.watch("discount_type")` para el render condicional |
| Input porcentaje | `<Input>` (number 0-100) con sufijo "%" |
| Input monto fijo | `<Input inputMode="decimal">` (decimal-string) + `<Dropdown>` moneda (`SUPPORTED_CURRENCIES`) |
| Vigencia / límites | `<DatePicker>` + `<Input>` (max_uses_*, ge=1, vacío=ilimitado) |
| Toggle todos los productos | `<Switch>` `applies_to_all_products` (oculta el picker cuando ON) |
| Editor M:N productos | `SearchableOptionList` (controlado) → `PUT /promotions/{id}/products { product_ids }` |
| Tab Campañas (read-only) | chips (`<CampaignStatusBadge>` + nombre), no editable |
| Auditoría | grid `styles.audit` + conteo de usos (link a `/marketing/usos`) |
| Error inline | `<MessageBar intent="error">` arriba del form |

---

### Pantalla 3 — `/marketing/usos` (reporte read-only de usos de promoción)

Tabla **read-only** (sin RowActions de mutación, sin drawer de edición) que lista los `PromotionUsage`, con filtros chip + deep-link. Es la "vista de redenciones": quién usó qué promo, en qué producto, cuánto se descontó y cuándo. Molde `mis-leads`/`DoctorsClient` read-only. Gateada `PROMOTION_USAGES_READ`.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Usos de promoción                                                            │
│   Historial de promociones aplicadas (descuentos redimidos).                   │
│  ┌──────────────┐┌──────────────┐┌──────────────┐                             │
│  │Promo: Todas ▾││Persona…     🔍││Fecha: Todas ▾│                            │
│  └──────────────┘└──────────────┘└──────────────┘                             │
│  ┌──────────────────────┐ ┌──────────────────────┐                            │
│  │ Promo: 2x1 Limpieza ✕│ │ Fecha: feb 2026     ✕│  ← chips                   │
│  └──────────────────────┘ └──────────────────────┘                            │
│  ╭─ DataTable ──────────────────────────────────────────────────────────────╮ │
│  │ Fecha       │ Promoción    │ Persona      │ Producto   │ Original│ Desc. │Final│ │
│  ├─────────────┼──────────────┼──────────────┼────────────┼─────────┼───────┼─────┤ │
│  │ 12 feb 2026 │ 2x1 Limpieza │ Ana Torres   │ Limpieza   │ S/120.00│S/18.00│102.0│ │
│  │ 11 feb 2026 │ 2x1 Limpieza │ Luis Rojas   │ Limpieza   │ S/120.00│S/18.00│102.0│ │
│  │ 10 feb 2026 │ Desc. Botox  │ María Quispe │ Botox      │ S/400.00│S/50.00│350.0│ │
│  ╰──────────────────────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (mapean a `PromotionUsageItem`, spec §4.3; todo **read-only**, montos = `string` formateados con moneda):

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `created_on` | Fecha | date | ✅ (server, columna real / en `ALLOWED_FIELDS`) | `formatDate(created_on)` ("12 feb 2026") |
| `promotion_name` | Promoción | text (truncate) | ❌ (denorm) | `promotion_name` (deep-link al filtro por `promotion_id`) |
| `person_name` | Persona | text (truncate) | ❌ (denorm) | `person_name` (vía `person_option_map`) |
| `product_name` | Producto | text (truncate) | ❌ (denorm) | `product_name` |
| `campaign_name` | Campaña | text (truncate) | ❌ (denorm) | `campaign_name` o "—" si NULL |
| `original_amount` | Original | money | ❌ | `formatMoney(original_amount, currency)` |
| `discount_amount` | Descuento | money | ❌ | `formatMoney(discount_amount, currency)` |
| `final_amount` | Final | money | ❌ | `formatMoney(final_amount, currency)` |
| `appointment_id` | Cita | link/ícono | ❌ | ícono 📅 + link a la cita si `appointment_id` ≠ NULL; "—" si redención sin cita |

> **Denormalización sin N+1** (spec §6.3 `list_paginated`): `promotion_name`, `person_name` (vía `crm.person_option_map`), `product_name`, `campaign_name` se hidratan por batch. `created_by_user` (audit) también. **Lección `cd10c78`**: denormalizadas → NO en `ALLOWED_FIELDS` (`{'promotion_id','person_id','product_id','appointment_id','campaign_id','currency','created_on'}` — sin `updated_on`, es audit; spec §5) → `isSortable: false`. **Server-sortable solo `created_on`** (columna real indexada); `defaultSort = { field: "created_on", order: "desc" }`. Los filtros van por **id** (`promotion_id`/`person_id`/rango de `created_on`), no por texto.

**Filtros (deep-link + chip)** — read-only, sin mutación:
- **Promoción**: `<Dropdown>` de `GET /promotions/active` → `PromotionOption[]`. `?promotion_id=X`. Chip "Promo: {nombre} ✕". (Es el deep-link que llega desde la columna "Usos" de la pantalla de promociones y desde el tab Auditoría del drawer.)
- **Persona**: buscador/`<Input>` o `<Dropdown>` (según volumen) que mapea a `?person_id=X`. Chip "Persona: {nombre} ✕". (La búsqueda exacta de persona puede reusar el buscador de crm; mínimo MVP: filtro por id vía deep-link.)
- **Fecha**: `<DatePicker>` o presets (mes/rango) → `?date_from=&date_to=` sobre `created_on`. Chip "Fecha: {rango} ✕". Default "Todas" (cálculo de "hoy"/rango **client-only**, TZ).

**Sin RowActions, sin botón crear, sin drawer de edición**: la tabla es de solo lectura (audit inmutable). Un drawer de **solo-lectura** con el detalle de un uso (`PromotionUsageDetail`, hoy = `Item`) es **diferible/opcional** (no MVP — no aporta datos extra). La aplicación de promos no se hace acá (se hace al reservar una cita en scheduling o desde el bot).

#### Estados (Pantalla 3)

- **Empty (sin usos aún, sin filtro)**: ícono `ReceiptRegular` + "Aún no se ha aplicado ninguna promoción. Los descuentos redimidos aparecerán aquí."
- **Empty con filtro promo sin matches**: "Esta promoción no se ha usado todavía."
- **Empty con filtro persona/fecha sin matches**: "No hay usos con los filtros actuales."
- **Loading**: DataTable con 8 skeleton rows.
- **No-results (búsqueda client-side)**: genérico de `DataTable`.
- **Refetching**: tabla `opacity: 0.55` + spinner top-right.
- **Error**: 5xx por `error.tsx` global.

#### Componentes Fluent UI (usos)

| Concepto UI | Componente |
|---|---|
| Header | `<h1>` + `<p>` |
| Filtro promoción | `<Dropdown>` + `nuqs useQueryState("promotion_id")` + chip |
| Filtro persona | `<Input contentBefore={<SearchRegular />} />` / `<Combobox>` → `?person_id=` + chip |
| Filtro fecha | `<DatePicker>` / presets → `?date_from=&date_to=` (client-only) + chip |
| Tabla (read-only) | `<DataTable<PromotionUsageItem>>` + `useTableQuery({ queryKey: "marketing:promotion-usages", defaultSort: { field: "created_on", order: "desc" } })` (sin `RowActions` de mutación) |
| Montos con moneda | `formatMoney(value, currency)` (helper; `value` es `string` del backend) |
| Fecha | `formatDate(created_on)` (audit absoluta, no relativa) |
| Link a cita | `<Link>` a `/scheduling/citas?appointment_id=` (si `appointment_id` ≠ NULL) |
| Estados | `<EmptyState>` + skeletons + spinner refetch |

---

## Decisiones de UI (cierres)

### Campaña/Promoción en drawer con tabs internas; Usos como reporte read-only
Ninguna de las 3 entidades llega al umbral de "página con tabs" de `Person`/`Office`/`Doctor` (sin timeline pesado ni multi-superficie editable densa). Campaign/Promotion = **drawer `size="medium"` con tabs internas** (Datos / M:N / Auditoría, + Descuento/Vigencia/Productos/Campañas en Promotion); el drawer sincroniza `?campaign_id=`/`?promotion_id=` para deep-link. PromotionUsage = **reporte read-only** (audit inmutable, sin mutaciones). El peso del sub-recurso manda la forma; marketing es "catálogos ricos", no "records con timeline".

### `CampaignStatusBadge` — color por enum vía token Fluent (NO por catálogo)
A diferencia de crm/scheduling (donde el badge lee el `color` hex del catálogo `LeadStatus.color`/`AppointmentStatus.color`), `Campaign` **no tiene** columna `color` (su `status` es enum fijo §2, no catálogo). El badge mapea el enum a un **token Fluent fijo** (recordatorio: NO existe `brandPalette.accent`):

| `status` | Etiqueta | Color (token Fluent) |
|---|---|---|
| `draft` | "Borrador" | `tokens.colorNeutralForeground3` (gris/neutro, `appearance="outline"`) |
| `active` | "Activa" | `tokens.colorPaletteGreenForeground1` (verde) |
| `paused` | "Pausada" | `tokens.colorPaletteMarigoldForeground2` (ámbar) |
| `ended` | "Finalizada" | `tokens.colorNeutralForeground4` (gris apagado) |

`CampaignStatusBadge` recibe `{ status }` y renderiza un `<Badge appearance="tint" color={...}>` con la etiqueta ES. Consistente en la lista, la cabecera del drawer y los chips de campaña del tab "Campañas" de la promoción. Es la única diferencia de fondo con los badges de crm/scheduling.

### Control de cambio de estado = atajos según la matriz fija (NO dropdown de "todos los estados")
Clon del lenguaje de `TransitionControl` + atajos de scheduling, pero la **matriz es fija en el frontend** (constante `CAMPAIGN_TRANSITIONS`, espejo de la matriz §2 hardcodeada en el service), **no** se consulta un endpoint de transiciones (no existe — `Campaign.status` no es un catálogo con aristas configurables). Se renderizan **solo los atajos que la matriz permite** desde el estado actual (`draft`→Activar; `active`→Pausar/Finalizar; `paused`→Reanudar/Finalizar; `ended`→terminal, sin atajos). El usuario **no puede elegir una transición inválida** (no aparece); el backend re-valida (`CAMPAIGN_TRANSITION_NOT_ALLOWED` 400) como defensa en profundidad. "Finalizar" pide confirmación (terminal). Como la matriz tiene ≤2 destinos por estado, **bastan atajos** (no se necesita el dropdown del `TransitionControl` de crm/scheduling).

### Form de descuento discriminado por `discount_type` (molde `ProductDrawer`)
El tab Descuento de la promoción renderiza condicionalmente según `form.watch("discount_type")`: `percentage` → input de porcentaje 0-100 (number) sin moneda; `fixed_amount` → input de monto (decimal-**string** en el wire) + dropdown de moneda. `discount_type` es **inmutable en edit** (disabled + hint). Zod: NO `z.discriminatedUnion` (por el `.partial()` del update) → base + `superRefine` aplicado a create Y update (spec §10); el SERVICE también valida el rango (uniforme entre create/update, `PROMOTION_INVALID_DISCOUNT`).

### Decimales = `string` en el wire; montos formateados con moneda
`discount_value` (fixed), `original_amount`, `discount_amount`, `final_amount` viajan como **`string`** (Numeric(10,2)). En TS se tipan `string`; los inputs de monto van `inputMode="decimal"` (no `type=number` — evita el round-trip de `number` que pierde la representación exacta). El `percentage` puede ser `number`. El render usa `formatMoney(value, currency)` (helper client-side que respeta el ISO `currency` de cada fila — distintas filas pueden tener distinta moneda; el símbolo se deriva del ISO, ej. PEN → "S/").

### Editores M:N por bulk-replace `PUT` (molde `BotToolsTab`/doctores)
Los dos M:N (`campaign_promotion`, `promotion_product`) usan `SearchableOptionList` **controlado** (la caller es dueña de `selected[]`) + bulk-replace **`PUT`** (no PATCH): `PUT /campaigns/{id}/promotions { promotion_ids }` y `PUT /promotions/{id}/products { product_ids }`. El GET de asignados devuelve `ApiSingle<Option[]>` → leer `.data`. El M:N campaña↔promoción se edita **solo desde el lado de la campaña** (tab Promociones); en la promoción el tab "Campañas" es **read-only** (evita dos fuentes de verdad para el mismo set). El toggle `applies_to_all_products` oculta el picker de productos cuando está ON (ignora el M:N).

### `applies_to_all_products` oculta el picker
Cuando el toggle "Aplica a todos los productos" está ON, el `SearchableOptionList` de productos se oculta y el M:N se ignora (spec §3.2: `true = ignora M:N`). El cómputo de cobertura (`covers_product`) en el `apply` del service corta por el toggle antes de mirar el M:N (spec §6.3 paso 5).

### Filtros por enum/id, nunca por texto denormalizado (hotfix `cd10c78`)
El filtro de status de campañas va sobre `status` (columna real en `ALLOWED_FIELDS`); el de tipo/estado de promociones sobre `discount_type`/`active` (reales); los de usos por `promotion_id`/`person_id`/`created_on`. `target_vertical_name`/`promotions_count`/`products_count`/`campaigns_count`/`total_uses`/`promotion_name`/`person_name`/`product_name`/`campaign_name` son denormalizados (batch, sin N+1) y NO están en `ALLOWED_FIELDS` → `isSortable: false`; nunca se ordena/filtra server-side por ellos (da 400). `defaultSort`/`searchFields` solo columnas reales. La búsqueda visible por nombre es client-side sobre lo cargado.

### "Hoy"/vigencia siempre client-only (TZ)
La vigencia ("vigente / por iniciar / vencida") y el default de los `DatePicker`/filtros de fecha se computan **client-only** (`useEffect`/`useMemo`, no SSR). Aunque `start_date`/`end_date` son `date` (sin hora/TZ), el cómputo de "¿hoy cae dentro?" usa `new Date()` → el SSR en UTC desfasaría el día en Lima (UTC-5) — bug recurrente de staff/crm/scheduling. Las fechas absolutas (auditoría, `created_on` de usos) usan `formatDate` (no relativas).

### Usos de promoción no se mutan desde la UI (audit inmutable)
`PromotionUsage` es PK·A·T (sin SoftDelete). La pantalla `/marketing/usos` es **read-only** total: sin crear, editar, ni borrar. Las filas las crea el `apply` del service (manual `POST /promotion-usages` con `PROMOTION_APPLY`, o automático desde scheduling/bot con `created_by = SYSTEM_USER_ID`). El "aplicar" se hace en el flujo de reserva de cita (scheduling) o de bot, no desde marketing.

### Sin i18n framework por ahora
Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm/scheduling). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive
Mismo criterio que catalog/clinic/staff/crm/scheduling (template optimizado para desktop interno): sidebar colapsado por default; DataTable scrollea horizontal; drawers a 100% del width en mobile; los tabs internos del drawer scrollean horizontal el `TabList` en mobile (Fluent lo soporta). No se diseñan pantallas mobile-first separadas.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, CSS classes, tags, perms) en inglés — solo los textos visibles van traducidos. Glosario clave: **Campaign = Campaña** (femenino), **Promotion = Promoción** (femenino), **PromotionUsage = Uso de promoción** (masculino), **Descuento** (masculino), **Vigencia** (femenino), **Producto** (masculino), **Persona** (femenino), **Estado** (masculino), **Vertical** (femenino). Estados de campaña: **Borrador / Activa / Pausada / Finalizada**.

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Sidebar — | |
| Grupo | "Marketing" |
| Items | "Campañas" · "Promociones" · "Usos de promoción" |
| — Campañas (tabla) — | |
| Page title | "Campañas" |
| Page subtitle | "Gestiona las campañas de marketing y sus promociones." |
| Botón crear | "+ Nueva campaña" |
| Filtro estado (placeholder) | "Todos los estados" |
| Chip filtro | "Estado: {etiqueta} ✕" |
| Columnas | "Código" / "Nombre" / "Estado" / "Vigencia" / "Vertical" / "Promos" |
| Vigencia sin cierre | "sin cierre" |
| Vertical (transversal) | "Todas" |
| Empty (sin campañas) | "Aún no hay campañas. Crea la primera para agrupar tus promociones." |
| Empty (filtro estado) | "Ninguna campaña está en este estado." |
| No-results genérico | "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía." |
| RowAction ver/editar/eliminar | "Ver" / "Editar" / "Eliminar" |
| Confirm delete (título) | "¿Eliminar campaña?" |
| Confirm delete (body) | "¿Eliminar la campaña '{nombre}'? Se ocultará; los usos de promoción que la referencian se conservan." |
| — Drawer de campaña — | |
| Drawer title | "Nueva campaña" / "Editar campaña" / "Detalle de campaña" |
| Tabs | "Datos" · "Promociones" · "Auditoría" |
| Labels | "Código" / "Nombre" / "Descripción" / "Vertical objetivo (opcional)" / "Inicio" / "Fin (opcional)" |
| Hint código | "Minúsculas, sin espacios (ej. verano26)." |
| Hint código inmutable | "El código no se puede cambiar." |
| Toggle activo | "Campaña habilitada" |
| Vertical (placeholder) | "Todas las verticales" |
| Hint estado | "El estado se gestiona arriba (no aquí)." |
| Label cambiar estado | "Cambiar estado:" |
| Atajos de estado | "Activar" / "Pausar" / "Reanudar" / "Finalizar" |
| Estado terminal | "Estado finalizado — no admite cambios." |
| Confirm finalizar | "¿Finalizar la campaña '{nombre}'? No podrá reactivarse." |
| Título tab promos | "Promociones de esta campaña" |
| Hint promos | "Marca las promociones que pertenecen a esta campaña. Una promoción puede estar en varias." |
| Botón guardar promos | "Guardar promociones" / "Guardando…" |
| Empty promos (en drawer) | "Esta campaña aún no tiene promociones." |
| Error código tomado | "Ya existe una campaña con este código." |
| Error fechas | "La fecha de fin no puede ser anterior a la de inicio." |
| Error vertical | "La vertical seleccionada no existe." |
| Error transición | "Esa transición de estado no está permitida." |
| Botón crear / guardar | "Crear" / "Creando…" — "Guardar" / "Guardando…" |
| — Promociones (tabla) — | |
| Page title | "Promociones" |
| Page subtitle | "Define los descuentos y a qué productos y campañas aplican." |
| Botón crear | "+ Nueva promoción" |
| Filtro tipo (placeholder) | "Todos los tipos" |
| Filtro estado (placeholder) | "Todas" |
| Chip filtro | "Tipo: {etiqueta} ✕" / "Estado: {etiqueta} ✕" |
| Columnas | "Código" / "Nombre" / "Descuento" / "Vigencia" / "Productos" / "Campañas" / "Usos" |
| Productos (todos) | "Todos" |
| Empty (sin promos) | "Aún no hay promociones. Crea la primera para ofrecer descuentos." |
| Empty (filtro tipo) | "Ninguna promoción es de este tipo." |
| Empty (filtro estado) | "Ninguna promoción está en este estado." |
| Confirm delete (título) | "¿Eliminar promoción?" |
| Confirm delete (body) | "¿Eliminar la promoción '{nombre}'? Se ocultará; los usos registrados se conservan." |
| — Drawer de promoción — | |
| Drawer title | "Nueva promoción" / "Editar promoción" / "Detalle de promoción" |
| Tabs | "Datos" · "Descuento" · "Vigencia y límites" · "Productos" · "Campañas" · "Auditoría" |
| Labels datos | "Código" / "Nombre" / "Descripción" |
| Hint código inmutable | "El código no se puede cambiar." |
| Toggle activo | "Promoción habilitada" |
| Label tipo descuento | "Tipo de descuento" |
| Opciones tipo | "Porcentaje" / "Monto fijo" |
| Hint tipo inmutable | "El tipo de descuento no se puede cambiar después de crear la promoción." |
| Label porcentaje | "Porcentaje" |
| Copy porcentaje | "Se descuenta el {v} % del precio del producto." |
| Label monto | "Monto" |
| Label moneda | "Moneda" |
| Copy monto fijo | "Se descuentan {monto} (tope: precio del producto)." |
| Labels vigencia | "Inicio" / "Fin (opcional)" / "Usos máximos (total)" / "Usos máximos por persona" |
| Hint límites | "Déjalo vacío para usos ilimitados." |
| Toggle todos productos | "Aplica a todos los productos" |
| Hint todos productos | "Cuando está activo, se ignora la lista de productos." |
| Título tab productos | "Productos cubiertos" |
| Botón guardar productos | "Guardar productos" / "Guardando…" |
| Empty productos | "Esta promoción no cubre ningún producto." |
| Título tab campañas | "Campañas que la incluyen" |
| Hint campañas (read-only) | "Las campañas se gestionan desde cada campaña." |
| Empty campañas | "Esta promoción no está en ninguna campaña." |
| Error código tomado | "Ya existe una promoción con este código." |
| Error descuento inválido | "El valor del descuento no es válido para el tipo elegido." |
| Error fechas | "La fecha de fin no puede ser anterior a la de inicio." |
| Error producto | "El producto seleccionado no existe." |
| — Usos de promoción — | |
| Page title | "Usos de promoción" |
| Page subtitle | "Historial de promociones aplicadas (descuentos redimidos)." |
| Filtro promo (placeholder) | "Todas las promociones" |
| Filtro persona (placeholder) | "Buscar persona…" |
| Filtro fecha (placeholder) | "Todas las fechas" |
| Chip filtro | "Promo: {nombre} ✕" / "Persona: {nombre} ✕" / "Fecha: {rango} ✕" |
| Columnas | "Fecha" / "Promoción" / "Persona" / "Producto" / "Campaña" / "Original" / "Descuento" / "Final" / "Cita" |
| Campaña / cita (vacío) | "—" |
| Empty (sin usos) | "Aún no se ha aplicado ninguna promoción. Los descuentos redimidos aparecerán aquí." |
| Empty (filtro promo) | "Esta promoción no se ha usado todavía." |
| Empty (filtro persona/fecha) | "No hay usos con los filtros actuales." |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Botón cancelar | "Cancelar" |
| Botón cerrar (view) | "Cerrar" |
| Loading placeholder en inputs | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |
| Audit labels | "Estado", "ID", "Creado el", "Creado por", "Actualizado el", "Actualizado por" |
| Status badge (active/inactive de catálogo) | "Activo" / "Inactivo" |

### Concordancia de género

- **Campaña / Promoción / Persona / Vigencia / Vertical / Moneda** son **femenino**: "la campaña", "Nueva campaña", "la promoción", "Eliminar la promoción", "la persona", "la vigencia".
- **Uso / Descuento / Producto / Estado / Código / Monto / Motivo / Tope** son **masculino**: "el uso", "el descuento", "el producto", "este estado", "el código", "el monto".
- En confirm dialogs mantener concordancia: "¿Eliminar **la** campaña?" / "¿Eliminar **la** promoción?" / "¿Finalizar **la** campaña?".

### Etiquetas de `CampaignStatus`

`status` (enum) en inglés, etiqueta visible en español. Color por token Fluent (no hay color de catálogo):

| `status` | Etiqueta | Color (token) |
|---|---|---|
| `draft` | "Borrador" | neutro (`appearance="outline"`) |
| `active` | "Activa" | verde (`colorPaletteGreenForeground1`) |
| `paused` | "Pausada" | ámbar (`colorPaletteMarigoldForeground2`) |
| `ended` | "Finalizada" | gris apagado (`colorNeutralForeground4`) |

### Etiquetas de `DiscountType`

| `discount_type` | Etiqueta | Render del valor |
|---|---|---|
| `percentage` | "Porcentaje" | "{discount_value} %" |
| `fixed_amount` | "Monto fijo" | `formatMoney(discount_value, currency)` (ej. "S/ 50.00") |

## Mapeo a fases de implementación (checklist de UI F0–F4)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md) y la spec §12 F0–F4). Cada checkbox es una tarea de UI.

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: grupo "Marketing" en `NAV_ITEMS` con 3 children (Campañas / Promociones / Usos de promoción), gate `MENU-MARKETING` + permiso por child; íconos Fluent verificados con fallback (`MegaphoneRegular`/`TicketDiamondRegular`/`ReceiptRegular`).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.MARKETING` (`const MARKETING = "/api/v1/marketing"`) con CAMPAIGNS (list/create/active/{id}/transition/promotions) · PROMOTIONS (list/create/active/{id}/products/usage-summary/eligible-for/validate) · PROMOTION_USAGES (compute-price/apply/list). Sub-recursos M:N como funciones: `CAMPAIGNS.PROMOTIONS_LIST(id)`/`PROMOTIONS_UPDATE(id)`, `PROMOTIONS.PRODUCTS_LIST(id)`/`PRODUCTS_UPDATE(id)`. **PUT no PATCH**.
- [ ] `types/marketing.types.ts`: interfaces espejo de Pydantic (`CampaignItem`/`Detail`/`Option`, `PromotionItem`/`Detail`/`Option`, `PromotionUsageItem`/`Detail`, `PromotionEligibility`, `ComputePriceResponse`, `PromotionUsageSummary`, payloads). **Decimales → `string`**; enums `CampaignStatus`/`DiscountType` como union + const readonly array; 6 cols audit (`created_by_user: UserAuditInfo | null`, etc.).
- [ ] `lib/schemas/marketing.schema.ts`: Zod base/create/update de campaign y promotion (discount **discriminado** vía `superRefine` a create Y update; NO `discriminatedUnion`; `code` slug inmutable; `currency` `z.enum(SUPPORTED_CURRENCIES)`).
- [ ] Componentes compartidos stub: `CampaignStatusBadge` (color por enum), `formatMoney(value, currency)` helper.

### F1 — Campaign
- [ ] **Pantalla 1** `/marketing/campanas`: lista (`DataTable`) + columnas denormalizadas (NO sortable: `target_vertical_name`/`promotions_count`/`vigencia`; sortable `code`/`name`/`start_date`) + filtro por status (chip + deep-link) + `RowActions` (Ver/Editar/Eliminar gated) + estados empty/loading/no-results/refetching/error.
- [ ] **CampaignDrawer** tab **Datos** (create + edit) con `code` inmutable en edit + vertical dropdown + fechas + control de cambio de estado (atajos `CAMPAIGN_TRANSITIONS` fijos) + tab **Auditoría**.
- [ ] **OJO subset F1** (spec §12): el tab **Promociones** y `promotions_count` llegan en F2 (Promotion no existe aún → `CampaignDetail.promotions = []`, `promotions_count = 0`). Dejar el tab como placeholder ("Disponible al crear promociones") o no renderizarlo hasta F2.
- [ ] Migración backend `0022_marketing_campaign` + cierre FKs forward (no toca UI).

### F2 — Promotion + M:N
- [ ] **Pantalla 2** `/marketing/promociones`: lista + columnas denormalizadas + filtros tipo/estado (chip + deep-link) + RowActions + estados.
- [ ] **PromotionDrawer** multi-tab: **Datos** · **Descuento** (discriminado por `discount_type`, inmutable en edit) · **Vigencia y límites** · **Productos** (toggle `applies_to_all_products` + `SearchableOptionList` → `PUT /products`) · **Campañas** (read-only chips) · **Auditoría**.
- [ ] **CampaignDrawer** tab **Promociones** activado (editor M:N `SearchableOptionList` → `PUT /campaigns/{id}/promotions`); `promotions_count`/`products_count`/`campaigns_count`/`total_uses` activos en las tablas.

### F3 — PromotionUsage (reporte)
- [ ] **Pantalla 3** `/marketing/usos`: DataTable **read-only** (sin RowActions de mutación) + filtros promo/persona/fecha (chip + deep-link) + montos con `formatMoney` + link a cita + estados. Gated `PROMOTION_USAGES_READ`.
- [ ] Link "Usos" desde la tabla de promociones y desde el tab Auditoría del drawer → `/marketing/usos?promotion_id={id}`.

### F4 — Integración (sin pantallas nuevas de marketing)
- [ ] **scheduling** (toca el módulo scheduling, no marketing): `AppointmentCreate` gana `apply_promotion_id?` opcional; (opcional, nice-to-have) un selector de promo elegible en el **paso de confirmación** del wizard de reserva que consume `eligibleFor(product_id, person_id)` → lista `PromotionEligibility[]` (mostrar descuento/precio final). Mínimo MVP: el campo opcional en el espejo de tipos del wizard. El descuento aplicado se refleja luego en `/marketing/usos` (con `appointment_id` poblado).
- [ ] **bots** (toca bots, no marketing): sin UI nueva. La tool `list_eligible_promotions` y el `apply_promotion_id` extendido en `book_appointment` no tienen superficie de admin propia; sus efectos se ven en `/marketing/usos` (origen automático, `created_by = SYSTEM_USER_ID`).
