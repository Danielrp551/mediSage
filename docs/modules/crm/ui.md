# Módulo `crm` — UI design

> **Última actualización**: 2026-05-31
> **Audiencia**: developer implementando las pantallas de `crm` en `frontend/src/app/(main)/crm/`.
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). Modelo en [ADR-003](../../decisions/ADR-003-person-with-separated-lifecycle-statuses.md), matriz de transiciones en ADR-008 (a consolidar), forward-FK diferidas en ADR-009 (a consolidar).

> **Alineación con staff/clinic/catalog (módulos gold-standard ya en prod)**: `crm` reutiliza directamente los patrones que esos módulos dejaron como precedente del template: DataTable + filtros con chip + deep-link (`OfficesClient`/`DoctorsClient`), drawer de creación con multi-select (`DoctorCreateDrawer` + `SearchableOptionList`), **página de detalle con tabs** (`OfficeDetailShell`/`DoctorDetailShell`), y los catálogos simples por drawer (`VerticalsClient`). La gran diferencia es el **Timeline de Actividad** (tab Actividad) — el componente bespoke más pesado de este módulo, análogo en peso (no en forma) al calendario semanal de `staff`. Se documenta en detalle y se construye **al final** (F5), sobre una base ya usable.

> **Contexto de diseño (pedido explícito del usuario)**: aplicar pensamiento de CRMs modernos (HubSpot, Pipedrive, Intercom, Salesforce) **ejecutado DENTRO de Fluent UI 9** del template. Consistencia con catalog/clinic/staff shipped **>** introducir un estilo nuevo (regla de la metodología). Detalles técnicos no negociables:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Para otros colores usar tokens Fluent (`tokens.colorPaletteRedForeground1`, `tokens.colorPaletteGreenForeground1`, etc.) o el `color` hex del catálogo (badges de estado).
> - Cualquier cálculo de la fecha de **"hoy"** que afecte el render (agrupación del timeline, "hace 2 h", resaltado de seguimientos futuros) debe ser **client-only** — el SSR corre en UTC y desfasa el día en Lima (UTC-5). Lección recurrente de `staff` (`new Date()` en SSR rompe el día).

---

## Decisión de arquitectura: 1 lista de Contactos + detalle por tabs + 2 catálogos + Mis leads

`clinic` estableció la regla, reafirmada por `staff`: **si una entidad tiene sub-recursos con interacción propia (timelines, grids editables, listas CRUD anidadas, máquinas de estado), su detalle va a una página dedicada con tabs; si solo tiene metadata, va a drawer.** El `Person` cae claramente en el primer caso — tiene identificadores multicanal, dos máquinas de estado (lead/cliente) con su historial, asignación de owner y un **timeline de actividad** pesado. Por eso su detalle es **página** `/crm/personas/{id}` con tabs. La **creación** del Person, en cambio, es ligera (identidad + identificadores iniciales opcionales) y cabe en un **drawer**.

| Recurso | Lista | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **Person (Contacto)** | `/crm/personas` (sidebar, filtrable por estado lead/cliente/asesor + "con lead activo") | **drawer** (identidad + identificadores iniciales opcionales) | **página** `/crm/personas/{id}` (tabs Resumen · Identificadores · Lead · Cliente · Actividad · Auditoría) | igual molde que `OfficeDetailShell`/`DoctorDetailShell` |
| **LeadStatus** (catálogo) | `/crm/estados-lead` (sidebar) | drawer | drawer + editor de matriz de transiciones | molde `VerticalsClient` (catalog) |
| **CustomerStatus** (catálogo) | `/crm/estados-cliente` (sidebar) | drawer | drawer + editor de matriz | molde `VerticalsClient` |
| **Mis leads** | `/crm/mis-leads` (sidebar, solo del asesor logueado) | — | click → `/crm/personas/{id}` | DataTable read-only (molde `DoctorsClient`) |
| **PersonContactIdentifier** | — (no tiene lista propia) | dentro del tab **Identificadores** | dentro del tab Identificadores | lista CRUD anidada |
| **LeadActivity** | — | dentro del tab **Actividad** (composer) | dentro del tab Actividad (Timeline) | **bespoke: feed cronológico agrupado por día** |

### Por qué el detalle del Person es página con tabs y no una página única ni un drawer

Misma justificación-precedente que el Office de clinic y el Doctor de staff (el sub-recurso pesado manda la forma), pero la decisión clave acá es **tabs vs página única (todo scrolleado)**:

| Opción | Veredicto |
|---|---|
| **A. Página `/crm/personas/{id}` con tabs** (Resumen · Identificadores · Lead · Cliente · Actividad · Auditoría) — cada hilo (identidad, lead, cliente, timeline) es una superficie densa con su propia carga de datos, sus propios permisos (`LEAD_*` vs `PERSONS_*` vs `LEAD_STATUS_HISTORY_READ`) y sus propias mutaciones; el timeline necesita ancho completo; URL bookmarkable (`/crm/personas/abc?tab=actividad`); reusa el shell que clinic/staff ya construyeron. | **Elegida** |
| B. Página única, todo en scroll vertical (estilo "record page" de Salesforce/HubSpot) | Rechazada — seis superficies densas en un solo scroll obligan a cargar todo (history + timeline + identifiers) en el primer render (waterfalls), y el gating por permiso por sección (un ASESOR ve Lead/Actividad pero no edita catálogos) se vuelve un laberinto de `<PermissionGuard>` intercalados. Tabs aíslan la carga (cada tab fetcha lo suyo al activarse) y el gating (tab que no se renderiza). |
| C. Drawer `size=large` con tabs | Rechazada — el timeline (feed largo + composer) y las dos máquinas de estado no caben cómodos en ~640 px; los popovers de transición/edición sobre el overlay del drawer = z-index frágil. Mismo veredicto que el calendario de staff. |
| D. Acordeón inline en la lista | Rechazada — no escala a un timeline ni a un detalle de 6 superficies. |

**El Person reusa literalmente el patrón de `DoctorDetailShell`/`OfficeDetailShell`**: header con back-link + nombre + badges de estado + `TabList` sincronizado con `?tab=` vía `nuqs` + gating por permisos por tab + fallback a la primera tab permitida. No reinventamos el shell: lo clonamos como `PersonDetailShell`.

> ⚠ La **creación** del Person vive en un drawer desde la lista (`PersonCreateDrawer`); **ver/editar** un contacto existente **navega** a su página de detalle. Crear es ligero (identidad + identificadores); administrar lead/cliente/timeline necesita la página.

> **Patrón de tab lazy + permiso** (igual que `DoctorDetailShell`): `ALLOWED_TABS = ["resumen","identificadores","lead","cliente","actividad","auditoria"]`. Una tab solo se renderiza si el viewer tiene su permiso de lectura (Lead/Cliente/Actividad gateadas por `LEAD_ACTIVITIES_READ`/`LEAD_STATUS_HISTORY_READ`; Identificadores/Resumen/Auditoría por `PERSONS_READ`). Si la URL pide una tab no permitida o desconocida → cae a `resumen`. El contenido de cada tab se monta solo al activarse (sin waterfall de seis fetches en el primer render).

## Sidebar — extensión de `NAV_ITEMS` (grupo "CRM", gated `MENU-CRM`)

> ⚠ **Textos UI en español**. `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un parent item `crm` con 4 children, entre `staff` y `admin`:

```ts
{
  key: "crm",
  label: "CRM",
  icon: "PeopleRegular",                 // verificar en la versión de Fluent; fallback "ContactCardRegular"
  children: [
    { key: "personas",        label: "Contactos",          icon: "ContactCardRegular", url: "/crm/personas",        permissions: ["MENU-CRM"] },
    { key: "mis-leads",       label: "Mis leads",           icon: "PersonRegular",      url: "/crm/mis-leads",       permissions: ["MY_LEADS_READ"] },
    { key: "estados-lead",    label: "Estados de lead",     icon: "TagRegular",         url: "/crm/estados-lead",    permissions: ["LEAD_STATUSES_READ"] },
    { key: "estados-cliente", label: "Estados de cliente",  icon: "TagMultipleRegular", url: "/crm/estados-cliente", permissions: ["CUSTOMER_STATUSES_READ"] },
  ],
},
```

> El parent usa `MENU-CRM` como gate de visibilidad del grupo. Cada child gatea por **su** permiso de lectura para que un ASESOR (que tiene `MENU-CRM`, `PERSONS_READ`, `MY_LEADS_READ`, `LEAD_STATUSES_READ`, `CUSTOMER_STATUSES_READ` — ver [`_seed-and-roles.md`](../_seed-and-roles.md)) vea Contactos, Mis leads y los catálogos en read-only, mientras los permisos finos (`PERSONS_CREATE`, `LEAD_STATUSES_WRITE`, `LEAD_ACTIVITIES_WRITE`…) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>` / `usePermissions()`. La **página de detalle** del contacto no tiene entrada propia en el sidebar — se llega navegando desde la lista o desde Mis leads.

> Iconos Fluent (verificar que existan en la versión instalada; usar fallback si no): `PeopleRegular`/`ContactCardRegular`/`PersonRegular`/`TagRegular`/`TagMultipleRegular`. Mismo criterio de verificación que `staff` con `DoctorRegular`/`PersonStethoscopeRegular`.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error) + tabla de componentes Fluent.

1. `/crm/personas` — lista (DataTable + filtros estado/asesor con chip + deep-link + badges de estado).
2. `PersonCreateDrawer` — creación (identidad + identificadores iniciales opcionales).
3. `/crm/personas/{id}` — página de detalle con 6 tabs (Resumen · Identificadores · Lead · Cliente · Actividad · Auditoría).
4. **Tab Actividad — el Timeline** (la pieza central: feed por día + chips + composer + tarjetas tipadas).
5. `/crm/estados-lead` y `/crm/estados-cliente` — catálogos + editor de matriz de transiciones.
6. `/crm/mis-leads` — los leads del asesor logueado.

---

### Pantalla 1 — `/crm/personas` (lista de Contactos)

