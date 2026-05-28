# Módulo `catalog` — UI design

> **Última actualización**: 2026-05-28
> **Audiencia**: developer implementando las pantallas de catalog en `frontend/src/app/(main)/catalog/`.
> **Pre-requisito**: leer [`README.md`](README.md) (overview), [`backend.md`](backend.md) (contracts), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template).

## Decisión de arquitectura: 3 páginas separadas en sidebar

Hay 4 alternativas razonables para presentar la jerarquía Vertical → Service → Product:

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **A. 3 páginas en sidebar** (`/catalog/verticals`, `/catalog/services`, `/catalog/products`) | Consistente con `admin/users`, `admin/roles`, `admin/permissions`. Cada CRUD vive en su propia URL con su drawer. Permite filtros independientes y deep-links (`?vertical_id=X`). | El admin debe navegar entre 3 páginas para "ver la vertical estética con sus servicios". | **Elegida** |
| B. Una página con tabs | Menos espacio en sidebar. Contexto cohesivo (3 tabs en pantalla). | Cada tab necesita su `PermissionGuard`. Permisos parciales (admin con `SERVICES_READ` pero no `PRODUCTS_READ`) muestran tabs vacíos. Drawers compitiendo por z-index. Rompe el patrón del template. | Rechazada |
| C. Maestro-detalle anidado (`/catalog`, `/catalog/{vertical_id}`, …) | "Natural" para la jerarquía. | Difícil reportar "todos los products de la clínica". URLs largas. Rompe el patrón. | Rechazada |
| D. Tree-view en sidebar | Power-user. | Cero precedente en el template. Costo de mantener el árbol con permisos. | Rechazada |

**Justificación final**:

1. **Consistencia con el patrón del template** (admin/users, admin/roles, admin/permissions son 3 páginas hermanas). Cambiar el patrón **aquí** confunde el modelo mental del usuario que aprendió a usar el admin.
2. **Cada entidad tiene su CRUD completo con drawer**. Mezclar 3 entidades en una página complica `PermissionGuard`, drawers anidados, y permisos parciales.
3. **Filtros y deep-links independientes**: `/catalog/services?vertical_id=X` es bookmarkable. La URL refleja el estado.
4. **Drill-down sin perder contexto**: cuando el admin abre el drawer de una vertical y quiere "ver sus services", los items de la tabla muestran un link "View N services" que navega a `/catalog/services?vertical_id=X` con un chip filterable ya aplicado.

## Sidebar — extensión de `NAV_ITEMS`

> ⚠ **Textos UI en español** (ver [[feedback-medisage-spanish-ui]] en memoria global). `key` y `icon` se mantienen en inglés porque son identificadores de código. Solo `label` va en español.

Agregar un parent item `catalog` con 3 children entre `home` y `admin`:

```ts
{
  key: "catalog",
  label: "Catálogo",
  icon: "AppsListRegular",
  children: [
    { key: "verticals", label: "Verticales", icon: "TagRegular",       url: "/catalog/verticals", permissions: ["MENU-CATALOG"] },
    { key: "services",  label: "Servicios",  icon: "BriefcaseRegular", url: "/catalog/services",  permissions: ["MENU-CATALOG"] },
    { key: "products",  label: "Productos",  icon: "BoxRegular",       url: "/catalog/products",  permissions: ["MENU-CATALOG"] },
  ],
}
```

