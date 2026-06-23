# Módulo `calendar` — UI design

> **Última actualización**: 2026-06-22
> **Audiencia**: developer implementando las pantallas de `calendar` en `frontend/src/app/(main)/clinic/calendarios-externos/` (config de la clínica) y el overlay en la grilla `frontend/src/app/(main)/scheduling/_components/CalendarGrid.tsx` (la monta `scheduling/calendario/CalendarClient`).
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts), la **spec autoritativa** (`C:/tmp/calendar_spec.md`) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). Decisión de arquitectura en [ADR-014](../../decisions/ADR-014-external-calendar-integration.md); diseño consolidado (mockups base de la conexión + overlay) en [`design.md`](./design.md) (§8). Adaptador agnóstico = molde [ADR-005](../../decisions/ADR-005-agnostic-bot-engine.md); tokens OAuth en Secret Manager = [ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md).

> **Alineación con clinic/staff/crm/conversations/scheduling (módulos gold-standard ya diseñados/en prod)**: `calendar` reutiliza directamente los patrones que esos módulos dejaron como precedente del template y **no inventa un estilo nuevo** (regla de la metodología: consistencia con lo shippeado **>** estilo nuevo). En concreto:
> - **La vista de config de la clínica** (`/clinic/calendarios-externos`) vive en el **grupo "Clínica"** del sidebar (junto a Sedes/Consultorios) y reusa el shell de página con header + toolbar de `clinic`. La sección de **mapeo calendario→sede** es un clon de superficie de la tab `Horarios`/`Excepciones` de `OfficeDetailPage` (`OfficeOperatingHoursTab`/`OfficeClosuresTab`): **filas de configuración con `<Dropdown>` + `<Switch>` + un solo botón "Guardar"** (bulk replace atómico, igual que `PUT /offices/{id}/operating-hours`).
> - **Las "conexiones como cards"** reusan el lenguaje de las tarjetas de cuenta de **`conversations`** (Canales / `ChannelAccount`): ícono del proveedor + identidad (`account_email`) + badge de salud + acciones de reconectar/desconectar. El flujo OAuth (redirect → callback público → vuelta a la config) espeja el de conectar un canal de WhatsApp.
> - **El overlay de eventos externos** se dibuja sobre la **grilla bespoke de `scheduling`** (`CalendarGrid`, F4) como una **capa visual distinta** (atenuada/rayada), reutilizando los helpers de solapamiento (`layoutOverlaps`) y de TZ (`calendarWeek.ts`) ya existentes. **No** crea una grilla nueva ni introduce una librería de calendario externa.
> - **El aviso suave en el `BookingWizard`** (F2) reusa el `<MessageBar intent="info">` del paso 3 (Horario) del wizard de `scheduling`.

> **Contexto de diseño (regla del template, no negociable)**:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Los colores de salud de conexión y la distinción medisage-vs-externo salen de **tokens Fluent** (`tokens.colorPaletteGreenForeground1`, `tokens.colorPaletteYellowForeground1`, `tokens.colorPaletteRedForeground1`, `tokens.colorNeutralForeground3`, `tokens.colorNeutralStroke2`), nunca de un hex hardcodeado fuera del design system. No se introduce ninguna librería de calendario (FullCalendar, react-big-calendar) ni de OAuth UI: el overlay vive en la grilla bespoke de scheduling y el OAuth es un redirect server-side.
> - **TZ — lección recurrente de staff/crm/scheduling (binding)**: los eventos externos son **instantes** (`starts_at`/`ends_at` UTC tz-aware). Se ubican en la grilla **en hora local del navegador** con los helpers `calendarWeek.ts` (`localMinutesOf`/`localDateIsoOf`), **exactamente igual que las citas** de la grilla shippeada de `scheduling` — el overlay **debe** compartir la base temporal de la grilla que lo monta (si difiriera, los eventos no calzarían con las citas). Renderizar toda la grilla (citas + overlay) en la TZ de la sede con `Intl.DateTimeFormat({ timeZone })` = **mejora diferida conjunta** de la grilla shippeada (no es alcance de F2). El "Última revisión: hace N" y cualquier `new Date()`/`now` que afecte el render (frescura de la salud, resaltado de "hoy") es **client-only** (`useEffect`/`useMemo`) — el SSR en UTC desfasaría el día en Lima (UTC-5).

> **Importante (alcance Fase 1, no exceder)**: PULL-only, **informativo**. El overlay **NO** toca `scheduling.compute_available_slots` ni los invariantes de booking — es una capa puramente aditiva, no-clicable para reservar. CalDAV, per-doctor, push y sync están **diferidos** (se documentan como roadmap en el README/design, no se diseñan pantallas aquí).

---

## Decisión de arquitectura: config en el grupo "Clínica" + overlay en la grilla de scheduling

`clinic` estableció la regla, reafirmada por `staff`/`scheduling`: **si una entidad de configuración tiene sub-recursos con interacción propia (grids editables, mapeos multi-fila, máquinas de estado), su superficie va a una página/grilla dedicada; si es ligera, va a drawer.** En `calendar` la integración tiene **dos superficies** y ninguna pantalla-lista clásica con DataTable:

| Superficie | Dónde vive | Crear / editar | Patrón |
|---|---|---|---|
| **Conexiones + mapeo calendario→sede** (`CalendarConnection` + `CalendarSource`) | **página** `/clinic/calendarios-externos` (grupo "Clínica" en el sidebar) | **cards de conexión** (OAuth redirect, sin drawer de creación) + **tabla de mapeo multi-fila** por conexión con bulk save (`PUT .../sources`) | shell de página de `clinic` + cards de `conversations` (Canales) + mapeo multi-fila de `OfficeHoursTab` |
| **Overlay de eventos externos** | dentro de la grilla `CalendarGrid` de `/scheduling/calendario` (NO página propia) | — (lectura informativa, no-clicable para reservar) | capa aditiva sobre la grilla bespoke de scheduling (`layoutOverlaps` + `calendarWeek.ts`) |
| **Aviso suave en el wizard** (F2) | dentro del paso 3 (Horario) del `BookingWizard` de scheduling | — (advisory, no bloquea) | `<MessageBar intent="info">` |

### Por qué la config es una **página** y no un drawer

La conexión externa no es un CRUD ligero de una entidad plana: una `CalendarConnection` expone **N calendarios** (de `list_calendars` live) que se mapean cada uno a una **sede** con un **toggle de habilitación**, y el guardado del mapeo es un **bulk replace atómico** (`PUT .../sources`, patrón `OfficeOperatingHours`). Esa interacción multi-fila + el flujo OAuth (redirect fuera de la app y vuelta) + la salud por conexión **no caben** en un drawer con footer único (mismo rationale que `OfficeDetailPage`: "el sub-recurso manda la forma"). Además la URL refleja el estado del OAuth callback (`?calendar_error=CODE` / éxito), lo que un drawer no puede modelar. Por eso es una **página dedicada** dentro del grupo "Clínica", no un drawer ni una pestaña anidada.