Misma estructura que `OfficesClient`/`DoctorsClient`, con **tres filtros** deep-linkables (estado lead, estado cliente, asesor) + un toggle "con lead activo", todos con chip y ×, espejando exactamente el patrón shipped.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                      │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │ TopBar                                                     │ │
│ │            │ ├──────────────────────────────────────────────────────────┤ │
│ │ ▸ Inicio   │ │   Contactos                                                │ │
│ │ ▸ Catálogo │ │   Gestiona las personas, sus leads y clientes.             │ │
│ │ ▸ Clínica  │ │                                                            │ │
│ │ ▸ Staff    │ │  ┌────────────┐┌────────────┐┌──────────┐┌──────────┐┌────┐│ │
│ │ ▾ CRM      │ │  │Lead: Todos▾││Clte: Todos▾││Asesor:T.▾││🔍 Buscar ││+ Co││ │
│ │   • Contac█│ │  └────────────┘└────────────┘└──────────┘└──────────┘└────┘│ │
│ │   • Mis l. │ │  ☐ Solo con lead activo                                    │ │
│ │   • Est.L  │ │  ┌──────────────────────┐ ┌──────────────────────┐         │ │
│ │   • Est.C  │ │  │ Lead: Interesado    ✕│ │ Asesor: Ana Pérez   ✕│ ← chips │ │
│ │ ▸ Admin    │ │  └──────────────────────┘ └──────────────────────┘         │ │
│ │            │ │  ╭─ DataTable ────────────────────────────────────────╮   │ │
│ │            │ │  │ ⋯ │ Nombre        │ Contacto      │Lead    │Cliente │Asesor│Últ.act│ │
│ │            │ │  ├───┼───────────────┼──────────────┼────────┼────────┼──────┼───────┤ │
│ │            │ │  │ ⋯ │ Ana Torres    │📱+51 999…    │●Interes│●Activo │A.Pérez│hace 2h│ │
│ │            │ │  │ ⋯ │ Luis Rojas    │✉ luis@x.pe   │●Nuevo  │  —     │J.Díaz │hace 1d│ │
│ │            │ │  │ ⋯ │ María Quispe  │📱+51 988…    │  —     │●En trat│A.Pérez│hace 5d│ │
│ │            │ │  ├──────────────────────────────────────────────────────┤   │ │
│ │            │ │  │ Mostrando 1–3 de 3      ‹  Página 1 de 1  ›          │   │ │
│ │            │ │  ╰──────────────────────────────────────────────────────╯   │ │
│ └────────────┘ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas de la tabla** (`key` en inglés, coherente con los campos denormalizados de `PersonItem`; `header` visible en español). Mapean a `PersonItem` (ver [`backend.md`](./backend.md) y la spec §7 denormalización):

| `key` | Header | Tipo | min/max | Sortable | Render |
|---|---|---|---|---|---|
| `actions` | `""` (sin header) | RowActions | 48–56 | — | menú `…` con Ver / Editar / Eliminar (gated por permisos) |
| `full_name` | Nombre | text (truncate) | 220 | ✅ (server) | nombre completo (`first_name last_name second_last_name`) |
| `primary_identifier` | Contacto principal | text + ícono | 200 | ❌ | ícono de canal (`ChannelIcon`) + valor del identifier primario; "—" si no tiene |
| `lead_status` | Estado lead | badge | 140 | ❌ (deep-link) | `<StatusBadge color={...}>{name}</StatusBadge>`; "—" si no hay lead activo |
| `customer_status` | Estado cliente | badge | 140 | ❌ (deep-link) | `<StatusBadge>`; "—" si no es cliente |
| `assigned_advisor` | Asesor | text (truncate) | 160 | ❌ | `full_name` del asesor asignado; "Sin asignar" si no tiene |
| `last_activity_at` | Última actividad | date relativa | 140 | ✅ (server) | `formatRelative(...)` ("hace 2 h", "ayer", "12 may") — **client-only** |

> **Denormalización sin N+1** (spec §7): `primary_identifier`, `lead_status` (code/name/color), `customer_status`, `assigned_advisor` (full_name) y `last_activity_at` se hidratan por **batch** en el service (mismo patrón que `office.verticals_count` / `doctor.full_name`). **Importante (lección hotfix `cd10c78` de staff)**: estas columnas son **denormalizadas**, NO están en `ALLOWED_FIELDS` de Person → **no son server-sortable/filterable por su valor textual**. Por eso `primary_identifier`/`lead_status`/`customer_status`/`assigned_advisor` tienen `isSortable: false`, y el filtro por estado/asesor **no** filtra por el texto sino por el **id** (`lead_status_id`/`customer_status_id`/`advisor_user_id`), que el backend traduce a un `EXISTS`/JOIN (igual que staff `?branch_id=`). Solo `full_name` y `last_activity_at` (columnas reales de Person/denormalizada indexada) son server-sortable. `searchFields` del `useTableQuery` se limita a columnas de `ALLOWED_FIELDS`; la búsqueda por nombre/identificador visible es **client-side** (ver más abajo).

**RowActions** (gated por `usePermissions()`, mismo patrón que `OfficesClient`):
- 👁 **Ver** — siempre visible (asume `PERSONS_READ`). **Navega** a `/crm/personas/{id}` (no abre drawer).
- ✏ **Editar** — gated `PERSONS_UPDATE`. **Navega** a `/crm/personas/{id}?tab=resumen`.
- 🗑 **Eliminar** — gated `PERSONS_DELETE`. Confirm dialog (soft-delete del Person; arrastra sus identifiers/estados por filtrado, no borra historial).

**Botón "+ Nuevo contacto"**: gated `<PermissionGuard anyOf={["PERSONS_CREATE"]}>`. Abre `PersonCreateDrawer`.

**Filtros (Dropdown + chip + deep-link)** — espejo exacto de `OfficesClient`/`DoctorsClient`:
- **Filtro Estado lead**: opciones de `GET /crm/lead-statuses/active` → `LeadStatusOption[]` (cada opción muestra su swatch de color). `null` = "Todos los estados". Sincronizado con `?lead_status_id=X` vía `nuqs useQueryState`. Chip "Lead: {nombre} ✕". El backend traduce el id a `EXISTS person_lead_status WHERE lead_status_id = X AND deleted_at IS NULL`.
- **Filtro Estado cliente**: opciones de `GET /crm/customer-statuses/active`. `null` = "Todos". `?customer_status_id=X`. Chip "Cliente: {nombre} ✕".
- **Filtro Asesor**: opciones de `GET /crm/advisors/active` (lista cruda `AdvisorOption[]` de asesores, gated `LEAD_ASSIGNMENTS_READ` — **pertenece a crm**, no a admin; el ASESOR no tiene `USERS_VIEW`; ver [`backend.md`](./backend.md)). `null` = "Todos los asesores". `?advisor_user_id=X`. Chip "Asesor: {nombre} ✕". (Útil para que un líder vea "los leads de Ana".)
- **Toggle "Solo con lead activo"** (`<Switch>` o `<Checkbox>`): `?has_active_lead=true` → el backend filtra `EXISTS person_lead_status (no borrado)`. Sin chip (es un toggle visible).
- Todos se traducen a `extraFilters`/query params para `useTableQuery`, igual que la sede en offices.

> Deep-link de entrada: desde Mis leads, desde un dashboard ("12 leads en Interesado"), o desde marketing futuro se podrá llegar con `/crm/personas?lead_status_id=X&advisor_user_id=Y` y los chips aparecen pre-poblados (igual que "Ver N consultorios" en clinic).

**Búsqueda (client-side por nombre/identificador)**: el `<Input>` con `SearchRegular` filtra **client-side** sobre las filas ya cargadas, matcheando contra `full_name` **y** `primary_identifier` (ambos denormalizados, no server-filterable). Es búsqueda "en lo visible/cargado". Para la búsqueda global de un identificador exacto (la que usará el bot) existe `GET /crm/persons/search?q=&channel_type=&identifier=` en backend, pero la lista de UI usa el filtro client-side por consistencia con el resto del listado y porque la denormalización no es `ALLOWED_FIELD`. Placeholder: "Buscar por nombre o contacto…".

#### Estados

**Empty (no hay contactos aún, sin filtro)**:
```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                                │
│                          👥  (PeopleRegular)                                   │
│                                                                                │
│                          Aún no hay contactos                                  │
│        Registra el primer contacto para asignarle un lead, un asesor           │
│        y empezar a registrar su actividad.                                     │
│                                                                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

> Usa `<EmptyState icon title message>` del `DataTable`. El botón "Nuevo contacto" del toolbar cumple la función (no va dentro del EmptyState — consistencia con catalog/clinic/staff).

**Empty con filtro de estado lead sin matches**: "Ningún contacto está en este estado de lead."
**Empty con filtro de asesor sin matches**: "Este asesor no tiene contactos asignados todavía."
**Empty con "solo con lead activo"**: "Ningún contacto tiene un lead activo en este momento."

**Loading (primera carga)**: DataTable con 8 skeleton rows; toolbar normal; sin spinner extra (el server-prefetch del `page.tsx` evita ver esto en el primer load).

**No-results (búsqueda client-side sin matches)**: variante automática de `DataTable` cuando `isFiltered` → "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía."

**Refetching (background)**: tabla con `opacity: 0.55` + spinner pequeño top-right (overlay `shadow4`). Igual que clinic/staff.

**Error (5xx)**: capturado por `error.tsx` global. Soft-errors (ej. 409 `IDENTIFIER_TAKEN` al crear con un identificador tomado) se muestran inline en el drawer (ver Pantalla 2).

#### Componentes Fluent UI / del template

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Sidebar | `Sidebar` (auto-renderiza `NAV_ITEMS` filtrados por permisos) |
| Header | `<h1 className={styles.title}>` + `<p className={styles.subtitle}>` |
| Filtro Lead / Cliente / Asesor | `<Dropdown>` + `nuqs useQueryState("lead_status_id"/"customer_status_id"/"advisor_user_id")` (patrón `OfficesClient`) |
| Opción de estado en dropdown | swatch de color (`<div>` con `backgroundColor: opt.color`) + nombre |
| Toggle lead activo | `<Switch label="Solo con lead activo">` + `useQueryState("has_active_lead")` |
| Chip filtro | `styles.chip` + `<Button icon={<DismissRegular />} />` (patrón `OfficesClient`) |
| Search | `<Input contentBefore={<SearchRegular />} />` (filtro client-side) |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Permission gate | `<PermissionGuard anyOf={["PERSONS_CREATE"]}>` |
| Tabla | `<DataTable<PersonItem> columns={...} ...>` con `useTableQuery({ queryKey: "crm:persons", searchFields: ["full_name"], defaultSort: { field: "last_activity_at", order: "desc" } })` |
| Badge de estado | `<StatusBadge color={s.color}>{s.name}</StatusBadge>` (custom, ver Decisiones de UI) |
| Ícono de canal | `<ChannelIcon channel={i.channel_type} />` (custom, mapea `ChannelType` → ícono Fluent) |
| Fecha relativa | `formatRelative(iso)` (helper **client-only** nuevo en `lib/utils/date.ts`) |
| Navegación a detalle | `useRouter().push("/crm/personas/" + p.id)` desde RowActions / fila |
| Row menu | `<RowActions item={p} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive ... />` |
| Drawer create | `<PersonCreateDrawer leadStatuses customerStatuses>` (custom) |

---

### Pantalla 2 — `PersonCreateDrawer` (creación: identidad + identificadores)

Drawer del template (`<Drawer size="medium">`), **solo modo create** (ver/editar viven en la página de detalle). Es ligero comparado con el `DoctorCreateDrawer` (no crea User ni M:N obligatorias). Dos secciones en un solo scroll (no necesita tabs como el doctor): **Datos de la persona** + **Identificadores iniciales (opcionales)**.

```
                  ┌─────────────────────────────────────────────────┐
                  │  Nuevo contacto                               ✕ │
                  ├─────────────────────────────────────────────────┤
                  │  Datos de la persona                            │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Nombres *        │  │ Apellido paterno*│    │
                  │  │ Ana              │  │ Torres           │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Apellido materno                               │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Quispe                                   │   │
                  │  └─────────────────────────────────────────┘   │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Tipo de doc.    ▾│  │ N° de documento  │    │
                  │  │ DNI              │  │ 45678912         │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Fecha nac.      📅│  │ Género           │    │
                  │  │ 1990-03-12       │  │ Femenino         │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Dirección                                      │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Av. Ejemplo 123, Lima                    │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Notas                                          │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Contactó por la campaña de verano.       │   │
                  │  └─────────────────────────────────────────┘   │
                  │  ───────────────────────────────────────────   │
                  │  Identificadores (opcional)        [ + Agregar ]│
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 📱 WhatsApp ▾ │ +51 999 111 222 │ ●Princ│✕│   │
                  │  ├─────────────────────────────────────────┤   │
                  │  │ ✉ Email    ▾ │ ana@correo.pe   │ ○     │✕│   │
                  │  └─────────────────────────────────────────┘   │
                  │  Se valida que ningún identificador esté en     │
                  │  uso por otro contacto.                         │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Crear ]  │
                  └─────────────────────────────────────────────────┘