> Todos los children usan `MENU-CATALOG` como gate de visibilidad (sidebar). Los permisos finos (`VERTICALS_READ`, etc.) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>`.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / error) + lista de componentes.

---

### Pantalla 1 — `/catalog/verticals` (lista)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                    │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │ TopBar                                                   │ │
│ │            │ ├──────────────────────────────────────────────────────────┤ │
│ │ [≡] Brand  │ │                                                          │ │
│ │            │ │   Verticales                                             │ │
│ │ ▸ Inicio   │ │   Gestiona las áreas comerciales principales de la       │ │
│ │ ▾ Catálogo │ │   clínica.                                               │ │
│ │   • Verts█ │ │                                                          │ │
│ │   • Svcs   │ │   ┌──────────────────────────────┐  ┌──────────────────┐ │ │
│ │   • Prods  │ │   │ 🔍 Buscar por código o nom…│  │ + Nueva vertical│ │ │
│ │ ▸ Admin    │ │   └──────────────────────────────┘  └──────────────────┘ │ │
│ │            │ │                                                          │ │
│ │            │ │   ╭─ DataTable ──────────────────────────────────────╮  │ │
│ │            │ │   │ ⋯ │ Código       │ Nombre         │Color│Servs.│  │ │
│ │            │ │   ├───┼──────────────┼────────────────┼─────┼──────┤  │ │
│ │            │ │   │ ⋯ │ estetica_fa…│ Estética facial│  🔴 │   5  │  │ │
│ │            │ │   │ ⋯ │ dental       │ Dental         │  🔵 │   3  │  │ │
│ │            │ │   │ ⋯ │ dermat_clin │ Dermat. clínica│  🟣 │   2  │  │ │
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
| `code` | Código | text (truncate) | 200 | ✅ | `<code>` mono tag |
| `name` | Nombre | text (truncate) | 240 | ✅ | nombre comercial |
| `color` | Color | swatch | 80 | — | círculo de 12×12 px relleno con `color`, vacío si NULL |
| `services_count` | Servicios | numeric | 80 | ✅ | derecha, tabular-nums |
| `products_count` | Productos | numeric | 80 | ✅ | derecha, tabular-nums |
| `active` | Estado | badge | 100 | — | "Activo" (success) / "Deshabilitado" (informative) |
| `display_order` | Orden | numeric | 100 | ✅ | derecha |
| `updated_on` | Última actualización | date | 160 | ✅ | `formatDate(...)` |

**RowActions** (gated por `usePermissions()`):
- 👁 **Ver** — siempre visible (asume `VERTICALS_READ`).
- ✏ **Editar** — gated `VERTICALS_UPDATE`.
- 🗑 **Eliminar** — gated `VERTICALS_DELETE`. Confirm dialog: "¿Eliminar la vertical 'X'? Los servicios y productos asociados se conservan. Podrás recrear la vertical más adelante."

**Botón "+ Nueva vertical"**: gated `<PermissionGuard anyOf={["VERTICALS_CREATE"]}>`.

#### Estados

**Empty (no hay verticales aún)**:
```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                            📋  (DocumentDismissRegular)                      │
│                                                                              │
│                          Aún no hay verticales                               │
│         Las verticales son las áreas principales que ofrece tu clínica.      │
│         Crea la primera para empezar a construir el catálogo.                │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

> El template tiene `<EmptyState icon title message>` en `DataTable`. El botón **no** va dentro del EmptyState — el "New vertical" del toolbar superior cumple la función. Mantener consistencia.

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
- Si es un soft-error (ej. `409 VERTICAL_HAS_ACTIVE_CHILDREN` al borrar), `MessageBar intent="error"` dentro del confirm dialog o como toast.

#### Componentes Fluent UI / del template

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Sidebar | `Sidebar` (del template) — auto-renderiza `NAV_ITEMS` filtrados por permisos |
| Header | `<h1 className={styles.title}>` + `<p className={styles.subtitle}>` |
| Search | `<Input contentBefore={<SearchRegular />} />` |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Permission gate | `<PermissionGuard anyOf={["VERTICALS_CREATE"]}>` |
| Tabla | `<DataTable<VerticalItem> columns={...} ...>` |
| Color swatch | `<div style={{ background: row.color, width: 12, height: 12, borderRadius: '50%' }}>` |
| Badge active | `<Badge appearance="filled" color={u.active ? 'success' : 'informative'}>` |
| Row menu | `<RowActions item={u} actions={rowActions} />` |
| Drawer | `<VerticalDrawer mode={...} verticalId={...}>` (custom) |

---

### Pantalla 2 — VerticalDrawer (create / edit / view)

Drawer del template (`<Drawer size="medium">`). Una sola "tab" porque Vertical no tiene relaciones cargadas — solo metadata.

