# Módulo `clinic` — UI design

> **Última actualización**: 2026-05-29
> **Audiencia**: developer implementando las pantallas de clinic en `frontend/src/app/(main)/clinic/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview), [`backend.md`](backend.md) (contracts), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template).

> **Alineación con el catálogo ya shippeado**: este módulo reutiliza los patrones de `catalog` (DataTable, Drawer, filtros con chip, deep-link `?...`). Dos diferencias deliberadas vs catalog se justifican abajo: (1) el **detalle de Office es una PÁGINA dedicada** con tabs, no un drawer; (2) los endpoints usan **`PUT`** (no PATCH) para updates y **`/active`** (no `/options`) para dropdowns — ver [`backend.md`](backend.md#alineación-con-el-catálogo-shippeado).

## Decisión de arquitectura: 2 listas en sidebar + 1 página de detalle

Catalog son 3 páginas-lista hermanas, cada una con su CRUD vía drawer. Clinic tiene la misma forma para las listas (`/clinic/branches`, `/clinic/offices`), **pero** el Office tiene sub-recursos pesados (horario semanal de 7 días con múltiples bloques, calendario de excepciones) que no caben cómodamente en un drawer. Por eso el detalle del Office es una **página dedicada** `/clinic/offices/{id}` con tabs.

| Recurso | Lista | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **Branch** (Sede) | `/clinic/branches` (sidebar) | drawer | drawer (tabs Datos · Ubicación · Contacto · Auditoría) | **igual que catalog** |
| **Office** (Consultorio) | `/clinic/offices` (sidebar, filtrable por sede) | drawer (campos básicos + verticales) | **página** `/clinic/offices/{id}` (tabs Detalles · Horarios · Excepciones · Auditoría) | **nuevo: page over drawer** |

### Por qué el detalle del Office es página y no drawer

Hay 4 alternativas razonables para alojar el editor de horarios + el calendario de excepciones de un Office:

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **A. Página dedicada `/clinic/offices/{id}` con tabs** | El grid semanal (7 días × N bloques) y el calendario de excepciones tienen aire para respirar. URL bookmarkable (`/clinic/offices/abc?tab=hours`). Tabs separan los 4 sub-recursos sin competir por z-index. Reutilizable para futuros módulos con "entidad + sub-recursos ricos" (ej. `staff` doctor + disponibilidad). | Romper el patrón drawer-only del template. El admin navega fuera de la lista. | **Elegida** |
| B. Drawer `size=large` con tabs | Consistente con catalog. Sin navegación. | El grid de 7 días con add/remove de bloques + el calendario de cierres se sienten apretados en ~640 px. Dos "Guardar" distintos (horarios bulk vs cierres CRUD) confunden el footer único del drawer. Tabs anidados dentro de un drawer flotante = z-index frágil (DatePicker/TimePicker popovers sobre el overlay). | Rechazada |
| C. Modal full-screen | Espacio total. | Cero precedente en el template. Pierde la URL (no bookmarkable). Mismo problema de "qué guarda el botón". | Rechazada |
| D. Maestro-detalle inline en la lista (acordeón por fila) | Sin navegación. | La lista se vuelve gigante. Un solo Office expandido empuja el resto. No escala a closures con calendario. | Rechazada |

**Justificación final**:

1. **El sub-recurso manda la forma**: horarios + excepciones son agregados ricos con su propia interacción (bulk save vs CRUD individual). Un drawer con footer único no puede modelar dos modos de guardado limpiamente.
2. **La URL refleja el estado**: `/clinic/offices/{id}?tab=excepciones&from=2026-07-01` es bookmarkable y compartible. Un drawer no tiene URL propia.
3. **Reutilizable**: el shell de "página de detalle con tabs" lo necesitará después `staff` (doctor + disponibilidad). Lo construimos aquí como patrón nuevo del template (`_components/OfficeDetailPage.tsx`).
4. **Branch se queda en drawer** porque no tiene sub-recursos pesados: solo metadata (datos, ubicación, contacto). Forzar página ahí sería inconsistente sin ganancia.

> ⚠ La **lista** de offices (`/clinic/offices`) mantiene un **drawer de creación** para nuevos consultorios (campos básicos + verticales). Ver/editar un office existente **navega** a su página de detalle. Crear es ligero (cabe en drawer); editar el agregado completo necesita la página.

## Sidebar — extensión de `NAV_ITEMS`

> ⚠ **Textos UI en español** (ver [[feedback-medisage-spanish-ui]] en memoria global). `key` y `icon` se mantienen en inglés porque son identificadores de código. Solo `label` va en español.

Agregar un parent item `clinic` con 2 children, entre `catalog` y `admin`:

```ts
{
  key: "clinic",
  label: "Clínica",
  icon: "BuildingMultipleRegular",
  children: [
    { key: "branches", label: "Sedes",        icon: "BuildingRegular",     url: "/clinic/branches", permissions: ["MENU-CLINIC"] },
    { key: "offices",  label: "Consultorios", icon: "ConferenceRoomRegular", url: "/clinic/offices",  permissions: ["MENU-CLINIC"] },
  ],
}
```

> Ambos children usan `MENU-CLINIC` como gate de visibilidad (sidebar). Los permisos finos (`BRANCHES_READ`, `OFFICES_READ`, `OFFICE_HOURS_READ`, `OFFICE_CLOSURES_READ`, etc.) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>`. La **página de detalle** del office no tiene entrada propia en el sidebar — se llega navegando desde la lista.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error) + lista de componentes.

---