```

**Campos y validación (Zod, `personCreateSchema`)** — espejo de `PersonCreate` (ver [`backend.md`](./backend.md)):
- `first_name` requerido (1–80), `last_name` requerido (1–80), `second_last_name` opcional (≤80).
- `document_type` (`<Dropdown>` con DNI/RUC/CE — misma lista curada que `UserDrawer` reduce a estos) + `document_number` (≤40), ambos opcionales.
- `birth_date` opcional (`<DatePicker>` de `@fluentui/react-datepicker-compat`; el valor que afecte render se computa **client-only**). `gender` texto libre opcional (la spec dice sin enum — `<Input>` simple, no dropdown).
- `address` opcional (≤255), `notes` opcional (textarea, text largo).
- `identifiers[]` **opcional**: lista add/remove de `{ channel_type, identifier, is_primary }`. Cada fila: `<Dropdown>` de `ChannelType` (whatsapp/telegram/web/phone/email/instagram/facebook/other) + `<Input>` del valor + radio/toggle "Principal" (uno principal por `(channel_type)`; al marcar uno desmarca el de su mismo canal en el form). Validación Zod: si hay identificadores, `identifier` no vacío; formato libre (el backend valida dedup). NO se crea lead automáticamente (eso es una acción aparte en el tab Lead).

**Modo del drawer**: solo `create`. Título "Nuevo contacto". Footer `[ Cancelar ] [ Crear ]` (`Creando…` en pending). NO hay tab Auditoría (eso vive en la página de detalle).

#### Estados de error / loading

- **Guardando**: footer `[ Creando… ]` disabled; fields disabled (patrón `useTransition`).
- **Error 409 (`IDENTIFIER_TAKEN`)**: `<MessageBar intent="error">` arriba del form con el `detail` (en español, del backend: "Este identificador ya está en uso por otro contacto."); la fila del identificador en conflicto se marca con error inline. Si llega, **hacer scroll** a la sección de identificadores.
- **Error 422 (validation drift)**: improbable (mismo Zod). Mostrar `detail` genérico + loguear.
- **Error de red**: `<MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.

#### Componentes Fluent UI

| Concepto UI | Componente |
|---|---|
| Drawer | `<Drawer size="medium">` (del template) |
| Campos | `<FormField>` + `<Input>` / `<Textarea>` (notas) vía `Controller` (react-hook-form) |
| Tipo de documento | `<Dropdown>` con `DOCUMENT_TYPES` (reusado de `UserDrawer`, subset DNI/RUC/CE) |
| Fecha de nacimiento | `<DatePicker>` (`@fluentui/react-datepicker-compat`) |
| Género | `<Input>` (texto libre, sin enum) |
| Dos columnas | `styles.twoCol` (grid `1fr 1fr`, reusado de `DoctorCreateDrawer`) |
| Lista de identificadores | filas dinámicas (`useFieldArray`): `<Dropdown>` (canal) + `<Input>` (valor) + `<Radio>`/`<Switch>` principal + `<Button icon={<DismissRegular/>}>` |
| Botón agregar identificador | `<Button appearance="subtle" icon={<AddRegular/>}>` |
| Inline error 409 | `<MessageBar intent="error">` arriba del form |

---

### Pantalla 3 — `/crm/personas/{id}` (página de detalle con tabs)

Página dedicada (RSC `page.tsx` que prefetcha el Person + las opciones de catálogos/asesores, luego un client `PersonDetailShell`). **Clon directo de `DoctorDetailShell`/`OfficeDetailShell`**. 6 tabs: `Resumen` · `Identificadores` · `Lead` · `Cliente` · `Actividad` · `Auditoría`. La tab activa se sincroniza con la URL (`?tab=actividad`).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Volver a contactos                                                           │
│                                                                                │
│ Ana Torres Quispe                          [●Interesado] [●Activo] [👤 A.Pérez] │
│ 📱 +51 999 111 222 · DNI 45678912 · Lima                                       │
│                                                                                │
│ ╭─[ Resumen ][ Identificadores ][ Lead ][ Cliente ][ Actividad ][ Auditoría ]╮ │
│ │                                                                            │ │
│ │ ...contenido de la tab activa...                                           │ │
│ ╰────────────────────────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Header de la página** (idéntico al de `DoctorDetailShell`):
- `← Volver a contactos` (`<Button appearance="subtle" icon={<ArrowLeftRegular/>}>` → `/crm/personas`). MVP: link plano (igual que clinic/staff; no preservamos los filtros de la lista).
- Título = `person.full_name`.
- **Badges al lado** (lo que un CRM moderno muestra de un vistazo): `StatusBadge` de estado lead (si hay lead activo), `StatusBadge` de estado cliente (si es cliente), y un mini-badge del asesor asignado (avatar inicial + nombre). Omitir los que no apliquen (sin lead → no aparece el badge lead).
- Subtítulo = `{contacto principal} · {document_type} {document_number} · {address}` (omitir piezas NULL — ej. sin documento el segmento desaparece).

**Resolución de tab + permisos por tab** (misma lógica `allowed[tab]` de `DoctorDetailShell`):
- `Resumen` — `PERSONS_READ` (ver) / `PERSONS_UPDATE` (editar). Siempre visible.
- `Identificadores` — `PERSONS_READ` (ver) / `PERSONS_UPDATE` (editar). Siempre visible.
- `Lead` — `LEAD_ACTIVITIES_WRITE` para transicionar/promover; `LEAD_STATUS_HISTORY_READ` para el historial; `PERSONS_READ` para ver el estado. La tab se renderiza si hay `PERSONS_READ`.
- `Cliente` — análogo (transición = `LEAD_ACTIVITIES_WRITE`; historial = `LEAD_STATUS_HISTORY_READ`).
- `Actividad` — `LEAD_ACTIVITIES_READ` (ver el timeline) / `LEAD_ACTIVITIES_WRITE` (composer). Si el user no tiene `LEAD_ACTIVITIES_READ`, la tab **no se renderiza**.
- `Auditoría` — `PERSONS_READ`.
- Fallback: si la URL apunta a una tab no permitida o desconocida, cae a `resumen`.

#### Tab `Resumen / Datos`

Form embebido en la tab (no drawer) con su propio botón "Guardar cambios", igual que `OfficeDetailsTab`/`DoctorProfileTab`. Envía `PersonUpdate`. Muestra arriba un **resumen no editable** (estado lead, estado cliente, asesor con control de reasignación inline) y abajo los **campos de identidad editables**.

```
│ │ Estado lead       Estado cliente     Asesor                                │ │
│ │ [●Interesado]     [●Activo]          👤 Ana Pérez   [ Reasignar ▾ ]        │ │
│ │ ──────────────────────────────────────────────────────────────────────── │ │
│ │ Nombres *                     Apellido paterno *                           │ │
│ │ ┌─────────────────────────┐  ┌─────────────────────────┐                  │ │
│ │ │ Ana                     │  │ Torres                  │                  │ │
│ │ └─────────────────────────┘  └─────────────────────────┘                  │ │
│ │ Apellido materno              Tipo doc.        N° documento                │ │
│ │ ┌─────────────────────────┐  ┌──────────┐    ┌──────────┐                 │ │
│ │ │ Quispe                  │  │ DNI    ▾ │    │ 45678912 │                 │ │
│ │ └─────────────────────────┘  └──────────┘    └──────────┘                 │ │
│ │ Fecha nac.       Género               Dirección                           │ │
│ │ ┌────────────┐  ┌────────────┐       ┌─────────────────────────┐          │ │
│ │ │ 1990-03-12 │  │ Femenino   │       │ Av. Ejemplo 123, Lima   │          │ │
│ │ └────────────┘  └────────────┘       └─────────────────────────┘          │ │
│ │ Notas                                                                      │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐      │ │
│ │ │ Contactó por la campaña de verano.                               │      │ │
│ │ └──────────────────────────────────────────────────────────────────┘      │ │
│ │                                                       [ Guardar cambios ]   │ │
```

> El bloque "Asesor + Reasignar" es el `AssignmentControl` (ver Decisiones de UI). Si el viewer no tiene `LEAD_ASSIGNMENTS_WRITE`, se ve el asesor sin el botón Reasignar. Si el viewer solo tiene `PERSONS_READ` (no `PERSONS_UPDATE`), todos los campos quedan disabled y el botón "Guardar cambios" no se renderiza (read-only), igual que clinic/staff.

**Validación / estados**: Zod `personUpdateSchema` (mismos límites que create, sin identifiers). Guardando → `[ Guardando… ]` disabled. Error → `<MessageBar intent="error">` con el `detail`. Loading inicial → prefetcheado por `page.tsx`, arranca poblado.

#### Tab `Identificadores`

Lista CRUD anidada de los `PersonContactIdentifier` del Person (`GET /crm/persons/{id}/identifiers`). Cada fila: ícono de canal + valor + badge "Principal" + badge "Verificado". Acciones: agregar (drawer/dialog), editar, eliminar, marcar principal.

```
│ │ Identificadores                                       [ + Agregar ]        │ │
│ │ ┌────────────────────────────────────────────────────────────────────┐    │ │
│ │ │ 📱 WhatsApp   +51 999 111 222    ●Principal  ✔Verificado   [✏][🗑] │    │ │
│ │ │ ✉  Email      ana@correo.pe                  ○ Verificar    [✏][🗑] │    │ │
│ │ │ 💬 Telegram   @ana_t                          ○             [✏][🗑] │    │ │
│ │ └────────────────────────────────────────────────────────────────────┘    │ │
│ │ El identificador principal de cada canal se usa para contactar.            │ │
```

- **Agregar / Editar**: dialog con `<Dropdown>` (canal) + `<Input>` (valor) + `<Switch>` "Principal" + `<Switch>` "Verificado". `POST`/`PUT` a `/crm/persons/{id}/identifiers[/{ident_id}]`. Marcar principal desmarca el anterior del mismo canal (lo hace el service en una tx; el front re-fetcha).
- **Eliminar**: `<ConfirmDialog>` → `DELETE` (soft-delete; el índice UNIQUE parcial permite reasignar el mismo valor tras borrar).
- **Estados**: empty ("Este contacto aún no tiene identificadores. Agrega uno para poder contactarlo."), error inline (409 `IDENTIFIER_TAKEN`: "Este identificador ya está en uso por otro contacto.").
- Gating: `PERSONS_UPDATE` para agregar/editar/eliminar; sin él, lista read-only.