```
                       ┌─────────────────────────────────────────────────┐
                       │  Editar vertical                              ✕ │
                       │  estetica_facial                                │
                       ├─────────────────────────────────────────────────┤
                       │                                                 │
                       │  ╭─ [Detalles] [Auditoría] ───────────────────╮ │
                       │                                                 │
                       │  Código *                                       │
                       │  ┌─────────────────────────────────────────┐   │
                       │  │ estetica_facial      (no editable)      │   │
                       │  └─────────────────────────────────────────┘   │
                       │  Slug estable usado por bots — no editable.    │
                       │                                                 │
                       │  Nombre *                                       │
                       │  ┌─────────────────────────────────────────┐   │
                       │  │ Estética facial                          │   │
                       │  └─────────────────────────────────────────┘   │
                       │                                                 │
                       │  Descripción                                    │
                       │  ┌─────────────────────────────────────────┐   │
                       │  │ Tratamientos faciales no invasivos.     │   │
                       │  └─────────────────────────────────────────┘   │
                       │                                                 │
                       │  ┌───────────────────┐  ┌──────────────────┐   │
                       │  │ Color             │  │ Orden            │   │
                       │  │ ▢ #FF6B6B  [elegir]│ │ 10               │   │
                       │  └───────────────────┘  └──────────────────┘   │
                       │                                                 │
                       │  Ícono                                          │
                       │  ┌─────────────────────────────────────────┐   │
                       │  │ Sparkle24Regular  [elegir de galería]   │   │
                       │  └─────────────────────────────────────────┘   │
                       │                                                 │
                       │  ☑ Activa                                       │
                       │                                                 │
                       │  💡 Para eliminar o renombrar, usa el menú      │
                       │     de acciones de la fila.                     │
                       │                                                 │
                       ├─────────────────────────────────────────────────┤
                       │                       [ Cancelar ] [ Guardar ] │
                       └─────────────────────────────────────────────────┘
```

**Modos del drawer** (títulos visibles):
- `create`: título "Nueva vertical". Todos los fields editables, sin tab Auditoría.
- `edit`: título "Editar vertical". `code` disabled, resto editable, tab Auditoría visible.
- `view`: título "Detalle de vertical". Todos los fields disabled, footer con un solo botón `Cerrar`.

**Color picker**:
- Input read-only con swatch + botón "pick".
- Click abre un popover con paleta predefinida del `appTokens` (10–15 hex relevantes) + input manual `#RRGGBB`.
- Validación Zod regex `/^#[0-9A-Fa-f]{6}$/`.

**Icon picker**:
- Input read-only con preview del ícono + botón "pick".
- Click abre un popover con una **galería curada** de íconos Fluent UI permitidos para verticals (~30 íconos pre-elegidos por dominios típicos: `SparkleRegular`, `ToothRegular`, `HeartPulseRegular`, `LeafOneRegular`, etc.). Mantener una lista cerrada evita que el admin elija un ícono inexistente y rompa el sidebar.
- Almacenado como string (`Sparkle24Regular`).

**Tab Auditoría** (solo `edit` / `view`):
```
                       │  Creada el            Creada por               │
                       │  28 may 2026          Admin User               │
                       │                                                │
                       │  Actualizada el       Actualizada por          │
                       │  28 may 2026          Admin User               │
                       │                                                │
                       │  ─────────────────                             │
                       │                                                │
                       │  ID de la vertical                             │
                       │  8c5a-…  (mono code)                           │
```

#### Estados de error / loading

- **Guardando**: botón footer `[Guardando…]` disabled. Form fields disabled.
- **Error 409 (CODE_TAKEN)**: `MessageBar intent="error"` arriba del form con el `detail` (en español, viene del backend — ver glosario de copy abajo). El campo `code` queda con error inline.
- **Error 422 (validation drift)**: improbable porque el form valida con el mismo Zod. Si llega, muestra el `detail` genérico y loguea (drift schema con el backend).
- **Error de red**: `MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.
- **Cargando datos iniciales (edit / view)**: footer enabled cuando el `getVertical(id)` termina. Mientras carga, fields disabled con `placeholder="Cargando…"`.

---

### Pantalla 3 — `/catalog/services` (lista)

Igual estructura que verticals, con **filtros por vertical**:

```
   Servicios
   Agrupa productos dentro de cada vertical.

   ┌───────────────────────────────┐  ┌──────────────────────────────┐  ┌──────────────┐
   │ Vertical: Todas ▾             │  │ 🔍 Buscar por código o nom…│  │ + Nuevo serv.│
   └───────────────────────────────┘  └──────────────────────────────┘  └──────────────┘

   ╭─ DataTable ─────────────────────────────────────────────────────────────────╮
   │ ⋯ │ Vertical         │ Código          │ Nombre           │ Productos│ ...│
   ├───┼──────────────────┼─────────────────┼──────────────────┼──────────┼────┤
   │ ⋯ │ 🔴 Estética fa…│ limpieza_prof…  │ Limpieza profunda│      4   │ ...│
   │ ⋯ │ 🔴 Estética fa…│ hydrafacial     │ HydraFacial      │      3   │ ...│
   │ ⋯ │ 🔵 Dental       │ ortodoncia      │ Ortodoncia       │      6   │ ...│
   ╰─────────────────────────────────────────────────────────────────────────────╯