> Alternativas descartadas: (B) **un drawer `size=large` de conexión** — el mapeo multi-fila con su bulk-save y el callback OAuth con `?error=` no caben en un footer único; z-index frágil con los `<Dropdown>` de sede sobre el overlay. (C) **una pestaña dentro de `/clinic/offices/{id}`** — el mapeo es **a nivel clínica** (una conexión global → N sedes), no por consultorio; meterlo bajo un office contradice el modelo (la conexión NO pertenece a un branch). (D) **una entrada en el grupo "Conversaciones"** junto a Canales — tentador por el parecido de las cards, pero el dominio es *configuración de la clínica* (calendarios de las sedes), no un canal de mensajería; va en "Clínica" como pidió el spec.

### Por qué el overlay vive en la grilla de scheduling y no en una pantalla nueva

Los eventos externos **solo tienen sentido sobre las citas medisage** (para ver de un vistazo qué horas de la sede ya están ocupadas por algo externo). Crear una pantalla "Eventos externos" separada rompería ese contexto. Se dibuja como **capa aditiva** sobre la grilla `CalendarGrid` que `scheduling` ya construyó (F4), reutilizando su maquinaria de solapamiento y TZ. Es **frontend-only** en su composición (el `CalendarClient` de scheduling suma una llamada a `fetchExternalEvents` y pasa el resultado como prop nueva `externalEvents`); la grilla decide cómo pintar la capa. **Si la lectura externa falla, la grilla renderiza las citas normalmente** + un aviso de salud (nunca rompe la grilla ni la reserva — lección §23, regla no-negociable del aislamiento best-effort).

## Sidebar — extensión de `NAV_ITEMS` (grupo "Clínica", child nuevo)