#### Tab `Lead`

Estado lead actual + **control de transición** (solo estados permitidos por la matriz) + origen + **timeline de history** + botón "Promover a cliente".

```
│ │ Estado actual                                                              │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐      │ │
│ │ │ [●Interesado]   en este estado desde hace 3 días                  │      │ │
│ │ │ Origen: Campaña Verano 2026 (solo lectura)                        │      │ │
│ │ │                                                                    │      │ │
│ │ │ Cambiar estado a:  [ Selecciona…            ▾ ]  [ Cambiar ]       │      │ │
│ │ │                    └─ Evaluando / No interesado (de la matriz)     │      │ │
│ │ │ Motivo (opcional): [ ……………………………………………………………………… ]                │      │ │
│ │ │                                                  [ Promover a cliente ] │  │ │
│ │ └──────────────────────────────────────────────────────────────────┘      │ │
│ │ Historial de estados                                                       │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐      │ │
│ │ │ ● Interesado        ← Contactado    Ana Pérez · hace 3 d           │      │ │
│ │ │ ● Contactado        ← Nuevo         Ana Pérez · hace 5 d           │      │ │
│ │ │ ● Nuevo             (inicial)       Sistema · hace 6 d             │      │ │
│ │ └──────────────────────────────────────────────────────────────────┘      │ │
```

- **Sin lead activo**: en vez del bloque de estado, un empty con CTA: "Este contacto no tiene un lead activo." + botón "Crear lead" (gated `LEAD_ACTIVITIES_WRITE`) → `POST /crm/persons/{id}/lead-status` (nace en `is_initial`; si no hay estado inicial configurado, el backend devuelve `NO_INITIAL_LEAD_STATUS` y se muestra el detalle).
- **Control de transición** (`TransitionControl`, ver Decisiones de UI): el `<Dropdown>` **solo lista los estados permitidos** por la matriz para el estado actual (`GET /crm/lead-statuses/{currentId}/transitions`). Si el estado actual es terminal (`is_final`), el control queda **deshabilitado** con el texto "Estado terminal — no admite cambios". Al confirmar → `POST /crm/persons/{id}/lead-status/transition {to_lead_status_id, reason?}`; el backend re-valida la matriz (`LEAD_TRANSITION_NOT_ALLOWED` si se coló una arista inválida) y, si el destino es `is_final`, cierra el lead (la fila se soft-deletea; la UI re-fetcha y muestra el lead como cerrado en el history).
- **Promover a cliente**: botón gated `LEAD_ACTIVITIES_WRITE` → `POST /crm/persons/{id}/promote-to-customer`. Confirm dialog ("¿Promover a Ana Torres a cliente? Se creará su ficha de cliente y, si el estado actual lo permite, se cerrará el lead como ganado."). Errores: `ALREADY_CUSTOMER` (409, "Este contacto ya es cliente.").
- **Origen** (`source_campaign_id`): solo lectura por ahora (marketing no existe). Si está poblado, mostrar el id o un placeholder "Campaña (módulo marketing pendiente)"; si NULL, omitir.
- **Historial** (`GET /crm/persons/{id}/lead-status/history`, gated `LEAD_STATUS_HISTORY_READ`): timeline simple `to ← from · actor · fecha relativa`, el inicial marcado "(inicial)", actor "Sistema" cuando `changed_by` es NULL/SYSTEM.

#### Tab `Cliente`

Análogo al tab Lead pero para la máquina de estado cliente (sin `is_won`, matriz customer permisiva):

```
│ │ Estado actual                                                              │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐      │ │
│ │ │ [●Activo]   cliente desde el 12 may 2026 · en este estado hace 1 d │      │ │
│ │ │                                                                    │      │ │
│ │ │ Cambiar estado a:  [ En tratamiento / Completado / Inactivo… ▾ ]   │      │ │
│ │ │                                                  [ Cambiar ]       │      │ │
│ │ └──────────────────────────────────────────────────────────────────┘      │ │
│ │ Historial de estados de cliente                                            │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐      │ │
│ │ │ ● Activo            (inicial)       Ana Pérez · 12 may             │      │ │
│ │ └──────────────────────────────────────────────────────────────────┘      │ │
```

- **No es cliente todavía**: empty "Este contacto aún no es cliente." (la conversión se hace desde el tab Lead con "Promover a cliente"; no se crea cliente "desde cero" en el MVP — es siempre promoción de lead).
- `became_customer_at` se muestra como "cliente desde el {fecha}". Transición vía `POST /crm/persons/{id}/customer-status/transition` (matriz customer). Historial `GET /crm/persons/{id}/customer-status/history`.

#### Tab `Actividad`

→ Ver **Pantalla 4** (es la pieza central, documentada aparte). En F1 esta tab es un **placeholder** ("Próximamente: actividad del contacto"), exactamente como clinic/staff dejaron tabs como placeholder hasta su fase. Se vuelve funcional en F3 (tarjetas de sistema STATUS_CHANGE/REASSIGNED + history) y rica en F5 (composer + NOTE/CALL/FOLLOW_UP).

#### Tab `Auditoría`

Idéntica estructura al `AuditTab` de `DoctorAuditTab`/`OfficeAuditTab`: grid de Estado · ID del contacto · Creado el/por · Actualizado el/por. Concordancia: **Contacto = masculino** ("Creado el", "Creado por"); **Persona = femenino** se evita en labels de auditoría usando "contacto". `created_by`/`updated_by` hidratados vía `UserAuditInfo` (patrón shipped, batch sin N+1).

#### Componentes Fluent UI (página de detalle)

| Concepto UI | Componente |
|---|---|
| Shell (back-link + título + badges + tabs) | `PersonDetailShell` — clon de `DoctorDetailShell` |
| Volver | `<Button appearance="subtle" icon={<ArrowLeftRegular />}>` → `/crm/personas` |
| Badges de header | `StatusBadge` (lead) + `StatusBadge` (cliente) + mini-badge de asesor (`<Avatar size={20}>` inicial) |
| Tabs de la página | `<TabList>` + `nuqs useQueryState("tab")` con `allowed[tab]` gating |
| Form Resumen | `<FormField>` + `<Input>`/`<Textarea>`/`<Dropdown>`/`<DatePicker>` + `<Button appearance="primary">` |
| AssignmentControl | custom (ver Decisiones de UI) — `<Menu>`/`<Dropdown>` reasignar + "Asignarme" + "Auto" |
| TransitionControl | custom (ver Decisiones de UI) — `<Dropdown>` con solo estados permitidos + `<Button>` |
| StatusBadge | custom — `<Badge>` con color del catálogo |
| Lista identificadores | filas + `<Dialog>` editor + `<ConfirmDialog>` |
| Historial de estados | lista vertical simple (no es el Timeline pesado; molde tabla compacta) |
| Auditoría | grid `styles.audit` (reusado de `DoctorAuditTab`/`OfficeAuditTab`) |

---

### Pantalla 4 — Tab `Actividad`: el TIMELINE (la pieza central)

> **HONESTIDAD (binding por la spec §8.4)**: este Timeline es el **componente más pesado de `crm`** (análogo en peso, no en forma, al calendario semanal de `staff`). Fluent UI 9 **no trae** un componente de "feed de actividad / timeline" — se construye con primitivos de Fluent (`Card`, `Avatar`, `Badge`, `Tab`/`TabList`, `Textarea`, `Input`, `DatePicker`, `Spinner`, `Skeleton`, `MessageBar`) + **tokens del design system** (`tokens.*`, `appTokens.*`, `makeStyles`). **NO se usa librería externa de timeline.** El lenguaje visual se inspira en el feed de actividad de HubSpot/Intercom (tarjetas tipadas con ícono de color, actor, timestamp relativo, agrupación por día, composer arriba) pero **enteramente dentro de Fluent**. Se construye **en F5**, al final, sobre un detalle ya usable.

#### Anatomía — mockup

```
│ │  Actividad                                                                 │ │
│ │  ╭─ Composer ──────────────────────────────────────────────────────────╮  │ │
│ │  │ [ 📝 Nota ][ 📞 Llamada ][ ⏰ Seguimiento ]                          │  │ │
│ │  │ ┌────────────────────────────────────────────────────────────────┐  │  │ │
│ │  │ │ Escribe una nota sobre este contacto…                          │  │  │ │
│ │  │ └────────────────────────────────────────────────────────────────┘  │  │ │
│ │  │                                                       [ Registrar ]  │  │ │
│ │  ╰──────────────────────────────────────────────────────────────────────╯  │ │
│ │  Filtrar: (Todos) (Notas) (Llamadas) (Seguimientos) (Estado) (Sistema)     │ │
│ │                                                                            │ │
│ │  ── Hoy ──────────────────────────────────────────────────────────────    │ │
│ │  ┌────────────────────────────────────────────────────────────────────┐   │ │
│ │  │ ⏰  Seguimiento programado                       AP  hace 1 h        │   │ │
│ │  │     Llamar para confirmar la cita.                                   │   │ │
│ │  │     📅 Para: mañana 10:00  ·  Recordatorio: WhatsApp     ◀ FUTURO   │   │ │
│ │  └────────────────────────────────────────────────────────────────────┘   │ │
│ │  ┌────────────────────────────────────────────────────────────────────┐   │ │
│ │  │ 📞  Llamada                                      AP  hace 2 h        │   │ │
│ │  │     No contestó, vuelvo a intentar en la tarde.                      │   │ │
│ │  │     [ Sin respuesta ]                                                │   │ │
│ │  └────────────────────────────────────────────────────────────────────┘   │ │
│ │  ── Ayer ─────────────────────────────────────────────────────────────    │ │
│ │  ┌────────────────────────────────────────────────────────────────────┐   │ │
│ │  │ 🔄  Cambio de estado                             ⚙  ayer 16:20       │   │ │
│ │  │     Contactado → Interesado                                          │   │ │
│ │  └────────────────────────────────────────────────────────────────────┘   │ │
│ │  ┌────────────────────────────────────────────────────────────────────┐   │ │
│ │  │ 📝  Nota                                         AP  ayer 15:55      │   │ │
│ │  │     Le interesa el paquete de estética facial.       [✏][🗑]        │   │ │
│ │  └────────────────────────────────────────────────────────────────────┘   │ │
│ │  ── 12 may 2026 ──────────────────────────────────────────────────────    │ │
│ │  ┌────────────────────────────────────────────────────────────────────┐   │ │
│ │  │ 👤  Lead asignado                                ⚙  12 may 09:00     │   │ │
│ │  │     Asignado a Ana Pérez (round-robin).                              │   │ │
│ │  └────────────────────────────────────────────────────────────────────┘   │ │
│ │  ┌────────────────────────────────────────────────────────────────────┐   │ │
│ │  │ 🎯  Atribución de campaña                        ⚙  12 may 09:00     │   │ │
│ │  │     Origen: Campaña Verano 2026.                                     │   │ │
│ │  └────────────────────────────────────────────────────────────────────┘   │ │
│ │  [ Cargar más ]                                                            │ │
```

