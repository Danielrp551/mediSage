# Módulo `scheduling` — UI design

> **Última actualización**: 2026-06-06
> **Audiencia**: developer implementando las pantallas de `scheduling` en `frontend/src/app/(main)/scheduling/` (y la self-service `/scheduling/mi-agenda` del doctor).
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). Slots híbridos sin tabla en [ADR-006](../../decisions/ADR-006-hybrid-calendar-slots.md); disponibilidad del doctor por **bloques concretos** en [ADR-007](../../decisions/ADR-007-doctor-availability-concrete-blocks.md); matriz de transiciones espeja crm/ADR-008.

> **Alineación con crm/clinic/staff/catalog (módulos gold-standard ya en prod)**: `scheduling` reutiliza directamente los patrones que esos módulos dejaron como precedente del template y **no inventa un estilo nuevo** (regla de la metodología: consistencia con lo shippeado **>** estilo nuevo). En concreto:
> - **El catálogo `AppointmentStatus` + editor de matriz** es un clon casi literal de `/crm/estados-lead` (lista `VerticalsClient` + `LeadStatusDrawer` + `StatusMatrixEditor`). La única diferencia: scheduling expone **además** la vista de **grilla `from × to` con checkboxes** que crm dejó "diferible" — acá es parte del MVP (decisión del usuario).
> - **La tabla de citas + filtros chip + deep-link** espeja `OfficesClient`/`DoctorsClient` (filtros `<Dropdown>` con chip × y `nuqs useQueryState`).
> - **El wizard de reserva** es un drawer de 4 pasos; reutiliza el patrón de `DoctorCreateDrawer` (multi-sección + `SearchableOptionList`) y agrega un paso de **grilla de slots** alimentada por `POST /availability/compute`.
> - **La grilla semanal de calendario** es un primo directo del **calendario de disponibilidad de `staff`** (`DoctorAvailability`): misma grilla CSS bespoke, misma navegación de semana, mismos tokens. La diferencia: aquí los bloques sólidos son **citas** (color = estado) y los slots libres son **overlay clickeable** que abre el wizard prefilled.
> - **El detalle de cita** (control de estado gated por la matriz + timeline) reutiliza `TransitionControl` (crm) y el lenguaje visual del **Timeline de Actividad de crm** (tarjetas tipadas, agrupación por día client-only).
> - **`/scheduling/mi-agenda`** reutiliza el patrón self-service `/me` de `staff` (mismo calendario en `mode="self"`, gateado por `MY_APPOINTMENTS_READ`).

> **Contexto de diseño (regla del template, no negociable)**:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Los colores de estado de cita salen del `color` hex del catálogo (`AppointmentStatus.color`, badges/bloques). El resto usa tokens Fluent (`tokens.colorPaletteRedForeground1`, `tokens.colorPaletteGreenForeground1`, etc.). No introducir una librería de calendario externa (FullCalendar, react-big-calendar): el modelo (slots on-the-fly + bloques por estado) y la validación custom no encajan limpio y agregan peso de bundle + estilos fuera del design system.
> - **TZ — lección recurrente de staff/crm (binding)**: cualquier `new Date()`/`now` que afecte el render debe ser **client-only**. Esto cubre: resaltar la columna/celda de **"hoy"** en la grilla, el **default de fecha** del wizard y del calendario, los **timestamps relativos** del timeline ("hace 2 h"), y el resaltado de citas **vencidas/futuras**. El SSR corre en UTC y desfasaría el día en Lima (UTC-5). Las horas de las citas se renderizan en el **timezone del branch** de la cita (no en el del navegador): el backend manda `scheduled_for` en UTC tz-aware + el `branch.timezone` IANA, y el front formatea con `Intl.DateTimeFormat(..., { timeZone })`.

---

## Decisión de arquitectura: 3 listas en sidebar + detalle de cita en drawer + self-service `mi-agenda`

`clinic` estableció la regla, reafirmada por `staff`/`crm`: **si una entidad tiene sub-recursos con interacción propia (timelines, grids editables, máquinas de estado), su superficie va a una página/grilla dedicada; si es ligera, va a drawer.** En `scheduling`:

| Recurso | Lista / superficie | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **AppointmentStatus** (catálogo) | `/scheduling/estados` (sidebar) | drawer | drawer (color/flags) + **editor de matriz** (multiselect en el drawer **+** grilla `from×to`) | clon `/crm/estados-lead` (`VerticalsClient` + `StatusMatrixEditor`) |
| **Appointment** (Cita) | `/scheduling/citas` (sidebar, tabla con filtros chip + deep-link) | **wizard de reserva** (drawer 4 pasos) | **detalle en drawer** `size=large` (control de estado + timeline + reschedule/cancel) | tabla = `OfficesClient`; wizard = `DoctorCreateDrawer` + grilla de slots |
| **Calendario** | `/scheduling/calendario` (sidebar, **grilla semanal/día**) | overlay de slot libre → wizard prefilled | click en bloque-cita → detalle (drawer) | clon de la grilla de `staff` (citas = bloques por estado) |
| **Mi agenda** (doctor, self) | `/scheduling/mi-agenda` (sidebar, gated `MY_APPOINTMENTS_READ`) | — (read) | click → detalle de su cita | calendario en `mode="self"` (molde `/me/agenda` de staff) |
| `AppointmentStatusHistory` + `AppointmentChangeLog` | — | — | dentro del **detalle de cita** (timeline entrelazado) | feed cronológico (lenguaje visual del Timeline de crm) |
| `compute_available_slots` | — | dentro del **wizard** (paso Slot) y del **calendario** (overlays) | — | grilla de slots / overlays (no es pantalla propia) |

### Por qué el detalle de la cita es un **drawer** y no una página con tabs

A diferencia del `Office`/`Doctor`/`Person` (que tienen varios sub-recursos densos → página con tabs), la **cita** es una sola entidad con: un estado (máquina pequeña), un timeline read-only (history + changelog entrelazados), y dos acciones puntuales (reschedule/cancel). No hay multi-superficie editable que justifique una página + URL bookmarkable por tab. Por eso el detalle vive en un **drawer `size="large"`** (no `medium` — el timeline necesita aire), abierto desde la tabla, desde el calendario o desde Mi agenda. Es la misma decisión que `crm` tomó para los **catálogos** (drawer) vs el `Person` (página): el peso del sub-recurso manda la forma.

> Alternativas descartadas: (B) **página `/scheduling/citas/{id}` con tabs** — sobra; la cita no tiene 4 superficies densas, solo estado + timeline, y forzar una página rompe el flujo "veo la tabla/calendario → abro la cita → actúo → vuelvo". (C) **Dialog modal** — el timeline crece y el control de estado con popovers de confirmación sobre un modal = z-index frágil; el drawer lateral es el patrón del template para "ver/actuar sin perder el contexto de la lista". El drawer **sí** sincroniza un `?appointment_id=` en la URL de la lista/calendario para ser deep-linkable y sobrevivir refresh (igual espíritu que `?tab=` de clinic).

### Por qué el calendario es una superficie de primer nivel (decisión #2 del spec)

El MVP **incluye** la grilla de calendario semanal (no solo la tabla). La tabla es la vista "operativa/lista" (filtrar, buscar, deep-link); el calendario es la vista "espacial" (ver huecos, agendar en un slot libre de un vistazo). Ambas leen las mismas citas; el calendario suma los **slots libres** (de `GET /appointments/calendar`, que combina citas + disponibilidad computada en el rango). Es el componente de frontend más pesado del módulo (como el calendario de `staff` lo fue de ese módulo) y se construye **al final** (F4), sobre una base de tabla + wizard + detalle ya usable.

## Sidebar — extensión de `NAV_ITEMS` (grupo "Agenda", gated `MENU-SCHEDULING`)

> ⚠ **Textos UI en español**. `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un parent item `scheduling` con 4 children, **después de `crm`** (es el módulo #7, cierra el flujo lead → conversación/bot → **cita** → cliente):

```ts
{
  key: "scheduling",
  label: "Agenda",
  icon: "CalendarLtrRegular",              // verificar en la versión de Fluent; fallback "CalendarRegular"
  children: [
    { key: "citas",       label: "Citas",         icon: "CalendarClockRegular", url: "/scheduling/citas",       permissions: ["APPOINTMENTS_READ"] },
    { key: "calendario",  label: "Calendario",    icon: "CalendarWeekStartRegular", url: "/scheduling/calendario", permissions: ["APPOINTMENTS_READ"] },
    { key: "mi-agenda",   label: "Mi agenda",     icon: "PersonCalendarRegular", url: "/scheduling/mi-agenda",   permissions: ["MY_APPOINTMENTS_READ"] },
    { key: "estados",     label: "Estados de cita", icon: "TagRegular",        url: "/scheduling/estados",     permissions: ["APPOINTMENT_STATUSES_READ"] },
  ],
},
```

> El parent usa `MENU-SCHEDULING` como gate de visibilidad del grupo. Cada child gatea por **su** permiso de lectura:
> - **ASESOR** (tiene `MENU-SCHEDULING`, `APPOINTMENTS_READ/CREATE/UPDATE/TRANSITION/CANCEL/RESCHEDULE`, `APPOINTMENTS_READ`, `APPOINTMENT_STATUSES_READ`) ve Citas, Calendario y Estados (read-only en Estados, sin `_WRITE`). No tiene `MY_APPOINTMENTS_READ` → **no** ve "Mi agenda".
> - **DOCTOR** (tiene `MENU-SCHEDULING`, `APPOINTMENTS_READ` [scoped a sí mismo vía service], `APPOINTMENTS_TRANSITION`, `MY_APPOINTMENTS_READ`, `APPOINTMENTS_READ`) ve Citas (solo las suyas, el service filtra), Calendario y **Mi agenda**. No tiene `APPOINTMENT_STATUSES_READ` → **no** ve "Estados de cita".
> - **ADMIN** ve todo.
> Los permisos finos (`APPOINTMENTS_CREATE`, `APPOINTMENT_STATUSES_WRITE`, `APPOINTMENTS_CANCEL_OVERRIDE`, etc.) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>` / `usePermissions()`. El **detalle de la cita** no tiene entrada propia en el sidebar — se llega desde la tabla/calendario/mi-agenda.

> Iconos Fluent (verificar que existan en la versión instalada; usar fallback si no): `CalendarLtrRegular`/`CalendarClockRegular`/`CalendarWeekStartRegular`/`PersonCalendarRegular`/`TagRegular`. Mismo criterio de verificación que `staff` con `DoctorRegular` y `crm` con `PeopleRegular`.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error / success) + tabla de componentes Fluent.