> ⚠ **Textos UI en español** (ver [[feedback-medisage-spanish-ui]] en memoria global). `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un **child** `external-calendars` al **grupo "Clínica"** ya existente (`clinic`), **después de** `offices` (Consultorios) — junto a Sedes/Consultorios, como pide la spec §11. El grupo "Clínica" ya está en `NAV_ITEMS`; solo se le suma un hijo:

```ts
// dentro del item { key: "clinic", label: "Clínica", ... } → children:
{
  key: "external-calendars",
  label: "Calendarios externos",
  icon: "CalendarSyncRegular",          // ← AGREGAR al ICONS map de Sidebar.tsx (ver nota de icono)
  url: "/clinic/calendarios-externos",
  permissions: ["CALENDAR_CONNECTIONS_READ"],   // MENU-CALENDAR reservado (precedente scheduling)
},
```

> **Gate de visibilidad (sidebar)**: igual que el precedente de `scheduling` (el child gatea por su **permiso fino de lectura**, no por el `MENU-*`), el child se muestra con **`CALENDAR_CONNECTIONS_READ`**; **`MENU-CALENDAR`** existe en el set pero queda **reservado** (no se usa para gatear, como `MENU-SCHEDULING`). Subsets del spec §7: **ADMIN** (los 4 perms) y **ASESOR** (`CALENDAR_CONNECTIONS_READ` + `CALENDAR_EXTERNAL_EVENTS_READ`) ven el item; **DOCTOR** (solo `CALENDAR_EXTERNAL_EVENTS_READ`) **no** ve el item de config pero **sí** ve el overlay en la grilla de scheduling. El parent "Clínica" no lleva `permissions` propios: su visibilidad cae a la de sus children (ya es así con Sedes/Consultorios).
>
> El permiso **fino** `CALENDAR_CONNECTIONS_WRITE` (conectar/desconectar/mapear) se chequea **dentro** de la página vía `<PermissionGuard anyOf={["CALENDAR_CONNECTIONS_WRITE"]}>` (botones "Conectar X"/"Reconectar"/"Desconectar"/"Guardar mapeo") y en el RSC con `requirePermission("CALENDAR_CONNECTIONS_READ")` para el redirect. El ASESOR, sin `_WRITE`, ve la config **read-only** (cards + mapeo en gris, sin botones de acción).

> **Nota de icono (verificación contra el `ICONS` map de `Sidebar.tsx`)**: el `ICONS` map **actual** del Sidebar (`components/layout/Sidebar/Sidebar.tsx`) **NO** registra `CalendarSyncRegular` todavía (sí registra `CalendarLtrRegular`, `PlugConnectedRegular`, `BuildingMultipleRegular`, etc.). `CalendarSyncRegular` **sí existe** en la versión instalada de `@fluentui/react-icons` (verificado). Por tanto, F0 debe **importarlo y agregarlo al `ICONS` map** (una línea, junto a los íconos del módulo Clínica). Si por alguna razón se quisiera evitar tocar el import set, el **fallback ya registrado** es `CalendarLtrRegular` (el mismo que usa el grupo Agenda/scheduling). Recomendado: `CalendarSyncRegular` (comunica "sincronización de calendario", el dominio exacto del módulo).

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error / success) + tabla de componentes Fluent.

1. `/clinic/calendarios-externos` — **config de la clínica**: cards de conexión (proveedor + `account_email` + badge de salud) + botones "Conectar Google"/"Conectar Outlook" (OAuth) + por conexión la **tabla de mapeo** calendario→sede (`<Dropdown>` + `<Switch>` + "Guardar mapeo") + Reconectar/Desconectar.
2. **Overlay** en `scheduling/CalendarGrid` — eventos externos como capa atenuada/rayada + leyenda "Cita medisage" vs "Evento externo" (no-clicable) + aviso de salud si una fuente falla.
3. **(F2) Aviso suave en el `BookingWizard`** — `<MessageBar intent="info">` cuando el slot elegido solapa un evento externo de esa sede (advisory, no bloquea).

---

### Pantalla 1 — `/clinic/calendarios-externos` (config de la clínica)

Página dedicada (RSC `page.tsx` con `requirePermission("CALENDAR_CONNECTIONS_READ")` que prefetcha `POST /calendar/connections/list`, luego un client `CalendarConnectionsClient`). Header + toolbar con los dos botones de "Conectar X"; debajo, una **lista de cards de conexión**; cada card trae su **tabla de mapeo** (calendarios de `list_calendars` → sede + habilitar) con un solo "Guardar mapeo".

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                      │
│ ┌────────────┐ ┌──────────────────────────────────────────────────────────┐  │
│ │  Sidebar   │ │  Calendarios externos                                     │  │
│ │ ▸ Catálogo │ │  Conecta los calendarios de Google u Outlook de la        │  │
│ │ ▾ Clínica  │ │  clínica para ver su ocupación junto a la agenda.         │  │
│ │  • Sedes   │ │                       [ + Conectar Google ] [ + Outlook ] │  │
│ │  • Consul. │ │                                                            │  │
│ │  • Calend.█│ │  ╭─ ConnectionCard ──────────────────────────────────────╮ │  │
│ │ ▸ Staff    │ │  │  📅 clinica@gmail.com  ·  Google      [● Conectada]  ⋮│ │  │
│ │ ▸ Agenda   │ │  │  3 calendarios · Última revisión: hace 3 min          │ │  │
│ │            │ │  │  ┌──────────────────────────────────────────────────┐ │ │  │
│ │            │ │  │  │ Calendario          │ Sede             │ Habilit. │ │ │  │
│ │            │ │  │  ├──────────────────────┼──────────────────┼──────────┤ │ │  │
│ │            │ │  │  │ Sede Miraflores      │ [Miraflores   ▾] │ [ ●━━ ] │ │ │  │
│ │            │ │  │  │ Sede San Isidro      │ [San Isidro   ▾] │ [ ●━━ ] │ │ │  │
│ │            │ │  │  │ Personal             │ [Todas las s. ▾] │ [ ━━○ ] │ │ │  │
│ │            │ │  │  └──────────────────────────────────────────────────┘ │ │  │
│ │            │ │  │           [ Reconectar ]  [ Desconectar ] [Guardar mapeo]│ │  │
│ │            │ │  ╰──────────────────────────────────────────────────────╯ │  │
│ │            │ │  ╭─ ConnectionCard ──────────────────────────────────────╮ │  │
│ │            │ │  │  📧 recepcion@clinica.com · Outlook   [⚠ Reconectar] ⋮│ │  │
│ │            │ │  │  La conexión perdió acceso. Vuelve a conectarla.      │ │  │
│ │            │ │  │           [ Reconectar ]  [ Desconectar ]              │ │  │
│ │            │ │  ╰──────────────────────────────────────────────────────╯ │  │
│ └────────────┘ └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Header de la página**:
- Título = "Calendarios externos"; subtítulo = "Conecta los calendarios de Google u Outlook de la clínica para ver su ocupación junto a la agenda."
- **Toolbar (botones de conectar)** — gated `<PermissionGuard anyOf={["CALENDAR_CONNECTIONS_WRITE"]}>`:
  - **`[ + Conectar Google ]`** (`<Button appearance="primary" icon={<CalendarSyncRegular />}>`): dispara el OAuth. Es un **Server Action** `startOAuth("google", returnTo)` que llama `GET /calendar/oauth/google/start?return_to=/clinic/calendarios-externos`, recibe `{ auth_url }` y el **cliente** hace `window.location.href = auth_url` (NO `redirect()` del Server Action, que no sale transparente a un host externo; el navegador va al consentimiento de Google y el callback público del backend vuelve a `return_to`). No abre drawer ni popup propio.
  - **`[ + Conectar Outlook ]`** (`<Button appearance="secondary" icon={<CalendarSyncRegular />}>`): idéntico con `provider="microsoft"`. La etiqueta visible es **"Outlook"** (el usuario lo conoce así), aunque el `provider` del contrato es `microsoft`.
  - Las opciones de proveedor salen de `CalendarProviderOption[] { value, label }` (spec §10): `{ value: "google", label: "Google" }`, `{ value: "microsoft", label: "Outlook" }`. Si en el futuro entra `caldav`, aparece un 3er botón sin reescribir la página.

#### Card de conexión (`ConnectionCard`)

Cada `CalendarConnectionItem`/`Detail` se renderiza como un `<Card>` con cabecera (ícono del proveedor + `account_email` + `display_name` opcional + badge de salud + menú `⋮`), una línea de metadatos (`sources_count` calendarios · "Última revisión: hace N" derivado de `last_checked_at`, **client-only**), la **tabla de mapeo** (solo si `status` permite leer calendarios), y un footer de acciones.

**Badge de salud** (de `ConnectionStatus`, spec §3) — color por **token Fluent**, no hex:

| `status` | Etiqueta visible | `<Badge>` color | Ícono |
|---|---|---|---|
| `connected` | "Conectada" | `success` (`colorPaletteGreenForeground1`) | `CheckmarkCircleRegular` |
| `needs_reauth` | "Reconectar" | `warning` (`colorPaletteYellowForeground1`) | `WarningRegular` |
| `error` | "Error" | `danger` (`colorPaletteRedForeground1`) | `ErrorCircleRegular` |
| `revoked` | "Revocada" | `danger` (`colorPaletteRedForeground1`) | `DismissCircleRegular` |

> Concordancia: **conexión** es femenino → "Conectada"/"Revocada". El badge muestra ícono + texto; el `last_error` (si lo hay, de `CalendarConnectionDetail`) se muestra como subtítulo de la card en `tokens.colorPaletteRedForeground1` ("La conexión perdió acceso. Vuelve a conectarla."). El estado `connected` con `last_checked_at` reciente muestra "Última revisión: hace N" (relativo, client-only); si `last_checked_at` es null, "Aún sin revisar".

**Ícono del proveedor** (cabecera de la card): **NO** se usan logos de marca de Google/Microsoft (no están en `@fluentui/react-icons` y meter SVGs de marca fuera del design system es inconsistente — misma regla que "no librería externa"). Se usa un **ícono Fluent neutral por proveedor** + el nombre textual del proveedor al lado:
- `google` → `<CalendarLtrRegular />` + texto "Google".
- `microsoft` → `<MailRegular />` (Outlook es correo+calendario) + texto "Outlook".
- (futuro `caldav` → `<GlobeRegular />` + "CalDAV".)

**Menú `⋮` de la card** (`<Menu>` overflow, gated `CALENDAR_CONNECTIONS_WRITE`): "Reconectar" / "Desconectar" (duplica los botones del footer para acceso rápido; en read-only el menú no se renderiza).

#### Tabla de mapeo calendario→sede (`SourceMappingTable`) — bulk save

Molde directo de `OfficeOperatingHoursTab`/`OfficeClosuresTab`: una **tabla de filas de configuración** que se edita en estado local y se persiste con **un solo** botón "Guardar mapeo" (`PUT /calendar/connections/{id}/sources`, **bulk replace atómico** — soft-delete los sources viejos + insert el set nuevo, patrón `OfficeOperatingHours`). Las filas se arman cruzando los **calendarios live** del proveedor (`GET /calendar/connections/{id}/calendars` → `ExternalCalendarOption[] { id, name, primary }`) con los **sources ya guardados** (`CalendarConnectionDetail.sources: CalendarSourceItem[]`), de modo que cada calendario aparece una vez con su mapeo actual (o sin mapear).

```
│  │  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  │ Calendario              │ Sede                  │ Habilitado       │ │
│  │  ├─────────────────────────┼───────────────────────┼──────────────────┤ │
│  │  │ Sede Miraflores  ⭐prim. │ [ Sede Miraflores  ▾ ]│ [ ●━━ ]          │ │
│  │  │ Sede San Isidro         │ [ Sede San Isidro  ▾ ]│ [ ●━━ ]          │ │
│  │  │ Personal                │ [ Todas las sedes  ▾ ]│ [ ━━○ ]          │ │
│  │  │ Cumpleaños              │ [ (no mapear)      ▾ ]│ [ ━━○ ]          │ │
│  │  └──────────────────────────────────────────────────────────────────┘ │
│  │  Las horas de los eventos se interpretan en la zona de la sede mapeada.│
│  │                                                       [ Guardar mapeo ] │
```

**Columnas**:
- **Calendario** (`external_calendar_name`, denorm): nombre del calendario tal como lo da el proveedor + un badge `⭐ prim.` (`<Badge appearance="tint">`) si `ExternalCalendarOption.primary === true`. Read-only (es el dato del proveedor). Si el nombre es muy largo, `<Tooltip>` con el nombre completo.
- **Sede** (`<Dropdown>` de `GET /clinic/branches/active` → `BranchOption[]`): la opción especial **"Todas las sedes"** mapea a `branch_id = null` (spec decisión #3: nullable = "aplica a todas las sedes"). Una opción **"(no mapear)"** deja el calendario sin source persistido (no entra al bulk replace, o entra con `is_enabled=false` — ver nota de semántica abajo). Default por fila = la sede actual del source si existe, o "(no mapear)".
- **Habilitado** (`<Switch>`, mapea a `is_enabled` ← `ActiveMixin.active` del backend, spec §2): ON = el calendario se lee en el overlay; OFF = mapeado pero pausado. El conjunto de filas con `is_enabled=true` **ES** "el grupo de calendarios de la clínica".

> **Semántica del bulk replace (binding, espejo de `OfficeOperatingHoursReplace`)**: "Guardar mapeo" arma `CalendarSourcesReplace { sources: CalendarSourceCreate[] }` recorriendo **todas las filas mapeadas** (sede ≠ "(no mapear)"), cada una `{ external_calendar_id, external_calendar_name, branch_id?, is_enabled }`. El `PUT` **reemplaza el set completo** de sources de esa conexión (soft-delete de los que ya no están + insert/reactivación). Filas "(no mapear)" se **omiten** del payload (quedan sin source). El backend valida cada `branch_id` (404 `BRANCH_NOT_FOUND` si la sede no existe — lección §20/§22, validar FK antes de insertar). Respuesta = `SingleResponse[CalendarConnectionDetail]` (la card se re-renderiza con los sources frescos). Tras éxito: `revalidateTag("calendar:connections")` + toast "Mapeo guardado.".

**Validación (Zod, client-side antes del bulk PUT)** — mirror de `lib/schemas/calendar.schema.ts` (`sourceCreate`/`sourcesReplace`, spec §12):
- `external_calendar_id` / `external_calendar_name`: string min 1 (vienen del proveedor, siempre presentes).
- `branch_id`: opcional (null = todas las sedes); si se setea, debe ser un id de la lista activa (el `<Dropdown>` ya lo limita; el backend re-valida → 404 `BRANCH_NOT_FOUND`).
- `is_enabled`: boolean (default `true` en `CalendarSourceCreate`).
- `sources`: lista min 0 (`CalendarSourcesReplace` permite vaciar el mapeo — desmapear todo es válido).

#### Footer de acciones de la card (gated `CALENDAR_CONNECTIONS_WRITE`)

- **`[ Reconectar ]`** (`<Button>` con `ArrowSyncRegular`): re-dispara el OAuth para la **misma cuenta** (`startOAuth(provider, returnTo)`), útil cuando `status = needs_reauth`/`revoked`. Vuelve por el callback y actualiza la conexión a `connected`. En `needs_reauth`/`revoked` este botón es el **CTA primario** de la card.
- **`[ Desconectar ]`** (`<Button>` destructive con `PlugDisconnectedRegular`): abre un `<ConfirmDialog destructive>` → `disconnect(connId)` → `DELETE /calendar/connections/{id}` (204; soft-delete + best-effort revoke del token + borra el secreto). Tras éxito la card desaparece, `revalidateTag("calendar:connections")`, toast "Conexión eliminada.".
- **`[ Guardar mapeo ]`** (`<Button appearance="primary">`): el bulk save descrito arriba. **Disabled** si no hay cambios (`isDirty`) o si el `status` no permite leer calendarios (`revoked`/`error` sin reconectar).

#### Estados (Pantalla 1)

- **Empty (sin conexiones)**: `<EmptyState>` con ícono `CalendarSyncRegular` + título "Aún no hay calendarios conectados" + mensaje "Conecta el calendario de Google u Outlook de la clínica para ver su ocupación junto a la agenda." Los botones "Conectar Google"/"Conectar Outlook" del toolbar cumplen el CTA (no van dentro del EmptyState — consistencia con clinic/scheduling).
- **Loading (primera carga)**: 2 card-skeletons (`<Skeleton><SkeletonItem>` con cabecera + 3 filas de mapeo en gris). El server-prefetch del `page.tsx` evita verlo en el primer load.
- **Loading de calendarios (dentro de una card recién conectada)**: la tabla de mapeo muestra `<Spinner size="tiny" label="Cargando calendarios…">` mientras `GET /connections/{id}/calendars` resuelve (el `list_calendars` es live, puede tardar). Si la conexión está `connected` pero `list_calendars` falla → `<MessageBar intent="warning">"No se pudieron cargar los calendarios. Reintenta o reconecta."` con un botón `[ Reintentar ]`.
- **Refetching (tras guardar mapeo / reconectar)**: la card mantiene lo visible con `opacity: 0.55` + `<Spinner size="tiny">` en la esquina.
- **Éxito del OAuth callback (vuelta del proveedor)**: al volver a `/clinic/calendarios-externos` sin `?calendar_error`, un `<MessageBar intent="success">"Calendario conectado. Asigna cada calendario a una sede y guárdalo."` (auto-dismiss); la nueva card aparece arriba con su tabla de mapeo cargando.
- **Error del OAuth callback (`?calendar_error=CODE`)**: el RSC/cliente lee el query param y muestra un `<MessageBar intent="error">` arriba de la lista con el mensaje en español del code (tabla abajo). El param se limpia de la URL tras mostrarse (no persiste en refresh).
- **Error de guardado de mapeo**: `<MessageBar intent="error">` dentro de la card con el `detail` del backend (ej. 404 `BRANCH_NOT_FOUND` → "Una de las sedes seleccionadas ya no existe. Recarga e inténtalo de nuevo.").
- **Read-only (sin `CALENDAR_CONNECTIONS_WRITE`, ej. ASESOR)**: los botones "Conectar X"/"Reconectar"/"Desconectar"/"Guardar mapeo" no se renderizan; los `<Dropdown>` de sede y los `<Switch>` se muestran **disabled** (lectura de la configuración). Un hint suave: "Solo un administrador puede conectar o mapear calendarios."

#### Mapeo de códigos de error → mensaje en español (callback OAuth + acciones)

El callback redirige con `?calendar_error=CODE`; las acciones devuelven `{ ok:false, error }` con el `detail` ya en español del backend. La UI mapea el `code` a copy:

| `code` (spec §8) | Copy en español (MessageBar) |
|---|---|
| `CALENDAR_OAUTH_STATE_INVALID` (400) | "La sesión de conexión expiró o no es válida. Vuelve a intentar conectar." |
| `CALENDAR_OAUTH_EXCHANGE_FAILED` (400) | "No se pudo completar la conexión con el proveedor. Inténtalo de nuevo." |
| `CALENDAR_CONNECTION_ALREADY_EXISTS` (409) | "Esa cuenta ya está conectada." |
| `CALENDAR_PROVIDER_NOT_SUPPORTED` (400) | "Ese proveedor no está disponible." |
| `CALENDAR_TOKEN_REFRESH_FAILED` (400) | "La conexión perdió acceso. Reconéctala." (la conexión queda `needs_reauth`) |
| `CALENDAR_CREDENTIALS_MISSING` (400) | "No se encontraron las credenciales de la conexión. Reconéctala." |
| `CALENDAR_CONNECTION_NOT_FOUND` (404) | "La conexión ya no existe. Recarga la página." |
| `CALENDAR_SOURCE_NOT_FOUND` (404) | "El calendario ya no existe en esta conexión. Recarga la página." |
| `BRANCH_NOT_FOUND` (404) | "Una de las sedes seleccionadas ya no existe. Recarga e inténtalo de nuevo." |

#### Componentes Fluent UI (Pantalla 1)

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Header | `<h1 className={styles.title}>` + `<p className={styles.subtitle}>` |
| Botón conectar (Google / Outlook) | `<Button appearance="primary"/"secondary" icon={<CalendarSyncRegular />}>` → Server Action `startOAuth` (devuelve `{ auth_url }`) + cliente `window.location.href = auth_url` |
| Permission gate (acciones) | `<PermissionGuard anyOf={["CALENDAR_CONNECTIONS_WRITE"]}>` |
| Card de conexión | `<Card>` + `<CardHeader>` (ícono proveedor + `account_email` + `<Badge>` salud + `<Menu>` `⋮`) |
| Badge de salud | `<Badge appearance="filled" color={success/warning/danger} icon={...}>` (tokens, no hex) |
| Ícono del proveedor | `<CalendarLtrRegular />` (Google) / `<MailRegular />` (Outlook) — neutral, no logo de marca |
| Tabla de mapeo | filas custom (`makeStyles`, tokens) — molde `OfficeOperatingHoursTab` |
| Dropdown de sede | `<Dropdown>` de `GET /clinic/branches/active` + opción "Todas las sedes" (null) + "(no mapear)" |
| Toggle habilitado | `<Switch>` (mapea a `is_enabled`) |
| Badge "primario" | `<Badge appearance="tint">⭐ prim.</Badge>` (si `ExternalCalendarOption.primary`) |
| Guardar mapeo (bulk) | `<Button appearance="primary">` único → `replaceSources(connId, body)` → `PUT .../sources` |
| Reconectar | `<Button icon={<ArrowSyncRegular />}>` → `startOAuth(provider)` |
| Desconectar | `<Button icon={<PlugDisconnectedRegular />}>` + `<ConfirmDialog destructive>` → `DELETE` |
| "Última revisión: hace N" | `formatRelative(last_checked_at)` (client-only) + `<Tooltip>` con la fecha absoluta |
| Loading calendarios | `<Spinner size="tiny" label="Cargando calendarios…">` |
| Skeleton cards | `<Skeleton>` + `<SkeletonItem>` por card |
| Éxito / error / aviso | `<MessageBar intent="success"/"error"/"warning">` |
| Confirm desconectar | `<ConfirmDialog destructive>` |
| Empty | `<EmptyState icon={<CalendarSyncRegular />} title message>` |

---

### Pantalla 2 — Overlay de eventos externos en `scheduling/CalendarGrid`

**No es una pantalla nueva.** Es una **capa visual aditiva** que se dibuja sobre la grilla bespoke `CalendarGrid` que `scheduling` ya construyó (F4, `frontend/src/app/(main)/scheduling/_components/CalendarGrid.tsx`; la monta `scheduling/calendario/CalendarClient`). El `CalendarClient` de scheduling se modifica para llamar además a la Server Action `fetchExternalEvents(branch_id, from, to)` (lectura, sin `revalidateTag`) y pasar el resultado a `CalendarGrid` como una **prop opcional nueva** `externalEvents?: ExternalEventItem[]`. La grilla decide cómo pintar la capa. **El módulo `calendar` no toca el cómputo de slots ni las citas** — solo añade el render de la capa externa + la leyenda.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Calendario                                                                   │
│   Vista semanal de las citas y horarios disponibles.                           │
│   ┌──────────┐┌──────────┐ [Semana|Día]  ‹  Sem. 6–12 jun 2026  ›  [ Hoy ]    │
│   │Doctor:R.▾││Sede: L. ▾│                                                     │
│   └──────────┘└──────────┘  Leyenda: ▓Cita medisage  ▦Evento externo ◌libre   │
│   ┌────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐               │
│   │    │ vie 6▸│ sáb 7 │ dom 8 │ lun 9 │ mar10 │ mié11 │ jue12 │               │
│   ├────┼───────┼───────┼───────┼───────┼───────┼───────┼───────┤               │
│   │08:00      │       │       │▦▦▦▦▦▦▦│       │       │       │ ▦=evento ext. │
│   │08:30      │       │       │▦Reunión│      │       │       │  (atenuado,    │
│   │09:00▓▓▓▓▓▓│       │       │▦equipo │◌libre │       │       │   rayado,      │
│   │09:30▓Ana  │       │       │       │◌      │       │       │   no-clicable) │
│   │     ▓Limp │       │       │◌libre │       │       │       │               │
│   │10:00▓▓▓▓▓▓│       │       │◌      │       │       │       │ ▓=cita med.   │
│   │10:30◌libre│       │  ▦▦▦▦ │       │       │       │       │  (color=estado)│
│   │11:00▓▓▓▓▓▓│       │  ▦Cita│       │◌libre │       │       │               │
│   │11:30▓Pedro│       │  ▦ext.│       │◌      │       │       │ ◌=slot libre  │
│   └────┴───────┴───────┴───────┴───────┴───────┴───────┴───────┘               │
│   ⚠ No se pudo leer el calendario de Outlook (recepcion@clinica.com). Reintentar│
└──────────────────────────────────────────────────────────────────────────────┘
```