```

**Filtro Vertical** (dropdown de Fluent):
- Opciones cargadas de `GET /catalog/verticals/active` → `VerticalOption[]`.
- Selected = `null` → "Todas las verticales". Selected `X` → filtra `vertical_id=X`.
- El filtro se sincroniza con la URL como `?vertical_id=X` (vía `nuqs`). Permite deep-link desde otras pantallas.
- Al venir con `?vertical_id=X`, se muestra un **chip** indicando el filtro activo con una × para limpiar (consistente con el patrón de "row → drill down"):

```
   ┌─────────────────────────────────┐
   │ ⚡ Filtrado por: Estética facial ✕│
   └─────────────────────────────────┘
```

**Columnas** (`key` en inglés / `header` en español):

| `key` | Header | Render | Notas |
|---|---|---|---|
| `actions` | (sin) | RowActions | Ver / Editar (perm) / Eliminar (perm) |
| `vertical_name` | Vertical | text + color dot | dot 🔴 + nombre de la vertical. Sortable. |
| `code` | Código | mono | sortable |
| `name` | Nombre | text (truncate) | sortable |
| `products_count` | Productos | numeric | sortable, link "→ Ver 4 productos" al click va a `/catalog/products?service_id=X` |
| `active` | Estado | badge | "Activo" / "Deshabilitado" |
| `display_order` | Orden | numeric | sortable |
| `updated_on` | Última actualización | date | sortable |

**ServiceDrawer**: similar al VerticalDrawer. Tabs: `Detalles` + `Auditoría`. En `Detalles`, el campo `Vertical *` es un Dropdown con `VerticalOption[]`:

```
   Vertical *
   ┌─────────────────────────────────────────────┐
   │ 🔴  Estética facial                       ▾ │
   └─────────────────────────────────────────────┘
```

En `edit` mode el dropdown queda **disabled** (el `vertical_id` es inmutable post-creación).

#### Estados

- **Empty sin filtro**: "Aún no hay servicios. Crea tu primer servicio dentro de una vertical."
- **Empty con filtro por vertical sin services**: "Esta vertical aún no tiene servicios."
- **No-results** (search no matchea): el genérico de DataTable ("No hay resultados con los filtros actuales").
- Resto idéntico a verticals.

---

### Pantalla 4 — `/catalog/products` (lista)

Como services pero con **2 filtros encadenados** (vertical + service) y más columnas:

```
   Productos
   Unidades reservables. Cada cita reserva un producto.

   ┌─────────────────┐  ┌────────────────┐  ┌────────────────────┐  ┌───────────────┐
   │ Vertical: ▾     │  │ Servicio: ▾    │  │ 🔍 Buscar…         │  │ + Nuevo prod. │
   └─────────────────┘  └────────────────┘  └────────────────────┘  └───────────────┘

   ╭─ DataTable ────────────────────────────────────────────────────────────────────╮
   │ ⋯ │ Vert.  │ Servicio       │ Nombre            │ Precio│ Dur. │ Estado │ ...│
   ├───┼────────┼────────────────┼───────────────────┼───────┼──────┼────────┼────┤
   │ ⋯ │ 🔴 EF │ Limpieza prof. │ HydraFacial Prem. │  S/350│ 60'  │ Activo │ ...│
   │ ⋯ │ 🔴 EF │ HydraFacial    │ HydraFacial Basic │  S/180│ 30'  │ Activo │ ...│
   │ ⋯ │ 🔵 D  │ Ortodoncia     │ Plan 18m          │S/3,500│ —    │ Activo │ ...│
   ╰────────────────────────────────────────────────────────────────────────────────╯