1. `/scheduling/estados` — catálogo `AppointmentStatus` (tabla + drawer color/flags) + **editor de matriz** (multiselect en drawer + grilla `from×to`).
2. `/scheduling/citas` — tabla de citas (filtros chip + deep-link) + **wizard de reserva** (drawer 4 pasos).
3. `/scheduling/calendario` — **grilla semanal/día** (citas = bloques por estado; slots libres = overlay → wizard prefilled).
4. **Detalle de cita** (drawer) — control de estado (shortcuts gated por la matriz) + **timeline** (history + changelog) + reschedule/cancel.
5. `/scheduling/mi-agenda` — vista del doctor (read).

---

### Pantalla 1 — `/scheduling/estados` (catálogo `AppointmentStatus` + matriz)

Clon de `/crm/estados-lead` (molde `VerticalsClient`). Cada estado tiene `color`, flags (`is_initial` único, `is_final`, `is_active_attention`) y `display_order`. El editor de transiciones tiene **dos modos**: el **multiselect por estado** (dentro del drawer, como crm) **y** una **grilla `from × to`** (pedida explícitamente, lo que crm dejó diferible). Seed F1 = 8 estados + matriz base.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                      │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │   Estados de cita                                          │ │
│ │ ▸ CRM      │ │   Configura los estados de una cita y sus transiciones.    │ │
│ │ ▾ Agenda   │ │                          [ Ver matriz ]  [ + Nuevo estado ]│ │
│ │   • Citas  │ │  ╭─ DataTable ──────────────────────────────────────────╮ │ │
│ │   • Calend.│ │  │ ⋯ │ Código     │ Nombre       │Color│ Flags        │Ord│ │ │
│ │   • Mi ag. │ │  ├───┼────────────┼──────────────┼─────┼──────────────┼───┤ │ │
│ │   • Estad █│ │  │ ⋯ │ SCHEDULED  │ Agendada     │⬤azul│ ●Inicial     │10 │ │ │
│ │ ▸ Admin    │ │  │ ⋯ │ CONFIRMED  │ Confirmada   │⬤cian│              │20 │ │ │
│ │            │ │  │ ⋯ │ CHECKED_IN │ En recepción │⬤ámb.│              │30 │ │ │
│ │            │ │  │ ⋯ │ IN_PROGRESS│ En atención  │⬤viol│ ●En atención │40 │ │ │
│ │            │ │  │ ⋯ │ ATTENDED   │ Atendida     │⬤verd│ ●Final       │50 │ │ │
│ │            │ │  │ ⋯ │ NO_SHOW    │ No asistió   │⬤rojo│ ●Final       │60 │ │ │
│ │            │ │  │ ⋯ │ CANCELLED  │ Cancelada    │⬤gris│ ●Final       │70 │ │ │
│ │            │ │  │ ⋯ │ RESCHEDULED│ Reagendada   │⬤gris│ ●Final       │80 │ │ │
│ │            │ │  ╰──────────────────────────────────────────────────────╯ │ │
│ └────────────┘ └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (`key` inglés / `header` español): Código (`code`, mono `<code>`), Nombre (`name`), Color (swatch `⬤` + hex), Flags (badges "Inicial"/"Final"/"En atención"), Orden (`display_order`, numérico tabular). RowActions: Ver/Editar (drawer, gated `APPOINTMENT_STATUSES_WRITE` para editar), Eliminar (gated `APPOINTMENT_STATUSES_WRITE`; 409 `APPOINTMENT_STATUS_IN_USE` si hay citas en ese estado → "No se puede eliminar: hay citas en este estado."). Sort default = `display_order ASC` (es columna real, server-sortable).

**Botón "+ Nuevo estado"**: gated `<PermissionGuard anyOf={["APPOINTMENT_STATUSES_WRITE"]}>`.
**Botón "Ver matriz"**: abre la vista de grilla `from × to` (ver más abajo). Visible siempre (read); las casillas son editables solo con `APPOINTMENT_STATUSES_WRITE`.

#### Drawer de estado (`AppointmentStatusDrawer`, create/edit/view)

`<Drawer size="medium">`. Campos + el multiselect de transiciones de salida embebido (igual que `LeadStatusDrawer`). **No** tiene flag "Ganado" (eso es de crm; aquí los flags son `is_initial`/`is_final`/`is_active_attention`).

```
                  ┌─────────────────────────────────────────────────┐
                  │  Nuevo estado de cita                         ✕ │
                  ├─────────────────────────────────────────────────┤
                  │  Código *        (MAYÚSCULAS, sin espacios)     │
                  │  [ IN_PROGRESS                               ]  │
                  │  Convención: MAYÚSCULAS/dígitos/_ (ej. NO_SHOW).│
                  │  Nombre *                                       │
                  │  [ En atención                                ] │
                  │  Descripción                                    │
                  │  [ ……………………………………………………………………………………………… ]    │
                  │  Color            Orden                         │
                  │  [ #8B5CF6  ⬤ ]   [ 40 ]                        │
                  │  ☐ Estado inicial   (solo uno puede serlo)      │
                  │  ☐ Estado final (terminal)                      │
                  │  ☐ En atención ahora  (vista operativa)         │
                  │  ───────────────────────────────────────────   │
                  │  Transiciones permitidas hacia…                 │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 🔍 Buscar estados…                       │   │
                  │  │ ☑ Atendida                               │   │
                  │  │ ☑ Cancelada                              │   │
                  │  │ ☐ Confirmada                             │   │
                  │  │ ☐ En recepción                           │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Desde "En atención" una cita podrá pasar a     │
                  │  los estados marcados.                          │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Guardar ]│
                  └─────────────────────────────────────────────────┘
```

- **Validaciones (Zod + backend)**: `code` en MAYÚSCULAS (espeja crm.LeadStatus; el front fuerza el casing; sin pattern slug restrictivo en el Pydantic, solo min/max length); `name` requerido; **solo un `is_initial`** por catálogo (al marcar Inicial, advertir "Reemplazará al estado inicial actual: {nombre}"; el backend rechaza `MULTIPLE_INITIAL_STATUS`). `is_final` e `is_active_attention` son flags libres (0..N para `is_active_attention`). `color` hex opcional.
- **Editor de matriz por fila** (`StatusMatrixEditor`, embebido): multiselect "Transiciones permitidas hacia…" con los demás estados activos (`GET /scheduling/appointment-statuses/active`), reutilizando `SearchableOptionList`. Al guardar, además del `PUT /scheduling/appointment-statuses/{id}`, hace `PUT /scheduling/appointment-statuses/{id}/transitions { to_ids: [...] }` que **reemplaza las aristas de salida** del estado. Si el estado es `is_final` (terminal), el multiselect se deshabilita con "Un estado final no admite transiciones de salida." (coherente con la matriz seed: los finales no tienen aristas).
- **Modos**: `create` ("Nuevo estado de cita") / `edit` ("Editar estado de cita") / `view` ("Detalle de estado", todo disabled, footer `Cerrar`). Tab de **Auditoría** opcional dentro del drawer (estado/ID/creado/actualizado) en edit/view, igual que los catálogos de crm.

#### Editor de matriz — vista de grilla `from × to` (la diferencia vs crm)

Pedida explícitamente. Abre desde "Ver matriz" como una **superficie aparte** (Dialog `size="large"` o sub-vista de la misma página). Filas = estados origen; columnas = estados destino; cada celda es un `<Checkbox>` (marcado = arista permitida). La **diagonal** (estado → sí mismo) está bloqueada (no tiene sentido). Las **filas de estados `is_final`** están deshabilitadas en bloque (sin aristas de salida). Cambios se aplican por fila (`PUT .../{from_id}/transitions`) al confirmar.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Matriz de transiciones                                                     ✕ │
│  Marca a qué estados puede pasar una cita desde cada estado de origen.         │
│  Las filas en gris son estados finales (sin salida).                          │
│  ┌──────────────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐     │
│  │  desde \ a   │ Agen │ Conf │ Recp │ Aten │ Atnd │ NoSh │ Canc │ Reag │     │
│  ├──────────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┤     │
│  │ Agendada     │  ▦   │  ☑   │  ☑   │  ☐   │  ☐   │  ☑   │  ☑   │  ☑   │     │
│  │ Confirmada   │  ☐   │  ▦   │  ☑   │  ☐   │  ☐   │  ☑   │  ☑   │  ☑   │     │
│  │ En recepción │  ☐   │  ☐   │  ▦   │  ☑   │  ☐   │  ☐   │  ☑   │  ☐   │     │
│  │ En atención  │  ☐   │  ☐   │  ☐   │  ▦   │  ☑   │  ☐   │  ☑   │  ☐   │     │
│  │ Atendida   ▒ │  ▒   │  ▒   │  ▒   │  ▒   │  ▦   │  ▒   │  ▒   │  ▒   │     │
│  │ No asistió ▒ │  ▒   │  ▒   │  ▒   │  ▒   │  ▒   │  ▦   │  ▒   │  ▒   │     │
│  │ Cancelada  ▒ │  ▒   │  ▒   │  ▒   │  ▒   │  ▒   │  ▒   │  ▦   │  ▒   │     │
│  │ Reagendada ▒ │  ▒   │  ▒   │  ▒   │  ▒   │  ▒   │  ▒   │  ▒   │  ▦   │     │
│  └──────────────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘     │
│  ▦ = no aplica (mismo estado)   ▒ = fila final (sin salida)                    │
│                                              [ Cancelar ]  [ Guardar matriz ]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Cabeceras** = `name` de cada estado, en `display_order`, con su swatch de color en tooltip. Encabezados cortos truncados con `<Tooltip>` que muestra el nombre completo.
- **Celda**: `<Checkbox>` con `aria-label="Permitir {origen} → {destino}"`. Marcar/desmarcar es estado local; **Guardar matriz** difunde por fila (un `PUT .../{from_id}/transitions { to_ids }` por cada fila que cambió). Concordancia con el multiselect del drawer: ambos pegan al mismo endpoint; abrir uno tras otro siempre refleja el estado actual (re-fetch).
- **Diagonal** (`▦`): no editable (no se permite `from == to`).
- **Filas finales** (`▒`): deshabilitadas; tooltip "Estado final — no admite transiciones de salida."
- **Gating**: con `APPOINTMENT_STATUSES_WRITE` los checkboxes son editables; sin él, la grilla es read-only (solo lectura de la configuración) y el botón "Guardar matriz" no se renderiza.

#### Estados (Pantalla 1)