**Anatomía de la capa externa** (sobre la grilla de scheduling, sin alterarla):
- **Bloque de evento externo** (`▦`, **capa visual distinta**): cada `ExternalEventItem { external_id, title, starts_at, ends_at, all_day, branch_id, branch_name, source_id }` ocupa `[starts_at, ends_at)` en su columna-fecha. Estilo **deliberadamente diferenciado de las citas medisage** para que nadie los confunda: fondo **atenuado** (`tokens.colorNeutralBackground3`), **patrón de rayas diagonales** (CSS `repeating-linear-gradient` con `tokens.colorNeutralStroke2`), borde `tokens.colorNeutralStroke2` (no el color de un estado de cita). Etiqueta = `title` del evento (truncado, `<Tooltip>` con título + rango horario en hora local, igual que las citas). Eventos `all_day` se pintan como una banda fina en la cabecera de la columna-fecha (no ocupan filas-hora), con etiqueta "{title} · todo el día".
- **No-clicable para reservar** (binding): los bloques externos **no** abren el wizard ni el detalle — `pointerEvents: "none"` sobre el bloque salvo el `<Tooltip>` informativo al hover (`cursor: default`). Son lectura pura. El overlay de **slot libre** (`◌`, de scheduling) sigue siendo clickeable como antes — la capa externa **no** lo bloquea (informativo: un slot libre que solapa un evento externo se sigue pudiendo reservar; el aviso del wizard F2 lo advierte).
- **Solapamiento**: cuando un evento externo y una cita medisage caen en la misma franja, se reusa el `layoutOverlaps` de scheduling para repartir el ancho de la columna (cita a un lado, evento externo al otro), de modo que ambos sean visibles. La cita medisage tiene **prioridad visual** (color sólido del estado); el evento externo queda atenuado al lado.
- **TZ**: `starts_at`/`ends_at` son instantes UTC → se ubican en la grilla con los helpers `calendarWeek.ts` en **hora local del navegador**, **igual que las citas** (consistencia obligatoria: el overlay comparte la base temporal de la grilla). El `?branch_id=` filtra QUÉ eventos se muestran (y fija la TZ de las ventanas de disponibilidad), pero el posicionamiento horario es local del navegador como en la grilla shippeada; render por TZ de sede = mejora diferida conjunta.