#### Composer inline (arriba, gated `LEAD_ACTIVITIES_WRITE`)

Tres tabs rápidas (`<TabList>`) que cambian el form contextual. Un solo botón "Registrar" abajo. Reglas por tipo:

| Tab | `activity_type` | Form | Body a `POST /crm/persons/{id}/activities` |
|---|---|---|---|
| **📝 Nota** | `NOTE` | `<Textarea>` (contenido) | `{ activity_type: "NOTE", content }` |
| **📞 Llamada** | `CALL_ATTEMPT` | `<Dropdown>` outcome (`successful`/`no_answer`/`busy`/`wrong_number`/`not_interested`/`interested`) + `<Input>` duración (min, opcional → va a `payload`) + `<Textarea>` nota | `{ activity_type: "CALL_ATTEMPT", outcome, content, payload: { duration_min } }` |
| **⏰ Seguimiento** | `FOLLOW_UP_SCHEDULED` | `<DatePicker>` + `<Input type="time">` (`scheduled_for`) + `<Dropdown>` canal recordatorio (opcional → `payload`) + `<Textarea>` nota | `{ activity_type: "FOLLOW_UP_SCHEDULED", scheduled_for, content, payload: { reminder_channel } }` |

> El composer **no** ofrece tipos de sistema (STATUS_CHANGE/REASSIGNED/CAMPAIGN_ATTRIBUTION) ni los diferidos de otros módulos (MESSAGE_SENT, etc.) — esos los emite el backend. Solo NOTE/CALL_ATTEMPT/FOLLOW_UP_SCHEDULED (los que el asesor crea, spec §1.2). Marcar un seguimiento como completado (`FOLLOW_UP_COMPLETED`) se hace desde la tarjeta del seguimiento (acción "Marcar completado" → `PUT` con `completed_at`), no desde el composer.

Validación Zod (`activityCreateSchema`, `superRefine` por tipo): NOTE requiere `content`; CALL_ATTEMPT requiere `outcome`; FOLLOW_UP_SCHEDULED requiere `scheduled_for` futuro. Al registrar con éxito → `revalidateTag("crm:activities:{personId}")`, el composer se limpia, el feed re-fetcha y la nueva tarjeta aparece arriba.

#### Chips de filtro por tipo

Fila de chips (`<Button appearance={active?"primary":"outline"} shape="circular">`) que filtran las tarjetas. Mapeo chip → `activity_type[]`:

| Chip | Filtra |
|---|---|
| **Todos** | sin filtro |
| **Notas** | `[NOTE]` |
| **Llamadas** | `[CALL_ATTEMPT]` |
| **Seguimientos** | `[FOLLOW_UP_SCHEDULED, FOLLOW_UP_COMPLETED]` |
| **Estado** | `[STATUS_CHANGE]` |
| **Sistema** | `[REASSIGNED, CAMPAIGN_ATTRIBUTION, MESSAGE_SENT, CONVERSATION_TAKEN, CONVERSATION_RELEASED, APPOINTMENT_BOOKED, APPOINTMENT_CANCELLED]` |

El filtro se re-consulta al backend (`POST /crm/persons/{id}/activities/list { activity_type: [...], date_from?, date_to? }`) — no es puro client-side porque el timeline pagina (no todas las actividades están en memoria). El chip activo se guarda en URL state (`?act_type=`) para que sea bookmarkable.

#### Tarjetas tipadas (`ActivityCard`)

Cada actividad es un `<Card>` con ícono + color por `activity_type`, actor (avatar inicial + nombre), timestamp relativo, contenido y extras por tipo. **Color** vía tokens Fluent (recordatorio: NO existe `brandPalette.accent`):

| `activity_type` | Ícono Fluent | Color (token) | Extras de la tarjeta |
|---|---|---|---|
| `NOTE` | `NoteRegular` | `tokens.colorNeutralForeground2` | acciones editar/eliminar (autor) |
| `CALL_ATTEMPT` | `CallRegular` | `tokens.colorPaletteBlueForeground2` | chip de `outcome` (color por resultado), duración |
| `FOLLOW_UP_SCHEDULED` | `ClockAlarmRegular` | `tokens.colorPalettePurpleForeground2` | fecha objetivo + canal; **resaltado si es futuro** (banda lateral `tokens.colorPalettePurpleBorderActive`); acción "Marcar completado" |
| `FOLLOW_UP_COMPLETED` | `CheckmarkCircleRegular` | `tokens.colorPaletteGreenForeground1` | "completado el {fecha}" |
| `STATUS_CHANGE` | `ArrowSwapRegular` | `tokens.colorPaletteTealForeground2` | "{from} → {to}" (con los colores de cada estado) |
| `REASSIGNED` | `PersonSwapRegular` | `tokens.colorPaletteMarigoldForeground2` | "Asignado a {nombre}" |
| `CAMPAIGN_ATTRIBUTION` | `MegaphoneRegular` | `tokens.colorPaletteberryForeground2` (o `colorBrandForeground1`) | "Origen: {campaña}" |
| `MESSAGE_SENT`/`CONVERSATION_*` | `ChatRegular` | `tokens.colorNeutralForeground3` | (diferido a conversations; el render existe, no se emite aún) |
| `APPOINTMENT_*` | `CalendarRegular` | `tokens.colorPaletteGreenForeground2` | (diferido a scheduling) |

- **Actor**: `<Avatar size={24} name={advisor.full_name} color="colorful" />` (inicial) + nombre. Para actividades de sistema (`advisor_user_id` NULL) → avatar `⚙` con nombre "Sistema".
- **Timestamp relativo**: `formatRelative(created_on)` ("hace 1 h", "ayer 15:55", "12 may 09:00") — **client-only** (TZ). Tooltip con la fecha absoluta al hover.
- **`outcome` en llamadas**: chip con copy ES (`successful`→"Exitosa", `no_answer`→"Sin respuesta", `busy`→"Ocupado", `wrong_number`→"Número errado", `not_interested`→"No interesado", `interested`→"Interesado"), color por resultado (verde/ámbar/rojo).
- **Seguimientos futuros resaltados**: si `scheduled_for > now` (cálculo **client-only**), banda lateral de acento y badge "◀ Próximo" para que el asesor los vea de un vistazo (patrón "tasks" de Pipedrive).
- **Editar/eliminar** (solo NOTE y solo del autor o admin, gated `LEAD_ACTIVITIES_WRITE`): editar `content`/`outcome` inline → `PUT /crm/persons/{id}/activities/{act_id}`; eliminar = `active=false` (no borra; desaparece del feed) → `DELETE`. Confirm para eliminar.

#### Agrupación por día (`DayGroup`, "hoy" client-side)

El feed se agrupa en secciones con encabezado **"Hoy" / "Ayer" / "{fecha}"**. El cálculo de qué es "hoy"/"ayer" se hace **client-only** (la lección TZ de staff: el servidor en UTC pondría la frontera del día 5 h corrida en Lima). Implementación: el componente que decide los grupos es `"use client"` y calcula `today`/`yesterday` con `new Date()` **dentro de un `useEffect`/`useMemo` montado en cliente** (no en el render del servidor), evitando el mismatch de hidratación. Dentro de cada grupo, las actividades van **descendentes por timestamp** (lo más nuevo arriba), con los seguimientos futuros del día "Hoy" arriba del todo.

#### Performance (reglas vercel-react — binding)

> El timeline puede crecer a cientos de actividades. Reglas (de la skill vercel-react-best-practices):
- **`ActivityCard` memoizada** (`React.memo`) — la lista no debe re-renderizar todas las tarjetas cuando cambia el composer o el chip de filtro. Cada card recibe props estables (la actividad ya normalizada); los handlers (editar/eliminar) se pasan **estables** (`useCallback`) para que `React.memo` no se rompa.
- **Listas largas con `content-visibility: auto`** + `contain-intrinsic-size` en cada card (CSS via `makeStyles`) → el navegador no paga layout/paint de las tarjetas fuera del viewport. Es el approach barato (sin librería de virtualización) y suficiente para el volumen esperado; si el volumen explota, evaluar virtualización después.
- **Paginación "Cargar más"** (no infinite-scroll en MVP): `POST /crm/persons/{id}/activities/list` con `skip`/`limit`; el botón "Cargar más" trae el siguiente lote y lo **appendea** (no re-fetcha todo). Evita traer cientos de filas de un saque.
- **Sin waterfalls**: la tab Actividad fetcha su data al activarse (no en el primer render de la página). El composer **no** dispara un re-fetch del feed completo en cada tecla — solo al "Registrar" (con `revalidateTag` puntual). El filtro por chip re-consulta una sola vez al cambiar.
- **`useMemo` para la agrupación por día** (no recomputar los grupos en cada render; solo cuando cambia la lista de actividades).

#### Estados

- **Loading**: 3–4 `ActivityCard` skeletons (avatar + 2 líneas) bajo el composer; el composer ya es interactivo. `<Skeleton><SkeletonItem>`.
- **Empty (sin actividad)**: ícono + "Sin actividad aún" + "Registra la primera nota, llamada o seguimiento con el panel de arriba." (el composer está presente arriba; el empty está debajo). Copy alineado a la spec §8.4 ("Sin actividad aún · registra la primera nota").
- **No-results (chip de filtro sin matches)**: "No hay actividades de este tipo." con botón "Ver todas" que resetea el chip a "Todos".
- **Guardando (composer)**: botón `[ Registrando… ]` disabled; el form disabled; al éxito se limpia y la card aparece arriba (optimista opcional; mínimo: re-fetch tras éxito).
- **Error**: `<MessageBar intent="error">` arriba del feed con el `detail` del backend (`ACTIVITY_NOT_FOUND` 404 si se edita una actividad borrada en otra pestaña; error de red).

#### Componentes Fluent UI (Timeline)

| Concepto UI | Componente |
|---|---|
| Composer (tabs Nota/Llamada/Seguimiento) | `<TabList>` + form contextual (`<Textarea>`/`<Dropdown>`/`<DatePicker>`/`<Input type="time">`) + `<Button appearance="primary">` |
| Chips de filtro | `<Button appearance={active?"primary":"outline"} shape="circular">` + `nuqs useQueryState("act_type")` |
| Tarjeta de actividad | `ActivityCard` = `<Card>` (memoizada) con ícono Fluent + `<Avatar>` + `<Badge>` (outcome) + contenido |
| Ícono por tipo | íconos Fluent (`NoteRegular`, `CallRegular`, `ClockAlarmRegular`, `ArrowSwapRegular`, `PersonSwapRegular`, `MegaphoneRegular`, …) con color de `tokens.colorPalette*` |
| Color de tipo | `tokens.colorPalette*Foreground*` (NO `brandPalette.accent`) |
| Encabezado de día | `DayGroup` (custom, "use client", cálculo de hoy/ayer **client-only**) |
| Avatar de actor | `<Avatar size={24} name={...} color="colorful">` (inicial); "Sistema" = `⚙` |
| Timestamp relativo | `formatRelative(iso)` (helper **client-only** nuevo en `lib/utils/date.ts`) + `<Tooltip>` con fecha absoluta |
| Chip de outcome | `<Badge appearance="tint" color={...}>` (verde/ámbar/rojo según resultado) |
| Cargar más | `<Button appearance="subtle">` → append del siguiente lote |
| Skeleton | `<Skeleton>` + `<SkeletonItem>` por card |
| Editar/eliminar nota | edición inline (`<Textarea>`) + `<ConfirmDialog>` para eliminar |
| Error / éxito | `<MessageBar intent="error"/"success">` |
| Perf: lista larga | CSS `contentVisibility: "auto"` + `containIntrinsicSize` (makeStyles); `React.memo` en card |