- **Empty (catálogo vacío)**: "Aún no hay estados de cita. Crea el primero (marca uno como inicial)." (improbable: el seed F1 ya carga 8 + matriz base). Ícono `TagRegular`.
- **Loading**: DataTable con 8 skeleton rows; toolbar normal.
- **No-results** (búsqueda sin matches): genérico de `DataTable`.
- **Refetching**: tabla con `opacity: 0.55` + spinner top-right.
- **Success (matriz guardada)**: `<MessageBar intent="success">"Matriz de transiciones guardada."` + cierre del Dialog. Toast "Estado guardado." al guardar un estado.
- **Error**: 409 `APPOINTMENT_STATUS_IN_USE` en el confirm de borrado (inline en el `ConfirmDialog`); 400 `MULTIPLE_INITIAL_STATUS` inline en el drawer (`<MessageBar intent="error">`).

#### Componentes Fluent UI (estados + matriz)

| Concepto UI | Componente |
|---|---|
| Lista | `<DataTable<AppointmentStatusItem>>` + `useTableQuery({ queryKey: "scheduling:statuses", defaultSort: { field: "display_order", order: "asc" } })` |
| Swatch de color | `<div>` con `backgroundColor` + texto hex |
| Flags | `<Badge appearance="tint" color={...}>` "Inicial"/"Final"/"En atención" |
| Drawer estado | `<Drawer size="medium">` + `<FormField>` + `<Input>`/`<Textarea>`/`<Switch>` |
| Color picker | `<Input>` hex + swatch (sin color-picker complejo) |
| Editor matriz (fila) | `StatusMatrixEditor` = `SearchableOptionList` (multiselect) → `PUT /transitions` |
| Editor matriz (grilla) | `<Dialog size="large">` + tabla custom de `<Checkbox>` (CSS grid, `makeStyles`, tokens) |
| Confirm delete | `<ConfirmDialog destructive>` (maneja 409 `APPOINTMENT_STATUS_IN_USE`) |
| Éxito / error | `<MessageBar intent="success"/"error">` |

---

### Pantalla 2 — `/scheduling/citas` (tabla de citas + wizard de reserva)

Tabla estructura `OfficesClient`/`DoctorsClient`, con **cinco filtros** deep-linkables (doctor, estado, sede, fecha, producto), cada uno con chip y ×, espejando el patrón shipped. El botón primario abre el **wizard de reserva** (drawer 4 pasos).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Citas                                                                        │
│   Agenda, consulta y gestiona las citas de la clínica.                         │
│  ┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌──────────┐┌────┐┌────────┐│
│  │Doctor:T.▾││Estado:T.▾││Sede: T. ▾││Prod.: T.▾││Fecha:Hoy▾││🔍  ││+ Reser.││
│  └──────────┘└──────────┘└──────────┘└──────────┘└──────────┘└────┘└────────┘│
│  ┌──────────────────────┐ ┌──────────────────────┐ ┌────────────────────┐    │
│  │ Doctor: Dra. Ríos   ✕│ │ Estado: Agendada    ✕│ │ Fecha: 6 jun 2026 ✕│ chip│
│  └──────────────────────┘ └──────────────────────┘ └────────────────────┘    │
│  ╭─ DataTable ──────────────────────────────────────────────────────────────╮ │
│  │ ⋯ │ Fecha/hora      │ Paciente     │ Doctor    │ Producto │ Sede·Cons│Estado│ │
│  ├───┼─────────────────┼──────────────┼───────────┼──────────┼──────────┼──────┤ │
│  │ ⋯ │ 6 jun · 09:00   │ Ana Torres   │ Dra. Ríos │ Limpieza │ Lima·C-03│●Agend│ │
│  │ ⋯ │ 6 jun · 09:30   │ Luis Rojas   │ Dra. Ríos │ Consulta │ Lima·C-03│●Confi│ │
│  │ ⋯ │ 6 jun · 10:00   │ María Quispe │ Dr. Salas │ Botox    │ Lima·EST1│●Recep│ │
│  │ ⋯ │ 6 jun · 11:00   │ Pedro Lara   │ Dra. Ríos │ Consulta │ Lima·C-03│●Atend│ │
│  ├──────────────────────────────────────────────────────────────────────────┤ │
│  │ Mostrando 1–4 de 4      ‹  Página 1 de 1  ›                               │ │
│  ╰──────────────────────────────────────────────────────────────────────────╯ │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (mapean a `AppointmentItem`, con denormalizaciones del service):

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `actions` | `""` | RowActions | — | menú `…`: Ver detalle / Reagendar / Cancelar (gated) |
| `scheduled_for` | Fecha/hora | datetime | ✅ (server, columna real) | fecha + hora en el **timezone del branch** ("6 jun · 09:00"); render **client-only** |
| `person_name` | Paciente | text (truncate) | ❌ (denorm) | `full_name` del paciente; click navega al contacto crm (deep-link opcional) |
| `doctor_name` | Doctor | text (truncate) | ❌ (deep-link) | nombre del doctor |
| `product_name` | Producto | text (truncate) | ❌ (deep-link) | nombre del producto + duración (`{duration_min} min` en tooltip) |
| `branch_office` | Sede · Consultorio | text (truncate) | ❌ | `{branch_name} · {office_code}` |
| `status` | Estado | badge | ❌ (deep-link) | `<StatusBadge color={s.color}>{s.name}</StatusBadge>` |
| `source` | Origen | chip pequeño | ❌ | "Bot"/"Asesor"/"Admin"/"Import"/"API" (chip tenue; opcional, columna secundaria) |

> **Denormalización sin N+1** (mismo patrón que crm `assigned_advisor` / clinic `branch_name`): `person_name`, `doctor_name`, `product_name`, `branch_name`/`office_code` y el `status` (code/name/color) se hidratan por **batch** en el service. **Lección hotfix `cd10c78` de staff (binding)**: estas columnas son denormalizadas, NO están en `ALLOWED_FIELDS` → **no son server-sortable/filterable por su texto**. Por eso tienen `isSortable: false`, y los filtros por doctor/estado/sede/producto **no** filtran por el texto sino por el **id** (`doctor_id`/`status_id`/`branch_id`/`product_id`), que el backend traduce a JOIN/WHERE sobre la columna FK real. Solo `scheduled_for` (columna real indexada) es server-sortable; `defaultSort = { field: "scheduled_for", order: "asc" }`. `searchFields` se limita a columnas de `ALLOWED_FIELDS`; la búsqueda visible por nombre de paciente es client-side sobre lo cargado.

**Filtros (Dropdown + chip + deep-link)** — espejo de `OfficesClient`:
- **Doctor**: opciones de `GET /staff/doctors/active`. `?doctor_id=X`. Chip "Doctor: {nombre} ✕". Default "Todos los doctores".
- **Estado**: opciones de `GET /scheduling/appointment-statuses/active` (cada opción con su swatch de color). `?status_id=X`. Chip "Estado: {nombre} ✕".
- **Sede**: opciones de `GET /clinic/branches/active`. `?branch_id=X`. Chip "Sede: {nombre} ✕".
- **Producto**: opciones de `GET /catalog/products/active`. `?product_id=X`. Chip "Producto: {nombre} ✕".
- **Fecha**: un `<DatePicker>` (o presets "Hoy / Mañana / Esta semana") que mapea a `?date_from=&date_to=` (un día = `date_from == date_to`). Default **Hoy** (cálculo **client-only**, TZ del branch por defecto America/Lima). Chip "Fecha: {DD mmm YYYY} ✕".
- Todos se traducen a `extraFilters`/query params para `useTableQuery`.

> Deep-link de entrada: desde el calendario, desde el detalle de un contacto crm ("ver sus citas"), desde un dashboard ("12 citas hoy con la Dra. Ríos") se llega con `/scheduling/citas?doctor_id=X&date_from=...&status_id=...` y los chips aparecen pre-poblados.

**RowActions** (gated por `usePermissions()`):
- 👁 **Ver detalle** — siempre visible (asume `APPOINTMENTS_READ`). Abre el **drawer de detalle** (Pantalla 4) y setea `?appointment_id=`.
- 🔁 **Reagendar** — gated `APPOINTMENTS_RESCHEDULE`. Abre el drawer de detalle en la acción Reagendar.
- 🚫 **Cancelar** — gated `APPOINTMENTS_CANCEL`. Abre el confirm de cancelación.

**Botón "+ Reservar cita"**: gated `<PermissionGuard anyOf={["APPOINTMENTS_CREATE"]}>`. Abre el **wizard de reserva**.

#### Estados (tabla de citas)

- **Empty (sin citas, sin filtro)**: ícono `CalendarClockRegular` + "Aún no hay citas. Reserva la primera para empezar a llenar la agenda." (el botón "Reservar cita" del toolbar cumple la función; no va dentro del EmptyState).
- **Empty con filtro doctor sin matches**: "Este doctor no tiene citas en el rango seleccionado."
- **Empty con filtro fecha (Hoy) sin matches**: "No hay citas para hoy con los filtros actuales."
- **Empty con filtro estado sin matches**: "Ninguna cita está en este estado."
- **Loading**: DataTable con 8 skeleton rows.
- **No-results** (búsqueda client-side sin matches): genérico de `DataTable`.
- **Refetching**: tabla `opacity: 0.55` + spinner top-right.
- **Error**: 5xx por `error.tsx` global. Soft-errors del create/cancel inline en el wizard/confirm.

#### Wizard de reserva (`AppointmentWizardDrawer`, 4 pasos)

`<Drawer size="medium">` con un **stepper** de 4 pasos. Cada paso valida antes de avanzar; el footer muestra `[ Atrás ] [ Siguiente ]` y, en el último, `[ Reservar ]`. El paso 3 (Slot) es el corazón: llama `POST /availability/compute` y pinta una **grilla de slots**.

**Stepper (cabecera del drawer):**
```
   ①Paciente ─── ②Producto+Doctor ─── ③Horario ─── ④Confirmar
```

**Paso 1 — Paciente**
```
                  ┌─────────────────────────────────────────────────┐
                  │  Reservar cita — Paciente                     ✕ │
                  │  ①━━━② ── ③ ── ④                                │
                  ├─────────────────────────────────────────────────┤
                  │  Paciente *                                     │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ 🔍 Buscar por nombre o contacto…         │   │
                  │  ├─────────────────────────────────────────┤   │
                  │  │ Ana Torres Quispe · +51 999 111 222      │   │
                  │  │ Luis Rojas · luis@correo.pe              │   │
                  │  └─────────────────────────────────────────┘   │
                  │  ¿No está en la lista? [ + Nuevo contacto ]     │
                  ├─────────────────────────────────────────────────┤
                  │                            [ Cancelar ] [ Sig.→]│
                  └─────────────────────────────────────────────────┘
```
- Buscador de `Person` (`GET /crm/persons/search?q=` o el listado de crm), resultado = `person_id`. Atajo "+ Nuevo contacto" abre el `PersonCreateDrawer` de crm (gated `PERSONS_CREATE`) y al crear, vuelve al wizard con el contacto seleccionado.
- Si el wizard se abrió **prefilled** desde el calendario (slot libre) ya trae `doctor_id/office_id/scheduled_for`; el paso 1 sigue siendo elegir paciente.