**Leyenda** (extiende la leyenda existente de scheduling): se agregan dos entradas — **"Cita medisage"** (swatch sólido, representa los estados de cita) y **"Evento externo"** (swatch rayado/atenuado). Se mantienen los swatches de estado y el `◌ slot libre` de scheduling. La leyenda deja claro que el rayado = externo y no es reservable.

**Resolución de eventos (best-effort, regla no-negociable)**: `fetchExternalEvents(branch_id, from, to)` llama `GET /calendar/external-events?branch_id=&from=&to=` → `ExternalEventsResponse { events, sources_health }`. El backend resuelve los `CalendarSource` habilitados de la sede (`branch_id == X OR branch_id IS NULL`), agrupa por conexión, refresca tokens al vuelo, lee con `list_events`; **si una conexión falla, marca su salud y devuelve el resto (NUNCA 5xx)**. La UI:
- Pinta los `events` que llegaron (aunque una fuente haya fallado).
- Si `sources_health` trae alguna fuente con `status != connected`, muestra un **aviso suave de salud** debajo de la grilla (`<MessageBar intent="warning">`): "No se pudo leer el calendario de {proveedor} ({account_email}). Reintentar." con un botón que re-llama `fetchExternalEvents`. **La grilla de citas medisage se renderiza normalmente** — el fallo externo nunca rompe la agenda.
- Si el usuario **no** tiene `CALENDAR_EXTERNAL_EVENTS_READ`, el `CalendarClient` **no** llama `fetchExternalEvents` y la grilla se ve exactamente como antes (sin capa externa, sin leyenda de evento externo). El DOCTOR (que sí tiene el perm) ve el overlay; un viewer sin el perm, no.