### Pantalla 1 — `/clinic/branches` (lista)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                    │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │ TopBar                                                   │ │
│ │            │ ├──────────────────────────────────────────────────────────┤ │
│ │ [≡] Brand  │ │                                                          │ │
│ │            │ │   Sedes                                                  │ │
│ │ ▸ Inicio   │ │   Gestiona las sedes físicas de la clínica.              │ │
│ │ ▸ Catálogo │ │                                                          │ │
│ │ ▾ Clínica  │ │   ┌──────────────────────────────┐  ┌──────────────────┐ │ │
│ │   • Sedes█ │ │   │ 🔍 Buscar por código o nom…│  │ + Nueva sede    │ │ │
│ │   • Consul │ │   └──────────────────────────────┘  └──────────────────┘ │ │
│ │ ▸ Admin    │ │                                                          │ │
│ │            │ │   ╭─ DataTable ──────────────────────────────────────╮  │ │
│ │            │ │   │ ⋯ │ Código     │ Nombre       │Ciudad│Consult.│  │ │
│ │            │ │   ├───┼────────────┼──────────────┼──────┼────────┤  │ │
│ │            │ │   │ ⋯ │ lima_centro│ Sede Lima C…│ Lima │   4    │  │ │
│ │            │ │   │ ⋯ │ trujillo   │ Sede Trujillo│Truj.│   2    │  │ │
│ │            │ │   │ ⋯ │ arequipa   │ Sede Arequipa│Areq.│   0    │  │ │
│ │            │ │   ├──────────────────────────────────────────────────┤  │ │
│ │            │ │   │ Mostrando 1–3 de 3      ‹  Página 1 de 1  ›      │  │ │
│ │            │ │   ╰──────────────────────────────────────────────────╯  │ │
│ └────────────┘ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas de la tabla** (orden, alineación, ancho). `header` es el texto visible (en español), `key` es el identificador del column (en inglés, coherente con `ALLOWED_FIELDS` del backend):

| `key` | Header | Tipo | min/max | Sortable | Render |
|---|---|---|---|---|---|
| `actions` | `""` (sin header) | RowActions | 48–56 | — | menú `…` con Ver / Editar / Eliminar (gated por permisos) |
| `code` | Código | text (truncate) | 180 | ✅ | `<code>` mono tag |
| `name` | Nombre | text (truncate) | 240 | ✅ | nombre comercial |
| `city` | Ciudad | text (truncate) | 140 | ✅ | ciudad |
| `district` | Distrito | text (truncate) | 140 | ✅ | distrito o "—" si NULL |
| `phone` | Teléfono | text | 140 | — | teléfono o "—" |
| `offices_count` | Consultorios | numeric | 110 | ✅ | derecha, tabular-nums. Link "→ Ver N consultorios" navega a `/clinic/offices?branch_id=X` |
| `active` | Estado | badge | 100 | — | "Activa" (success) / "Deshabilitada" (informative) |
| `updated_on` | Última actualización | date | 180 | ✅ | `formatDate(...)` |

