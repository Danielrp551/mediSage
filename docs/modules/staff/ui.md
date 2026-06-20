# Módulo `staff` — UI design

> **Última actualización**: 2026-05-29
> **Audiencia**: developer implementando las pantallas de `staff` en `frontend/src/app/(main)/staff/` (y las de self-service `/me`).
> **Pre-requisito**: leer [`README.md`](README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](backend.md) (contracts) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template).

> **Alineación con clinic (módulo gold-standard ya en prod)**: `staff` reutiliza directamente los patrones que clinic dejó como precedente del template: DataTable + filtros con chip + deep-link (`OfficesClient`), drawer de creación con multi-select (`OfficeCreateDrawer` + `SearchableOptionList`), **página de detalle con tabs** (`OfficeDetailShell`), y la barra de contraseña generada del admin (`UserDrawer`). La gran diferencia es el **calendario semanal de disponibilidad** (tab Disponibilidad), que es un componente **bespoke** — Fluent UI 9 **no trae** un componente de calendario y **no usamos librería externa de calendario**. Ese calendario es la pieza de frontend más pesada y de mayor riesgo de todo el proyecto; está documentada en detalle y se construye **incrementalmente** (ver Pantalla 4).

## Decisión de arquitectura: 1 lista en sidebar + 1 página de detalle + self-service `/me`

Clinic estableció la regla: **si una entidad tiene sub-recursos con interacción propia (grids editables, calendarios, listas CRUD anidadas), su detalle va a una página dedicada con tabs; si solo tiene metadata, va a drawer.** El Doctor cae claramente en el primer caso (tiene disponibilidad = un calendario semanal pesado), así que su detalle es **página** `/staff/doctors/{id}`. La **creación** del doctor, en cambio, es ligera (cabe en un drawer), igual que `OfficeCreateDrawer`.

| Recurso | Lista | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **Doctor** | `/staff/doctors` (sidebar, filtrable por sede y/o vertical) | **drawer NESTED** (campos de user + campos de doctor + multiselect sedes + multiselect verticales) | **página** `/staff/doctors/{id}` (tabs Perfil · Disponibilidad · Auditoría) | igual molde que `OfficeDetailShell` |
| **DoctorAvailability** | — (no tiene lista propia) | dentro del tab **Disponibilidad** (calendario semanal) | dentro del tab Disponibilidad | **bespoke: grilla semanal con drag** |
| **Mi perfil / Mi agenda** (`/me`, F3) | — | — | `/me/perfil` (form self) + `/me/agenda` (mismo calendario en modo self) | reusa Perfil + el calendario en modo self |

### Por qué el detalle del Doctor es página y no drawer