#### Estados (overlay)

- **Loading externo**: la grilla pinta las citas de inmediato; la capa externa entra cuando `fetchExternalEvents` resuelve (no bloquea el render de citas). Mientras carga, un `<Spinner size="tiny">` discreto junto a la leyenda con "Cargando eventos externos…". **Nunca** un skeleton de toda la grilla por culpa de la capa externa.
- **Sin eventos externos (semana sin ocupación externa)**: la grilla se ve como la de scheduling sin la capa `▦`; la leyenda "Evento externo" puede mostrarse atenuada o omitirse. No hay empty-state propio (la grilla nunca está "vacía por culpa del overlay").
- **Sin conexiones / sin sources habilitados para la sede**: `fetchExternalEvents` devuelve `events: []` y `sources_health: []` → la grilla se ve idéntica a scheduling puro (sin leyenda externa). Cero ruido visual.
- **Una fuente falló (best-effort)**: `<MessageBar intent="warning">` de salud debajo de la grilla + los eventos de las fuentes sanas sí se pintan. Botón "Reintentar".
- **Sin permiso (`CALENDAR_EXTERNAL_EVENTS_READ` ausente)**: la grilla es la de scheduling sin overlay. Sin aviso (no es un error, es ausencia de feature).
- **Error total de la lectura externa**: aunque el backend es best-effort, si la action fallara (red), la grilla **igual** muestra las citas + un `<MessageBar intent="warning">"No se pudieron cargar los eventos externos."` (degradación con gracia; nunca rompe el calendario).

#### Componentes Fluent UI (overlay)

| Concepto UI | Componente |
|---|---|
| Grilla base | la `CalendarGrid` **custom** de scheduling (no se reescribe; se le pasa la prop `externalEvents`) |
| Bloque de evento externo | `<div>` posicionado, estilo rayado/atenuado (`makeStyles`: `repeating-linear-gradient` + `colorNeutralBackground3` + `colorNeutralStroke2`), `pointerEvents: "none"` |
| Evento `all_day` | banda fina en la cabecera de la columna-fecha (`makeStyles`, tokens) |
| Tooltip de evento | `<Tooltip>` con título + rango horario (hora local, igual que las citas) |
| Solapamiento cita↔evento | `layoutOverlaps` (reusado de scheduling) reparte el ancho de la columna |
| Leyenda | extensión de la leyenda de scheduling: swatch sólido "Cita medisage" + swatch rayado "Evento externo" |
| Aviso de salud (best-effort) | `<MessageBar intent="warning">` + `<Button>` "Reintentar" |
| Loading externo | `<Spinner size="tiny" label="Cargando eventos externos…">` (junto a la leyenda) |
| Fetch | Server Action `fetchExternalEvents(branchId, from, to)` (lectura, sin `revalidateTag`) |

---

### Pantalla 2.b (F2) — Aviso suave en el `BookingWizard`