**Paso 2 — Producto + Doctor**
```
                  │  Reservar cita — Producto y doctor            ✕ │
                  │  ① ━━━②━━━ ③ ── ④                              │
                  │  Producto *                                     │
                  │  [ Limpieza dental (30 min)              ▾ ]    │
                  │  Sede (opcional)                                │
                  │  [ Todas las sedes                       ▾ ]    │
                  │  Doctor *                                       │
                  │  [ Dra. Ríos                             ▾ ]    │
                  │  Solo se listan doctores activos aptos para     │
                  │  la vertical del producto.                     │
                  │                            [ ←Atrás ] [ Sig.→ ]│
```
- **Producto** (`<Dropdown>` de `GET /catalog/products/active`): cada opción muestra el nombre + duración (`{duration_min} min`). La duración + la vertical del producto determinan qué doctores/slots aplican.
- **Sede** (opcional, `<Dropdown>` de `GET /clinic/branches/active`): acota la búsqueda de slots; "Todas las sedes" deja al cómputo elegir cualquier office apto.
- **Doctor** (`<Dropdown>` de `GET /staff/doctors/active`): **solo doctores `active=true` aptos para la vertical** del producto (decisión #3 del spec: `active=false` excluido de nuevas reservas). Si se elige un doctor que el backend luego rechaza por vertical/branch, el paso 3 vuelve vacío con el motivo.

**Paso 3 — Horario (grilla de slots de `/availability/compute`)**
```
                  │  Reservar cita — Horario                      ✕ │
                  │  ① ── ② ━━━③━━━ ④                              │
                  │  ‹  Semana 6–12 jun 2026  ›   [ Hoy ]           │
                  │  Slots de 30 min · Dra. Ríos · Limpieza        │
                  │  ┌──────┬──────┬──────┬──────┬──────┬──────┐   │
                  │  │ vie 6│ sáb 7│ dom 8│ lun 9│ mar10│ mié11│   │
                  │  ├──────┼──────┼──────┼──────┼──────┼──────┤   │
                  │  │ 09:00│      │      │ 09:00│ 09:00│ 08:00│   │
                  │  │ 09:30│      │      │ 09:30│ 09:30│ 08:30│   │
                  │  │ 10:00│      │      │ 10:00│      │ 09:00│   │
                  │  │[10:30]      │      │      │ 11:00│ 09:30│   │ ← seleccionado
                  │  │ 16:00│      │      │ 16:00│      │      │   │
                  │  └──────┴──────┴──────┴──────┴──────┴──────┘   │
                  │  Cada botón es un inicio de slot libre.         │
                  │  Consultorio: C-03 (Sede Lima Centro)          │
                  │                            [ ←Atrás ] [ Sig.→ ]│
```
- Al entrar al paso 3, dispara `POST /availability/compute { doctor_id, product_id, branch_id?, office_id?, from_date, to_date }` con el rango de la **semana visible** (default = semana de hoy, **client-only**). La respuesta `AvailabilityResponse { slots, duration_min, doctor_slot_duration_min }` se agrupa por fecha en columnas; cada `AvailabilitySlot { starts_at, ends_at, office_id, office_name, branch_name, ... }` es un **`<Button>`** etiquetado con la hora de inicio (en TZ del branch). Click selecciona el slot → guarda `scheduled_for = starts_at`, `office_id`, `branch_id`.
- **Navegación de semana** (`‹`/`›`/`Hoy`): re-consulta `/availability/compute` con el nuevo rango. La grilla muestra el office de cada slot (un slot trae su `office_name`); si varios offices aplican, el botón muestra el office en tooltip y se agrupa por hora.
- **Sin reagendamiento aquí**: este es el flujo de **creación**. El reagendamiento reusa este mismo paso de slot desde el detalle (ver Pantalla 4).

**Paso 4 — Confirmar**
```
                  │  Reservar cita — Confirmar                    ✕ │
                  │  ① ── ② ── ③ ━━━④                              │
                  │  Resumen                                        │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ Paciente   Ana Torres Quispe             │   │
                  │  │ Producto   Limpieza dental (30 min)      │   │
                  │  │ Doctor     Dra. Ríos                     │   │
                  │  │ Cuándo     vie 6 jun · 10:30–11:00       │   │
                  │  │ Dónde      Sede Lima Centro · C-03       │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Notas (opcional)                               │
                  │  [ ……………………………………………………………………………………………… ]    │
                  │  Origen: Asesor                                 │
                  ├─────────────────────────────────────────────────┤
                  │                       [ ←Atrás ] [ Reservar ]  │
                  └─────────────────────────────────────────────────┘
```
- Resumen read-only de los 4 datos + `<Textarea>` de notas. `source` se fija a `advisor` (o `admin`) según el actor; no es editable en UI. **Reservar** → `POST /appointments { person_id, doctor_id, office_id, product_id, scheduled_for, notes?, source }`. `branch_id`/`duration_min`/`status_id` los deriva el service (decisión del spec: branch del office, duración del product, estado inicial de la matriz).

##### Estados del wizard

- **Loading slots (paso 3)**: la grilla muestra **skeleton** de columnas-fecha + filas-hora (no spinner suelto). Hint "Buscando horarios disponibles…".
- **Sin slots (paso 3, empty)**: la grilla vacía + EmptyState "No hay horarios disponibles para esta semana con este doctor y producto." + sugerencias: "Prueba otra semana, otra sede o cambia de doctor." + botones rápidos `[ ‹ Semana anterior ]` / `[ Semana siguiente › ]`. Esto cubre los casos donde el cómputo devuelve `[]` (doctor inactivo, vertical no cubierta, semana sin bloques de disponibilidad).
- **Doctor inactivo / no apto** (cómputo devuelve `[]` por decisión #3 o invariante de vertical): mismo empty + nota "Este doctor no atiende esta vertical o no tiene disponibilidad. Elige otro doctor." (volver al paso 2).
- **Guardando (paso 4)**: footer `[ Reservando… ]` disabled; resumen disabled.
- **Error de conflicto (409/400 `SLOT_TAKEN`)**: si entre que se computó el slot y se confirma, otro lo tomó → `<MessageBar intent="error">"Ese horario acaba de ocuparse. Elige otro."` + volver al paso 3 y re-computar (los slots se refrescan). Mismo trato para `OFFICE_SLOT_TAKEN` ("El consultorio ya está ocupado en ese horario.").
- **Otros invariantes (400 con code)**: el `<MessageBar>` muestra el `detail` en español del backend: `DOCTOR_INACTIVE` ("El doctor seleccionado está inactivo."), `DOCTOR_NOT_APT_FOR_VERTICAL` ("El doctor no atiende la vertical de este producto."), `OFFICE_NOT_APT_FOR_VERTICAL` ("El consultorio no admite esta vertical."), `DOCTOR_NOT_IN_BRANCH`, `OFFICE_NOT_IN_BRANCH`, `NO_AVAILABILITY_BLOCK` ("El horario elegido no cae en un bloque de disponibilidad del doctor."), `OFFICE_CLOSED` ("El consultorio está cerrado en ese horario."). Defensa en profundidad: la UI ya limita las opciones, pero el backend re-valida y la UI muestra el motivo.
- **Success**: drawer cierra, toast "Cita reservada para {paciente} el {fecha}." y la tabla/calendario revalidan (`revalidateTag("scheduling:appointments")`).

#### Componentes Fluent UI (tabla + wizard)

| Concepto UI | Componente |
|---|---|
| Filtros | `<Dropdown>` + `nuqs useQueryState("doctor_id"/"status_id"/"branch_id"/"product_id")` + `<DatePicker>` para fecha |
| Chip filtro | `styles.chip` + `<Button icon={<DismissRegular />} />` (patrón `OfficesClient`) |
| Search | `<Input contentBefore={<SearchRegular />} />` (client-side) |
| Tabla | `<DataTable<AppointmentItem>>` + `useTableQuery({ queryKey: "scheduling:appointments", defaultSort: { field: "scheduled_for", order: "asc" } })` |
| Badge de estado | `<StatusBadge color={s.color}>{s.name}</StatusBadge>` (custom, contraste por luminancia) |
| Chip de origen | `<Badge appearance="outline">` "Bot"/"Asesor"/… |
| Botón primario | `<Button appearance="primary" icon={<AddRegular />}>` |
| Wizard | `<Drawer size="medium">` + stepper custom (4 pasos) + footer condicional |
| Buscador de paciente | `<Combobox>`/`SearchableOptionList` → `GET /crm/persons/search` |
| Dropdowns (producto/sede/doctor) | `<Dropdown>` de `/active` de cada módulo |
| Grilla de slots | **custom** (CSS grid, `makeStyles`, tokens) — botones por slot de `/availability/compute`; navegación de semana `<Button icon={<ChevronLeft/Right/>}>` + `[ Hoy ]` |
| Skeleton slots | `<Skeleton>` + `<SkeletonItem>` por celda |
| Notas | `<Textarea>` |
| Error / éxito | `<MessageBar intent="error"/"success">` |

---

### Pantalla 3 — `/scheduling/calendario` (grilla semanal/día) — decisión #2

Clon directo de la grilla bespoke del calendario de `staff` (mismo CSS grid, navegación, tokens), pero los bloques sólidos son **citas** (color = estado) y los huecos son **slots libres clickeables**. **Fluent no trae componente de calendario** y **no** se usa librería externa (igual binding que staff). Vistas: **semana** (default) y **día**. Fetch único: `GET /appointments/calendar?branch_id=&doctor_id=&from=&to=&view=` → `{ appointments: [...], free_slots: [...] }` (citas + slots libres computados en el rango).

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Calendario                                                                   │
│   Vista semanal de las citas y horarios disponibles.                           │
│   ┌──────────┐┌──────────┐ [Semana|Día]  ‹  Sem. 6–12 jun 2026  ›  [ Hoy ]    │
│   │Doctor:R.▾││Sede: L. ▾│                                                     │
│   └──────────┘└──────────┘  Leyenda: ●Agend ●Confi ●Recep ●Aten ◌slot libre  │
│   ┌────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐               │
│   │    │ vie 6▸│ sáb 7 │ dom 8 │ lun 9 │ mar10 │ mié11 │ jue12 │ ▸=hoy(client) │
│   ├────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤               │
│   │08:00      │       │       │       │       │▓▓▓▓▓▓▓│       │               │
│   │08:30      │       │       │       │       │▓Botox │       │               │
│   │09:00▓▓▓▓▓▓│       │       │◌libre │◌libre │▓09:00 │       │ ▓=cita        │
│   │09:30▓Ana  │       │       │◌      │◌      │▓Quispe│       │  (color=estado)│
│   │     ▓Limp │       │       │       │       │       │       │               │
│   │10:00▓▓▓▓▓▓│       │       │◌libre │       │       │       │ ◌=slot libre  │
│   │10:30◌libre│       │       │◌      │       │       │       │  (overlay)    │
│   │11:00▓▓▓▓▓▓│       │       │       │◌libre │       │       │               │
│   │11:30▓Pedro│       │       │       │◌      │       │       │               │
│   │ …  │       │       │       │       │       │       │       │               │
│   │16:00◌libre│       │       │◌libre │       │       │       │               │
│   └────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘               │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Anatomía de la grilla** (espeja staff, adaptado a citas):
- **Columnas** = Lun…Dom de la semana visible **con fecha real** ("vie 6", "sáb 7", …); en vista **Día**, una sola columna. La columna del **día de hoy** se resalta sutilmente (`▸`/fondo tenue), cálculo **client-only** (TZ). Header con rango ("Sem. 6–12 jun 2026"). Inicio de semana = lunes (constante `DAY_LABELS = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]`, reutilizada de clinic, índice = `day_of_week` Python 0=Lun).
- **Filas** = horas, rango configurable (default **07:00–21:00**), paso = `doctor.slot_duration_min` del doctor filtrado (default 30). Las horas se muestran en el **timezone del branch** filtrado.
- **Bloques de cita** (`▓`, color sólido = `status.color`): cada `Appointment` ocupa `[scheduled_for, scheduled_for + duration_min)` en su columna-fecha, etiquetado con hora + paciente + (producto). Click abre el **detalle** (Pantalla 4, drawer) y setea `?appointment_id=`. Las citas en estados `CANCELLED/NO_SHOW/RESCHEDULED` **no** se pintan (no ocupan; consistente con el cómputo de slots).
- **Slots libres** (`◌`, overlay tenue clickeable): los `free_slots` del rango se pintan como celdas-overlay con borde punteado. Click abre el **wizard prefilled** (`doctor_id`, `office_id`, `branch_id`, `scheduled_for` = inicio del slot) directo en el **paso 1 (Paciente)** — el resto ya viene resuelto. Requiere `APPOINTMENTS_CREATE`; sin el permiso, los slots libres se muestran pero no son clickeables (solo lectura).
- **Leyenda**: una fila de swatches con `name`+`color` de los estados visibles + el marcador `◌ slot libre`. Se deriva de `GET /scheduling/appointment-statuses/active` (los colores no se hardcodean).

> **Por qué hace falta un doctor (o sede) para ver slots libres**: el cómputo de disponibilidad es **por doctor + producto**. El calendario por defecto muestra **citas** de todos (o de la sede filtrada); los **slots libres** solo se pintan cuando hay un **doctor** filtrado (y, en el overlay→wizard, se elige el producto en el paso 2 — o, si el filtro de calendario incluye un producto, ya viene). Sin doctor filtrado, el calendario es solo lectura de citas (sin overlays de slot). El dropdown de doctor arriba habilita los overlays.

**Filtros del calendario** (deep-link + chip, mismo patrón que la tabla):
- **Doctor** (`?doctor_id=`): obligatorio para ver slots libres; opcional para ver solo citas.
- **Sede** (`?branch_id=`): acota las citas/offices y fija el `timezone` de render.
- (Producto opcional `?product_id=` para precisar los slots; si no, el wizard lo pide en el paso 2.)
- **Rango/vista** en URL state: `?from=YYYY-MM-DD&view=week|day` (bookmarkable, sobrevive refresh).

**Navegación temporal**: `‹`/`›` (semana/día atrás-adelante, re-fetch), `[ Hoy ]` (salta a la semana/día actual, **client-only**), toggle **Semana | Día**.

#### Estados (calendario)

- **Loading**: **skeleton de la grilla** (marco de columnas-fecha + filas-hora con celdas en gris animado), no spinner suelto.
- **Empty (semana sin citas ni slots)**: la grilla vacía + texto guía: "No hay citas ni horarios disponibles en esta semana. Cambia de doctor, de sede o de semana." Si hay doctor filtrado pero la semana está libre, los `◌ slot libre` aparecen y el texto es "Sin citas esta semana — los horarios libres están disponibles para reservar."
- **Sin doctor filtrado**: la grilla muestra citas pero **sin overlays de slot** + un hint "Elige un doctor para ver y reservar en sus horarios libres."
- **Refetching (cambio de semana/filtro)**: la grilla mantiene lo visible con `opacity: 0.55` + spinner top-right.
- **Error**: `<MessageBar intent="error">` arriba de la grilla con el `detail` del backend.
- **Read-only (sin `APPOINTMENTS_CREATE`)**: los bloques-cita siguen clickeables (ver detalle, si tiene `APPOINTMENTS_READ`), pero los `◌ slot libre` se ven sin ser clickeables. El ASESOR sí tiene `APPOINTMENTS_CREATE` (puede reservar desde un slot); un viewer con solo lectura no.

#### Componentes Fluent UI (calendario)

| Concepto UI | Componente |
|---|---|
| Grilla | **custom** (CSS grid con `makeStyles`, tokens) — no hay componente Fluent de calendario; no se usa librería externa |
| Filtros doctor/sede | `<Dropdown>` + `nuqs useQueryState("doctor_id"/"branch_id")` + chip |
| Toggle vista | `<TabList>` o `<ToggleButton>` "Semana"/"Día" |
| Navegación semana/día | `<Button icon={<ChevronLeft/Right Regular/>}>` + `[ Hoy ]` + (opcional) `<DatePicker>` "Ir a…" |
| Bloque de cita | `<Button>`/`<div>` posicionado, `style={{ backgroundColor: status.color }}`; click → detalle |
| Slot libre | celda-overlay con borde punteado (`tokens`), clickeable → wizard prefilled |
| Resaltado de "hoy" | clase aplicada **client-only** (`useEffect`/`useMemo`) — nunca en SSR (TZ) |
| Leyenda | swatches de `appointment-statuses/active` + `◌ slot libre` |
| Skeleton grid | `<Skeleton>` + `<SkeletonItem>` por celda |
| URL state | `nuqs useQueryState("from"/"view"/"doctor_id"/"branch_id")` |
| Error | `<MessageBar intent="error">` |

#### Plan incremental (binding — construir en este orden, dentro de F4)

> El calendario es el mayor riesgo de frontend del módulo (como en staff). Construirlo de una vez es la trampa. Orden:
> 1. **Iteración A (read primero)** — grilla estática (columnas-fecha + filas-hora) que **renderiza las citas** de la semana (bloques por color de estado), navegación semana/Hoy + toggle Semana/Día, leyenda, resaltado de "hoy" (client-only), estados loading/empty/error/read-only. Con esto el calendario ya **muestra** la agenda.
> 2. **Iteración B (slots libres + reserva)** — pintar los `◌ free_slots` como overlays clickeables → abrir el wizard prefilled. Requiere el wizard de F2 ya construido (de ahí que el calendario sea F4).
> 3. **Iteración C (refinamientos)** — vista Día pulida, tooltips de cita (paciente/producto/estado), drag-para-reagendar **diferido** (no MVP: reagendar se hace desde el detalle).

---

### Pantalla 4 — Detalle de cita (drawer `size="large"`): control de estado + timeline

Drawer abierto desde la tabla, el calendario o Mi agenda (deep-link `?appointment_id=`). Tres zonas: **cabecera** (datos de la cita + badge de estado), **control de estado** (shortcuts gated por la matriz) + acciones reschedule/cancel, y el **timeline** (history + changelog entrelazados, read-only). Reutiliza `TransitionControl` (crm) y el lenguaje visual del Timeline de crm.

```
              ┌──────────────────────────────────────────────────────────┐
              │  Cita de Ana Torres Quispe                  [●Agendada] ✕ │
              │  vie 6 jun 2026 · 10:30–11:00 (Lima)                       │
              │  Dra. Ríos · Limpieza dental (30 min) · Sede Lima C·C-03   │
              │  Origen: Asesor   ·   #ap_3f9c…                            │
              ├──────────────────────────────────────────────────────────┤
              │  Cambiar estado                                           │
              │  ┌────────────────────────────────────────────────────┐  │
              │  │ Atajos:  [ Confirmar ] [ Registrar llegada ]        │  │
              │  │          [ Iniciar atención ] [ No asistió ]        │  │
              │  │ Otro estado:  [ Selecciona…       ▾ ]  [ Cambiar ]  │  │
              │  │               └─ solo estados de la matriz          │  │
              │  │ Motivo (opcional): [ ……………………………………………………… ]      │  │
              │  └────────────────────────────────────────────────────┘  │
              │  ┌──────────────┐  ┌──────────────┐                       │
              │  │ 🔁 Reagendar │  │ 🚫 Cancelar  │                       │
              │  └──────────────┘  └──────────────┘                       │
              │  ──────────────────────────────────────────────────────  │
              │  Historial                                                │
              │  ── Hoy ───────────────────────────────────────────────  │
              │  ┌────────────────────────────────────────────────────┐  │
              │  │ 🔄 Cambio de estado            AP  hace 10 min       │  │
              │  │    Confirmada → En recepción                        │  │
              │  └────────────────────────────────────────────────────┘  │
              │  ┌────────────────────────────────────────────────────┐  │
              │  │ ✎ Cambio de datos              AP  hace 1 h          │  │
              │  │    Notas: "" → "Paciente llega 10 min antes"        │  │
              │  └────────────────────────────────────────────────────┘  │
              │  ── 5 jun 2026 ────────────────────────────────────────  │
              │  ┌────────────────────────────────────────────────────┐  │
              │  │ 🔄 Cambio de estado            AP  5 jun 16:20       │  │
              │  │    Agendada → Confirmada                            │  │
              │  └────────────────────────────────────────────────────┘  │
              │  ┌────────────────────────────────────────────────────┐  │
              │  │ ✨ Cita creada                 ⚙  5 jun 09:00       │  │
              │  │    → Agendada  ·  Origen: Asesor                    │  │
              │  └────────────────────────────────────────────────────┘  │
              ├──────────────────────────────────────────────────────────┤
              │  Editar notas / datos                       [ Cerrar ]    │
              └──────────────────────────────────────────────────────────┘
```

**Cabecera**: paciente + `StatusBadge` (color del estado); subtítulo con fecha/hora (TZ del branch, **client-only**), doctor + producto (duración) + sede·consultorio, `source` y un id corto. Si la cita es resultado de un reagendamiento (`previous_appointment_id`), un mini-link "↩ Viene de una cita reagendada" navega a la anterior (cadena).

**Control de estado** (gated `APPOINTMENTS_TRANSITION`):
- **Atajos** (`<Button>` por shortcut): "Confirmar" (→CONFIRMED), "Registrar llegada" (→CHECKED_IN), "Iniciar atención" (→IN_PROGRESS), "Atender" (→ATTENDED), "No asistió" (→NO_SHOW). **Cada atajo solo se renderiza si la matriz permite** ir del estado actual a su to-state (`GET /scheduling/appointment-statuses/{currentId}/transitions`). Si la matriz no lo permite, el atajo no aparece (no se muestra deshabilitado-confuso). Defensa en profundidad: el backend re-valida (`APPOINTMENT_TRANSITION_NOT_ALLOWED`).
- **"Otro estado"** (`TransitionControl`, clon de crm): `<Dropdown>` que **solo lista los estados permitidos** por la matriz desde el actual + `[ Cambiar ]`. Si el estado actual es `is_final`, todo el control se deshabilita con "Estado terminal — no admite cambios." (las citas finales mantienen la fila viva, registro histórico — NO se soft-deletean; diverge de crm).
- **Motivo (opcional)**: `<Input>` que viaja como `reason` en `POST /appointments/{id}/transition { to_status_id, reason? }` (o el shortcut equivalente).
- **Side-effects visibles**: al "Atender" (→ATTENDED), si el paciente aún no es cliente, el backend dispara `crm.promote_to_customer` (cierra lead ganado + crea cliente) y emite `LeadActivity(APPOINTMENT_ATTENDED)`; la UI muestra un toast "Cita atendida. {Paciente} fue promovido a cliente." (o solo "Cita atendida." si ya era cliente). Es informativo; el efecto vive en el service, misma transacción.

**Acciones reschedule / cancel** (botones aparte):
- 🔁 **Reagendar** (gated `APPOINTMENTS_RESCHEDULE`): abre el **wizard de slot** (reusa el **paso 3 (Horario)** del wizard de reserva, prefilled con el mismo producto/doctor; permite cambiar doctor/office) → `POST /appointments/{id}/reschedule { new_scheduled_for, new_doctor_id?, new_office_id?, reason? }`. El service marca la actual `RESCHEDULED` y crea la nueva con `previous_appointment_id`. **No** está sujeto a `min_hours_to_cancel`. Tras éxito, el drawer salta a la **nueva** cita y la vieja queda en el history como reagendada.
- 🚫 **Cancelar** (gated `APPOINTMENTS_CANCEL`): `<ConfirmDialog>` con `<Textarea>` motivo → `POST /appointments/{id}/cancel { reason? }`. Si `(scheduled_for - now) < min_hours_to_cancel` y el actor **no** tiene `APPOINTMENTS_CANCEL_OVERRIDE` → 400 `CANCEL_TOO_LATE` inline: "No se puede cancelar: faltan menos de {N} horas para la cita. Pide a un administrador que la cancele." Si el actor tiene override, el confirm muestra una advertencia extra "Estás cancelando con menos de {N} h de antelación (cancelación forzada)." y procede.

**Editar notas / datos** (footer, gated `APPOINTMENTS_UPDATE`): `PUT /appointments/{id}` para columnas no-estado (notes, y reasignar doctor/office a uno libre — re-valida invariantes). `scheduled_for` **no** se edita aquí (eso es Reagendar). Cada cambio in-place se registra en `AppointmentChangeLog` y aparece como tarjeta "✎ Cambio de datos" en el timeline. Los cambios de estado **no** van al changelog (van al history).

#### Timeline (history + changelog entrelazados)

Feed cronológico read-only, **entrelaza** `AppointmentStatusHistory` (cambios de estado) y `AppointmentChangeLog` (cambios de columnas), ordenado por `changed_at` descendente, **agrupado por día** ("Hoy"/"Ayer"/"{fecha}", frontera de día **client-only**). Mismo lenguaje visual que el Timeline de crm (tarjetas tipadas con ícono de color, actor, timestamp relativo), pero **sin composer** (no es editable — es traza de auditoría). Tarjetas:

| Tipo de evento | Origen | Ícono Fluent | Color (token / estado) | Contenido |
|---|---|---|---|---|
| **Cita creada** | history (`from=NULL`) | `SparkleRegular` | `tokens.colorPaletteGreenForeground2` | "→ {estado inicial} · Origen: {source}" |
| **Cambio de estado** | history (`from→to`) | `ArrowSwapRegular` | `tokens.colorPaletteTealForeground2` | "{from} → {to}" (con los colores de cada estado) + motivo si hay |
| **Cancelada** | history (→CANCELLED) | `DismissCircleRegular` | `tokens.colorPaletteRedForeground1` | "Cancelada" + motivo (`cancellation_reason`) |
| **Reagendada** | history (→RESCHEDULED) | `CalendarSyncRegular` | `tokens.colorNeutralForeground3` | "Reagendada → nueva cita" (link a la nueva) |
| **Cambio de datos** | changelog | `EditRegular` | `tokens.colorPaletteMarigoldForeground2` | "{campo}: {valor previo} → {valor nuevo}" (campos serializados; FK→nombre resuelto) + motivo si hay |

- **Actor**: `<Avatar size={24} name={actor.full_name} color="colorful">` (inicial) + nombre. Eventos automáticos (bot/sistema, `changed_by` NULL) → avatar `⚙` "Sistema".
- **Timestamp relativo**: `formatRelative(changed_at)` ("hace 10 min", "ayer 16:20", "5 jun 09:00") — **client-only** (helper compartido de crm en `lib/utils/date.ts`); `<Tooltip>` con la fecha absoluta al hover.
- **Serialización del changelog**: `previous_value`/`new_value` vienen como string del backend (UUID/ISO8601/texto). Para `doctor_id`/`office_id`/`product_id` la UI **resuelve el id a nombre** vía un batch map (igual que las denormalizaciones de la tabla); para `notes`/`scheduled_for` se muestra el valor formateado (la fecha en TZ del branch). Si no se puede resolver un id, se muestra el id corto.

##### Estados del timeline

- **Loading**: 3–4 `EventCard` skeletons.
- **Empty**: improbable (toda cita tiene al menos su evento "creada"); si llegara vacío, "Sin historial." 
- **Error**: `<MessageBar intent="error">` arriba del feed.

#### Componentes Fluent UI (detalle de cita)

| Concepto UI | Componente |
|---|---|
| Drawer | `<Drawer size="large">` + `nuqs useQueryState("appointment_id")` |
| Badge de estado (cabecera) | `<StatusBadge color={status.color}>` |
| Atajos de estado | `<Button>` por shortcut (renderizado solo si la matriz lo permite) |
| TransitionControl | custom (clon de crm) — `<Dropdown>` con solo estados permitidos + `<Button>` |
| Reagendar | `<Button>` → reusa el **paso 3 (Horario)** del wizard → `POST /reschedule` |
| Cancelar | `<Button>` + `<ConfirmDialog>` con `<Textarea>` motivo → `POST /cancel` (maneja `CANCEL_TOO_LATE`) |
| Editar notas/datos | `PUT /appointments/{id}` (gated `APPOINTMENTS_UPDATE`) |
| Timeline | feed custom (lenguaje del Timeline de crm) — `EventCard` memoizada + `DayGroup` (client-only) |
| Tarjeta de evento | `<Card>` + ícono Fluent + `<Avatar>` + timestamp relativo |
| Timestamp relativo | `formatRelative(iso)` (client-only) + `<Tooltip>` |
| Error / éxito | `<MessageBar intent="error"/"success">` |

---

### Pantalla 5 — `/scheduling/mi-agenda` (vista del doctor, read)

Self-service del doctor logueado (molde `/me/agenda` de staff). **El mismo calendario** de la Pantalla 3 en **modo self** (read-focused): muestra **solo sus citas** (`GET /me/calendar`, gated `APPOINTMENTS_READ` + scoping del service por `current.doctor.id`) + la lista `POST /me/appointments/list` como vista alterna. El doctor **no reserva** (no tiene `APPOINTMENTS_CREATE`); puede **transicionar** sus citas (tiene `APPOINTMENTS_TRANSITION`): confirmar / registrar llegada / iniciar / atender / no-show desde el detalle.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Mi agenda                                                                    │
│   Tus citas como doctor.                                                        │
│   [Semana|Día|Lista]   ‹  Sem. 6–12 jun 2026  ›   [ Hoy ]                       │
│   Leyenda: ●Agendada ●Confirmada ●En recepción ●En atención ●Atendida          │
│   ┌────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐               │
│   │    │ vie 6▸│ sáb 7 │ dom 8 │ lun 9 │ mar10 │ mié11 │ jue12 │ ▸=hoy(client) │
│   ├────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤               │
│   │09:00▓▓▓▓▓▓│       │       │▓▓▓▓▓▓▓│▓▓▓▓▓▓▓│       │       │               │
│   │09:30▓Ana  │       │       │▓Luis  │▓Carla │       │       │ ▓=tu cita     │
│   │10:00▓Limp │       │       │▓Cons. │▓Cons. │       │       │  (color=estado)│
│   │ …  │       │       │       │       │       │       │       │  sin slots ◌  │
│   └────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘               │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Sin overlays de slot libre** (`◌`): Mi agenda es read de "lo que tengo", no una superficie de reserva (el doctor no agenda). Solo bloques-cita.
- **Vistas**: Semana / Día / **Lista** (la lista usa `POST /me/appointments/list`, columnas como la tabla de citas pero scoped al doctor: Fecha/hora · Paciente · Producto · Sede·Cons · Estado).
- **Click en una cita** → el **detalle** (Pantalla 4) con el control de estado habilitado para los shortcuts que su rol permite (`APPOINTMENTS_TRANSITION`). El doctor **no** ve Reagendar/Cancelar (no tiene esos permisos) — esos botones se ocultan por gating.
- **Scoping anti-IDOR**: el backend resuelve el `doctor` desde `CurrentAuth.user.id`; si el user no es doctor → 403 `NOT_A_DOCTOR` (la UI muestra "Esta vista es solo para doctores."). El componente del calendario se parametriza por `mode: "admin" | "self"` (igual que staff): en self, el `doctorId` viene implícito del token, no de la URL, y la familia de endpoints es `/me/*`. Construir el calendario en F4 desacoplado del origen de datos para no reescribirlo aquí.

#### Estados (mi-agenda)

- **Loading**: skeleton de la grilla / skeleton de filas en vista Lista.
- **Empty (semana sin citas)**: "No tienes citas esta semana." + nota "Tus próximas citas aparecerán aquí cuando el equipo las agende."
- **No es doctor (403)**: "Esta vista es solo para doctores." (no debería ocurrir: el ítem de menú está gateado por `MY_APPOINTMENTS_READ`).
- **Refetching / Error**: igual que el calendario.

#### Componentes Fluent UI (mi-agenda)

| Concepto UI | Componente |
|---|---|
| Calendario | el mismo de la Pantalla 3 en `mode="self"` (sin overlays de slot) |
| Vista Lista | `<DataTable<MyAppointmentItem>>` + `useTableQuery({ queryKey: "scheduling:my-appointments", fetcher: listMyAppointments })` |
| Toggle vista | `<TabList>`/`<ToggleButton>` "Semana"/"Día"/"Lista" |
| Navegación | `<Button icon={<ChevronLeft/Right/>}>` + `[ Hoy ]` |
| Badge de estado | `<StatusBadge>` |
| Click cita → detalle | `nuqs useQueryState("appointment_id")` (mismo drawer) |

---

## Decisiones de UI (cierres)

### Catálogo + matriz como clon de crm, con grilla `from×to` adicional
El catálogo `AppointmentStatus` y su editor de transiciones son un clon de `/crm/estados-lead` (multiselect "Transiciones permitidas hacia…" dentro del drawer). **La diferencia**: scheduling **sí** construye la vista de **grilla `from × to` con checkboxes** (lo que crm marcó diferible), accesible por "Ver matriz". Ambos editores pegan al **mismo** endpoint `PUT /appointment-statuses/{from_id}/transitions` (REPLACE de aristas de salida por estado). Sin `is_won` (eso es de crm): los flags son `is_initial`/`is_final`/`is_active_attention`.

### Detalle de cita en drawer, no página con tabs
La cita es una entidad con estado + timeline + dos acciones; no tiene la multi-superficie densa de Office/Doctor/Person que justifica una página con tabs. Drawer `size="large"` con `?appointment_id=` deep-linkable. Misma regla-precedente: el peso del sub-recurso manda la forma; la cita no llega al umbral de "página".

### `TransitionControl` + atajos: solo lo que la matriz permite
Los atajos de estado y el dropdown "Otro estado" se pueblan **únicamente** con los estados a los que la matriz permite ir desde el actual (`GET /appointment-statuses/{currentId}/transitions`). El usuario **no puede elegir una transición inválida** (no aparece) — el backend re-valida (`APPOINTMENT_TRANSITION_NOT_ALLOWED`) como defensa en profundidad. Estado `is_final` → control deshabilitado. Idéntico patrón a `TransitionControl` de crm.

### Las citas en estados finales NO se soft-deletean (diverge de crm)
A diferencia de crm (donde un lead `is_final` soft-deletea su fila viva), una cita en estado final (ATTENDED/CANCELLED/NO_SHOW/RESCHEDULED) **mantiene la fila viva** (registro histórico). El soft-delete (`DELETE`) es solo "error de captura". En UI: las citas finales siguen apareciendo en la tabla/detalle (con su badge de estado), pero **no** se pintan en el calendario ni ocupan tiempo en el cómputo de slots.

### Slots on-the-fly: nunca una "tabla de slots" en UI
La grilla de slots del wizard y los overlays del calendario se computan en cada apertura (`/availability/compute`, `/appointments/calendar`) — no hay una entidad "slot" que listar/editar. Si el cómputo devuelve `[]`, el empty del wizard/calendario guía a cambiar semana/doctor/sede (no es un error).

### Reagendar reusa el paso de slot del wizard
El reagendamiento desde el detalle reabre el **paso 3 (Horario)** del wizard (mismo componente, prefilled con producto/doctor), no una pantalla nueva. Crea una nueva cita con `previous_appointment_id` y marca la vieja RESCHEDULED. No sujeto a `min_hours_to_cancel`.

### TZ y "hoy" siempre client-only; horas en TZ del branch
Toda fecha que afecte el render (resaltar "hoy" en la grilla, default de fecha del wizard/calendario, timestamps relativos del timeline, citas vencidas) se computa **client-only** (`useEffect`/`useMemo`, no SSR). Las **horas de las citas/slots** se renderizan en el **timezone del branch** de la cita (no el del navegador): el backend manda `scheduled_for` UTC + `branch.timezone`, el front formatea con `Intl.DateTimeFormat(..., { timeZone })`. El servidor en UTC desfasaría el día en Lima (UTC-5) — bug recurrente de staff/crm.

### Denormalizadas no son sortable/filterable por texto (hotfix `cd10c78`)
`person_name`/`doctor_name`/`product_name`/`branch_office`/`status` son denormalizados (batch, sin N+1) y NO están en `ALLOWED_FIELDS` → `isSortable: false`; los filtros van por **id** (FK real → JOIN/WHERE), no por texto. Solo `scheduled_for` (columna real indexada) es server-sortable; `defaultSort` y `searchFields` solo columnas reales. La búsqueda visible por paciente es client-side.

### Doctor `active=false` excluido de nuevas reservas (decisión #3)
El dropdown de doctor del wizard solo ofrece doctores activos aptos para la vertical; el cómputo de slots devuelve `[]` para un doctor inactivo. El backend re-valida con `DOCTOR_INACTIVE`. (Diverge de staff, donde `active` no es gate de auto-gestión; en scheduling sí es gate de nueva reserva. Las citas existentes de un doctor que se desactiva quedan intactas.)

### Sin i18n framework por ahora
Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive
Mismo criterio que clinic/staff/crm (template optimizado para desktop interno): sidebar colapsado por default; DataTable scrollea horizontal; drawers a 100% del width en mobile; el **calendario** en pantallas angostas scrollea horizontal las 7 columnas o cae a la vista **Día** (selector de día); el wizard (drawer) apila sus pasos verticalmente. No se diseñan pantallas mobile-first separadas.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, IANA, CSS classes) en inglés — solo los textos visibles van traducidos. Glosario clave: **Appointment = Cita** (femenino), **AppointmentStatus = Estado de cita**, **Doctor** (masculino), **Paciente** (masculino genérico), **Consultorio** (masculino), **Sede** (femenino), **Producto** (masculino), **Slot = horario/horario disponible**, **Reagendar / Cancelar / Confirmar**.

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Sidebar — | |
| Grupo | "Agenda" |
| Items | "Citas" · "Calendario" · "Mi agenda" · "Estados de cita" |
| — Estados de cita — | |
| Page title | "Estados de cita" |
| Page subtitle | "Configura los estados de una cita y sus transiciones." |
| Botón ver matriz | "Ver matriz" |
| Botón crear | "+ Nuevo estado" |
| Drawer title | "Nuevo estado de cita" / "Editar estado de cita" / "Detalle de estado" |
| Labels | "Código" / "Nombre" / "Descripción" / "Color" / "Orden" |
| Hint código | "MAYÚSCULAS, sin espacios (ej. IN_PROGRESS)." |
| Flag inicial | "Estado inicial" |
| Hint inicial | "Solo un estado puede ser el inicial." |
| Aviso reemplazo inicial | "Reemplazará al estado inicial actual: {nombre}." |
| Flag final | "Estado final (terminal)" |
| Flag en atención | "En atención ahora" |
| Hint en atención | "Marca el estado que representa una cita en curso (vista operativa)." |
| Título matriz (fila) | "Transiciones permitidas hacia…" |
| Hint matriz (fila) | "Desde '{estado}' una cita podrá pasar a los estados marcados." |
| Matriz deshabilitada (final) | "Un estado final no admite transiciones de salida." |
| Matriz (grilla) title | "Matriz de transiciones" |
| Matriz (grilla) subtitle | "Marca a qué estados puede pasar una cita desde cada estado de origen." |
| Matriz (grilla) leyenda | "Las filas en gris son estados finales (sin salida)." |
| Botón guardar matriz | "Guardar matriz" / "Guardando…" |
| Toast matriz guardada | "Matriz de transiciones guardada." |
| Empty catálogo | "Aún no hay estados de cita. Crea el primero (marca uno como inicial)." |
| Error en uso | "No se puede eliminar: hay citas en este estado." |
| — Citas (tabla) — | |
| Page title | "Citas" |
| Page subtitle | "Agenda, consulta y gestiona las citas de la clínica." |
| Botón crear | "+ Reservar cita" |
| Search placeholder | "Buscar por paciente…" |
| Filtro doctor (placeholder) | "Todos los doctores" |
| Filtro estado (placeholder) | "Todos los estados" |
| Filtro sede (placeholder) | "Todas las sedes" |
| Filtro producto (placeholder) | "Todos los productos" |
| Filtro fecha (default) | "Hoy" |
| Chip filtro | "Doctor: {nombre} ✕" / "Estado: {nombre} ✕" / "Sede: {nombre} ✕" / "Producto: {nombre} ✕" / "Fecha: {DD mmm YYYY} ✕" |
| Columnas | "Fecha/hora" / "Paciente" / "Doctor" / "Producto" / "Sede · Consultorio" / "Estado" / "Origen" |
| Empty (sin citas) | "Aún no hay citas. Reserva la primera para empezar a llenar la agenda." |
| Empty (filtro doctor) | "Este doctor no tiene citas en el rango seleccionado." |
| Empty (filtro fecha hoy) | "No hay citas para hoy con los filtros actuales." |
| Empty (filtro estado) | "Ninguna cita está en este estado." |
| No-results genérico | "No hay resultados con los filtros actuales" / "Prueba quitar algún criterio o revisa la ortografía." |
| RowAction ver | "Ver detalle" |
| RowAction reagendar | "Reagendar" |
| RowAction cancelar | "Cancelar" |
| Origen (chips) | "Bot" / "Asesor" / "Admin" / "Importación" / "API" |
| — Wizard de reserva — | |
| Drawer title (por paso) | "Reservar cita — Paciente" / "— Producto y doctor" / "— Horario" / "— Confirmar" |
| Pasos (stepper) | "Paciente" · "Producto y doctor" · "Horario" · "Confirmar" |
| Label paciente | "Paciente" |
| Search paciente | "Buscar por nombre o contacto…" |
| Atajo nuevo contacto | "+ Nuevo contacto" |
| Label producto | "Producto" |
| Label sede (opcional) | "Sede (opcional)" |
| Label doctor | "Doctor" |
| Hint doctor | "Solo se listan doctores activos aptos para la vertical del producto." |
| Encabezado slots | "Slots de {N} min · {doctor} · {producto}" |
| Hint slots | "Cada botón es un inicio de horario disponible." |
| Buscando slots | "Buscando horarios disponibles…" |
| Empty slots | "No hay horarios disponibles para esta semana con este doctor y producto." |
| Sugerencia slots | "Prueba otra semana, otra sede o cambia de doctor." |
| Empty slots (doctor no apto) | "Este doctor no atiende esta vertical o no tiene disponibilidad. Elige otro doctor." |
| Resumen (labels) | "Paciente" / "Producto" / "Doctor" / "Cuándo" / "Dónde" |
| Label notas | "Notas (opcional)" |
| Botón reservar / reservando | "Reservar" / "Reservando…" |
| Botón siguiente / atrás | "Siguiente" / "Atrás" |
| Toast reservado | "Cita reservada para {paciente} el {fecha}." |
| Error slot tomado | "Ese horario acaba de ocuparse. Elige otro." |
| Error office tomado | "El consultorio ya está ocupado en ese horario." |
| Error doctor inactivo | "El doctor seleccionado está inactivo." |
| Error doctor no apto | "El doctor no atiende la vertical de este producto." |
| Error office no apto | "El consultorio no admite esta vertical." |
| Error sin bloque | "El horario elegido no cae en un bloque de disponibilidad del doctor." |
| Error office cerrado | "El consultorio está cerrado en ese horario." |
| — Calendario — | |
| Page title | "Calendario" |
| Page subtitle | "Vista semanal de las citas y horarios disponibles." |
| Toggle vista | "Semana" / "Día" |
| Navegación | "‹" / "›" / "Hoy" |
| Leyenda slot libre | "slot libre" |
| Hint sin doctor | "Elige un doctor para ver y reservar en sus horarios libres." |
| Empty (semana vacía) | "No hay citas ni horarios disponibles en esta semana. Cambia de doctor, de sede o de semana." |
| Empty (semana libre con doctor) | "Sin citas esta semana — los horarios libres están disponibles para reservar." |
| — Detalle de cita — | |
| Drawer title | "Cita de {paciente}" |
| Subtítulo | "{fecha} · {hora_inicio}–{hora_fin} ({tz}) · {doctor} · {producto} · {sede}·{consultorio}" |
| Link cita anterior | "↩ Viene de una cita reagendada" |
| Sección estado | "Cambiar estado" |
| Atajos | "Confirmar" / "Registrar llegada" / "Iniciar atención" / "Atender" / "No asistió" |
| Label otro estado | "Otro estado" |
| Botón cambiar | "Cambiar" / "Cambiando…" |
| Estado terminal | "Estado terminal — no admite cambios." |
| Label motivo | "Motivo (opcional)" |
| Botón reagendar | "Reagendar" |
| Botón cancelar | "Cancelar" |
| Confirm cancelar (título) | "¿Cancelar esta cita?" |
| Confirm cancelar (body) | "Se marcará como cancelada. Indica el motivo (opcional)." |
| Error cancelación tardía | "No se puede cancelar: faltan menos de {N} horas para la cita. Pide a un administrador que la cancele." |
| Aviso override | "Estás cancelando con menos de {N} h de antelación (cancelación forzada)." |
| Toast atendida (promovido) | "Cita atendida. {Paciente} fue promovido a cliente." |
| Toast atendida (ya cliente) | "Cita atendida." |
| Editar notas/datos | "Editar notas / datos" |
| — Timeline — | |
| Título | "Historial" |
| Encabezados de día | "Hoy" / "Ayer" / "{DD mmm YYYY}" |
| Tarjeta creada | "→ {estado} · Origen: {source}" |
| Tarjeta cambio estado | "{from} → {to}" |
| Tarjeta cancelada | "Cancelada" |
| Tarjeta reagendada | "Reagendada → nueva cita" |
| Tarjeta cambio datos | "{campo}: {valor previo} → {valor nuevo}" |
| Actor sistema | "Sistema" |
| Empty timeline | "Sin historial." |
| — Mi agenda — | |
| Page title | "Mi agenda" |
| Page subtitle | "Tus citas como doctor." |
| Toggle vista | "Semana" / "Día" / "Lista" |
| Empty | "No tienes citas esta semana. Tus próximas citas aparecerán aquí cuando el equipo las agende." |
| No es doctor (403) | "Esta vista es solo para doctores." |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Botón guardar / guardando | "Guardar" / "Guardando…" |
| Botón cancelar | "Cancelar" |
| Botón cerrar (view) | "Cerrar" |
| Loading placeholder en inputs | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |

### Concordancia de género

- **Cita** es **femenino**: "Nueva cita" (se usa "Reservar cita"), "la cita", "Cancelar esta cita", "Cita atendida", "Cita reservada".
- **Estado** es **masculino**: "Nuevo estado", "el estado", "este estado", "Estado terminal".
- **Doctor / Paciente / Producto / Consultorio / Horario / Slot / Motivo / Origen** son **masculino**: "el doctor", "el paciente", "el producto", "el consultorio", "este horario", "el motivo", "el origen".
- **Sede** es **femenino**: "la sede", "esta sede".
- En confirm dialogs mantener concordancia: "¿Cancelar **la** cita?" / "Reagendar **la** cita".

### Etiquetas de estado de cita (`AppointmentStatus`)

`code` (slug) en inglés, etiqueta visible en español (del seed). Color del catálogo (no hardcodeado):

| `code` | Etiqueta | Color seed |
|---|---|---|
| `SCHEDULED` | "Agendada" | #3B82F6 (azul) |
| `CONFIRMED` | "Confirmada" | #06B6D4 (cian) |
| `CHECKED_IN` | "En recepción" | #F59E0B (ámbar) |
| `IN_PROGRESS` | "En atención" | #8B5CF6 (violeta) |
| `ATTENDED` | "Atendida" | #22C55E (verde) |
| `NO_SHOW` | "No asistió" | #EF4444 (rojo) |
| `CANCELLED` | "Cancelada" | #6B7280 (gris) |
| `RESCHEDULED` | "Reagendada" | #9CA3AF (gris claro) |

> **Casing del `code` (RESUELTO)**: los codes del catálogo de estado son **MAYÚSCULAS sin pattern slug**, espejando `crm.LeadStatus` (NUEVO/CONTACTADO/…). La etiqueta visible va en español (del seed). El `code` es inmutable (los shortcuts del service resuelven por code).

### Etiquetas de `source` (origen de la cita)

| `source` | Etiqueta |
|---|---|
| `bot` | "Bot" |
| `advisor` | "Asesor" |
| `admin` | "Admin" |
| `import` | "Importación" |
| `api` | "API" |

### Sin i18n framework por ahora
Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm).