#### Plan incremental (binding — construir en este orden, dentro de F5)

> El Timeline es el mayor riesgo de frontend de `crm`. Construirlo de una sola vez es la trampa. Orden recomendado:

1. **Iteración A (lo funcional primero)** — feed read-only: fetch paginado, agrupación por día (client-only), `ActivityCard` por tipo (con render de TODOS los tipos del enum, aunque algunos no se emitan), chips de filtro, "Cargar más", estados loading/empty/error. Con esto la tab Actividad **muestra** el historial (incluyendo las STATUS_CHANGE/REASSIGNED/CAMPAIGN_ATTRIBUTION que F3 ya emite).
2. **Iteración B (composer)** — composer con tabs Nota/Llamada/Seguimiento + `POST` + limpiar + re-fetch. NOTE/CALL_ATTEMPT/FOLLOW_UP_SCHEDULED.
3. **Iteración C (refinamientos)** — editar/eliminar nota inline; "Marcar completado" en seguimientos; resaltado de seguimientos futuros; memoización + `content-visibility` afinados.

> Si el tiempo aprieta dentro de F5, la Iteración A (read-only) ya es entregable: el timeline muestra todo lo que el sistema emite. El composer (B) es lo que convierte al asesor en autor. **Mantenerse dentro de Fluent tokens**; no introducir una librería de timeline.

---

### Pantalla 5 — Catálogos `/crm/estados-lead` y `/crm/estados-cliente` (+ editor de matriz)

Dos pantallas casi idénticas (molde `VerticalsClient` de catalog), con la **diferencia** de que cada estado tiene un **editor de transiciones permitidas** (la matriz, ADR-008). LeadStatus tiene un flag extra (`is_won`) que CustomerStatus no.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Estados de lead                                                              │
│   Configura los estados por los que pasa un lead y sus transiciones.           │
│                                                          [ + Nuevo estado ]    │
│   ╭─ DataTable ──────────────────────────────────────────────────────────╮   │
│   │ ⋯ │ Código        │ Nombre        │ Color │ Flags         │ Orden │     │   │
│   ├───┼───────────────┼───────────────┼───────┼───────────────┼───────┤     │   │
│   │ ⋯ │ NUEVO         │ Nuevo         │ ⬤ gris│ ●Inicial      │  10   │     │   │
│   │ ⋯ │ CONTACTADO    │ Contactado    │ ⬤ azul│               │  30   │     │   │
│   │ ⋯ │ INTERESADO    │ Interesado    │ ⬤ cian│               │  40   │     │   │
│   │ ⋯ │ CITA_AGENDADA │ Cita agendada │ ⬤verde│ ●Final ●Ganado│  60   │     │   │
│   │ ⋯ │ NO_INTERESADO │ No interesado │ ⬤ rojo│ ●Final        │  70   │     │   │
│   ╰──────────────────────────────────────────────────────────────────────╯   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas**: Código (`code`, mono), Nombre (`name`), Color (swatch `⬤` + hex), Flags (badges "Inicial"/"Final"/"Ganado"), Orden (`display_order`, numérico). RowActions: Ver/Editar (drawer), Eliminar (gated `LEAD_STATUSES_WRITE`; 409 `LEAD_STATUS_IN_USE` si hay leads en ese estado → "No se puede eliminar: hay contactos en este estado.").

**Drawer de estado** (create/edit, `LeadStatusDrawer`):
```
                  ┌─────────────────────────────────────────────────┐
                  │  Nuevo estado de lead                         ✕ │
                  ├─────────────────────────────────────────────────┤
                  │  Código *        (mayúsculas, sin espacios)     │
                  │  [ EVALUANDO                                  ] │
                  │  Nombre *                                       │
                  │  [ Evaluando                                  ] │
                  │  Descripción                                    │
                  │  [ ……………………………………………………………………………………………… ]    │
                  │  Color            Orden                         │
                  │  [ #8B5CF6  ⬤ ]   [ 50 ]                        │
                  │  ☐ Estado inicial   (solo uno puede serlo)      │
                  │  ☐ Estado final (terminal)                      │
                  │  ☐ Estado ganado    (requiere "final")          │
                  │  ───────────────────────────────────────────   │
                  │  Transiciones permitidas hacia…                 │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 🔍 Buscar estados…                       │   │
                  │  │ ☑ Cita agendada                          │   │
                  │  │ ☑ Interesado                             │   │
                  │  │ ☑ No interesado                          │   │
                  │  │ ☐ Nuevo                                  │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Desde "Evaluando" un lead podrá pasar a los    │
                  │  estados marcados.                              │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Guardar ]│
                  └─────────────────────────────────────────────────┘
```

- **Validaciones (Zod + backend)**: `code` requerido (slug mayúsculas; el front sugiere mayúscula); `name` requerido; **solo un `is_initial`** por catálogo (al marcar Inicial, advertir "Reemplazará al estado inicial actual: {nombre}" si ya hay otro; el backend rechaza con `MULTIPLE_INITIAL_STATUS` si quedaran dos); **`is_won` requiere `is_final`** (al marcar Ganado, auto-marcar/forzar Final; el backend rechaza `WON_REQUIRES_FINAL`). El checkbox "Ganado" solo aparece en estados de lead (CustomerStatus no lo tiene).
- **Editor de matriz** (`StatusMatrixEditor`, embebido en el drawer): un **multiselect** ("Transiciones permitidas hacia…") con los demás estados activos del catálogo, reutilizando `SearchableOptionList` (el helper de admin/users). Al guardar, además del `PUT /crm/lead-statuses/{id}`, hace `PUT /crm/lead-statuses/{id}/transitions { to_ids: [...] }` que **reemplaza las aristas de salida** del estado. Si el estado es `is_final` (terminal), el multiselect se deshabilita con "Un estado final no tiene transiciones de salida." (coherente con la matriz seed: los finales no tienen aristas de salida).
- **Vista de grilla from×to (opcional, diferible)**: una matriz visual `from` (filas) × `to` (columnas) con checkboxes para editar todas las aristas de un vistazo. La spec §8.5 la marca **diferible**: el MVP es el multiselect por fila (dentro del drawer). Si se construye, va en una sub-vista "Ver matriz" de la pantalla de catálogo.

> **Estados/empty**: catálogo vacío "Aún no hay estados de lead. Crea el primero (marca uno como inicial)." (improbable porque el seed F2 ya carga 7+5). Loading skeletons. Error inline en el drawer.

**`/crm/estados-cliente`** es idéntico **menos** el flag "Ganado" y la columna correspondiente; matriz customer permisiva (seed §4.2). Copy: "Estados de cliente" / "Nuevo estado de cliente".

#### Componentes Fluent UI (catálogos)

| Concepto UI | Componente |
|---|---|
| Lista | `<DataTable<LeadStatusItem>>` + `useTableQuery({ queryKey: "crm:lead-statuses" })` |
| Swatch de color | `<div>` con `backgroundColor` + texto hex |
| Flags | `<Badge appearance="tint" color={...}>` "Inicial"/"Final"/"Ganado" |
| Drawer estado | `<Drawer size="medium">` con `<FormField>` + `<Input>`/`<Textarea>`/`<Switch>` |
| Color picker | `<Input>` hex + swatch (sin color-picker complejo; lista curada opcional) |
| Editor de matriz | `StatusMatrixEditor` = `SearchableOptionList` (multiselect) → `PUT /transitions` |
| Confirm delete | `<ConfirmDialog destructive>` (maneja 409 `*_STATUS_IN_USE`) |

---

### Pantalla 6 — `/crm/mis-leads` (los leads del asesor logueado)

Lista (DataTable) read-only de los leads asignados al asesor logueado (`GET /crm/me/leads/list`, gated `MY_LEADS_READ`). Molde `DoctorsClient` simplificado. Click en fila → `/crm/personas/{id}` (tab Lead o Actividad). Es la "bandeja de trabajo" del asesor (estilo "My open deals" de HubSpot).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Mis leads                                                                    │
│   Los contactos que tienes asignados como asesor.                              │
│                                              ┌────────────┐ ┌──────────────┐   │
│                                              │Lead: Todos▾│ │🔍 Buscar…    │   │
│                                              └────────────┘ └──────────────┘   │
│   ╭─ DataTable ──────────────────────────────────────────────────────────╮   │
│   │ Contacto       │ Estado lead │ Última actividad │ Próximo seguimiento │   │
│   ├────────────────┼─────────────┼──────────────────┼─────────────────────┤   │
│   │ Ana Torres     │ ●Interesado │ hace 2 h         │ mañana 10:00 ⏰      │   │
│   │ Luis Rojas     │ ●Nuevo      │ hace 1 d         │ —                   │   │
│   │ Carla Méndez   │ ●Contactado │ hace 3 h         │ hoy 17:00 ⏰ ◀      │   │
│   ╰──────────────────────────────────────────────────────────────────────╯   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Columnas**: Contacto (`full_name`), Estado lead (`StatusBadge`), Última actividad (`formatRelative`, client-only), **Próximo seguimiento** (el `FOLLOW_UP_SCHEDULED` futuro más cercano, denormalizado por el backend si está disponible; "—" si no hay; **resaltado ◀ si es hoy/vencido**, cálculo client-only).
- **Filtro Estado lead** (chip + deep-link `?lead_status_id=`), igual que la lista de Contactos pero ya pre-acotado al asesor logueado (no hay filtro de asesor — son "los míos").
- **Sin RowActions de edición** en la lista (es una bandeja); las acciones están en el detalle. Click en fila navega.
- **Estados**: empty ("No tienes leads asignados todavía. Cuando se te asigne un contacto aparecerá aquí."), loading skeletons, no-results (filtro sin matches), error global.

#### Componentes Fluent UI (mis-leads)

| Concepto UI | Componente |
|---|---|
| Header | `<h1>` + `<p>` |
| Filtro lead | `<Dropdown>` + `nuqs useQueryState("lead_status_id")` + chip |
| Tabla | `<DataTable<MyLeadItem>>` + `useTableQuery({ queryKey: "crm:my-leads", fetcher: listMyLeads, defaultSort: { field: "last_activity_at", order: "desc" } })` |
| Estado lead | `StatusBadge` |
| Fechas | `formatRelative` (client-only) |
| Navegación | `useRouter().push("/crm/personas/" + p.id)` al click en fila |

---

## Decisiones de UI (cierres)

### Detalle del Person como página con 6 tabs; creación como drawer
Misma regla-precedente de clinic/staff: entidad con sub-recursos de interacción propia (identifiers, dos máquinas de estado, timeline) → detalle en **página con tabs**; creación ligera → **drawer**. Tabs (no página única en scroll) para aislar carga y gating por permiso por superficie. El Person reusa el shell de `DoctorDetailShell`.