Mejora **advisory** dentro del paso 3 (Horario) del wizard de reserva de scheduling. Si el slot que el asesor está por elegir **solapa un evento externo** de esa sede, se muestra un `<MessageBar intent="info">` informativo **sin impedir la reserva** (decisión #5 del spec: es advisory, no bloqueante). Reusa los mismos `externalEvents` ya disponibles (la sede del wizard + el rango de la semana visible).

```
                  │  Reservar cita — Horario                      ✕ │
                  │  ① ── ② ━━━③━━━ ④                              │
                  │  ‹  Semana 6–12 jun 2026  ›   [ Hoy ]           │
                  │  ┌─────────────────────────────────────────┐   │
                  │  │ ℹ Hay un evento externo a esta hora       │   │  ← MessageBar info
                  │  │   ("Reunión equipo", 09:00–10:00). Puedes │   │
                  │  │   reservar igual.                         │   │
                  │  └─────────────────────────────────────────┘   │
                  │  Slots de 30 min · Dra. Ríos · Limpieza        │
                  │  ┌──────┬──────┬──────┬──────┬──────┬──────┐   │
                  │  │ …grilla de slots de scheduling…          │   │
                  │  └──────┴──────┴──────┴──────┴──────┴──────┘   │
                  │                            [ ←Atrás ] [ Sig.→ ]│
```

- **Disparo**: al seleccionar un slot (`scheduled_for`), el wizard comprueba client-side si `[scheduled_for, scheduled_for + duration_min)` solapa algún `ExternalEventItem` de la sede del wizard. Si sí → muestra el `<MessageBar intent="info">` con el título del evento y su rango. **No** deshabilita el botón "Siguiente"/"Reservar".
- **Copy**: "Hay un evento externo a esta hora (\"{title}\", {hora_inicio}–{hora_fin}). Puedes reservar igual." Concordancia: **evento** masculino.
- **Si la lectura externa falló** (best-effort): el wizard **no** muestra ningún aviso (ausencia de dato ≠ "no hay solapamiento"); jamás bloquea la reserva por un fallo externo.
- **Sin permiso `CALENDAR_EXTERNAL_EVENTS_READ`**: el wizard no consulta eventos externos y no muestra el aviso (idéntico al wizard de scheduling puro).

#### Componentes Fluent UI (aviso del wizard)

| Concepto UI | Componente |
|---|---|
| Aviso de solapamiento | `<MessageBar intent="info">` (advisory, no bloquea) dentro del paso 3 del `AppointmentWizardDrawer` |
| Detección de solapamiento | helper client-side sobre los `externalEvents` ya cargados (sin llamada extra) |

---

## Decisiones de UI (cierres)

### Config a nivel clínica como página en el grupo "Clínica", no drawer ni pestaña de office

La conexión externa es **a nivel clínica** (una conexión global → N sedes), con mapeo multi-fila + bulk save + flujo OAuth con callback. Eso excede un drawer (footer único no modela el bulk-save + el `?error=` del callback) y no pertenece a un `Office` (la conexión no es de un consultorio). Va a una **página dedicada** en el grupo "Clínica" (`/clinic/calendarios-externos`), junto a Sedes/Consultorios. Mismo precedente que `OfficeDetailPage`: el sub-recurso rico manda la forma.

### Cards de conexión (lenguaje de Canales de conversations), no DataTable

Las conexiones son pocas (1-2 por clínica) y cada una tiene salud + un mapeo anidado → una DataTable sería desproporcionada. Se usan **cards** (como las cuentas de canal de `conversations`): ícono de proveedor + `account_email` + badge de salud + el mapeo embebido. Escala bien a 2-3 conexiones sin paginación.

### Mapeo calendario→sede con bulk save (molde OfficeHoursTab), no CRUD por fila

El mapeo de los N calendarios de una conexión es un **agregado coherente** (se piensan juntos: "este calendario a esta sede, ese a la otra") → un solo "Guardar mapeo" (`PUT .../sources` bulk replace atómico, patrón `OfficeOperatingHours`) evita estados intermedios inválidos y N requests. La opción "(no mapear)" + el `<Switch>` de habilitación cubren los casos de "no me interesa este calendario" sin borrar filas a mano. Asimetría intencional vs los closures de office (que sí son CRUD individual) — el mapeo es bulk porque es un set coherente.

### "Todas las sedes" = `branch_id` null en el Dropdown (decisión #3)

El `<Dropdown>` de sede incluye la opción especial **"Todas las sedes"** que mapea a `branch_id = null` (el calendario aplica a cualquier sede). Resuelve el caso "calendario global de la clínica". Es la primera opción del dropdown, antes de las sedes concretas, + una opción "(no mapear)" para excluir el calendario.

### Ícono Fluent neutral por proveedor, no logo de marca

No se incrustan los logos oficiales de Google/Microsoft (no están en `@fluentui/react-icons`; meter SVGs de marca fuera del design system rompe la consistencia — misma regla que "no librería de calendario externa"). Se usa un ícono Fluent neutral (`CalendarLtrRegular` para Google, `MailRegular` para Outlook) + el nombre textual del proveedor. Suficiente para que el admin distinga la conexión.

### Overlay como capa visual distinta, atenuada y NO-clicable

Los eventos externos se pintan **deliberadamente diferentes** de las citas medisage (rayado/atenuado con tokens neutrales, no con colores de estado) y son **no-clicables para reservar** (`pointerEvents: "none"` salvo el tooltip). Esto comunica de un vistazo "esto no es una cita medisage, es ocupación externa informativa" y evita que alguien crea que puede gestionarlo desde aquí. La leyenda lo refuerza. Coherente con la semántica informativa de la Fase 1 (no toca booking).

### Best-effort: un fallo externo nunca rompe la grilla ni la reserva (lección §23)

La lectura externa es **best-effort y aislada**: si una conexión falla, la grilla pinta las citas medisage normalmente + un `<MessageBar intent="warning">` de salud; el wizard no bloquea la reserva por un fallo externo. **Nunca un 5xx, nunca un skeleton de toda la grilla por culpa del overlay, nunca una reserva impedida por la capa externa.** Es la regla no-negociable del aislamiento (la integración es puramente aditiva).

### El overlay se construye en F2, sobre la grilla de scheduling ya shippeada

El overlay **no** reescribe `CalendarGrid`: le agrega una prop opcional `externalEvents` y el `CalendarClient` suma una llamada a `fetchExternalEvents`. Si `scheduling` F4 (la grilla) no estuviera en prod, el overlay no tiene dónde vivir — por eso `calendar` F2 depende de `scheduling` F4. La config (Pantalla 1) es independiente y entra en `calendar` F1.

### Sin i18n framework por ahora

Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm/scheduling). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive

Mismo criterio que clinic/staff/crm/scheduling (template optimizado para desktop interno): sidebar colapsado por default; las **cards de conexión** apilan su tabla de mapeo (el `<Dropdown>` de sede y el `<Switch>` caen bajo el nombre del calendario en pantallas angostas); el **overlay** hereda el comportamiento responsive de la grilla de scheduling (scroll horizontal de las 7 columnas o caída a vista Día). No se diseñan pantallas mobile-first separadas.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, IANA, CSS classes, `provider` values) en inglés — solo los textos visibles van traducidos. Glosario clave: **CalendarConnection = Conexión** (femenino), **CalendarSource = Calendario** (masculino, "el calendario"), **Provider = Proveedor** (masculino), **Branch = Sede** (femenino), **External event = Evento externo** (masculino), **Mapeo** (masculino), **Outlook** (etiqueta visible de `microsoft`).

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Sidebar — | |
| Child (grupo Clínica) | "Calendarios externos" |
| — Config (Pantalla 1) — | |
| Page title | "Calendarios externos" |
| Page subtitle | "Conecta los calendarios de Google u Outlook de la clínica para ver su ocupación junto a la agenda." |
| Botón conectar Google | "+ Conectar Google" |
| Botón conectar Outlook | "+ Conectar Outlook" |
| Empty title | "Aún no hay calendarios conectados" |
| Empty message | "Conecta el calendario de Google u Outlook de la clínica para ver su ocupación junto a la agenda." |
| Línea de metadatos (card) | "{N} calendarios · Última revisión: hace {N}" |
| Sin revisión aún | "Aún sin revisar" |
| Badge salud | "Conectada" / "Reconectar" / "Error" / "Revocada" |
| Subtítulo error (needs_reauth/revoked) | "La conexión perdió acceso. Vuelve a conectarla." |
| — Tabla de mapeo — | |
| Columnas | "Calendario" / "Sede" / "Habilitado" |
| Opción dropdown (todas) | "Todas las sedes" |
| Opción dropdown (sin mapear) | "(no mapear)" |
| Badge calendario primario | "⭐ prim." |
| Hint TZ | "Las horas de los eventos se interpretan en la zona de la sede mapeada." |
| Botón guardar mapeo | "Guardar mapeo" / "Guardando…" |
| Toast mapeo guardado | "Mapeo guardado." |
| Botón reconectar | "Reconectar" |
| Botón desconectar | "Desconectar" |
| Confirm desconectar (título) | "¿Desconectar esta cuenta?" |
| Confirm desconectar (body) | "Se eliminará la conexión y sus calendarios mapeados. Podrás volver a conectarla más adelante." |
| Toast desconectada | "Conexión eliminada." |
| Loading calendarios | "Cargando calendarios…" |
| Error cargar calendarios | "No se pudieron cargar los calendarios. Reintenta o reconecta." |
| Botón reintentar | "Reintentar" |
| Read-only (sin write) | "Solo un administrador puede conectar o mapear calendarios." |
| — OAuth callback — | |
| Éxito conexión | "Calendario conectado. Asigna cada calendario a una sede y guárdalo." |
| Error state inválido | "La sesión de conexión expiró o no es válida. Vuelve a intentar conectar." |
| Error exchange | "No se pudo completar la conexión con el proveedor. Inténtalo de nuevo." |
| Error ya existe | "Esa cuenta ya está conectada." |
| Error refresh | "La conexión perdió acceso. Reconéctala." |
| Error credenciales | "No se encontraron las credenciales de la conexión. Reconéctala." |
| Error sede no existe | "Una de las sedes seleccionadas ya no existe. Recarga e inténtalo de nuevo." |
| — Overlay (grilla scheduling) — | |
| Leyenda cita | "Cita medisage" |
| Leyenda evento externo | "Evento externo" |
| Tooltip evento | "{title} · {hora_inicio}–{hora_fin}" |
| Evento todo el día | "{title} · todo el día" |
| Loading externo | "Cargando eventos externos…" |
| Aviso salud (fuente falló) | "No se pudo leer el calendario de {proveedor} ({account_email}). Reintentar." |
| Aviso lectura total falló | "No se pudieron cargar los eventos externos." |
| — Aviso del wizard (F2) — | |
| Aviso solapamiento | "Hay un evento externo a esta hora (\"{title}\", {hora_inicio}–{hora_fin}). Puedes reservar igual." |
| — Común — | |
| Botón guardar / guardando | "Guardar" / "Guardando…" |
| Botón cancelar | "Cancelar" |
| Botón cerrar | "Cerrar" |
| Loading placeholder | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |

### Concordancia de género

- **Conexión** es **femenino**: "esta conexión", "Conectada"/"Revocada", "¿Desconectar esta cuenta?", "Conexión eliminada".
- **Calendario** es **masculino**: "el calendario", "este calendario", "cargar los calendarios".
- **Sede** es **femenino**: "la sede", "Todas las sedes", "una de las sedes".
- **Evento (externo) / Proveedor / Mapeo** son **masculino**: "un evento externo", "el proveedor", "Guardar mapeo".
- En confirm dialogs mantener concordancia: "¿Desconectar **esta** cuenta?".

### Etiquetas de proveedor (`CalendarProvider`)

`value` (enum) en inglés, etiqueta visible en español/comercial:

| `value` | Etiqueta | Ícono Fluent |
|---|---|---|
| `google` | "Google" | `CalendarLtrRegular` |
| `microsoft` | "Outlook" | `MailRegular` |
| `caldav` (futuro, no seedeado) | "CalDAV" | `GlobeRegular` |

### Etiquetas de salud (`ConnectionStatus`)

| `status` | Etiqueta | `<Badge>` color (token) |
|---|---|---|
| `connected` | "Conectada" | `success` |
| `needs_reauth` | "Reconectar" | `warning` |
| `error` | "Error" | `danger` |
| `revoked` | "Revocada" | `danger` |

### Sin i18n framework por ahora

Los textos están **directos como strings en cada componente**. Si negocio pide soporte multilingüe, introducir `next-intl` o similar después. Postergado (misma decisión que catalog/clinic/staff/crm/scheduling).

## Mapeo a fases de implementación (checklist de UI F0–F2)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md) y la spec §13 F0–F2; diferidas B1–B4 = roadmap, sin UI).

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: child "Calendarios externos" en el grupo "Clínica" de `NAV_ITEMS` (ruta `/clinic/calendarios-externos`, gate `["CALENDAR_CONNECTIONS_READ"]`, `MENU-CALENDAR` reservado); **registrar `CalendarSyncRegular` en el `ICONS` map de `Sidebar.tsx`** (importarlo de `@fluentui/react-icons`; fallback `CalendarLtrRegular` ya registrado).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.CALENDAR` (OAUTH start/callback, CONNECTIONS list/get/delete/calendars/sources, EXTERNAL_EVENTS).
- [ ] `types/calendar.types.ts`: interfaces espejo de Pydantic (`CalendarProvider`/`ConnectionStatus` enums, `CalendarConnectionItem`/`Detail`, `CalendarSourceItem`/`Create`, `CalendarSourcesReplace`, `ExternalCalendarOption`, `ExternalEventItem`/`Response`, `OAuthStartResponse`, `CalendarProviderOption`).
- [ ] `lib/schemas/calendar.schema.ts`: Zod (`sourceCreate` [external ids min 1, branch_id opcional, is_enabled bool], `sourcesReplace` [sources min 0]).
- [ ] Reusar `formatRelative` (client-only) de crm para "Última revisión: hace N"; reusar `<EmptyState>`/`<ConfirmDialog>`/`<MessageBar>` del template; reusar `<Dropdown>` de sede de `clinic` (`GET /clinic/branches/active`).
- [ ] La página `/clinic/calendarios-externos` **NO** se construye aún (paquete frontend inerte salvo nav/types/endpoints/schemas). QA E2E/PROD RO F0 = login admin + assert perm count + ver el item en el sidebar + ruta `/calendar/*` → 404 (módulo backend no registrado).

### F1 — Conexión + mapeo
- [ ] **Pantalla 1** `/clinic/calendarios-externos`: `CalendarConnectionsClient` (lista de cards prefetcheada por el RSC con `requirePermission("CALENDAR_CONNECTIONS_READ")`) + `ConnectionCard` (ícono proveedor + `account_email` + badge salud + menú `⋮` + "Última revisión") + botones "Conectar Google"/"Conectar Outlook" (Server Action `startOAuth` devuelve `{ auth_url }` → cliente `window.location.href = auth_url`) + manejo del callback (`?calendar_error=CODE` → MessageBar mapeado).
- [ ] `SourceMappingTable` (filas calendario→sede con `<Dropdown>` [Todas las sedes/(no mapear)/sedes] + `<Switch>` `is_enabled` + bulk "Guardar mapeo" → `replaceSources` → `PUT .../sources`; carga de calendarios live `GET /connections/{id}/calendars`; validación Zod; estados loading/error/empty).
- [ ] Reconectar (`startOAuth`) + Desconectar (`<ConfirmDialog destructive>` → `DELETE`) + read-only sin `CALENDAR_CONNECTIONS_WRITE`.
- [ ] Migración backend `0025_calendar_connection` (no toca UI).

### F2 — Lectura informativa (overlay)
- [ ] **Pantalla 2** overlay en `scheduling/calendario`: MOD del `CalendarClient` (llamar `fetchExternalEvents(branch_id, from, to)` + pasar a `CalendarGrid`) + MOD de `CalendarGrid` (prop opcional `externalEvents` + render de la capa rayada/atenuada no-clicable + `layoutOverlaps` para solapamiento + leyenda "Cita medisage"/"Evento externo") + aviso de salud best-effort (`<MessageBar intent="warning">`) + gating por `CALENDAR_EXTERNAL_EVENTS_READ`.
- [ ] **Pantalla 2.b** aviso suave en el `BookingWizard` (paso 3): `<MessageBar intent="info">` cuando el slot solapa un evento externo (advisory, no bloquea).
- [ ] Sin migración (F2 no crea tablas). El overlay depende de `scheduling` F4 (la grilla) ya en prod.

### Diferidas (B1–B4) — sin UI
- [ ] Documentadas como roadmap en README/design (modo bloqueante, per-doctor + push, sync por webhooks + tabla `ExternalEvent`, 3er proveedor CalDAV). **No se diseñan pantallas aquí.**
</content>
</invoke>