Misma justificación que el Office de clinic (ver [`clinic/ui.md`](../clinic/ui.md#por-qué-el-detalle-del-office-es-página-y-no-drawer)): el sub-recurso pesado manda la forma.

| Opción | Veredicto |
|---|---|
| **A. Página dedicada `/staff/doctors/{id}` con tabs** (Perfil · Disponibilidad · Auditoría) — el calendario semanal necesita ancho completo; URL bookmarkable (`/staff/doctors/abc?tab=disponibilidad`); reusa el shell que clinic ya construyó. | **Elegida** |
| B. Drawer `size=large` con tabs | Rechazada — un calendario semanal de 7 columnas × ~32 filas no cabe en ~640 px; los popovers de edición de bloque sobre el overlay del drawer = z-index frágil; el calendario tiene su propio modo de guardado (bulk POST al soltar) que no encaja en el footer único del drawer. |
| C. Modal full-screen | Rechazada — cero precedente, pierde la URL. |
| D. Acordeón inline en la lista | Rechazada — no escala a un calendario. |

**El Doctor reusa literalmente el patrón de `OfficeDetailShell`** (header con back-link + nombre + badge estado + `TabList` sincronizado con `?tab=` via `nuqs` + gating por permisos por tab). No reinventamos el shell: lo clonamos como `DoctorDetailShell`.

> ⚠ La **creación** del doctor vive en un drawer desde la lista (`DoctorCreateDrawer`); **ver/editar** un doctor existente **navega** a su página de detalle. Crear es ligero (cabe en drawer); editar el perfil + administrar la disponibilidad necesitan la página.

## Sidebar — extensión de `NAV_ITEMS`

> ⚠ **Textos UI en español**. `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un parent item `staff` con 1 child, entre `clinic` y `admin` (el self-service NO va al sidebar de admin; ver nota):

```ts
{
  key: "staff",
  label: "Staff",
  icon: "PersonStethoscopeRegular",     // si no existe en la versión de Fluent, usar "PeopleTeamRegular"
  children: [
    { key: "doctors", label: "Doctores", icon: "DoctorRegular", url: "/staff/doctors", permissions: ["MENU-STAFF"] },
  ],
},
```

> El único child usa `MENU-STAFF` como gate de visibilidad (sidebar). Los permisos finos (`DOCTORS_READ`, `DOCTORS_CREATE`, `DOCTOR_AVAILABILITY_READ/WRITE`, etc.) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>` / `usePermissions()`. La **página de detalle** del doctor no tiene entrada propia en el sidebar — se llega navegando desde la lista.

> **Self-service `/me` (F3)**: las pantallas "Mi perfil" y "Mi agenda" se gatean con `MY_DOCTOR_PROFILE_READ` / `MY_AVAILABILITY_READ` (que **solo** tiene el role DOCTOR, no el ASESOR). Decisión de UX: en F3 se agregan como un grupo de menú aparte **"Mi cuenta"** → "Mi perfil", "Mi agenda" (o bajo el avatar del TopBar). No se mezclan con "Staff → Doctores" porque conceptualmente son "lo mío" vs "administrar a otros". Detalle en Pantalla 5.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error) + tabla de componentes Fluent.

1. `/staff/doctors` — lista (DataTable + filtros sede/vertical con chip + deep-link).
2. `DoctorCreateDrawer` — creación NESTED (user + doctor + sedes + verticales).
3. `/staff/doctors/{id}` — página de detalle con tabs (Perfil · Disponibilidad · Auditoría).
4. **Tab Disponibilidad** — el calendario semanal bespoke (la pieza central).
5. `/me/perfil` + `/me/agenda` — self-service (F3).

---

### Pantalla 1 — `/staff/doctors` (lista)

Misma estructura que `OfficesClient`, con **dos filtros** (sede y vertical), ambos deep-linkables (`?branch_id=`, `?vertical_id=`) con chip y ×, espejando exactamente el patrón de `OfficesClient`.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                    │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │ TopBar                                                   │ │
│ │            │ ├──────────────────────────────────────────────────────────┤ │
│ │ ▸ Inicio   │ │   Doctores                                               │ │
│ │ ▸ Catálogo │ │   Gestiona los doctores y su disponibilidad.             │ │
│ │ ▸ Clínica  │ │                                                          │ │
│ │ ▾ Staff    │ │   ┌─────────────┐ ┌─────────────┐ ┌────────────┐ ┌─────┐ │ │
│ │   • Doctor█│ │   │ Sede: Todas▾│ │ Vert.: Todo▾│ │🔍 Buscar…  │ │+ Doc│ │ │
│ │ ▸ Admin    │ │   └─────────────┘ └─────────────┘ └────────────┘ └─────┘ │ │
│ │            │ │   ┌──────────────────────┐ ┌──────────────────────┐      │ │
│ │            │ │   │ Sede: Sede Lima C.  ✕│ │ Vertical: Estética  ✕│ ←chips│ │
│ │            │ │   └──────────────────────┘ └──────────────────────┘      │ │
│ │            │ │   ╭─ DataTable ──────────────────────────────────────╮  │ │
│ │            │ │   │ ⋯ │ Nombre        │ Correo       │ CMP   │Slot│Sed│Ver│Est│  │ │
│ │            │ │   ├───┼───────────────┼──────────────┼───────┼────┼───┼───┼───┤  │ │
│ │            │ │   │ ⋯ │ Dra. Ana Pérez│ ana@medi.pe  │ 54321 │30m │ 2 │ 3 │Act│  │ │
│ │            │ │   │ ⋯ │ Dr. Juan Díaz │ juan@medi.pe │ 12987 │20m │ 1 │ 1 │Act│  │ │
│ │            │ │   │ ⋯ │ Dr. Luis Soto │ luis@medi.pe │  —    │30m │ 3 │ 2 │Des│  │ │
│ │            │ │   ├──────────────────────────────────────────────────┤  │ │
│ │            │ │   │ Mostrando 1–3 de 3      ‹  Página 1 de 1  ›      │  │ │
│ │            │ │   ╰──────────────────────────────────────────────────╯  │ │
│ └────────────┘ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas de la tabla** (`key` en inglés, coherente con `ALLOWED_FIELDS` del backend; `header` visible en español). Mapean 1:1 a `DoctorItem` (ver [`backend.md`](backend.md#doctoritem) y la spec):

| `key` | Header | Tipo | min/max | Sortable | Render |
|---|---|---|---|---|---|
| `actions` | `""` (sin header) | RowActions | 48–56 | — | menú `…` con Ver / Editar / Eliminar (gated por permisos) |
| `full_name` | Nombre | text (truncate) | 220 | ✅ | nombre completo (denormalizado del User) |
| `email` | Correo | text (truncate) | 240 | ✅ | correo (denormalizado del User) |
| `cmp_code` | CMP | text | 120 | ✅ | `cmp_code` o "—" si NULL |
| `slot_duration_min` | Slot | numeric | 90 | ✅ | derecha, tabular-nums, sufijo "min" (ej. "30 min") |
| `branches_count` | Sedes | numeric | 90 | ✅ | derecha, tabular-nums (denormalizado batch, mirror de `offices_count`) |
| `verticals_count` | Verticales | numeric | 110 | ✅ | derecha, tabular-nums (mirror de `verticals_count` de office) |
| `active` | Estado | badge | 100 | — | "Activo" (success) / "Deshabilitado" (informative) |
| `updated_on` | Última actualización | date | 180 | ✅ | `formatDate(...)` |

> `branches_count` / `verticals_count` son denormalizaciones hidratadas por **batch** en el listado (mismo patrón que `office.verticals_count`). NO unimos a las M:N por fila. Ver [`backend.md`](backend.md#doctoritem). `full_name` / `email` se denormalizan del User para evitar el join contra `user` en la tabla (lo dice la spec).

**RowActions** (gated por `usePermissions()`, mismo patrón que `OfficesClient`):
- 👁 **Ver** — siempre visible (asume `DOCTORS_READ`). **Navega** a `/staff/doctors/{id}` (no abre drawer).
- ✏ **Editar** — gated `DOCTORS_UPDATE`. **Navega** a `/staff/doctors/{id}?tab=perfil`.
- 🗑 **Eliminar** — gated `DOCTORS_DELETE`. Confirm dialog. **Nota importante**: el soft-delete del doctor **NO** borra ni desactiva el `User` (ADR-002) — el copy del confirm lo aclara (ver tabla de copy).

**Botón "+ Nuevo doctor"**: gated `<PermissionGuard anyOf={["DOCTORS_CREATE"]}>`. Abre `DoctorCreateDrawer`.

**Filtros (Dropdown + chip + deep-link)** — espejo exacto de `OfficesClient`:
- **Filtro Sede**: opciones de `GET /clinic/branches/active` → `BranchOption[]`. `null` = "Todas las sedes". Sincronizado con `?branch_id=X` via `nuqs useQueryState`. Chip "Sede: {nombre} ✕". Fallback de nombre si la sede no está en la lista activa: igual que `OfficesClient`, usar el nombre que venga en las filas si existiera (en doctores no tenemos `branch_name` por fila, así que el fallback es mostrar el id crudo solo en el caso degenerado — preferir mantener el nombre del dropdown).
- **Filtro Vertical**: opciones de `GET /catalog/verticals/active` → `VerticalOption[]`. `null` = "Todas las verticales". Sincronizado con `?vertical_id=X`. Chip "Vertical: {nombre} ✕".
- Ambos filtros se traducen a `extraFilters` para `useTableQuery`, **o** se pasan como query params al endpoint `/doctors/list` según cómo el backend resuelva el filtro M:N. La spec define `GET /doctors/active?branch_id=&vertical_id=` para dropdowns; para la **lista paginada** el filtro por M:N lo resuelve el `POST /doctors/list` (ver [`backend.md`](backend.md#filtrado-por-mn)). En la UI ambos son `useQueryState` + chip, igual que la sede en offices.

> Deep-link de entrada: desde la futura lista de sedes o desde scheduling se podrá llegar con `/staff/doctors?branch_id=X` y el chip aparece pre-poblado (igual que "Ver N consultorios" en clinic).

#### Estados

**Empty (no hay doctores aún, sin filtro)**:
```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                          🩺  (DoctorRegular)                                 │
│                                                                              │
│                          Aún no hay doctores                                 │
│        Registra el primer doctor para asignarle sedes, verticales            │
│        y su disponibilidad de atención.                                      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

> Usa `<EmptyState icon title message>` del `DataTable`. El botón "Nuevo doctor" del toolbar cumple la función (no va dentro del EmptyState — consistencia con catalog/clinic).

**Empty con filtro de sede sin doctores**: "Esta sede aún no tiene doctores asignados."
**Empty con filtro de vertical sin doctores**: "Ningún doctor cubre esta vertical todavía."

**Loading (primera carga)**: DataTable con 6 skeleton rows; toolbar normal; sin spinner extra (el server-prefetch del `page.tsx` evita ver esto en el primer load).

**No-results (search activo sin matches)**: variante automática de `DataTable` cuando `isFiltered={search.length > 0 || branchFilter !== null || verticalFilter !== null}` → "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía."

**Refetching (background)**: tabla con `opacity: 0.55` + spinner pequeño top-right (overlay `shadow4`). Igual que clinic.

**Error (5xx)**: capturado por `error.tsx` global. Soft-errors (ej. 409 al crear con email tomado) se muestran inline en el drawer (ver Pantalla 2).

#### Componentes Fluent UI / del template

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Sidebar | `Sidebar` (auto-renderiza `NAV_ITEMS` filtrados por permisos) |
| Header | `<h1 className={styles.title}>` + `<p className={styles.subtitle}>` |
| Filtro Sede / Vertical | `<Dropdown>` + `nuqs useQueryState("branch_id"/"vertical_id")` (patrón `OfficesClient`) |
| Chip filtro | `styles.chip` + `<Button icon={<DismissRegular />} />` (patrón `OfficesClient`) |
| Search | `<Input contentBefore={<SearchRegular />} />` |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Permission gate | `<PermissionGuard anyOf={["DOCTORS_CREATE"]}>` |
| Tabla | `<DataTable<DoctorItem> columns={...} ...>` con `useTableQuery({ queryKey: "staff:doctors", ... })` |
| Badge active | `<Badge appearance="filled" color={d.active ? 'success' : 'informative'}>` |
| Navegación a detalle | `useRouter().push("/staff/doctors/" + d.id)` desde RowActions / fila |
| Row menu | `<RowActions item={d} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive ... />` |
| Drawer create | `<DoctorCreateDrawer branches verticals defaultBranchId defaultVerticalId>` (custom) |

---

### Pantalla 2 — `DoctorCreateDrawer` (creación NESTED)

Drawer del template (`<Drawer size="medium">`), **solo modo create** (ver/editar viven en la página de detalle). Es el caso más rico de creación del proyecto porque crea **dos entidades en una transacción**: el `User` (con role DOCTOR) **y** el `Doctor`, más las dos M:N. El payload es **anidado** (`DoctorCreate { user: DoctorUserCreate, cmp_code?, bio?, …, branch_ids, vertical_ids }`, ver spec). Tabs para no saturar: `Cuenta` (campos del user) · `Perfil` (campos del doctor) · `Asignaciones` (sedes + verticales).

```
                  ┌─────────────────────────────────────────────────┐
                  │  Nuevo doctor                                 ✕ │
                  ├─────────────────────────────────────────────────┤
                  │  ╭─[ Cuenta ][ Perfil ][ Asignaciones ]───────╮ │
                  │                                                 │
                  │  [Tab Cuenta]  — crea el User                   │
                  │                                                 │
                  │  Correo *                                       │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ ana@medisage.pe                          │   │
                  │  └─────────────────────────────────────────┘   │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Nombres *        │  │ Apellido paterno*│    │
                  │  │ Ana              │  │ Pérez            │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Apellido materno                               │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Gómez                                    │   │
                  │  └─────────────────────────────────────────┘   │
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ Tipo de doc.    ▾│  │ N° de documento  │    │
                  │  │ DNI              │  │ 45678912         │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Teléfono                                       │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ +51 …                                    │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Contraseña                                     │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │                          (opcional)      │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Si la dejas vacía, se genera una temporal.    │
                  │                                                 │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Crear ]  │
                  └─────────────────────────────────────────────────┘
```

**Tab `Perfil`** (campos del `Doctor`):
```
                  │  ┌──────────────────┐  ┌──────────────────┐    │
                  │  │ CMP              │  │ Duración slot *  │    │
                  │  │ 54321            │  │ 30 min        ▾  │    │
                  │  └──────────────────┘  └──────────────────┘    │
                  │  Colegiatura (opcional para no-médicos).       │
                  │                                                 │
                  │  Biografía                                      │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Dermatóloga con 10 años de experiencia… │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Texto público que el bot puede leer al lead.  │
                  │                                                 │
                  │  Foto (URL)                                     │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ https://…/ana.jpg                        │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Firma (URL)                                    │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ https://…/firma-ana.png                  │   │
                  │  └─────────────────────────────────────────┘   │
```

**Tab `Asignaciones`** (las dos M:N, ambas con `SearchableOptionList` reutilizado):
```
                  │  Sedes *                       (2 de 4)        │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 🔍 Buscar sedes…                        │   │
                  │  ├─────────────────────────────────────────┤   │
                  │  │ ☑ Sede Lima Centro                      │   │
                  │  │ ☑ Sede Trujillo                         │   │
                  │  │ ☐ Sede Arequipa                         │   │
                  │  │ ☐ Sede Cusco                            │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Sedes donde el doctor atiende.                │
                  │                                                 │
                  │  Verticales *                  (3 de 6)        │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 🔍 Buscar verticales…                   │   │
                  │  ├─────────────────────────────────────────┤   │
                  │  │ ☑ Estética facial                       │   │
                  │  │ ☑ Dermatología clínica                  │   │
                  │  │ ☑ Dental                                │   │
                  │  │ ☐ Pediatría                             │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Verticales que el doctor cubre.               │
```

**Barra de contraseña generada** (idéntica a `UserDrawer` del admin): tras crear, si el backend devolvió `generated_password` (porque el campo Contraseña quedó vacío), se muestra un `<MessageBar intent="info">` **dentro del drawer** y el drawer **no se cierra** hasta que el admin la copia:

```
                  ├─────────────────────────────────────────────────┤
                  │  ℹ Doctor creado. Contraseña temporal           │
                  │    (cópiala ahora — no se mostrará otra vez):   │
                  │    [ Kx9$mP2vQ ]  📋                            │
                  └─────────────────────────────────────────────────┘
```

> Esto replica el flujo exacto de `UserDrawer.onSubmit`: si `mode === "create"` y `result.data.generated_password` viene, `setGeneratedPassword(pwd)` y **return** (no `onClose()`). La spec lo confirma: `DoctorCreatedResponse { data: DoctorDetail, generated_password: str | None }` es el espejo de `UserCreatedResponse`.

**Campos y validación (Zod, `staffDoctorCreateSchema`)** — espejo de `DoctorCreate` + `DoctorUserCreate`:
- `user.email` requerido, formato correo. Conflicto se maneja como 409 `EMAIL_TAKEN` (ver estados).
- `user.first_name`, `user.last_name` requeridos. `user.second_last_name` opcional.
- `user.document_type` (Dropdown con la misma lista que `UserDrawer`: DNI/CE/PASSPORT…) + `user.document_number` (con `DOCUMENT_RULES` por tipo, igual que admin); opcionales.
- `user.phone` opcional.
- `user.password` **opcional** → si falta, el backend genera una temporal (igual que `admin.user.create`). Hint: "Si la dejas vacía, se genera una temporal."
- `cmp_code` opcional (hint "Colegiatura (opcional para no-médicos)."), `bio` opcional, `photo_url` / `signature_url` opcionales (URL válida si presentes), `slot_duration_min` requerido default 30.
- `branch_ids.length >= 1` ("Selecciona al menos una sede."), `vertical_ids.length >= 1` ("Selecciona al menos una vertical.").

**Duración de slot (Dropdown curado)**: lista cerrada `[15, 20, 30, 45, 60]` min etiquetada "15 min"…"60 min" (mismo rationale que el timezone dropdown de clinic: evita valores arbitrarios; el grano del calendario y de scheduling). Default 30.

**Sedes / Verticales (multi-select)**: reutilizan **`SearchableOptionList`** (el helper de `admin/users/_components` que selecciona roles/permisos, ya reutilizado por `OfficeCreateDrawer`). Opciones de `GET /clinic/branches/active` y `GET /catalog/verticals/active` mapeadas a `{ id, primary: name }`. Pre-selección opcional con `defaultBranchId` / `defaultVerticalId` (los filtros activos de la lista, igual que `OfficeCreateDrawer` recibe `defaultBranchId`).

**Modo del drawer**: solo `create`. Título "Nuevo doctor". Footer `[ Cancelar ] [ Crear ]` (`Creando…` en pending). NO hay tab Auditoría (eso vive en la página de detalle).

#### Estados de error / loading

- **Guardando**: footer `[ Creando… ]` disabled; fields disabled (patrón `useTransition` de `UserDrawer`).
- **Error 409 (`EMAIL_TAKEN`)**: `<MessageBar intent="error">` arriba del form con el `detail` (en español, del backend); el campo `user.email` (tab Cuenta) queda con error inline. Si el error es del email, **abrir la tab Cuenta** automáticamente para que el campo sea visible.
- **Error 400 (`branch_ids`/`vertical_ids` con ids inexistentes/muertos)**: improbable porque la lista activa solo trae vivos, pero si llega, MessageBar con el `detail`.
- **Error 422 (validation drift)**: improbable (mismo Zod). Mostrar `detail` genérico + loguear.
- **Error de red**: `<MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.

#### Componentes Fluent UI

| Concepto UI | Componente |
|---|---|
| Drawer | `<Drawer size="medium">` (del template) |
| Tabs en drawer | `<TabList><Tab value="cuenta">…</Tab></TabList>` (patrón `UserDrawer`) |
| Campos | `<FormField>` + `<Input>` / `<Textarea>` (bio) vía `Controller` (react-hook-form) |
| Tipo de documento | `<Dropdown>` con `DOCUMENT_TYPES` (reusado de `UserDrawer`) |
| Duración slot | `<Dropdown>` con lista curada `[15,20,30,45,60]` |
| Dos columnas | `styles.twoCol` (grid `1fr 1fr`) |
| Multi-select sedes / verticales | `SearchableOptionList` (reutilizado de `UserDrawer`) |
| Barra contraseña generada | `<MessageBar intent="info">` con `<code>{generatedPassword}</code>` (patrón `UserDrawer`) |
| Inline error 409 | `<MessageBar intent="error">` arriba del form |

---

### Pantalla 3 — `/staff/doctors/{id}` (página de detalle con tabs)

Página dedicada (RSC `page.tsx` que prefetcha el doctor + sus opciones de sedes/verticales, luego un client `DoctorDetailShell`). **Clon directo de `OfficeDetailShell`**. 3 tabs: `Perfil` · `Disponibilidad` · `Auditoría`. La tab activa se sincroniza con la URL (`?tab=disponibilidad`).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Volver a doctores                                                           │
│                                                                              │
│ Dra. Ana Pérez                                                  [Activo]      │
│ ana@medisage.pe · CMP 54321 · Slot 30 min                                    │
│                                                                              │
│ ╭─[ Perfil ][ Disponibilidad ][ Auditoría ]────────────────────────────────╮ │
│ │                                                                          │ │
│ │ ...contenido de la tab activa...                                         │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Header de la página** (idéntico al de `OfficeDetailShell`):
- `← Volver a doctores` (`<Link href="/staff/doctors">` con `ArrowLeftRegular`). MVP: link plano (igual que clinic; no preservamos el `?branch_id` de la lista).
- Título = `doctor.full_name`; badge de estado al lado ("Activo" / "Deshabilitado", masculino).
- Subtítulo = `{email} · CMP {cmp_code} · Slot {slot_duration_min} min` (omitir piezas NULL — ej. sin CMP el segmento desaparece).

**Resolución de tab + permisos por tab** (misma lógica `allowed[tab]` de `OfficeDetailShell`):
- `Perfil` — `DOCTORS_READ` (ver) / `DOCTORS_UPDATE` (editar). Siempre visible.
- `Disponibilidad` — `DOCTOR_AVAILABILITY_READ` (ver) / `DOCTOR_AVAILABILITY_WRITE` (editar). Si el user no tiene `DOCTOR_AVAILABILITY_READ`, la tab **no se renderiza** (ej. un ASESOR sí la ve en read-only porque tiene `DOCTOR_AVAILABILITY_READ`).
- `Auditoría` — `DOCTORS_READ`.
- Fallback: si la URL apunta a una tab no permitida o desconocida, cae a `perfil` (igual que `OfficeDetailShell` cae a `details`).

#### Tab `Perfil`

Form embebido en la tab (no drawer) con su propio botón "Guardar cambios", igual que `OfficeDetailsTab`. Envía `DoctorUpdate`. Reglas de editabilidad:
- **Solo-lectura** (vienen del User, NO editables aquí — la spec dice que el `/me/doctor` y el admin de usuarios manejan al User; `staff` no muta el User salvo en la creación nested): `Correo`, `Nombres`, `Apellidos`. Se muestran disabled con un hint "Estos datos se editan en Administración → Usuarios."
- **Editables** (campos del Doctor): `cmp_code`, `bio`, `photo_url`, `signature_url`, `slot_duration_min`, multiselect **sedes** (`branch_ids` → replace total de la M:N), multiselect **verticales** (`vertical_ids` → replace total), y `active` (Switch).
- **Inmutable**: `user_id` (no se muestra como editable; aparece como referencia en Auditoría).

```
│ │ Correo (solo lectura)            Nombre (solo lectura)                    │ │
│ │ ┌─────────────────────────┐    ┌─────────────────────────┐               │ │
│ │ │ ana@medisage.pe     (—) │    │ Ana Pérez Gómez     (—) │               │ │
│ │ └─────────────────────────┘    └─────────────────────────┘               │ │
│ │ Estos datos se editan en Administración → Usuarios.                       │ │
│ │                                                                          │ │
│ │ CMP                    Duración de slot                                   │ │
│ │ ┌─────────────┐        ┌─────────────┐                                    │ │
│ │ │ 54321       │        │ 30 min    ▾ │                                    │ │
│ │ └─────────────┘        └─────────────┘                                    │ │
│ │                                                                          │ │
│ │ Biografía                                                                 │ │
│ │ ┌──────────────────────────────────────────────────────────────────┐    │ │
│ │ │ Dermatóloga con 10 años de experiencia…                          │    │ │
│ │ └──────────────────────────────────────────────────────────────────┘    │ │
│ │                                                                          │ │
│ │ Foto (URL)                       Firma (URL)                              │ │
│ │ ┌─────────────────────────┐    ┌─────────────────────────┐               │ │
│ │ │ https://…/ana.jpg       │    │ https://…/firma-ana.png │               │ │
│ │ └─────────────────────────┘    └─────────────────────────┘               │ │
│ │                                                                          │ │
│ │ Sedes *               (2 de 4)   Verticales *          (3 de 6)           │ │
│ │ ┌─────────────────────────┐    ┌─────────────────────────┐               │ │
│ │ │ 🔍 Buscar sedes…        │    │ 🔍 Buscar verticales…   │               │ │
│ │ │ ☑ Sede Lima Centro      │    │ ☑ Estética facial       │               │ │
│ │ │ ☑ Sede Trujillo         │    │ ☑ Dermatología clínica  │               │ │
│ │ │ ☐ Sede Arequipa         │    │ ☑ Dental  ☐ Pediatría   │               │ │
│ │ └─────────────────────────┘    └─────────────────────────┘               │ │
│ │                                                                          │ │
│ │ ☑ Activo                                              [ Guardar cambios ] │ │
```

> Si el user solo tiene `DOCTORS_READ` (no `DOCTORS_UPDATE`), todos los campos quedan disabled y el botón "Guardar cambios" no se renderiza (read-only), igual que clinic gatea por `OFFICE_HOURS_WRITE`.

**Validación / estados** (mismo molde que `OfficeDetailsTab`):
- Zod `staffDoctorUpdateSchema`: `branch_ids.length >= 1`, `vertical_ids.length >= 1`, urls válidas si presentes.
- **Guardando**: `[ Guardando… ]` disabled.
- **Error**: `<MessageBar intent="error">` arriba del form con el `detail` del backend.
- **Loading inicial**: el `page.tsx` prefetcha el `DoctorDetail`, así que el form arranca poblado; si se re-fetcha, fields disabled con placeholder "Cargando…".

#### Tab `Disponibilidad`

→ Ver **Pantalla 4** (es la pieza central, documentada aparte). En F1 esta tab es un **placeholder** ("Próximamente: calendario de disponibilidad"), exactamente como clinic dejó Horarios/Excepciones como placeholder en F2 hasta F3/F4.

#### Tab `Auditoría`

Idéntica estructura al `AuditTab` de `UserDrawer` / `OfficeAuditTab`: grid de Estado · ID del doctor · Creado el/por · Actualizado el/por. Concordancia **masculina** (Doctor = masculino): "Creado el", "Creado por", "Actualizado el", "Actualizado por". Además muestra el **`user_id`** vinculado (referencia inmutable) y, opcionalmente, un link "Ver usuario en Administración" si el viewer tiene `MENU-ADMIN-USERS`.

#### Componentes Fluent UI (página de detalle)

| Concepto UI | Componente |
|---|---|
| Shell (back-link + título + badge + tabs) | `DoctorDetailShell` — clon de `OfficeDetailShell` |
| Volver | `<Link href="/staff/doctors">` + `<ArrowLeftRegular />` |
| Tabs de la página | `<TabList>` + `nuqs useQueryState("tab")` con `allowed[tab]` gating |
| Form Perfil | `<FormField>` + `<Input>` / `<Textarea>` / `<Dropdown>` (slot) + `SearchableOptionList` ×2 + `<Switch>` |
| Guardar Perfil | `<Button appearance="primary">` único → `updateDoctor(id, payload)` |
| Auditoría | grid `styles.audit` (reusado de `UserDrawer`/`OfficeAuditTab`) |

---

### Pantalla 4 — Tab `Disponibilidad`: el CALENDARIO SEMANAL (la pieza central)

> **HONESTIDAD (binding por la spec)**: este calendario es **custom / bespoke**. Fluent UI 9 **NO trae** un componente de calendario tipo agenda; lo único cercano es `@fluentui/react-datepicker-compat` (solo elige una fecha, no es una grilla de agenda). **NO usamos ninguna librería de calendario externa** (FullCalendar, react-big-calendar, etc.) — todo se construye con primitivos de Fluent (`Button`, `Input`, `Spinner`, `MessageBar`, `Tooltip`, `Popover`/`Dialog`) y **tokens del design system** (`tokens.*`, `appTokens.*`, `makeStyles`). Es el **componente de frontend más pesado y de mayor riesgo de todo el proyecto**. Por eso se construye **incrementalmente** (ver "Plan incremental" al final de esta pantalla). No subestimar: la grilla, el hit-testing de celdas, el drag, la validación de solapamiento en vivo y el bulk POST son trabajo real.

A diferencia del modelo viejo del overview (`staff.md`, patrón semanal recurrente + overrides), el modelo nuevo (spec) es **bloques concretos por fecha** (`DoctorAvailability`: `date` + `opens_at` + `closes_at`, sin `day_of_week`, sin recurrencia, sin `is_available`). Por eso el calendario muestra **una semana real con fechas**, no un patrón abstracto Lun–Dom.

#### Vista semana — mockup

```
│ │  Disponibilidad                                                            │ │
│ │  Consultorio: ┌──────────────────────────────┐  ‹  Sem. 1–7 jul 2026  ›  │ │
│ │              │ Sede Lima C. · C-03 (Dental)▾│  [ Hoy ]  [ 📅 Ir a… ]      │ │
│ │              └──────────────────────────────┘   ●color del consultorio    │ │
│ │  ┌────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐            │ │
│ │  │    │ Lun 1 │ Mar 2 │ Mié 3 │ Jue 4 │ Vie 5 │ Sáb 6 │ Dom 7 │            │ │
│ │  ├────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤            │ │
│ │  │06:00│      │       │       │       │       │░░░░░░░│       │            │ │
│ │  │06:30│      │       │       │       │       │░cerr.░│       │            │ │
│ │  │07:00│░░░░░░│░░░░░░░│░░░░░░░│░░░░░░░│░░░░░░░│░░░░░░░│       │ ← banda     │ │
│ │  │07:30│░░░░░░│░░░░░░░│░░░░░░░│░░░░░░░│░░░░░░░│░░░░░░░│       │  horario    │ │
│ │  │08:00│▓▓▓▓▓▓│       │▓▓▓▓▓▓▓│       │▓▓▓▓▓▓▓│       │       │  office     │ │
│ │  │08:30│▓08:00│       │▓08:00 │       │▓08:00 │       │       │  (tenue)    │ │
│ │  │09:00│▓13:00│▓▓▓▓▓▓▓│▓13:00 │▓▓▓▓▓▓▓│▓13:00 │       │       │            │ │
│ │  │09:30│▓bloq.│▓09:00 │▓bloq. │▓09:00 │▓bloq. │       │       │ ▓=bloque   │ │
│ │  │ …  │      │▓18:00 │       │▓18:00 │       │       │       │  del doctor│ │
│ │  │13:00│      │▓bloq. │       │▓bloq. │       │       │       │            │ │
│ │  │ …  │      │       │       │       │       │       │       │            │ │
│ │  │16:00│▓▓▓▓▓▓│       │       │       │       │       │       │            │ │
│ │  │ …  │▓16:00│       │       │       │       │       │       │            │ │
│ │  │20:00│▓20:00│       │       │       │       │       │       │            │ │
│ │  │22:00│      │       │       │       │       │       │       │            │ │
│ │  └────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘            │ │
│ │  [ + Agregar disponibilidad ]   (form alterno multi-día)                  │ │
│ │  Sin disponibilidad guardada para esta semana en este consultorio.        │ │
```

**Anatomía de la grilla**:
- **Columnas** = Lun … Dom de la semana visible, **con su fecha real** ("Lun 1", "Mar 2", …). El header muestra el rango ("Sem. 1–7 jul 2026"). Convención de inicio de semana = lunes (coherente con `DAY_LABELS` / `WEEKDAY_LABELS` Python 0=Lun ya existentes en `lib/constants/`). La columna del **día de hoy** se resalta sutilmente.
- **Filas** = horas, rango configurable (default **06:00–22:00**), paso = `doctor.slot_duration_min` (30 por default; cae a 60 si el slot es 60). El paso del grid se deriva del slot del doctor para que un bloque encaje en N celdas enteras.
- **Banda de horario del office** (`░`, fondo tenue): para el `office` seleccionado, su `OfficeOperatingHours` del weekday correspondiente se pinta como **guía de fondo** (read-only). Es solo orientación — la spec (invariante #4) aclara que NO se valida como hard-block en staff: scheduling intersecta después, así que pintar fuera de la banda está permitido (se marca visualmente "fuera de horario", no se bloquea).
- **Franjas/días de cierre** (`▒` hachurado): los `OfficeClosure` del office en esa fecha se pintan hachurados (read-only, vienen de clinic). No editables aquí.
- **Bloques del doctor** (`▓`, color sólido): cada `DoctorAvailability` ocupa de `opens_at` a `closes_at` en su columna-fecha, etiquetado con sus horas. **Color por consultorio**: un selector de office arriba define el office activo; cada office tiene un color estable (paleta de tokens) para distinguir, si en el futuro se superponen offices, de quién es cada bloque. En MVP se muestra un office a la vez (el seleccionado).

**Selector de consultorio (arriba)**: `<Dropdown>` con los `(branch, office)` donde el doctor puede atender. Las opciones se derivan de: las **sedes del doctor** (`doctor.branches`) × los **offices de cada sede** (`GET /clinic/offices/active?branch_id=`). Cada opción muestra "Sede X · C-03 (Nombre)". Al pintar un bloque nuevo, se crea para **ese (branch_id, office_id)**. El office activo también determina qué banda de horario y qué cierres se muestran de fondo.

> Por qué hace falta elegir office para crear: el modelo (spec) exige `branch_id` + `office_id` en cada `DoctorAvailability`, y los invariantes de backend validan que el office pertenezca al branch (#1) y que el doctor esté asignado al branch (#2). El dropdown solo ofrece combinaciones válidas → el usuario no puede elegir un office fuera de sus sedes.

**Navegación temporal**:
- `‹` / `›` mueven una semana atrás/adelante (re-fetch del rango `from`/`to`).
- `[ Hoy ]` salta a la semana actual.
- `[ 📅 Ir a… ]` abre un `DatePicker` (`@fluentui/react-datepicker-compat`) para saltar a la semana que contiene una fecha dada.
- El rango visible (`from` = lunes, `to` = domingo) se mantiene en URL state (`?from=YYYY-MM-DD`) para que sea bookmarkable y sobreviva refresh (mismo espíritu que clinic `?tab=` y filtros).
- Fetch: `GET /doctors/{id}/availability?from=&to=` (admin) — devuelve `SingleResponse[list[DoctorAvailabilityItem]]` con los bloques cuya `date` cae en `from..to`. En self-mode: `GET /me/availability?from=&to=`.

#### Interacciones (en orden de prioridad de construcción)

1. **Click en celda vacía → crear bloque** (prioridad 1):
   - Click en una celda vacía abre un mini-form (Popover/Dialog anclado) pre-poblado con `date` = la fecha de la columna, `opens_at` = la hora de la fila, `closes_at` = `opens_at + slot_duration_min`, `branch_id`/`office_id` = el office activo. El usuario ajusta horas y confirma.
   - Persistencia: `POST /doctors/{id}/availability` con body `DoctorAvailabilityBulkCreate { blocks: [ <el bloque> ] }` (el endpoint es siempre bulk; un bloque suelto es una lista de 1). Tras éxito, revalidar y re-render.

2. **Click en bloque existente → editar / borrar** (prioridad 1):
   - Click en un `▓` lo selecciona → Popover con los inputs `opens_at` / `closes_at` (Fluent `Input type="time"`), botón **Guardar** (`PUT /doctors/{id}/availability/{block_id}` con `DoctorAvailabilityUpdate`) y botón **Eliminar** (`DELETE /doctors/{id}/availability/{block_id}` → 204, con confirm).
   - Mover/redimensionar un bloque editando sus horas es un `PUT` (la spec lo describe como "mover/redimensionar").

3. **"Agregar disponibilidad" (form alterno multi-día)** (prioridad 1 — la alternativa al drag para quienes no arrastran):
   - Botón `[ + Agregar disponibilidad ]` abre un drawer/dialog con: **consultorio** (mismo dropdown), **días marcados** (checkboxes Lun–Dom de la semana visible, o un mini-rango de fechas), y **bloque(s) horario** (`opens_at`–`closes_at`, con opción de agregar varios bloques tipo mañana/tarde como en `OfficeHoursTab`).
   - Al aplicar, arma el `blocks: [...]` (producto cartesiano días × bloques, expandido a fechas concretas) y hace **un solo** `POST /doctors/{id}/availability` (bulk). Esto cubre el caso "lleno mi semana de un saque".

4. **Drag para pintar en una columna** (prioridad 2 — refinamiento):
   - Mouse-down en celda vacía + arrastrar hacia abajo dentro de la misma columna pinta un rango (preview en vivo); al soltar, se crea un bloque `opens_at`=inicio, `closes_at`=fin (snap al grid del slot). Mismo `POST` bulk de 1.

5. **Drag del mismo rango a través de columnas (días) → alta masiva** (prioridad 2 — el más complejo):
   - Seleccionar un rango horario y arrastrarlo/extenderlo sobre varias columnas-día crea el **mismo** `opens_at`/`closes_at` en **todas** las fechas tocadas → un `POST` bulk con N bloques (uno por fecha). Es exactamente lo que el form alterno (#3) hace, pero por gesto.

#### Validación inline (espeja el backend, en español)

- **`closes_at > opens_at`** por bloque (mirror del CHECK `ck_doctor_availability_closes_after_opens`). Error inline: "La hora de cierre debe ser mayor que la de apertura." (mismo copy que clinic).
- **No-solapamiento del mismo doctor en la misma fecha** (`AVAILABILITY_OVERLAP`): se detecta **en vivo** con el mismo algoritmo que `OfficeHoursTab` usa para overlaps (ordenar por `opens_at`, `cur.opens < prev.closes` ⇒ solapan; adyacentes OK). Aplica entre los bloques existentes de esa fecha **y** entre los del propio body en bulk. Los bloques solapados se marcan en rojo y se **bloquea** el guardado/POST. Copy: "Este bloque se solapa con otro del mismo día."
- **Invariantes que NO se validan en front pero el backend sí rechaza** (mostrar el `detail` del 400 si llega): `OFFICE_NOT_IN_BRANCH` (#1) y `DOCTOR_NOT_IN_BRANCH` (#2) — improbables porque el dropdown solo ofrece combinaciones válidas, pero el MessageBar los muestra por defensa en profundidad.
- **Fuera de horario del office** (invariante #4 "suave"): NO se bloquea. Se muestra una marca visual sutil ("este bloque queda fuera del horario del consultorio; no generará citas en esa franja") como advertencia informativa, no error.

> El front re-valida con Zod (`staffAvailabilityCreateSchema` / `BulkCreate`) antes de cada POST/PUT; los mensajes de Pydantic del backend están en inglés (el front re-valida y muestra el español). Mismo contrato que clinic.

#### Estados

- **Loading**: **skeleton de la grilla** — render del marco (columnas con fechas + filas de horas) con celdas en gris animado (`<Skeleton><SkeletonItem>`), no un spinner suelto. Mientras `getAvailability(id, from, to)` resuelve.
- **Empty (semana sin bloques)**: la grilla se muestra vacía (con la banda de horario y cierres de fondo si los hay) + un texto guía: "Sin disponibilidad guardada para esta semana en este consultorio. Pinta bloques en la grilla o usa **Agregar disponibilidad**."
- **Guardando**: el bloque en creación/edición muestra estado pending (`Guardando…` en el popover); el resto de la grilla sigue interactiva pero el bloque afectado se ve atenuado hasta confirmar.
- **Error**: `<MessageBar intent="error">` arriba de la grilla con el `detail` del backend (ej. 400 `AVAILABILITY_OVERLAP` si un solapamiento se coló, 404 `AVAILABILITY_NOT_FOUND` si se editó un bloque borrado en otra pestaña).
- **Read-only (sin `DOCTOR_AVAILABILITY_WRITE`, o sin `MY_AVAILABILITY_WRITE` en self)**: la grilla se muestra completa pero **no interactiva** — sin click-to-create, sin drag, sin popover de edición; los bloques se ven pero no se pueden tocar; el botón "Agregar disponibilidad" no se renderiza. Un ASESOR (que tiene `DOCTOR_AVAILABILITY_READ` pero no `_WRITE`) ve la agenda del doctor para agendar, sin poder editarla.

#### Componentes Fluent UI (calendario)

| Concepto UI | Componente |
|---|---|
| Grilla | **custom** (CSS grid con `makeStyles`, tokens del design system) — **no hay** componente Fluent de calendario; **no** se usa librería externa |
| Selector de consultorio | `<Dropdown>` (combinaciones (branch, office) válidas del doctor) |
| Color por consultorio | clase derivada de una paleta de `tokens.colorPalette*` estable por office |
| Banda de horario office | celdas de fondo con `appTokens` tenue (read-only) |
| Cierres (`OfficeClosure`) | celdas hachuradas con patrón CSS (read-only) |
| Bloque del doctor | `<Button>`/`<div>` posicionado en la grilla, color sólido, con sus horas |
| Navegación semana | `<Button icon={<ChevronLeft/Right Regular/>}>` + `[ Hoy ]` + `<DatePicker>` (`react-datepicker-compat`) para "Ir a…" |
| Editar bloque | `<Popover>`/`<Dialog>` con `<Input type="time">` ×2 + Guardar (`PUT`) + Eliminar (`DELETE` con `<ConfirmDialog>`) |
| Crear bloque (click/drag) | mismo Popover, pre-poblado; `POST` bulk de 1 |
| Form alterno multi-día | `<Drawer size="medium">` con dropdown office + checkboxes de días + bloques horarios (estilo `OfficeHoursTab`) → `POST` bulk N |
| Skeleton grid | `<Skeleton>` + `<SkeletonItem>` por celda |
| Error / éxito | `<MessageBar intent="error"/"success">` |
| URL state (semana) | `nuqs useQueryState("from")` + `?office_id=` |

#### Plan incremental (binding — construir en este orden)

> El calendario es el **mayor riesgo del proyecto**. Construirlo de una sola vez es la trampa. Orden recomendado:

1. **Iteración A (lo funcional primero)** — grilla estática (columnas-fecha + filas-hora) que **renderiza** los bloques existentes de la semana (read), navegación de semana/Hoy/Ir-a, banda de horario + cierres de fondo, **click-para-crear** (popover → `POST` bulk de 1), **click-para-editar/borrar** (popover → `PUT`/`DELETE`), y el **form alterno "Agregar disponibilidad" multi-día** (`POST` bulk N). Con esto el módulo es **completamente usable sin drag**. Validación inline de `closes>opens` y overlap reusando el algoritmo de `OfficeHoursTab`. Estados loading/empty/error/read-only.
2. **Iteración B (refinamiento)** — **drag-para-pintar** dentro de una columna (preview + snap al grid).
3. **Iteración C (refinamiento)** — **drag del mismo rango a través de columnas** = alta masiva por gesto (equivalente al form alterno, pero arrastrando).

> Iteraciones B y C son **mejoras de UX sobre una base que ya funciona**. Si el tiempo aprieta, A es entregable por sí sola (el form alterno cubre el alta masiva). Mantenerse **dentro de Fluent tokens**; no introducir una librería de calendario "para ahorrar tiempo" — el modelo de datos (bloques por fecha) y las validaciones custom no encajan limpio en las librerías genéricas, y agregaría peso de bundle + estilos fuera del design system.

---

### Pantalla 5 — Self-service `/me` (F3)

En F3 el doctor logueado gestiona **lo suyo** sin pasar por el admin. Dos pantallas, ambas reusan componentes ya construidos en F1/F2 pero apuntando a los endpoints `/me/*` (el backend resuelve el `doctor` desde `CurrentAuth.user.id`; si el user no es doctor → `403 NOT_A_DOCTOR`).

**Acceso (sidebar/menú)**: grupo "Mi cuenta" (o bajo el avatar del TopBar) con "Mi perfil" (`MY_DOCTOR_PROFILE_READ`) y "Mi agenda" (`MY_AVAILABILITY_READ`). Solo el role DOCTOR los tiene; el ASESOR no ve este grupo.

#### `/me/perfil` — "Mi perfil"

Reusa el **form de la tab Perfil** (Pantalla 3) en **modo self**, con diferencias por el contrato `/me`:
- Editable por el doctor: **solo** `cmp_code`, `bio`, `photo_url`, `signature_url`, `slot_duration_min` (lo que permite `PUT /me/doctor` con `MY_DOCTOR_PROFILE_WRITE`).
- **NO editable** por el doctor: `branch_ids` / `vertical_ids` ni `active` (eso es admin — la spec lo dice explícito). Se muestran como **solo-lectura** ("Tus sedes y verticales las administra la clínica.").
- Datos del User (correo, nombre): solo-lectura, igual que en el admin.
- Carga con `GET /me/doctor`. Guardar con `PUT /me/doctor`.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Mi perfil                                                                     │
│ Actualiza tu colegiatura, biografía, foto, firma y duración de slot.          │
│                                                                              │
│ Correo (solo lectura)            Nombre (solo lectura)                        │
│ [ ana@medisage.pe        (—) ]   [ Ana Pérez Gómez       (—) ]               │
│                                                                              │
│ CMP                              Duración de slot                            │
│ [ 54321         editable ]       [ 30 min               ▾ ]                  │
│                                                                              │
│ Biografía            [ … editable … ]                                        │
│ Foto (URL)  [ editable ]   Firma (URL) [ editable ]                          │
│                                                                              │
│ Sedes (solo lectura): Sede Lima Centro, Sede Trujillo                        │
│ Verticales (solo lectura): Estética facial, Dermatología, Dental             │
│ Tus sedes y verticales las administra la clínica.            [ Guardar ]      │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### `/me/agenda` — "Mi agenda"

Es **el mismo calendario** de la Pantalla 4 en **modo self**:
- Lee con `GET /me/availability?from=&to=`, escribe con `POST/PUT/DELETE /me/availability[/{block_id}]`.
- Gating por `MY_AVAILABILITY_READ` (ver) / `MY_AVAILABILITY_WRITE` (editar). Si el doctor tiene `_WRITE`, la grilla es interactiva (crear/editar/borrar/drag); si solo `_READ`, read-only.
- Mismas validaciones, mismos estados, mismo selector de consultorio (sus propias sedes/offices).
- El componente del calendario debe parametrizarse por un `mode: "admin" | "self"` que solo cambia (a) la familia de endpoints/actions y (b) el `doctorId` (en self viene implícito del token, no de la URL). **Todo lo demás se reutiliza** — por eso el calendario debe construirse en F2 desacoplado del origen de datos (pasar las funciones de fetch/mutate como props o elegirlas por `mode`).

> Implicación de diseño: al construir el calendario en F2 (admin), **anticipar el modo self de F3** dejando los endpoints inyectables. No hardcodear `/doctors/{id}/availability` dentro del componente; recibirlo. Esto evita reescribir el componente más pesado del proyecto en F3.

## Decisiones de UI (cierres)

### Doctor detail como página, creación como drawer
Misma regla-precedente de clinic: entidad con sub-recurso de interacción propia (aquí, el calendario) → detalle en **página con tabs**; creación ligera → **drawer**. El Doctor reusa el shell de `OfficeDetailShell`.

### Creación NESTED en un solo drawer (user + doctor + M:N)
La spec fija que `DoctorCreate` lleva un `user` anidado y el service crea User+Doctor en una transacción. La UI lo refleja con tabs (Cuenta · Perfil · Asignaciones) en **un** drawer y **un** submit, devolviendo la **contraseña generada** igual que el admin (`UserDrawer`). No hacemos "primero crea el usuario, luego el doctor" — es un solo flujo.

### El delete del doctor NO toca al User
Soft-delete del Doctor ≠ borrar/desactivar el User (ADR-002). El copy del confirm lo deja explícito para que el admin no asuma que "elimina la cuenta". El User sigue vivo y puede re-vincularse o usarse con otro role.

### Calendario bespoke, sin librería, incremental
Detallado en la Pantalla 4. Resumen: Fluent no trae calendario; no metemos librería externa; se construye dentro de tokens; se prioriza click-to-create + form multi-día (entregable) y el drag como refinamiento. Es el mayor riesgo del proyecto y la ficha lo dice abiertamente.

### Filtros con chips + deep-link, no breadcrumbs
Igual que clinic/catalog: sede y vertical son `useQueryState` con chip × y deep-link. La página de detalle tiene un "← Volver a doctores" (back-link, no breadcrumb).

### slot_duration_min como dropdown curado
Lista cerrada `[15,20,30,45,60]` min (mismo rationale que timezone/icon picker: evita valores arbitrarios; es el grano del calendario y de scheduling). Default 30. Rationale completo en [`README.md`](README.md#slot_duration_min-en-doctor-no-por-doctor-product) (Decisiones de diseño).

### Disponibilidad sin recurrencia (cambio vs overview viejo)
El overview viejo y ADR-006 asumían patrón semanal recurrente + overrides. La spec lo **reemplaza** por bloques concretos por fecha (sin `day_of_week`, sin `is_available`). Por eso el calendario muestra **fechas reales** de una semana, no un patrón abstracto. "No disponible" = no hay bloque; "vacaciones" = semana sin bloques; "extra" = agregar bloque. ADR-006 se actualizará aparte.

### Sin duplicate, sin bulk-delete masivo, sort default
- Sin "Duplicar doctor" en el MVP.
- El delete de bloques de disponibilidad es por bloque (con confirm); el alta sí es masiva (bulk POST) porque es el caso común ("lleno la semana").
- Sort default de la lista: `full_name ASC`.

### Mobile / responsive
Mismo criterio que clinic (template optimizado para desktop interno):
- Sidebar colapsado por default; DataTable scrollea horizontal.
- Drawers a 100% del width en mobile.
- **El calendario** en pantallas angostas: scroll horizontal de las 7 columnas, o un modo "un día a la vez" (selector de día) — definir en la Iteración A si el ancho lo exige; el MVP prioriza desktop y deja scroll horizontal como fallback aceptable.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, CSS classes) en inglés — solo los textos visibles van traducidos. Glosario clave: **Doctor = Doctor** (masculino), **Branch = Sede**, **Office = Consultorio**, **Vertical = Vertical**, **availability = disponibilidad**.

### Copy por contexto

| Contexto | Copy |
|---|---|
| Page title (lista) | "Doctores" |
| Page subtitle (lista) | "Gestiona los doctores y su disponibilidad." |
| Botón crear | "+ Nuevo doctor" |
| Search placeholder | "Buscar por nombre o correo…" |
| Filtro Sede (placeholder) | "Todas las sedes" |
| Filtro Vertical (placeholder) | "Todas las verticales" |
| Chip filtro sede | "Sede: {nombre} ✕" |
| Chip filtro vertical | "Vertical: {nombre} ✕" |
| Empty (sin doctores) | "Aún no hay doctores. Registra el primero para asignarle sedes, verticales y su disponibilidad." |
| Empty (filtro sede sin doctores) | "Esta sede aún no tiene doctores asignados." |
| Empty (filtro vertical sin doctores) | "Ningún doctor cubre esta vertical todavía." |
| No-results genérico (DataTable) | "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía." |
| Status badge (doctor) | "Activo" / "Deshabilitado" |
| Columna Slot (render) | "{n} min" |
| Confirm delete title | "¿Eliminar doctor?" |
| Confirm delete body | "¿Eliminar al doctor '{nombre}'? Esto deshabilita su perfil de doctor; su cuenta de usuario se conserva." |
| Botón confirmar eliminación | "Eliminar" |
| — DoctorCreateDrawer — | |
| Drawer title | "Nuevo doctor" |
| Tabs drawer | "Cuenta" · "Perfil" · "Asignaciones" |
| Label correo | "Correo" |
| Labels nombre | "Nombres" / "Apellido paterno" / "Apellido materno" |
| Labels documento | "Tipo de documento" / "N° de documento" |
| Label teléfono | "Teléfono" |
| Label contraseña | "Contraseña" |
| Hint contraseña | "Si la dejas vacía, se genera una temporal." |
| Label CMP | "CMP" |
| Hint CMP | "Colegiatura (opcional para no-médicos)." |
| Label slot | "Duración de slot" |
| Label bio | "Biografía" |
| Hint bio | "Texto público que el bot puede leer al lead." |
| Labels url | "Foto (URL)" / "Firma (URL)" |
| Label sedes | "Sedes" |
| Hint sedes | "Sedes donde el doctor atiende." |
| Label verticales | "Verticales" |
| Hint verticales | "Verticales que el doctor cubre." |
| Validación sedes (mín. 1) | "Selecciona al menos una sede." |
| Validación verticales (mín. 1) | "Selecciona al menos una vertical." |
| Barra contraseña generada | "Doctor creado. Contraseña temporal (cópiala ahora — no se mostrará otra vez): {pwd}" |
| Error 409 (email tomado) | "Ya existe un usuario con ese correo." |
| Botón crear / creando | "Crear" / "Creando…" |
| Botón cancelar | "Cancelar" |
| — Página de detalle — | |
| Back-link | "← Volver a doctores" |
| Subtítulo página | "{correo} · CMP {cmp_code} · Slot {slot} min" (omitir piezas NULL) |
| Tabs página | "Perfil" · "Disponibilidad" · "Auditoría" |
| Botón tab Perfil | "Guardar cambios" |
| Hint datos de user (solo lectura) | "Estos datos se editan en Administración → Usuarios." |
| Labels solo-lectura | "Correo (solo lectura)" / "Nombre (solo lectura)" |
| Switch activo | "Activo" |
| Placeholder tab Disponibilidad (F1) | "Próximamente: calendario de disponibilidad." |
| — Tab Disponibilidad (calendario) — | |
| Título | "Disponibilidad" |
| Label selector office | "Consultorio" |
| Botón Hoy | "Hoy" |
| Botón ir a fecha | "Ir a…" |
| Rango de semana (header) | "Sem. {d1}–{d2} {mes} {año}" |
| Botón agregar (form alterno) | "+ Agregar disponibilidad" |
| Empty semana | "Sin disponibilidad guardada para esta semana en este consultorio. Pinta bloques en la grilla o usa Agregar disponibilidad." |
| Validación closes>opens | "La hora de cierre debe ser mayor que la de apertura." |
| Validación solapamiento | "Este bloque se solapa con otro del mismo día." |
| Aviso fuera de horario | "Este bloque queda fuera del horario del consultorio; no generará citas en esa franja." |
| Popover crear/editar — guardar | "Guardar" / "Guardando…" |
| Popover crear/editar — eliminar | "Eliminar" |
| Confirm eliminar bloque | "¿Eliminar este bloque de disponibilidad?" |
| Form alterno — días | "Días" |
| Form alterno — bloque horario | "Desde" / "Hasta" |
| Form alterno — aplicar | "Agregar" / "Agregando…" |
| Toast guardado | "Disponibilidad guardada." |
| Error genérico calendario | "No se pudo guardar la disponibilidad. Intenta de nuevo." |
| Read-only (sin write) | (sin botones; la grilla muestra los bloques sin interacción) |
| — Self-service /me (F3) — | |
| Page title (mi perfil) | "Mi perfil" |
| Page subtitle (mi perfil) | "Actualiza tu biografía, foto, firma y duración de slot." |
| Hint sedes/verticales (self) | "Tus sedes y verticales las administra la clínica." |
| Page title (mi agenda) | "Mi agenda" |
| Page subtitle (mi agenda) | "Define cuándo y dónde atiendes." |
| Error no es doctor (403 NOT_A_DOCTOR) | "Tu cuenta no tiene un perfil de doctor asociado. Contacta a la clínica." |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Audit labels (doctor) | "Estado", "ID del doctor", "Creado el", "Creado por", "Actualizado el", "Actualizado por" |
| Loading placeholder en inputs | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |

### Concordancia de género

- **Doctor** es **masculino**: "Nuevo doctor", "Editar doctor", "Activo" / "Deshabilitado", "Creado el", "Creado por", "al doctor 'X'", "ID del doctor".
- En confirm dialogs y mensajes mantener concordancia masculina: "¿Eliminar **al** doctor 'X'?".
- **Sede** (heredado de clinic) es **femenino**: "una sede", "Selecciona al menos una sede".
- **Vertical** (heredado de catalog) es **femenino**: "una vertical", "Selecciona al menos una vertical".
- **Disponibilidad** es **femenino**: "Disponibilidad guardada" / "la disponibilidad".
- **Consultorio** es **masculino** (heredado de clinic): "este consultorio".

### Etiquetas de día de la semana

Convención del modelo Python (`0 = lunes … 6 = domingo`), igual que clinic. Reutilizar la **misma constante** `DAY_LABELS = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]` que clinic ya vive en `lib/constants/` (no duplicar). En el calendario, cada columna combina la etiqueta corta con la fecha real ("Lun 1", "Mar 2", …).

| `day_of_week` | Etiqueta corta | Etiqueta larga (tooltip) |
|---|---|---|
| 0 | "Lun" | "Lunes" |
| 1 | "Mar" | "Martes" |
| 2 | "Mié" | "Miércoles" |
| 3 | "Jue" | "Jueves" |
| 4 | "Vie" | "Viernes" |
| 5 | "Sáb" | "Sábado" |
| 6 | "Dom" | "Domingo" |

> El índice del array = valor Python directo (0=Lun). Documentado junto a la constante para evitar el off-by-one de Postgres (0=domingo). Ver [`clinic/ui.md`](../clinic/ui.md#etiquetas-de-día-de-la-semana) — `staff` la reusa.

### Sin i18n framework por ahora

Textos directos como strings en cada componente (misma decisión que catalog/clinic). Si negocio pide multilingüe, introducir `next-intl` después.

## Mapeo a fases de implementación

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](README.md#fases-de-implementación), [`backend.md`](backend.md#checklist-de-implementación) y la spec F0–F3):

- **F0 Prep** — sidebar `Staff → Doctores` (`NAV_ITEMS`, icono `DoctorRegular` / `PersonStethoscopeRegular`); `endpoints.ts` (DOCTORS + availability + `/me`); `types/staff.types.ts` (todas las interfaces espejo de Pydantic: `DoctorItem`, `DoctorDetail`, `DoctorOption`, `DoctorAvailabilityItem`, `DoctorCreatedResponse`, etc.); `lib/schemas/staff.schema.ts` (Zod). Sin pantallas funcionales aún. (Reusa `DAY_LABELS` y los pickers ya existentes de clinic.)
- **F1 Doctor (+M:N)** — **Pantalla 1** (`/staff/doctors` lista con filtros sede+vertical, chip, deep-link) + **Pantalla 2** (`DoctorCreateDrawer` NESTED con tabs Cuenta/Perfil/Asignaciones, `SearchableOptionList` ×2, barra de contraseña generada) + **shell de la página de detalle** `/staff/doctors/{id}` (`DoctorDetailShell` clon de `OfficeDetailShell`) con **Perfil** y **Auditoría** funcionales y **Disponibilidad** como placeholder.
- **F2 DoctorAvailability (calendario)** — **Pantalla 4**: tab `Disponibilidad` con la grilla semanal. Construir por iteraciones: **A** (grilla + render + navegación + click-to-create + edit/delete + form alterno multi-día + validación + estados + read-only), luego **B** (drag-pintar), luego **C** (drag-multi-día). Dejar los endpoints **inyectables** para anticipar el modo self de F3. Es el frontend más pesado del proyecto.
- **F3 Self-service `/me`** — **Pantalla 5**: `/me/perfil` (form Perfil en modo self, solo bio/foto/firma/slot editables) + `/me/agenda` (el calendario de F2 en `mode="self"`, apuntando a `/me/availability`). Grupo de menú "Mi cuenta". Gating por `MY_*`.