```

**Filtros** (deep-link friendly):
- `Vertical` dropdown — al cambiar, el `Servicio` dropdown se filtra a services de esa vertical y se resetea su selección.
- `Servicio` dropdown — opciones de `GET /catalog/services/active?vertical_id=X`. Disabled si `vertical_id` es null y muestra "Elige una vertical primero".
- URL: `?vertical_id=X&service_id=Y`.
- Chips arriba de la tabla cuando hay filtros activos:
  ```
  ⚡ Filtrado por: 🔴 Estética facial ✕   |   📌 Limpieza profunda ✕
  ```

**Columnas** (`key` en inglés / `header` en español):

| `key` | Header | Render | Notas |
|---|---|---|---|
| `actions` | (sin) | RowActions | Ver / Editar / Eliminar |
| `vertical_name` | Vertical | dot + abbrev | Tooltip con nombre completo. Sortable. |
| `service_name` | Servicio | truncate | sortable |
| `name` | Nombre | truncate, mono code below | "HydraFacial Premium" / `código: hydrafacial_premium_60` debajo en gris |
| `base_price` | Precio | numeric | `S/ 350.00` formato locale (Intl.NumberFormat con `currency`). Tabular nums. Sortable. |
| `duration_min` | Duración | numeric | "60'" o "—" si NULL. Sortable. |
| `requires_appointment` | Reserva | icon | 📅 si true, plain si false. Tooltip "Reservable" / "No reservable". |
| `is_package` | Paquete | icon | 📦 si true. Tooltip "Paquete". |
| `active` | Estado | badge | "Activo" / "Deshabilitado" |
| `updated_on` | Última actualización | date | sortable |

**ProductDrawer** — el más rico. Tabs: `Detalles`, `Precio`, `Reserva`, `Auditoría`.

```
┌─────────────────────────────────────────────────────────┐
│  Nuevo producto                                       ✕ │
│  hydrafacial_premium_60                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ╭─ [Detalles] [Precio] [Reserva] [Auditoría] ───────╮ │
│                                                         │
│  [Tab Detalles]                                         │
│                                                         │
│  ┌────────────────┐ ┌────────────────────────────────┐ │
│  │ Vertical *     │ │ Servicio *                     │ │
│  │ 🔴 Estética ▾ │ │ Limpieza profunda            ▾ │ │
│  └────────────────┘ └────────────────────────────────┘ │
│                                                         │
│  Código *                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ hydrafacial_premium_60                          │   │
│  └─────────────────────────────────────────────────┘   │
│  Slug en minúsculas. Lo usan los bots y los reportes.  │
│                                                         │
│  Nombre *                                               │
│  ┌─────────────────────────────────────────────────┐   │
│  │ HydraFacial Premium 60 min                      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  Descripción                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Tratamiento completo con sérum personalizado.   │   │
│  │                                                  │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ☑ Activo                                               │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                          [ Cancelar ] [ Crear ]         │
└─────────────────────────────────────────────────────────┘
```

**Tab Precio**:
```
│  Precio base *                 Moneda                   │
│  ┌────────────────────┐        ┌──────────────────┐    │
│  │ 350.00             │        │ PEN            ▾ │    │
│  └────────────────────┘        └──────────────────┘    │
│  Precio de lista sin descuento.                        │
│                                                         │
│  💡 Las promociones aplican descuento sobre este       │
│     precio base.                                       │
```

Dropdown `Moneda` con opciones `PEN / USD / EUR`. Si se necesitan más, ampliar el enum en código.

**Tab Reserva**:
```
│  ☑ Requiere cita                                        │
│  Este producto puede reservarse como cita.             │
│                                                         │
│  Duración                                               │
│  ┌────────────────────┐                                │
│  │ 60                 │ minutos                         │
│  └────────────────────┘                                │
│  Vacío = se deriva de la duración del slot del doctor. │
│                                                         │
│  ☐ Es paquete / tratamiento multi-sesión               │
│                                                         │
│  Horas mínimas para cancelar                            │
│  ┌────────────────────┐                                │
│  │ 24                 │ horas                           │
│  └────────────────────┘                                │
│  Vacío = sin límite de cancelación.                    │
```

Cross-field validation visible: si `Requiere cita + min_hours_to_cancel` set + `duración` NULL → MessageBar inline en el tab Reserva:

```
│  ⚠ Las reglas de cancelación requieren una duración.   │
│    Define la duración o quita las horas mínimas.       │
```

**Tab Auditoría**: idéntico al de Vertical (creado/actualizado el/por) + `ID del producto`.

#### Estados especiales del ProductDrawer

- **Cambiar Vertical en create**: al cambiar la vertical, el dropdown Servicio se filtra y se resetea a empty. Se llama `form.setValue("service_id", "")` para que Zod marque el campo como inválido.
- **Edit mode**: Vertical y Servicio dropdowns disabled (no son updatable).
- **Sin servicios en la vertical seleccionada**: dropdown Servicio muestra "Aún no hay servicios en esta vertical — crea uno primero" como Option disabled, y el footer Crear disabled.

#### Componentes Fluent UI

| Concepto UI | Componente |
|---|---|
| Dropdown jerárquico (Vert. + Svc.) | `<Dropdown>` × 2 con state encadenado |
| Tabs en drawer | `<TabList><Tab value="details">…</Tab></TabList>` |
| Currency dropdown | `<Dropdown>` con 3-5 opciones predefinidas |
| Number input duration / hours / display_order / price | `<Input type="number">` (Fluent acepta `type="number"`) |
| Checkbox `Active`, `Requires appointment`, `Is package` | `<Checkbox>` |
| Inline warning (cross-field) | `<MessageBar intent="warning">` dentro del tab Booking |
| Icon picker (vertical) | Custom popover con grid de íconos Fluent + búsqueda |
| Color picker (vertical) | Custom popover con paleta + input hex manual |

## Decisiones de UI (cierres)

### Drill-down vía chips, no breadcrumbs

Cuando el usuario click "View 4 services" en una vertical, navega a `/catalog/services?vertical_id=X` con un chip "Filtered by: Estética facial ✕". Razón: las páginas son hermanas (cada una con su propio CRUD); breadcrumbs sugerirían navegación jerárquica que no es real.

### Color y icon como pickers, no inputs libres

Razón: admin elige de paleta/galería curada → consistencia visual + no rompe sidebar con íconos que no existen. Trade-off: menos flexibilidad. Si negocio quiere abrir, agregar "Custom hex…" / "Other icon name…" opcional en cada picker.

### Sin "duplicate vertical/service/product"

No incluimos botón "Duplicate" en el RowActions del MVP. Crear es rápido; la copia parcial con cambio de code y reset de relaciones tiene casos borde (¿se copian los products del service?). Postergar.

### Sin bulk actions

No "select multiple → delete all". Los catálogos son chicos (decenas de filas) y bulk-delete tiene riesgo de errores. Cada delete tiene su confirmación. Postergar.

### Sort default por `display_order ASC`

Más útil para admin que `created_on DESC` (que es el default genérico en otros listados). El admin maneja el orden manualmente con esa columna.

### Mobile / responsive

El template está optimizado para desktop (admin internal). Para mobile:
- Sidebar colapsado por default.
- DataTable scrollea horizontal con custom scrollbar (ya implementado).
- Drawer ocupa 100% del width en mobile.
- Filtros se apilan verticalmente.

No diseñamos pantallas mobile-first separadas — la versión desktop se adapta. Si negocio pide tablet/móvil real, va a un MVP posterior.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, CSS classes) se mantienen en inglés — solo los textos visibles al usuario van traducidos. Ver [[feedback-medisage-spanish-ui]] en memoria global para el glosario completo.

### Copy por contexto

| Contexto | Copy |
|---|---|
| Page title (verticals) | "Verticales" |
| Page subtitle (verticals) | "Gestiona las áreas comerciales principales de la clínica." |
| Page title (services) | "Servicios" |
| Page subtitle (services) | "Agrupa productos dentro de cada vertical." |
| Page title (products) | "Productos" |
| Page subtitle (products) | "Unidades reservables. Cada cita reserva un producto." |
| Botón crear (verticals) | "+ Nueva vertical" |
| Botón crear (services) | "+ Nuevo servicio" |
| Botón crear (products) | "+ Nuevo producto" |
| Search placeholder (verticals/services/products) | "Buscar por código o nombre…" |
| Empty state (verticals) | "Aún no hay verticales. Crea la primera para empezar a construir el catálogo." |
| Empty state (services no filter) | "Aún no hay servicios. Crea tu primer servicio dentro de una vertical." |
| Empty state (services con filtro vertical sin services) | "Esta vertical aún no tiene servicios." |
| Empty state (products no filter) | "Aún no hay productos. Crea tu primer producto dentro de un servicio." |
| Empty state (products con filtro) | "No hay productos para esta combinación de filtros." |
| No-results genérico (DataTable) | "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía." |
| Drawer title `create` (vertical / service / product) | "Nueva vertical" / "Nuevo servicio" / "Nuevo producto" |
| Drawer title `edit` | "Editar vertical" / "Editar servicio" / "Editar producto" |
| Drawer title `view` | "Detalle de vertical" / "Detalle de servicio" / "Detalle de producto" |
| Botón guardar | "Guardar" / "Crear" (en create) |
| Botón guardando (pending) | "Guardando…" / "Creando…" |
| Botón cancelar | "Cancelar" |
| Botón cerrar (view) | "Cerrar" |
| Confirm delete title | "¿Eliminar vertical?" |
| Confirm delete body (vertical) | "¿Eliminar la vertical '{nombre}'? Los servicios y productos asociados se conservan. Podrás recrear la vertical más adelante." |
| Confirm delete body (service) | "¿Eliminar el servicio '{nombre}'? Los productos asociados se conservan." |
| Confirm delete body (product) | "¿Eliminar el producto '{nombre}'? Las citas y promociones históricas se conservan." |
| Botón confirmar eliminación | "Eliminar" |
| Error 409 al borrar (vertical_has_children) | "No se puede eliminar — la vertical tiene {N} servicio(s) activo(s). Deshabilítalos o elimínalos primero." |
| Error 409 al borrar (service_has_children) | "No se puede eliminar — el servicio tiene {N} producto(s) activo(s). Deshabilítalos o elimínalos primero." |
| Error 409 al crear (code_taken) | "Ya existe un elemento con ese código." |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |
| Status badge | "Activo" / "Deshabilitado" |
| Bookable badge tooltip | "Reservable" / "No reservable" |
| Package badge tooltip | "Paquete multi-sesión" |
| Chip filtro activo | "Filtrado por: {nombre} ✕" |
| Filter dropdown placeholder | "Todas las verticales" / "Elige una vertical primero" / "Todos los servicios" |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Audit labels | "Creada el", "Creada por", "Actualizada el", "Actualizada por", "ID de la vertical" (concordancia: el / la según entidad) |
| Hint (vertical.code) | "Slug en minúsculas, estable. Lo usan los bots para clasificar leads." |
| Hint (color picker) | "Hex como #FF6B6B" |
| Hint (icon picker) | "Elige uno de la galería" |
| Hint (price) | "Precio de lista sin descuento." |
| Hint (duration vacío) | "Vacío = se deriva de la duración del slot del doctor." |
| Hint (min_hours_to_cancel) | "Vacío = sin límite de cancelación." |
| Warning cross-field cancel | "Las reglas de cancelación requieren una duración. Define la duración o quita las horas mínimas." |
| Loading placeholder en inputs | "Cargando…" |
| Cargando initial data (drawer) | "Cargando…" |

### Concordancia de género

- **Vertical** es femenino: "Nueva vertical", "Editar vertical", "Activa", "Creada por".
- **Servicio** y **Producto** son masculinos: "Nuevo servicio", "Editar producto", "Activo", "Creado por".
- En los confirm dialogs y mensajes mantener concordancia: "¿Eliminar la vertical 'X'?" vs "¿Eliminar el servicio 'Y'?".

### Sin i18n framework por ahora

Los textos están **directos como strings en cada componente**. Si negocio pide soporte multilingüe (clínicas en otros idiomas), introducir `next-intl` o similar después. Postergado.

### Textos del template existente

El template trae `admin/users`, `admin/roles`, `admin/permissions` con textos en inglés (titles, navigation labels, etc.). Esos también deben traducirse a español como parte de la implementación. Documentado en [`frontend.md`](frontend.md) como TODO.