> `offices_count` es la denormalización (mirror de `vertical.services_count` en catalog). Se hidrata por batch en el listado. Ver [`backend.md`](backend.md#branchitem).

**RowActions** (gated por `usePermissions()`):
- 👁 **Ver** — siempre visible (asume `BRANCHES_READ`). Abre el drawer en modo `view`.
- ✏ **Editar** — gated `BRANCHES_UPDATE`. Abre el drawer en modo `edit`.
- 🗑 **Eliminar** — gated `BRANCHES_DELETE`. Confirm dialog (ver copy; incluye el guard 409 `BRANCH_HAS_ACTIVE_CHILDREN`).

**Botón "+ Nueva sede"**: gated `<PermissionGuard anyOf={["BRANCHES_CREATE"]}>`.

#### Estados

**Empty (no hay sedes aún)**:
```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                            🏢  (BuildingRegular)                             │
│                                                                              │
│                            Aún no hay sedes                                  │
│        Las sedes son las ubicaciones físicas donde opera la clínica.        │
│        Crea la primera para empezar a registrar consultorios.               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

> El template tiene `<EmptyState icon title message>` en `DataTable`. El botón **no** va dentro del EmptyState — el "Nueva sede" del toolbar superior cumple la función. Mantener consistencia con catalog.

**Loading (primera carga)**:
- DataTable muestra **6 skeleton rows** (`<Skeleton><SkeletonItem ...>`) con anchos pseudo-aleatorios (60–90%) por celda.
- Toolbar (search + button) renderiza normal.
- Sin spinner adicional — el server-pre-fetch del `page.tsx` evita ver esto en el primer load.

**No-results (filtro activo, sin matches)**:
```
                            🔍  (SearchRegular)

              No hay resultados con los filtros actuales
   Prueba quitar algún criterio o revisa la ortografía del término de búsqueda.
```

Variante automática de `DataTable` cuando `isFiltered={search.length > 0}`.

**Refetching (background)**:
- Tabla mantiene los datos visibles con `opacity: 0.55`.
- Spinner pequeño en esquina top-right (overlay con `boxShadow: tokens.shadow4`).

**Error (red, 5xx)**:
- Captura por `error.tsx` global. Toast/MessageBar en el árbol.
- Si es un soft-error (ej. `409 BRANCH_HAS_ACTIVE_CHILDREN` al borrar), `MessageBar intent="error"` dentro del confirm dialog (reusa el patrón de `ServicesClient`: el `description` del `ConfirmDialog` muestra el `deleteError`).

#### Componentes Fluent UI / del template

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Sidebar | `Sidebar` (del template) — auto-renderiza `NAV_ITEMS` filtrados por permisos |
| Header | `<h1 className={styles.title}>` + `<p className={styles.subtitle}>` |
| Search | `<Input contentBefore={<SearchRegular />} />` |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Permission gate | `<PermissionGuard anyOf={["BRANCHES_CREATE"]}>` |
| Tabla | `<DataTable<BranchItem> columns={...} ...>` |
| Badge active | `<Badge appearance="filled" color={b.active ? 'success' : 'informative'}>` |
| Link drill-down | `<Link href={"/clinic/offices?branch_id=" + b.id}>Ver N consultorios</Link>` |
| Row menu | `<RowActions item={b} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive ... />` |
| Drawer | `<BranchDrawer mode={...} branchId={...}>` (custom) |

---

### Pantalla 2 — BranchDrawer (create / edit / view)

Drawer del template (`<Drawer size="medium">`). Tabs: `Datos` · `Ubicación` · `Contacto` · `Auditoría` (la última solo en `edit`/`view`). Mismo esqueleto que `ServiceDrawer`/`UserDrawer` (TabList + render condicional por tab + footer único).

```
                  ┌─────────────────────────────────────────────────┐
                  │  Editar sede                                  ✕ │
                  │  lima_centro                                    │
                  ├─────────────────────────────────────────────────┤
                  │                                                 │
                  │  ╭─[Datos][Ubicación][Contacto][Auditoría]────╮ │
                  │                                                 │
                  │  [Tab Datos]                                    │
                  │                                                 │
                  │  Código *                                       │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ lima_centro          (no editable)      │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Slug estable usado en URLs y por bots.        │
                  │                                                 │
                  │  Nombre *                                       │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Sede Lima Centro                         │   │
                  │  └─────────────────────────────────────────┘   │
                  │                                                 │
                  │  Zona horaria *                                 │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ America/Lima (GMT-5)                  ▾ │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Define cómo se interpretan los horarios.      │
                  │                                                 │
                  │  ☑ Activa                                       │
                  │                                                 │
                  ├─────────────────────────────────────────────────┤
                  │                       [ Cancelar ] [ Guardar ] │
                  └─────────────────────────────────────────────────┘
```

**Tab `Ubicación`**:
```
                  │  Dirección *                                    │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Av. Larco 1234                           │   │
                  │  └─────────────────────────────────────────┘   │
                  │                                                 │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Distrito         │  │ Ciudad *         │    │
                  │  │ Miraflores       │  │ Lima             │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │                                                 │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Región           │  │ País *           │    │
                  │  │ Lima             │  │ PE               │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │                                                 │
                  │  Código postal                                  │
                  │  ┌──────────────────┐                          │
                  │  │ 15074            │                          │
                  │  └──────────────────┘                          │
                  │                                                 │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Latitud          │  │ Longitud         │    │
                  │  │ -12.121300       │  │ -77.029700       │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Coordenadas opcionales (para mapas a futuro). │
```

**Tab `Contacto`**:
```
                  │  Teléfono                                       │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ +51 1 234 5678                           │   │
                  │  └─────────────────────────────────────────┘   │
                  │                                                 │
                  │  Correo                                         │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ lima@medisage.pe                         │   │
                  │  └─────────────────────────────────────────┘   │
```

**Modos del drawer** (títulos visibles):
- `create`: título "Nueva sede". Todos los fields editables, sin tab Auditoría. Footer `[ Cancelar ] [ Crear ]`.
- `edit`: título "Editar sede". `code` disabled, resto editable, tab Auditoría visible. Footer `[ Cancelar ] [ Guardar ]`.
- `view`: título "Detalle de sede". Todos los fields disabled, footer con un solo botón `Cerrar`.

**Zona horaria (Dropdown)**:
- `<Dropdown>` con una lista cerrada de timezones IANA relevantes (`America/Lima`, `America/Mexico_City`, `America/Bogota`, `America/Santiago`, `America/Buenos_Aires`, …). Igual rationale que el icon picker de catalog: lista curada evita que el admin tipee una IANA inválida.
- Label visible enriquecido con el offset ("America/Lima (GMT-5)"), pero el `value` guardado es la IANA cruda.
- Default en create: `America/Lima`.

**Latitud / Longitud**:
- `<Input type="number">` con `step="0.000001"` (precisión `numeric(9,6)`). Opcionales.
- Validación Zod: rango `lat ∈ [-90, 90]`, `lng ∈ [-180, 180]`; ambos o ninguno (cross-field `model`/`superRefine`).

**País**:
- `<Input>` de 2 chars en mayúsculas, default `PE`. (No usamos dropdown de países completo para el MVP — la clínica es mono-país por ahora; abrir a dropdown ISO-3166 si se internacionaliza.)

**Tab Auditoría** (solo `edit` / `view`) — idéntico estructuralmente al de `UserDrawer`/`ServiceDrawer`:
```
                  │  Estado               ID de la sede           │
                  │  [Activa]             8c5a-…  (mono code)      │
                  │  ─────────────────                             │
                  │  Creada el            Creada por               │
                  │  29 may 2026          Admin User               │
                  │  Actualizada el       Actualizada por          │
                  │  29 may 2026          Admin User               │
```

#### Estados de error / loading

- **Guardando**: botón footer `[Guardando…]` / `[Creando…]` disabled. Form fields disabled.
- **Error 409 (CODE_TAKEN)**: `MessageBar intent="error"` arriba del form con el `detail` (en español, viene del backend). El campo `code` queda con error inline.
- **Error 422 (validation drift)**: improbable porque el form valida con el mismo Zod. Si llega, muestra el `detail` genérico y loguea.
- **Error de red**: `MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.
- **Cargando datos iniciales (edit / view)**: footer enabled cuando `getBranch(id)` termina. Mientras carga, fields disabled con `placeholder="Cargando…"`.

#### Componentes Fluent UI

| Concepto UI | Componente |
|---|---|
| Tabs en drawer | `<TabList><Tab value="datos">…</Tab></TabList>` (patrón de `UserDrawer`) |
| Timezone | `<Dropdown>` con lista IANA curada |
| Lat / Lng / postal | `<Input type="number">` / `<Input>` vía `FormField` |
| Checkbox `Activa` | `<Switch>` (consistente con `ServiceDrawer`) |
| Dos columnas | `styles.twoCol` (grid `1fr 1fr`) — igual que `UserDrawer` |
| Inline error 409 | `<MessageBar intent="error">` arriba del form |

---

### Pantalla 3 — `/clinic/offices` (lista)

Igual estructura que branches, con **filtro por sede** (deep-link `?branch_id=X`, mismo patrón que `ServicesClient` con `vertical_id`):

```
   Consultorios
   Gestiona los consultorios dentro de cada sede.

   ┌───────────────────────────────┐  ┌──────────────────────────────┐  ┌────────────────┐
   │ Sede: Todas ▾                 │  │ 🔍 Buscar por código o nom…│  │ + Nuevo consul.│
   └───────────────────────────────┘  └──────────────────────────────┘  └────────────────┘

   ┌──────────────────────────────────┐
   │ Sede: Sede Lima Centro          ✕│      ← chip cuando hay ?branch_id activo
   └──────────────────────────────────┘

   ╭─ DataTable ─────────────────────────────────────────────────────────────────╮
   │ ⋯ │ Sede             │ Código      │ Nombre            │ Verticales │ Estado │
   ├───┼──────────────────┼─────────────┼───────────────────┼────────────┼────────┤
   │ ⋯ │ Sede Lima Centro │ C-03        │ Consultorio 3 — D…│     2      │ Activo │
   │ ⋯ │ Sede Lima Centro │ ESTETICA-01 │ Estética 1        │     3      │ Activo │
   │ ⋯ │ Sede Trujillo    │ C-01        │ Consultorio 1     │     1      │ Activo │
   ╰─────────────────────────────────────────────────────────────────────────────╯
```

**Filtro Sede** (Dropdown de Fluent — espejo exacto del filtro Vertical de `ServicesClient`):
- Opciones cargadas de `GET /clinic/branches/active` → `BranchOption[]`.
- Selected = `null` → "Todas las sedes". Selected `X` → filtra `branch_id=X`.
- Se sincroniza con la URL como `?branch_id=X` (vía `nuqs` `useQueryState`). Permite deep-link desde la lista de Sedes ("Ver N consultorios").
- Al venir con `?branch_id=X`, se muestra un **chip** con × para limpiar (idéntico al chip "Vertical:" de catalog). Fallback de nombre: si la sede no está en la lista activa, usar `items[0].branch_name`.

> El backend `GET /offices/active?branch_id=&vertical_id=` también acepta `vertical_id` (para que `scheduling` filtre offices aptos), pero la UI de la lista solo expone el filtro por sede en el MVP. El filtro por vertical es un dropdown secundario que se puede agregar después sin cambiar el contrato.

**Columnas** (`key` en inglés / `header` en español):

| `key` | Header | Render | Notas |
|---|---|---|---|
| `actions` | (sin) | RowActions | Ver / Editar / Eliminar (gated). Ver/Editar **navegan** a la página de detalle (no abren drawer) |
| `branch_name` | Sede | text (truncate) | denormalizado (mirror de `service.vertical_name`). Sortable. |
| `code` | Código | mono | `<code>`, sortable |
| `name` | Nombre | text (truncate) | sortable |
| `floor` | Piso | text | piso o "—" |
| `verticals_count` | Verticales | numeric | derecha, tabular-nums (mirror de `services_count`) |
| `active` | Estado | badge | "Activo" / "Deshabilitado" |
| `updated_on` | Última actualización | date | sortable |

**Click en fila / acción "Ver"**: navega a `/clinic/offices/{id}` (`router.push` o `<Link>`). **No** abre drawer. La acción "Editar" navega a `/clinic/offices/{id}` directamente en la tab `Detalles` (igual destino; editar es el comportamiento natural de la página de detalle).

**Botón "+ Nuevo consultorio"**: gated `<PermissionGuard anyOf={["OFFICES_CREATE"]}>`. Abre el **drawer de creación** (no la página).

#### OfficeCreateDrawer (solo create)

Drawer ligero del template (`size="medium"`) — **solo** modo create (ver/editar viven en la página de detalle). Campos básicos + selección de verticales:

```
                  ┌─────────────────────────────────────────────────┐
                  │  Nuevo consultorio                            ✕ │
                  ├─────────────────────────────────────────────────┤
                  │                                                 │
                  │  Sede *                                         │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Sede Lima Centro                      ▾ │   │
                  │  └─────────────────────────────────────────┘   │
                  │                                                 │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Código *         │  │ Nombre *         │    │
                  │  │ C-04             │  │ Consultorio 4    │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Único dentro de la sede.                      │
                  │                                                 │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ N° de sala       │  │ Piso             │    │
                  │  │ 204              │  │ 2                │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │                                                 │
                  │  Descripción                                    │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Consultorio con sillón odontológico.    │   │
                  │  └─────────────────────────────────────────┘   │
                  │                                                 │
                  │  Verticales aptas *           (2 de 6)         │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 🔍 Buscar verticales…                   │   │
                  │  ├─────────────────────────────────────────┤   │
                  │  │ ☑ Estética facial                       │   │
                  │  │ ☑ Dermatología clínica                  │   │
                  │  │ ☐ Dental                                │   │
                  │  │ ☐ Pediatría                             │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Verticales que este consultorio puede acoger. │
                  │                                                 │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Crear ]  │
                  └─────────────────────────────────────────────────┘
```

**Sede (Dropdown)**:
- Opciones de `GET /clinic/branches/active` → `BranchOption[]`.
- Pre-seleccionada con `defaultBranchId` (el `?branch_id` del filtro de la lista, igual que `ServiceDrawer` recibe `defaultVerticalId`).

**Verticales aptas (multi-select)**:
- Reutiliza el helper **`SearchableOptionList`** de `admin/users/_components/UserDrawer.tsx` (el mismo que selecciona roles/permisos). Opciones de `GET /catalog/verticals/active` → `VerticalOption[]` mapeadas a `{ id, primary: name }`.
- El backend **filtra verticales soft-deleted** vía join (`deleted_at IS NULL`) al hidratar el detalle; la lista activa ya no las trae, así que el multi-select solo muestra verticales vivas. Ver [`backend.md`](backend.md#cross-module-office_vertical).
- Validación Zod: `vertical_ids.length >= 1` (un consultorio debe acoger al menos una vertical). Mensaje: "Selecciona al menos una vertical."

**Tras crear**: el drawer cierra y la lista se revalida (`revalidateTag("clinic:offices")`). Opcionalmente se navega directo a `/clinic/offices/{nuevoId}` para configurar horarios — decisión de UX menor; el MVP solo cierra y refresca.

#### Estados

- **Empty sin filtro**: "Aún no hay consultorios. Crea el primero dentro de una sede."
- **Empty con filtro por sede sin offices**: "Esta sede aún no tiene consultorios."
- **No-results** (search no matchea): el genérico de DataTable.
- Resto (loading/refetching/error) idéntico a branches.

#### Componentes Fluent UI

| Concepto UI | Componente |
|---|---|
| Filtro Sede | `<Dropdown>` + `nuqs useQueryState("branch_id")` (patrón `ServicesClient`) |
| Chip filtro | `styles.chip` + `<Button icon={<DismissRegular />} />` (patrón `ServicesClient`) |
| Navegación a detalle | `useRouter().push("/clinic/offices/" + o.id)` desde RowActions / fila |
| Drawer create | `<OfficeCreateDrawer defaultBranchId={branchFilter}>` (custom) |
| Multi-select verticales | `SearchableOptionList` (reutilizado de `UserDrawer`) |
| Dropdown Sede (form) | `<Dropdown><Option>…` |

---

### Pantalla 4 — `/clinic/offices/{id}` (página de detalle con tabs)

Página dedicada (RSC `page.tsx` que prefetcha el office + sus sub-recursos, luego un client `OfficeDetailPage`). 4 tabs: `Detalles` · `Horarios` · `Excepciones` · `Auditoría`. La tab activa se sincroniza con la URL (`?tab=horarios`).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Volver a consultorios                                                       │
│                                                                              │
│ Consultorio 3 — Dental                                          [Activo]      │
│ Sede Lima Centro · C-03 · Piso 2                                             │
│                                                                              │
│ ╭─[ Detalles ][ Horarios ][ Excepciones ][ Auditoría ]──────────────────────╮ │
│ │                                                                          │ │
│ │ ...contenido de la tab activa...                                         │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Header de la página**:
- `← Volver a consultorios` (`<Link href="/clinic/offices">` con `ArrowLeftRegular`). Si la lista venía filtrada, conserva el `?branch_id` (lo lleemos del `referrer` o lo guardamos en URL state — MVP: link plano a `/clinic/offices`).
- Título = `office.name`; badge de estado al lado.
- Subtítulo = `Sede {branch_name} · {code} · Piso {floor}` (omitir piezas NULL).

**Permisos por tab** (gating dentro de la página):
- `Detalles` — `OFFICES_READ` (ver) / `OFFICES_UPDATE` (editar).
- `Horarios` — `OFFICE_HOURS_READ` (ver) / `OFFICE_HOURS_WRITE` (editar). Si el user no tiene `OFFICE_HOURS_READ`, la tab no se renderiza.
- `Excepciones` — `OFFICE_CLOSURES_READ` / `OFFICE_CLOSURES_WRITE`. Misma regla.
- `Auditoría` — `OFFICES_READ`.

#### Tab `Detalles`

Mismos campos que el OfficeCreateDrawer pero editables in-place (form embebido en la tab) con su propio botón "Guardar cambios". `code` y `Sede` quedan **disabled** (inmutables post-creación, igual que `vertical_id` en `ServiceDrawer` edit). El multi-select de verticales es editable (manda `vertical_ids` en el `PUT /offices/{id}` — reasigna la M:N).

```
│ │ Sede                            Código                                    │ │
│ │ ┌─────────────────────────┐    ┌─────────────────────────┐               │ │
│ │ │ Sede Lima Centro    (—) ▾│   │ C-03         (no editable)│              │ │
│ │ └─────────────────────────┘    └─────────────────────────┘               │ │
│ │                                                                          │ │
│ │ Nombre *                                                                  │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐    │ │
│ │ │ Consultorio 3 — Dental                                           │    │ │
│ │ └──────────────────────────────────────────────────────────────────┘    │ │
│ │                                                                          │ │
│ │ N° de sala            Piso                                                │ │
│ │ ┌─────────────┐       ┌─────────────┐                                     │ │
│ │ │ 204         │       │ 2           │                                     │ │
│ │ └─────────────┘       └─────────────┘                                     │ │
│ │                                                                          │ │
│ │ Verticales aptas *   (2 de 6)                                             │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐    │ │
│ │ │ 🔍 Buscar verticales…                                             │    │ │
│ │ │ ☑ Estética facial   ☑ Dermatología clínica  ☐ Dental  ☐ …        │    │ │
│ │ └──────────────────────────────────────────────────────────────────┘    │ │
│ │                                                                          │ │
│ │ ☑ Activo                                                                  │ │
│ │                                                       [ Guardar cambios ] │ │
```

#### Tab `Horarios` (editor de grilla semanal — bulk save)

El patrón semanal (`OfficeOperatingHours`) se edita como un **agregado completo** y se guarda con **un solo** `PUT /offices/{id}/operating-hours` (bulk replace atómico). La grilla muestra los 7 días (Lun..Dom, convención Python 0=Lun); cada día puede tener **múltiples bloques** (mañana + tarde). Cada bloque tiene apertura/cierre. Un solo botón "Guardar horarios" persiste todo.

```
│ │  Horario semanal                                       [ Guardar horarios ]│ │
│ │  Define los bloques de atención por día. Puedes tener varios bloques      │ │
│ │  (ej. mañana y tarde). Las horas se interpretan en la zona de la sede.    │ │
│ │                                                                          │ │
│ │  Lun  ┌────────┐ – ┌────────┐  [✕]                                        │ │
│ │       │ 08:00  │   │ 13:00  │                                            │ │
│ │       └────────┘   └────────┘                                            │ │
│ │       ┌────────┐ – ┌────────┐  [✕]                                        │ │
│ │       │ 16:00  │   │ 20:00  │       + Agregar bloque                      │ │
│ │       └────────┘   └────────┘                                            │ │
│ │  ────────────────────────────────────────────────────────────────────   │ │
│ │  Mar  ┌────────┐ – ┌────────┐  [✕]     + Agregar bloque                   │ │
│ │       │ 09:00  │   │ 18:00  │                                            │ │
│ │       └────────┘   └────────┘                                            │ │
│ │  ────────────────────────────────────────────────────────────────────   │ │
│ │  Mié   (sin bloques)                    + Agregar bloque                  │ │
│ │  ────────────────────────────────────────────────────────────────────   │ │
│ │  Jue  ┌────────┐ – ┌────────┐  [✕]      + Agregar bloque                  │ │
│ │       │ 09:00  │   │ 18:00  │                                            │ │
│ │       └────────┘   └────────┘                                            │ │
│ │  ────────────────────────────────────────────────────────────────────   │ │
│ │  Vie  …                                                                   │ │
│ │  Sáb   (sin bloques)                    + Agregar bloque                  │ │
│ │  Dom   (sin bloques)                    + Agregar bloque                  │ │
```

**Interacción**:
- **Agregar bloque** (por día): `+ Agregar bloque` añade una fila `{opens_at, closes_at}` vacía bajo ese día (default sugerido `09:00`–`18:00`).
- **Quitar bloque**: `✕` al lado del bloque lo elimina del estado local (no llama al backend; se aplica al guardar).
- **Editar hora**: `<Input type="time">` (o `<TimePicker>` de Fluent si está disponible; el MVP usa `type="time"` por simplicidad y soporte nativo). Sin TZ — es hora local de la sede.
- **Guardar horarios**: arma el body `{ hours: [{ day_of_week, opens_at, closes_at }, …] }` recorriendo todos los días con sus bloques, y llama `replaceOfficeHours(officeId, body)` → `PUT /offices/{id}/operating-hours`. **Un solo request reemplaza todo el patrón.** Tras éxito, `revalidateTag("clinic:office:" + id)` y toast "Horarios guardados.".

**Validación (Zod, client-side antes del bulk PUT)**:
- Cada bloque: `closes_at > opens_at` (mirror del CHECK del backend). Si falla, error inline en ese bloque ("La hora de cierre debe ser mayor que la de apertura.").
- `day_of_week ∈ 0..6` (lo fija la fila, no editable por el user).
- Se permiten **múltiples bloques por día** (no hay unique en `(office_id, day_of_week)`), pero **no pueden solaparse**: el backend (`OfficeOperatingHoursReplace._no_overlaps`) y el Zod del frontend rechazan dos bloques del mismo día que se solapen (adyacentes `next.opens == prev.closes` sí valen). El editor deshabilita "Guardar horarios" y marca inline los bloques solapados, en español.
- Días sin bloques = el office no atiende ese día (no se envía ninguna fila para ese día).

**Estados de la tab Horarios**:
- **Loading**: skeleton de 7 filas (una por día) mientras `getOfficeHours(id)` resuelve.
- **Empty (patrón nuevo)**: los 7 días muestran "(sin bloques)" con su `+ Agregar bloque`. Hint arriba: "Este consultorio aún no tiene horario. Agrega bloques y guarda."
- **Guardando**: botón `[Guardando…]` disabled; la grilla disabled.
- **Error**: `MessageBar intent="error"` arriba de la grilla con el `detail` del backend (ej. 422 si un bloque inválido pasó el front).
- **Dirty guard**: si el user cambia bloques y navega de tab sin guardar, mostrar confirm "Tienes cambios sin guardar en los horarios. ¿Salir igual?" (opcional MVP; al menos un `isDirty` flag en el botón).

#### Tab `Excepciones` (cierres y aperturas extra — CRUD individual)

A diferencia de los horarios, las excepciones (`OfficeClosure`) son **CRUD individual** (cada excepción es una unidad atómica con su razón). Lista filtrable por rango + formulario para agregar. Un `is_closed` toggle distingue **cierre** (`true`, rojo) de **apertura extra** (`false`, verde).

```
│ │  Excepciones                                          [ + Agregar excepción]│ │
│ │  Cierres (feriados, mantenimiento) y aperturas extra fuera del horario.   │ │
│ │                                                                          │ │
│ │  Desde ┌──────────────┐   Hasta ┌──────────────┐                          │ │
│ │        │ 01/07/2026 📅 │        │ 31/07/2026 📅 │     (filtro de rango)     │ │
│ │        └──────────────┘        └──────────────┘                          │ │
│ │                                                                          │ │
│ │  ╭───────────────────────────────────────────────────────────────────╮  │ │
│ │  │ 🔴 Cierre   │ 28 jul 2026 00:00 → 28 jul 2026 23:59 │ Feriado    [✕]│ │ │
│ │  │ 🔴 Cierre   │ 15 jul 2026 08:00 → 15 jul 2026 14:00 │ Manten.    [✕]│ │ │
│ │  │ 🟢 Apertura │ 20 jul 2026 09:00 → 20 jul 2026 13:00 │ Demanda    [✕]│ │ │
│ │  ╰───────────────────────────────────────────────────────────────────╯  │ │
```

**Formulario "Agregar excepción"** (drawer o inline panel — MVP: drawer `size="small"`):

```
                  ┌─────────────────────────────────────────────────┐
                  │  Nueva excepción                              ✕ │
                  ├─────────────────────────────────────────────────┤
                  │  ┌──────────────────┐  ┌──────────────────┐     │
                  │  │ Inicio *         │  │ Fin *            │     │
                  │  │ 28/07/2026 📅    │  │ 28/07/2026 📅    │     │
                  │  │ 00:00            │  │ 23:59            │     │
                  │  └──────────────────┘  └──────────────────┘     │
                  │                                                 │
                  │  ◉ Cierre   ○ Apertura extra                    │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ [ ●━━━ ]  Cerrado en este rango         │   │
                  │  └─────────────────────────────────────────┘   │
                  │                                                 │
                  │  Motivo *                                       │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Feriado 28 de julio                     │   │
                  │  └─────────────────────────────────────────┘   │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Agregar ] │
                  └─────────────────────────────────────────────────┘
```

**Interacción**:
- **Inicio / Fin**: `<DatePicker>` de Fluent para la fecha + `<Input type="time">` para la hora → se combinan a un `timestamptz` ISO 8601. (Alternativa: un solo input datetime-local; el MVP separa fecha/hora por claridad.) Se envían como instante con offset; el browser y el backend manejan UTC (mismo contrato datetime que el resto del template).
- **is_closed (Switch)**: `<Switch>` etiquetado. ON = "Cerrado en este rango" (cierre, `is_closed=true`). OFF = "Abierto en este rango" (apertura extra, `is_closed=false`). El badge de la lista refleja el flag (🔴 Cierre / 🟢 Apertura).
- **Motivo**: `<Input>` requerido (`varchar(255)`), texto libre para auditoría.
- **Agregar**: `POST /offices/{id}/closures`. Tras éxito, cierra el drawer, revalida y la lista se refresca.
- **Eliminar (✕ por fila)**: confirm dialog → `DELETE /offices/{id}/closures/{closure_id}`.
- **Filtro de rango (Desde/Hasta)**: opcional; pasa `?from=&to=` a `GET /offices/{id}/closures?from=&to=`. **Por defecto vacío** → lista todas las excepciones no borradas del office (consistente con `frontend.md` "filtros de rango opcionales"; el MVP no preselecciona un mes). El usuario acota con Desde/Hasta y la lista se re-consulta.

**Validación (Zod)**:
- `ends_at > starts_at` (mirror del CHECK del backend). Mensaje: "La fecha de fin debe ser posterior a la de inicio."
- `reason` no vacío.

**Estados de la tab Excepciones**:
- **Empty (sin excepciones en el rango)**: EmptyState "No hay excepciones en este rango. Agrega un cierre o una apertura extra." con ícono `CalendarRegular`.
- **Loading**: skeleton de 3 filas.
- **Guardando / Eliminando**: botón disabled con "Agregando…" / "Eliminando…".
- **Error**: `MessageBar intent="error"` (ej. 422 rango inválido).

#### Tab `Auditoría`

Idéntico al de `ServiceDrawer`/`UserDrawer` (Estado · ID del consultorio · Creado el/por · Actualizado el/por). Concordancia masculina ("Creado por", "Actualizado por").

#### Componentes Fluent UI (página de detalle)

| Concepto UI | Componente |
|---|---|
| Volver | `<Link href="/clinic/offices">` + `<ArrowLeftRegular />` |
| Tabs de la página | `<TabList>` + `nuqs useQueryState("tab")` |
| Grilla de horarios | filas custom; por bloque `<Input type="time">` × 2 + `<Button icon={<DismissRegular />}>` |
| Agregar/quitar bloque | `<Button appearance="subtle" icon={<AddRegular />}>` / `<Button icon={<DismissRegular />}>` |
| Guardar horarios (bulk) | `<Button appearance="primary">` único → `replaceOfficeHours` |
| DatePicker (excepciones) | `<DatePicker>` (`@fluentui/react-datepicker-compat`) |
| Hora (excepciones / horarios) | `<Input type="time">` (MVP) o `<TimePicker>` si disponible |
| is_closed | `<Switch>` (ON = cierre) |
| Lista de excepciones | filas custom con badge `<Badge color={c.is_closed ? 'danger' : 'success'}>` + `✕` |
| Confirm eliminar excepción | `<ConfirmDialog destructive />` |
| Multi-select verticales | `SearchableOptionList` (reutilizado) |
| Switch `Activo` | `<Switch>` |

## Decisiones de UI (cierres)

### Office detail como página, Branch como drawer

Resumido arriba en la tabla de alternativas. Regla general que dejamos como precedente del template: **si una entidad tiene sub-recursos con interacción propia (grids editables, calendarios, listas CRUD anidadas), su detalle va a una página dedicada con tabs**; si solo tiene metadata, va a drawer. Branch = drawer (solo metadata), Office = página (horarios + excepciones).

### Horarios con bulk save, excepciones con CRUD individual

El patrón semanal es un agregado coherente (todos los bloques de la semana se piensan juntos) → un solo "Guardar horarios" evita estados intermedios inválidos. Las excepciones son eventos independientes (cada feriado es atómico) → CRUD individual con su propia razón. Esta asimetría es intencional y refleja el backend (`PUT` bulk para hours, `POST`/`DELETE` para closures). Ver [`README.md`](README.md#officeoperatinghours-se-gestiona-con-bulk-put-reemplazo-atómico).

### `is_closed` como toggle, no dos pantallas

Cierre y apertura extra comparten schema (rango + motivo), así que un `<Switch>` los distingue en un solo formulario. Coherente con la decisión de modelo ([`README.md`](README.md#officeclosure-cubre-cierres-y-aperturas-extra-con-un-solo-modelo-is_closed-bool)). El color del badge (🔴/🟢) hace evidente el sentido en la lista.

### Timezone como dropdown curado, no input libre

Igual rationale que color/icon picker de catalog: lista cerrada de IANA evita timezones inválidas que romperían el cálculo de slots en `scheduling`. Si negocio abre a más países, ampliar la lista en código.

### Verticales aptas con `SearchableOptionList` reutilizado

No reinventamos un multi-select: usamos el helper que ya selecciona roles/permisos en `UserDrawer`. Consistencia visual + menos código. Las verticales soft-deleted se filtran en el backend (no en el front).

### Drill-down vía chips, no breadcrumbs

Como catalog: "Ver N consultorios" desde una sede navega a `/clinic/offices?branch_id=X` con chip "Sede: … ✕". Las listas son hermanas; breadcrumbs sugerirían jerarquía de navegación que no existe. La **excepción** es la página de detalle del office, que sí tiene un "← Volver a consultorios" (no es breadcrumb, es un back-link explícito).

### Sin "duplicate", sin bulk actions, sort default

- Sin botón "Duplicar sede/consultorio" en el MVP (mismo rationale que catalog).
- Sin bulk-delete (los conjuntos son chicos; cada delete tiene su confirmación).
- Sort default: branches por `name ASC`; offices por `code ASC` dentro de la sede. (Catalog usaba `display_order`; clinic no tiene `display_order`, así que ordenamos por el identificador legible.)

### Mobile / responsive

Mismo criterio que catalog (template optimizado para desktop interno):
- Sidebar colapsado por default; DataTable scrollea horizontal.
- Drawers ocupan 100% del width en mobile.
- **Página de detalle del office**: las tabs se mantienen; el grid de horarios apila los dos `time` inputs verticalmente en pantallas angostas; el filtro de rango de excepciones se apila.

No diseñamos pantallas mobile-first separadas — la versión desktop se adapta.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, IANA, CSS classes) se mantienen en inglés — solo los textos visibles al usuario van traducidos. Ver [[feedback-medisage-spanish-ui]] en memoria global para el glosario completo. Glosario clave: **Branch = Sede**, **Office = Consultorio**.

### Copy por contexto

| Contexto | Copy |
|---|---|
| Page title (branches) | "Sedes" |
| Page subtitle (branches) | "Gestiona las sedes físicas de la clínica." |
| Page title (offices) | "Consultorios" |
| Page subtitle (offices) | "Gestiona los consultorios dentro de cada sede." |
| Botón crear (branches) | "+ Nueva sede" |
| Botón crear (offices) | "+ Nuevo consultorio" |
| Search placeholder (branches/offices) | "Buscar por código o nombre…" |
| Empty state (branches) | "Aún no hay sedes. Crea la primera para empezar a registrar consultorios." |
| Empty state (offices no filter) | "Aún no hay consultorios. Crea el primero dentro de una sede." |
| Empty state (offices con filtro sede sin offices) | "Esta sede aún no tiene consultorios." |
| No-results genérico (DataTable) | "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía." |
| Link drill-down (branch → offices) | "Ver {N} consultorios" |
| Chip filtro activo (offices) | "Sede: {nombre} ✕" |
| Filter dropdown placeholder (offices) | "Todas las sedes" |
| Drawer title `create` (branch / office) | "Nueva sede" / "Nuevo consultorio" |
| Drawer title `edit` (branch) | "Editar sede" |
| Drawer title `view` (branch) | "Detalle de sede" |
| Tabs BranchDrawer | "Datos" · "Ubicación" · "Contacto" · "Auditoría" |
| Botón guardar / crear | "Guardar" / "Crear" |
| Botón guardando / creando (pending) | "Guardando…" / "Creando…" |
| Botón cancelar | "Cancelar" |
| Botón cerrar (view) | "Cerrar" |
| Hint (branch.code) | "Slug estable usado en URLs y por bots. No editable." |
| Hint (branch.timezone) | "Define cómo se interpretan los horarios de los consultorios." |
| Hint (lat/lng) | "Coordenadas opcionales (para mapas a futuro)." |
| Hint (office.code) | "Único dentro de la sede." |
| Hint (office.verticals) | "Verticales que este consultorio puede acoger." |
| Confirm delete title (branch) | "¿Eliminar sede?" |
| Confirm delete body (branch) | "¿Eliminar la sede '{nombre}'? Esta acción la deshabilita; podrás recrearla más adelante." |
| Confirm delete title (office) | "¿Eliminar consultorio?" |
| Confirm delete body (office) | "¿Eliminar el consultorio '{nombre}'? Sus horarios y excepciones se conservan." |
| Botón confirmar eliminación | "Eliminar" |
| Error 409 al borrar (branch_has_active_children) | "No se puede eliminar — la sede tiene {N} consultorio(s) activo(s). Deshabilítalos o elimínalos primero." |
| Error 409 al crear (code_taken, branch) | "Ya existe una sede con ese código." |
| Error 409 al crear (code_taken, office) | "Ya existe un consultorio con ese código en esta sede." |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |
| Status badge (branch) | "Activa" / "Deshabilitada" |
| Status badge (office) | "Activo" / "Deshabilitado" |
| Validación verticales (mín. 1) | "Selecciona al menos una vertical." |
| — Página de detalle del office — | |
| Back-link | "← Volver a consultorios" |
| Subtítulo página | "Sede {branch_name} · {code} · Piso {floor}" |
| Tabs página office | "Detalles" · "Horarios" · "Excepciones" · "Auditoría" |
| Botón tab Detalles | "Guardar cambios" |
| — Tab Horarios — | |
| Título / subtítulo | "Horario semanal" / "Define los bloques de atención por día. Puedes tener varios bloques (ej. mañana y tarde). Las horas se interpretan en la zona de la sede." |
| Botón bulk save | "Guardar horarios" |
| Botón agregar bloque | "+ Agregar bloque" |
| Día sin bloques | "(sin bloques)" |
| Empty horarios | "Este consultorio aún no tiene horario. Agrega bloques y guarda." |
| Validación closes>opens | "La hora de cierre debe ser mayor que la de apertura." |
| Toast guardado | "Horarios guardados." |
| Dirty guard | "Tienes cambios sin guardar en los horarios. ¿Salir igual?" |
| — Tab Excepciones — | |
| Título / subtítulo | "Excepciones" / "Cierres (feriados, mantenimiento) y aperturas extra fuera del horario." |
| Botón agregar | "+ Agregar excepción" |
| Drawer title | "Nueva excepción" |
| Labels rango | "Inicio" / "Fin" |
| Toggle is_closed (ON) | "Cerrado en este rango" |
| Toggle is_closed (OFF) | "Abierto en este rango" |
| Radio / opciones | "Cierre" / "Apertura extra" |
| Label motivo | "Motivo" |
| Badge lista (cierre / apertura) | "Cierre" / "Apertura" |
| Filtro rango | "Desde" / "Hasta" |
| Empty excepciones | "No hay excepciones en este rango. Agrega un cierre o una apertura extra." |
| Validación rango | "La fecha de fin debe ser posterior a la de inicio." |
| Confirm eliminar excepción | "¿Eliminar esta excepción? El consultorio volverá a seguir su horario normal en ese rango." |
| Botón agregar (pending) | "Agregando…" |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Audit labels (branch / office) | "Estado", "ID de la sede" / "ID del consultorio", "Creada/Creado el", "Creada/Creado por", "Actualizada/Actualizado el", "Actualizada/Actualizado por" |
| Loading placeholder en inputs | "Cargando…" |
| Cargando initial data | "Cargando…" |

### Concordancia de género

- **Sede** es **femenino**: "Nueva sede", "Editar sede", "Activa" / "Deshabilitada", "Creada el", "Creada por", "la sede 'X'", "ID de la sede".
- **Consultorio** es **masculino**: "Nuevo consultorio", "Activo" / "Deshabilitado", "Creado el", "Creado por", "el consultorio 'X'", "ID del consultorio".
- En confirm dialogs y mensajes mantener concordancia: "¿Eliminar **la** sede 'X'?" vs "¿Eliminar **el** consultorio 'Y'?".
- **Vertical** (heredado de catalog) es femenino: "Selecciona al menos una vertical", "verticales aptas".

### Etiquetas de día de la semana

Convención del modelo: `day_of_week` Python (`0 = lunes … 6 = domingo`). Las etiquetas visibles en la grilla de horarios:

| `day_of_week` | Etiqueta corta (grilla) | Etiqueta larga (tooltip) |
|---|---|---|
| 0 | "Lun" | "Lunes" |
| 1 | "Mar" | "Martes" |
| 2 | "Mié" | "Miércoles" |
| 3 | "Jue" | "Jueves" |
| 4 | "Vie" | "Viernes" |
| 5 | "Sáb" | "Sábado" |
| 6 | "Dom" | "Domingo" |

> El array `DAY_LABELS = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]` se indexa por `day_of_week` directamente (índice = valor Python). Documentarlo junto a la constante para evitar el off-by-one Postgres (0=domingo). Vive en `lib/constants/` — ver [`frontend.md`](frontend.md).

### Sin i18n framework por ahora

Los textos están **directos como strings en cada componente**. Si negocio pide soporte multilingüe, introducir `next-intl` o similar después. Postergado (misma decisión que catalog).

### Textos del template existente

El template trae `admin/users`, `admin/roles`, `admin/permissions` con textos en inglés. Esos también deben traducirse a español como parte de la implementación. Documentado en [`frontend.md`](frontend.md) como TODO compartido con catalog.

## Mapeo a fases de implementación

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](README.md#fases-de-implementación) y [`backend.md`](backend.md#checklist-de-implementación)):

- **F0 Prep** — sidebar `Clínica → Sedes, Consultorios` (`NAV_ITEMS`), íconos (`BuildingMultipleRegular`, `BuildingRegular`, `ConferenceRoomRegular`), `DAY_LABELS` constant, lista IANA de timezones. Sin pantallas funcionales aún.
- **F1 Branch** — Pantalla 1 (`/clinic/branches` lista) + Pantalla 2 (BranchDrawer con tabs Datos/Ubicación/Contacto/Auditoría, timezone dropdown, lat/lng).
- **F2 Office + M:N** — Pantalla 3 (`/clinic/offices` lista con filtro sede + chip + deep-link) + OfficeCreateDrawer (verticales vía `SearchableOptionList`) + **shell de la página de detalle** `/clinic/offices/{id}` con las 4 tabs (Detalles funcional + Horarios/Excepciones placeholder) + columna `offices_count` activada en branches + confirm 409 `BRANCH_HAS_ACTIVE_CHILDREN`.
- **F3 OfficeOperatingHours** — Tab `Horarios` funcional (grilla semanal, add/remove bloque, bulk `PUT`).
- **F4 OfficeClosure** — Tab `Excepciones` funcional (lista filtrable, drawer agregar con DatePicker + Switch + motivo, eliminar).