## Mapeo a fases de implementación (checklist de UI F0–F5)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md) y la spec §10 F0–F5). Cada checkbox es una tarea de UI.

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: grupo "Agenda" en `NAV_ITEMS` con 4 children (Citas / Calendario / Mi agenda / Estados de cita), gate `MENU-SCHEDULING` + permiso por child; íconos Fluent verificados con fallback (`CalendarLtrRegular`/`CalendarClockRegular`/`CalendarWeekStartRegular`/`PersonCalendarRegular`/`TagRegular`).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.SCHEDULING` (appointment-statuses, transitions, availability/compute, availability/check-slot, appointments, appointments/calendar, transition + shortcuts, me/appointments, me/calendar, from-bot).
- [ ] `types/scheduling.types.ts`: interfaces espejo de Pydantic (`AppointmentStatusItem`/`Option`, `AppointmentStatusTransition`, `AppointmentItem`/`Detail`, `AppointmentStatusHistoryItem`, `AppointmentChangeLogItem`, `AvailabilityRequest`, `AvailabilitySlot`, `AvailabilityResponse`, `MyAppointmentItem`, enum `source`).
- [ ] `lib/schemas/scheduling.schema.ts`: Zod de appointment-status (code MAYÚSCULAS), wizard (por paso), transition, reschedule, cancel.
- [ ] Reusar `formatRelative` (client-only) de crm; reusar `DAY_LABELS` de clinic; reusar/parametrizar `StatusBadge`, `TransitionControl` y `SearchableOptionList`. (Traducción ya hecha.)

### F1 — AppointmentStatus + matriz
- [ ] **Pantalla 1** `/scheduling/estados`: lista (molde `VerticalsClient`) + `AppointmentStatusDrawer` (CRUD, flags `is_initial` único / `is_final` / `is_active_attention`, slug pattern) + `StatusMatrixEditor` (multiselect → `PUT /transitions`) + **grilla `from×to`** ("Ver matriz") + estados empty/error + confirm delete (409 `APPOINTMENT_STATUS_IN_USE`).
- [ ] `StatusBadge` consume el `color` del catálogo (contraste por luminancia).
- [ ] Migración backend `0020_scheduling_status` (no toca UI).

### F2 — Appointment + availability + booking
- [ ] **Pantalla 2** `/scheduling/citas`: tabla con columnas denormalizadas (NO sortable las denorm; solo `scheduled_for`) + filtros doctor/estado/sede/producto/fecha (chip + deep-link) + búsqueda client-side por paciente + RowActions (ver/reagendar/cancelar gated) + estados.
- [ ] **Wizard de reserva** (`AppointmentWizardDrawer`, 4 pasos): Paciente (search crm) → Producto+Doctor (active+apto) → **Slot** (grilla de `/availability/compute`, navegación de semana) → Confirmar (`POST /appointments`). Estados loading/sin-slots/conflicto (`SLOT_TAKEN`)/invariantes/success.
- [ ] Migración backend `0021_scheduling_appointment` (no toca UI).

### F3 — Lifecycle + audit
- [ ] **Pantalla 4** Detalle de cita (drawer `size=large`): cabecera + control de estado (atajos + `TransitionControl` gated por la matriz) + Reagendar (reusa paso Slot) + Cancelar (confirm + `CANCEL_TOO_LATE`/override) + Editar notas/datos (`PUT`).
- [ ] **Timeline** (history + changelog entrelazados): `EventCard` por tipo + `DayGroup` (client-only) + resolución de ids a nombres en el changelog + estados.
- [ ] Reflejar el side-effect attend→promote (toast informativo).

### F4 — Calendar grid (decisión #2)
- [ ] **Pantalla 3** `/scheduling/calendario`: grilla semanal/día (Iteración A: render de citas por color de estado + navegación + leyenda + "hoy" client-only; Iteración B: overlays de slot libre → wizard prefilled; Iteración C: vista Día + tooltips). Endpoints inyectables (anticipar `mode="self"`).
- [ ] **Pantalla 5** `/scheduling/mi-agenda`: el calendario en `mode="self"` (sin overlays de slot) + vista Lista (`POST /me/appointments/list`) + gating `MY_APPOINTMENTS_READ`/403 `NOT_A_DOCTOR`.

### F5 — Bot facade + tools (sin UI nueva)
- [ ] Sin pantallas. El origen `bot` ya se renderiza como chip "Bot" en la tabla y como "Origen: Bot" en el timeline desde F2/F3 (las citas creadas por el bot aparecen en la misma UI sin trabajo extra).