### `TransitionControl` — solo muestra los estados permitidos por la matriz
El dropdown de "Cambiar estado a…" se puebla **únicamente** con los estados a los que la matriz permite ir desde el estado actual (`GET /crm/lead-statuses/{currentId}/transitions`). El usuario **no puede elegir una transición inválida** (no aparece en la lista) — el backend re-valida (`LEAD_TRANSITION_NOT_ALLOWED`) como defensa en profundidad. Si el estado actual es `is_final`, el control queda deshabilitado. Esto evita el clásico CRM con dropdown de "todos los estados" que luego rebota con error. Mismo control para lead y cliente (parametrizado por familia de endpoints).

### `StatusBadge` con color del catálogo
Los badges de estado (lead/cliente) usan el `color` hex del catálogo (`LeadStatus.color`/`CustomerStatus.color`), **no** un color hardcodeado ni `brandPalette.accent` (que no existe). `StatusBadge` recibe `{ color, name }` y renderiza un `<Badge>` con `style={{ backgroundColor: color, color: contrastOn(color) }}` (texto blanco/negro según luminancia del fondo, para legibilidad). Si `color` es NULL, cae a `appearance="outline"` neutral. Consistente en lista, header del detalle, tabs Lead/Cliente, Mis leads y las tarjetas STATUS_CHANGE del timeline.

### `AssignmentControl` — reasignar + auto round-robin + "asignarme"
Un control (`<Menu>` con split-button o `<Dropdown>` + acciones) en el tab Resumen y/o header, gated `LEAD_ASSIGNMENTS_WRITE`:
- **Reasignar a…**: `<Dropdown>`/buscador de asesores (`GET /crm/advisors/active`, gated `LEAD_ASSIGNMENTS_READ`) → `PUT /crm/persons/{id}/assignment { advisor_user_id, reason? }`. Errores: `ADVISOR_NOT_ASESOR` (400, "El usuario seleccionado no es asesor.").
- **Asignarme** (atajo): asigna al user logueado → mismo `PUT` con `advisor_user_id = currentUser.id`. Útil para el asesor que "agarra" un lead sin owner.
- **Asignación automática** (round-robin): `POST /crm/persons/{id}/assignment/auto` → el backend elige el asesor con menos leads activos (`NO_ADVISOR_AVAILABLE` 400 si no hay ninguno). Botón "Asignar automáticamente".
- Si no hay asignación (`ASSIGNMENT_NOT_FOUND`), el control muestra "Sin asignar" + las tres acciones. Cada reasignación emite una `LeadActivity(REASSIGNED)` que aparece en el timeline.

### Búsqueda client-side por nombre/identificador (denormalizados)
Las columnas `full_name` (parcialmente) y `primary_identifier` son denormalizadas; el identifier **no** está en `ALLOWED_FIELDS`. Por eso la búsqueda visible de la lista es **client-side** sobre lo cargado (matchea nombre + identificador). La búsqueda global exacta de un identificador (la del bot) usa el endpoint dedicado `GET /crm/persons/search`. Lección hotfix `cd10c78` de staff: nunca ordenar/filtrar server-side por una columna denormalizada que no esté en `ALLOWED_FIELDS` (da 400) — `defaultSort`/`isSortable`/`searchFields` solo columnas reales (`full_name`, `last_activity_at`).

### Deep-links por estado/asesor
Estado lead, estado cliente, asesor y "lead activo" son `useQueryState` con chip × y deep-link (`?lead_status_id=`, `?customer_status_id=`, `?advisor_user_id=`, `?has_active_lead=`). El backend traduce los ids a `EXISTS`/JOIN (igual que staff `?branch_id=`), nunca a un filtro por texto del valor denormalizado. Permite linkear "los leads de Ana en Interesado" desde un dashboard o desde marketing futuro.

### "Hoy"/fechas relativas siempre client-only (TZ)
Toda fecha que afecte el render (agrupación del timeline, "hace 2 h", resaltado de seguimientos hoy/vencidos) se computa **client-only** (`useEffect`/`useMemo` montados en cliente, no en SSR). Se agrega un helper `formatRelative(iso)` a `lib/utils/date.ts` que **solo se usa en componentes cliente** (devuelve "hace N min/h", "ayer HH:mm", "DD mmm HH:mm", "DD mmm YYYY"). El servidor en UTC desfasaría el día en Lima (UTC-5) — bug recurrente de staff. Las fechas absolutas de auditoría siguen usando `formatDate` (no relativas, sin frontera de día).

### Sin i18n framework por ahora
Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive
Mismo criterio que clinic/staff (template optimizado para desktop interno): sidebar colapsado por default; DataTable scrollea horizontal; drawers a 100% del width en mobile. El **timeline** en pantallas angostas: las tarjetas son full-width naturalmente (apilan bien); el composer colapsa sus tabs; aceptable sin trabajo extra. La página de detalle con 6 tabs scrollea el `TabList` horizontalmente en mobile (Fluent lo soporta).

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, CSS classes) en inglés — solo los textos visibles van traducidos. Glosario clave (spec §0.4): **Lead = Lead** (masculino), **Cliente** (masculino), **Contacto** (masculino), **Asesor** (masculino), **Persona** (femenino — se evita en labels, se usa "contacto"), **Estado**, **Actividad** (femenino), **Seguimiento** (masculino), **Nota** (femenino), **Llamada** (femenino).

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Lista de Contactos — | |
| Page title | "Contactos" |
| Page subtitle | "Gestiona las personas, sus leads y clientes." |
| Botón crear | "+ Nuevo contacto" |
| Search placeholder | "Buscar por nombre o contacto…" |
| Filtro Lead (placeholder) | "Todos los estados" |
| Filtro Cliente (placeholder) | "Todos los estados" |
| Filtro Asesor (placeholder) | "Todos los asesores" |
| Toggle | "Solo con lead activo" |
| Chip filtro lead | "Lead: {nombre} ✕" |
| Chip filtro cliente | "Cliente: {nombre} ✕" |
| Chip filtro asesor | "Asesor: {nombre} ✕" |
| Columna contacto principal (vacío) | "—" |
| Columna asesor (vacío) | "Sin asignar" |
| Empty (sin contactos) | "Aún no hay contactos. Registra el primero para asignarle un lead, un asesor y empezar a registrar su actividad." |
| Empty (filtro lead sin matches) | "Ningún contacto está en este estado de lead." |
| Empty (filtro asesor sin matches) | "Este asesor no tiene contactos asignados todavía." |
| Empty (solo con lead activo) | "Ningún contacto tiene un lead activo en este momento." |
| No-results genérico | "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía." |
| Confirm delete title | "¿Eliminar contacto?" |
| Confirm delete body | "¿Eliminar al contacto '{nombre}'? Se ocultará junto con sus identificadores y estados; el historial se conserva." |
| — PersonCreateDrawer — | |
| Drawer title | "Nuevo contacto" |
| Sección 1 | "Datos de la persona" |
| Labels nombre | "Nombres" / "Apellido paterno" / "Apellido materno" |
| Labels documento | "Tipo de documento" / "N° de documento" |
| Label fecha nac. | "Fecha de nacimiento" |
| Label género | "Género" |
| Label dirección | "Dirección" |
| Label notas | "Notas" |
| Sección 2 | "Identificadores (opcional)" |
| Botón agregar identificador | "+ Agregar" |
| Hint identificadores | "Se valida que ningún identificador esté en uso por otro contacto." |
| Label canal | "Canal" |
| Label valor | "Valor" |
| Toggle principal | "Principal" |
| Error 409 (identificador tomado) | "Este identificador ya está en uso por otro contacto." |
| Botón crear / creando | "Crear" / "Creando…" |
| Botón cancelar | "Cancelar" |
| — Página de detalle — | |
| Back-link | "← Volver a contactos" |
| Tabs página | "Resumen" · "Identificadores" · "Lead" · "Cliente" · "Actividad" · "Auditoría" |
| Botón tab Resumen | "Guardar cambios" |
| — Tab Identificadores — | |
| Título | "Identificadores" |
| Botón agregar | "+ Agregar" |
| Badge principal | "Principal" |
| Badge verificado | "Verificado" |
| Acción verificar | "Verificar" |
| Hint | "El identificador principal de cada canal se usa para contactar." |
| Empty | "Este contacto aún no tiene identificadores. Agrega uno para poder contactarlo." |
| Confirm eliminar identificador | "¿Eliminar este identificador?" |
| — Tab Lead — | |
| Título estado | "Estado actual" |
| Sin lead | "Este contacto no tiene un lead activo." |
| Botón crear lead | "Crear lead" |
| Label cambiar estado | "Cambiar estado a:" |
| Botón cambiar | "Cambiar" / "Cambiando…" |
| Estado terminal | "Estado terminal — no admite cambios." |
| Label motivo | "Motivo (opcional)" |
| Botón promover | "Promover a cliente" |
| Confirm promover | "¿Promover a {nombre} a cliente? Se creará su ficha de cliente y, si el estado actual lo permite, se cerrará el lead como ganado." |
| Error ya cliente | "Este contacto ya es cliente." |
| Error sin lead inicial | "No hay un estado de lead inicial configurado. Crea uno en Estados de lead." |
| Label origen | "Origen" |
| Título historial | "Historial de estados" |
| Marca inicial | "(inicial)" |
| Actor sistema | "Sistema" |
| — Tab Cliente — | |
| Sin cliente | "Este contacto aún no es cliente." |
| Cliente desde | "cliente desde el {fecha}" |
| Título historial | "Historial de estados de cliente" |
| — Tab Actividad (Timeline) — | |
| Título | "Actividad" |
| Tabs composer | "Nota" · "Llamada" · "Seguimiento" |
| Placeholder nota | "Escribe una nota sobre este contacto…" |
| Label outcome | "Resultado" |
| Outcomes | "Exitosa" / "Sin respuesta" / "Ocupado" / "Número errado" / "No interesado" / "Interesado" |
| Label duración | "Duración (min)" |
| Label fecha seguimiento | "Programar para" |
| Label canal recordatorio | "Recordatorio por" |
| Botón registrar | "Registrar" / "Registrando…" |
| Chips de filtro | "Todos" · "Notas" · "Llamadas" · "Seguimientos" · "Estado" · "Sistema" |
| Encabezados de día | "Hoy" / "Ayer" / "{DD mmm YYYY}" |
| Badge seguimiento futuro | "◀ Próximo" |
| Tarjeta cambio estado | "{from} → {to}" |
| Tarjeta reasignado | "Asignado a {nombre}" |
| Tarjeta atribución | "Origen: {campaña}" |
| Acción marcar completado | "Marcar completado" |
| Botón cargar más | "Cargar más" |
| Empty timeline | "Sin actividad aún. Registra la primera nota, llamada o seguimiento con el panel de arriba." |
| No-results (chip) | "No hay actividades de este tipo." / "Ver todas" |
| Confirm eliminar actividad | "¿Eliminar esta actividad? Dejará de mostrarse en el timeline." |
| Error genérico timeline | "No se pudo guardar la actividad. Intenta de nuevo." |
| — AssignmentControl — | |
| Sin asignar | "Sin asignar" |
| Acción reasignar | "Reasignar a…" |
| Acción asignarme | "Asignarme" |
| Acción auto | "Asignar automáticamente" |
| Error no asesor | "El usuario seleccionado no es asesor." |
| Error sin asesor | "No hay asesores disponibles para asignar." |
| Toast reasignado | "Lead reasignado a {nombre}." |
| — Catálogos de estados — | |
| Page title (lead) | "Estados de lead" |
| Page subtitle (lead) | "Configura los estados por los que pasa un lead y sus transiciones." |
| Page title (cliente) | "Estados de cliente" |
| Page subtitle (cliente) | "Configura los estados por los que pasa un cliente y sus transiciones." |
| Botón crear | "+ Nuevo estado" |
| Drawer title (lead) | "Nuevo estado de lead" / "Editar estado de lead" |
| Drawer title (cliente) | "Nuevo estado de cliente" / "Editar estado de cliente" |
| Labels | "Código" / "Nombre" / "Descripción" / "Color" / "Orden" |
| Hint código | "Mayúsculas, sin espacios (ej. EN_TRATAMIENTO)." |
| Flag inicial | "Estado inicial" |
| Hint inicial | "Solo un estado puede ser el inicial." |
| Aviso reemplazo inicial | "Reemplazará al estado inicial actual: {nombre}." |
| Flag final | "Estado final (terminal)" |
| Flag ganado | "Estado ganado" |
| Hint ganado | "Un estado ganado debe ser también final." |
| Título matriz | "Transiciones permitidas hacia…" |
| Hint matriz | "Desde este estado un lead podrá pasar a los estados marcados." |
| Matriz deshabilitada (final) | "Un estado final no tiene transiciones de salida." |
| Empty catálogo | "Aún no hay estados. Crea el primero (marca uno como inicial)." |
| Error en uso | "No se puede eliminar: hay contactos en este estado." |
| Botón guardar / guardando | "Guardar" / "Guardando…" |
| — Mis leads — | |
| Page title | "Mis leads" |
| Page subtitle | "Los contactos que tienes asignados como asesor." |
| Columnas | "Contacto" / "Estado lead" / "Última actividad" / "Próximo seguimiento" |
| Próximo seguimiento (vacío) | "—" |
| Empty | "No tienes leads asignados todavía. Cuando se te asigne un contacto aparecerá aquí." |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Audit labels (contacto) | "Estado", "ID del contacto", "Creado el", "Creado por", "Actualizado el", "Actualizado por" |
| Status badge (estado activo/inactivo de catálogo) | "Activo" / "Inactivo" |
| Loading placeholder en inputs | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |

### Concordancia de género

- **Contacto** es **masculino**: "Nuevo contacto", "Eliminar contacto", "al contacto 'X'", "ID del contacto", "Creado el/por".
- **Lead** es **masculino**: "el lead", "un lead activo", "Crear lead", "los leads", "Lead reasignado".
- **Cliente** es **masculino**: "es cliente", "Promover a cliente", "ficha de cliente".
- **Asesor** es **masculino**: "el asesor seleccionado", "Sin asesores disponibles".
- **Actividad** es **femenino**: "la actividad", "Sin actividad", "una actividad de este tipo".
- **Nota / Llamada / Persona / Campaña** son **femenino**: "una nota", "la llamada", "la persona", "la campaña".
- **Seguimiento / Estado / Identificador / Motivo / Origen** son **masculino**: "el seguimiento", "este estado", "el identificador", "el motivo", "el origen".

### Etiquetas de canal (`ChannelType`)

`key` (slug) en inglés, etiqueta visible en español. Ícono Fluent por canal (verificar existencia en la versión instalada):

| `channel_type` | Etiqueta | Ícono Fluent (fallback) |
|---|---|---|
| `whatsapp` | "WhatsApp" | `ChatRegular` (no hay ícono de marca; usar genérico) |
| `telegram` | "Telegram" | `SendRegular` |
| `web` | "Web" | `GlobeRegular` |
| `phone` | "Teléfono" | `CallRegular` |
| `email` | "Email" | `MailRegular` |
| `instagram` | "Instagram" | `CameraRegular` |
| `facebook` | "Facebook" | `ChatRegular` |
| `other` | "Otro" | `LinkRegular` |

> No usar logos de marca (WhatsApp/Instagram/Facebook) — Fluent no los trae y meter SVGs de marca rompe la consistencia del design system. Íconos genéricos + etiqueta de texto bastan. `ChannelIcon` centraliza el mapeo `ChannelType → ícono + label`.

### Etiquetas de `ActivityType` (en tarjetas y chips)

| `activity_type` | Etiqueta de tarjeta |
|---|---|
| `NOTE` | "Nota" |
| `CALL_ATTEMPT` | "Llamada" |
| `FOLLOW_UP_SCHEDULED` | "Seguimiento programado" |
| `FOLLOW_UP_COMPLETED` | "Seguimiento completado" |
| `STATUS_CHANGE` | "Cambio de estado" |
| `REASSIGNED` | "Lead asignado" |
| `CAMPAIGN_ATTRIBUTION` | "Atribución de campaña" |
| `MESSAGE_SENT` | "Mensaje enviado" (diferido) |
| `CONVERSATION_TAKEN` | "Conversación tomada" (diferido) |
| `CONVERSATION_RELEASED` | "Conversación liberada" (diferido) |
| `APPOINTMENT_BOOKED` | "Cita agendada" (diferido) |
| `APPOINTMENT_CANCELLED` | "Cita cancelada" (diferido) |

## Mapeo a fases de implementación (checklist de UI F0–F5)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md) y la spec §10 F0–F5). Cada checkbox es una tarea de UI.

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: grupo "CRM" en `NAV_ITEMS` con 4 children (Contactos / Mis leads / Estados de lead / Estados de cliente), gate `MENU-CRM` + permiso por child; íconos Fluent verificados con fallback (`PeopleRegular`/`ContactCardRegular`/`PersonRegular`/`TagRegular`/`TagMultipleRegular`).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.CRM` (persons, identifiers, lead-statuses, customer-statuses, transitions, lead-status, customer-status, assignment, activities, me/leads, persons/search).
- [ ] `types/crm.types.ts`: todas las interfaces espejo de Pydantic (`PersonItem`, `PersonDetail`, `PersonOption`, `PersonContactIdentifier`, `LeadStatusItem`/`Option`, `CustomerStatusItem`/`Option`, `LeadStatusTransition`, `PersonLeadStatus`, `PersonCustomerStatus`, `LeadStatusHistoryItem`, `CustomerStatusHistoryItem`, `LeadAssignment`, `LeadActivityItem`, `MyLeadItem`, enums `ChannelType`/`ActivityType`/`ActivityOutcome`).
- [ ] `lib/schemas/*.schema.ts`: Zod de person, identifier, lead-status, customer-status, transition, activity (`superRefine` por tipo).
- [ ] `lib/utils/date.ts`: helper **client-only** `formatRelative(iso)` (no usar en SSR).
- [ ] Componentes compartidos stub: `StatusBadge`, `ChannelIcon`.

### F1 — Person + Identifiers
- [ ] **Pantalla 1** `/crm/personas`: lista con `DataTable` + columnas denormalizadas (NO sortable las denormalizadas; solo `full_name`/`last_activity_at`) + filtros lead/cliente/asesor/"lead activo" (chip + deep-link) + búsqueda client-side por nombre/identificador + `RowActions` (Ver/Editar/Eliminar gated) + estados empty/loading/no-results/refetching/error.
- [ ] **Pantalla 2** `PersonCreateDrawer`: identidad + identificadores iniciales (`useFieldArray`) + dedup error 409 inline.
- [ ] **Pantalla 3 (shell + tabs base)** `/crm/personas/{id}`: `PersonDetailShell` (clon de `DoctorDetailShell`) con header (back-link + título + badges) + `TabList` gateado; tabs **Resumen** (form editable + `AssignmentControl` read si aplica) · **Identificadores** (CRUD anidado) · **Auditoría** funcionales; **Lead/Cliente/Actividad** como placeholders ("Próximamente…").
- [ ] Migración backend: `0011_crm_person` (no toca UI).

### F2 — Catálogos + matriz
- [ ] **Pantalla 5** `/crm/estados-lead` y `/crm/estados-cliente`: lista (molde `VerticalsClient`) + `LeadStatusDrawer`/`CustomerStatusDrawer` (CRUD) con validación 1 inicial / won⟹final (lead) + `StatusMatrixEditor` (multiselect `SearchableOptionList` → `PUT /transitions`, deshabilitado en finales) + estados empty/error + confirm delete (409 `*_STATUS_IN_USE`).
- [ ] `StatusBadge` consume el `color` del catálogo (contraste por luminancia).
- [ ] (Diferible) vista de grilla from×to.

### F3 — Lead lifecycle + asignación + Mis leads
- [ ] **Tab Lead** (Pantalla 3): estado actual + `TransitionControl` (solo estados permitidos por la matriz, deshabilitado en terminal) + crear lead + historial (`LEAD_STATUS_HISTORY_READ`) + botón "Promover a cliente" (placeholder hasta F4 si se prefiere, o ya funcional si F4 va junto).
- [ ] `AssignmentControl` completo (reasignar / asignarme / auto round-robin) en Resumen/header, gated `LEAD_ASSIGNMENTS_WRITE`.
- [ ] **Pantalla 6** `/crm/mis-leads`: DataTable read-only de los leads del asesor (`GET /crm/me/leads/list`) + filtro lead + columna "Próximo seguimiento" resaltada (client-only) + click → detalle.
- [ ] **Tab Actividad — Iteración A** (parcial): el feed read-only ya renderiza las tarjetas de sistema que F3 emite (STATUS_CHANGE, REASSIGNED, CAMPAIGN_ATTRIBUTION) — `ActivityCard` por tipo + `DayGroup` (client-only) + "Cargar más" + estados. (El composer llega en F5.)

### F4 — Customer lifecycle
- [ ] **Tab Cliente** (Pantalla 3): estado actual + `TransitionControl` (matriz customer) + "became_customer_at" + historial; "Promover a cliente" desde el tab Lead totalmente funcional (409 `ALREADY_CUSTOMER`).

### F5 — Timeline rico + orquestación
- [ ] **Tab Actividad — Iteración B** (Pantalla 4): `ActivityComposer` con tabs Nota/Llamada/Seguimiento + `POST /activities` + Zod `superRefine` + limpiar/re-fetch + chips de filtro (re-query con `activity_type[]`, URL state).
- [ ] **Tab Actividad — Iteración C**: editar/eliminar nota inline (`PUT`/`DELETE active=false`) + "Marcar completado" en seguimientos + resaltado de seguimientos futuros (client-only) + performance (`React.memo` en `ActivityCard`, `content-visibility`, `useMemo` agrupación, sin waterfalls).
- [ ] Render de TODOS los `ActivityType` del enum (incl. los diferidos MESSAGE_SENT/CONVERSATION_*/APPOINTMENT_* — el ícono/etiqueta existen aunque no se emitan aún).
