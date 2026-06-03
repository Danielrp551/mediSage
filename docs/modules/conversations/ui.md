# Módulo `conversations` — UI design

> **Última actualización**: 2026-06-03 (rediseño CQRS: stream de mensajes en Firestore)
> **Audiencia**: developer implementando las pantallas de `conversations` en `frontend/src/app/(main)/conversaciones/`.
> **Pre-requisito**: leer [`README.md`](./README.md) (overview — **fuente autoritativa** de entidades/campos/endpoints/permisos/códigos de error; deben coincidir entre las 4 fichas), [`backend.md`](./backend.md) (contracts) y [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md) (patrones del template). Spec autoritativa en `C:/tmp/conversations_spec.md` + brief de rediseño `C:/tmp/conversations_firestore_redesign.md` (este último SUPERSEDE la persistencia de mensajes: a Firestore como read-model CQRS). Arquitectura del stream real-time en [ADR-011](../../decisions/ADR-011-firestore-message-stream-cqrs.md) (nuevo); modelo en [ADR-004](../../decisions/ADR-004-conversation-channel-account.md) (revisado 2026-06-03 — Message ya no es entidad Postgres relacional), resolución de secretos en [ADR-010](../../decisions/ADR-010-runtime-secret-resolution.md), forward-FK diferidas en ADR-009.

> **Alineación con crm/staff/clinic/catalog (módulos gold-standard ya en prod)**: `conversations` reutiliza directamente los patrones shipped: DataTable + filtros con chip + deep-link (`OfficesClient`/`PersonsClient`), drawer de creación/edición simple (molde `VerticalsClient`/`LeadStatusDrawer` de catalog/crm), `StatusBadge` y `ChannelIcon` (custom, ya creados en crm — se **reusan**, no se duplican), `formatRelative` (helper **client-only** de `lib/utils/date.ts`, ya creado en crm). La gran diferencia es el **Inbox de 2 paneles** — el componente bespoke más pesado de este módulo, **análogo en peso (no en forma) al Timeline de Actividad de `crm`** y al calendario semanal de `staff`. Se documenta en detalle y, dentro de las fases del módulo, se construye **incrementalmente** (read-only en F2, composer + handoff en F3), sobre una base ya usable.

> **Contexto de diseño (binding por la spec)**: aplicar pensamiento de bandejas de mensajería modernas (Intercom, Front, Crisp, WhatsApp Business, Zendesk Agent Workspace) **ejecutado DENTRO de Fluent UI 9** del template. Consistencia con catalog/clinic/staff/crm shipped **>** introducir un estilo nuevo (regla de la metodología). Detalles técnicos no negociables:
> - `brandPalette` solo tiene `primary`/`primaryHover`/`primaryPressed`/`primarySelected` — **NO existe `accent`**. Para otros colores usar tokens Fluent (`tokens.colorPaletteRedForeground1` para "falló el envío", `tokens.colorPaletteGreenForeground1` para "leído", `tokens.colorNeutralForeground3` para mensajes de sistema, etc.) o el `color` hex del catálogo (badges de estado/canal).
> - Cualquier cálculo de la fecha de **"hoy"/"ayer"** que afecte el render (agrupación del hilo por día, "hace 2 min", separador "Hoy"/"Ayer") debe ser **client-only** — el SSR corre en UTC y desfasa el día en Lima (UTC-5). Lección recurrente de `staff`/`crm` (`new Date()` en SSR rompe el día y produce mismatch de hidratación).
> - **El hilo (right pane) es REAL-TIME vía listeners de Firestore** (rediseño CQRS, ADR-011): los mensajes aparecen al instante con `onSnapshot`, sin polling del hilo; los estados de mensaje (✓/✓✓/leído/⚠) también llegan en vivo. El browser solo **LEE** el stream (read-only; `signInWithCustomToken` + Security Rules que espejan el RBAC) — **enviar/tomar/liberar/cerrar siguen 100 % por el backend server-side** (no se rompe "el browser no muta el backend"). **El listado (left pane) sigue por POLLING, no SSE/WebSocket** (decisión de la spec §1: Cloud Run con `min-instances 0` + cpu-throttling no favorece conexiones persistentes para las queries SQL del inbox). Refetch periódico (~10 s) de la lista, pausable. El listado podría migrar a live (misma collection Firestore) en una fase posterior; el real-time del hilo es lo prioritario.

---

## Glosario inglés → español del módulo (binding — UI 100 % en español)

> `key`, `code`, slugs, nombres de columna, enums y CSS classes se mantienen **en inglés** (identificadores de código). Solo los textos visibles van traducidos. Este glosario fija el vocabulario de TODA la UI de conversations; no inventar sinónimos.

| Término (código / inglés) | Etiqueta visible (español) | Género / notas |
|---|---|---|
| Conversation | **Conversación** | femenino ("la conversación", "esta conversación") |
| Message | **Mensaje** | masculino ("el mensaje", "un mensaje") |
| Channel / ChannelType | **Canal** | masculino ("el canal", "este canal") |
| ChannelAccount | **Cuenta de canal** / "Canal" (en el nav) | femenino la entidad; en el nav se rotula "Canales" |
| Inbox | **Bandeja** | femenino ("la bandeja", "tu bandeja") |
| My inbox | **Mi bandeja** | — |
| Take (assign to me) | **Tomar** | verbo; botón "Tomar" |
| Release (hand off) | **Liberar** | verbo; botón "Liberar" |
| Close | **Cerrar** | verbo; botón "Cerrar" |
| Reopen | **Reabrir** | verbo; botón "Reabrir" |
| Assigned to | **Asignado a** | "Asignado a Ana Pérez" |
| Unassigned | **Sin asignar** | — |
| Unread / unread_count | **Sin leer** / "N sin leer" | — |
| Mark read | **Marcar como leída** | la conversación es femenina |
| Inbound (message) | **Recibido** / "entrante" | mensaje del contacto |
| Outbound (message) | **Enviado** / "saliente" | mensaje del asesor |
| System (message) | **Sistema** | mensaje/nota de sistema |
| sent (status) | **Enviado** (✓) | estado del mensaje saliente |
| delivered (status) | **Entregado** (✓✓) | — |
| read (status) | **Leído** (✓✓ azul) | — |
| failed (status) | **Falló el envío** (⚠) | masculino "el envío" |
| Retry | **Reintentar** | verbo; acción sobre un mensaje fallido |
| Send | **Enviar** | botón del composer |
| Contact (sender) | **Contacto** | masculino — la persona del otro lado |
| Advisor (sender) | **Asesor** | masculino |
| Bot (sender) | **Bot** | masculino (no se usa en MVP) |
| Open (status) | **Abierta** | conversación abierta |
| Closed (status) | **Cerrada** | conversación cerrada |
| Last message | **Último mensaje** | masculino |
| Composer | **(redactor)** — no se rotula; es el área de escritura | — |
| Verify token | **Token de verificación** | masculino |
| Secret / secret_name | **Secreto** / "Nombre del secreto" | "configurado" / "sin configurar" |
| External identifier | **Identificador externo** | el número WA Business |
| Attachment | **Adjunto** | masculino (modelado; render diferido a F4) |

> Decisión de género (igual criterio que crm): **Conversación / Bandeja / Cuenta** son **femeninos**; **Mensaje / Canal / Asesor / Contacto / Envío / Adjunto / Identificador / Token / Secreto** son **masculinos**. Coherencia en confirms, empties y errores.

---

## Decisión de arquitectura: 1 bandeja global + 1 mi-bandeja (mismo shell de 2 paneles) + 1 CRUD de canales

`clinic` estableció la regla, reafirmada por `staff` y `crm`: **si una entidad tiene sub-recursos con interacción propia (timelines, grids editables, máquinas de estado), su superficie es una página dedicada bespoke; si solo tiene metadata, va a drawer.** La `Conversation` cae claramente en el primer caso — tiene un **hilo de mensajes** (sub-recurso pesado, en vivo, con composer y estados de entrega), una **máquina de handoff** (tomar/liberar/cerrar/reabrir con su historial `ConversationAssignmentLog`) y un **contador de no leídos**. Por eso la bandeja NO es una DataTable de filas que abren un detalle aparte, sino un **layout de 2 paneles** (lista + hilo) tipo cliente de mensajería, donde seleccionar una conversación carga su hilo en el panel derecho **sin navegar** (URL state `?conv=<id>`). El `ChannelAccount`, en cambio, es **metadata de configuración** (admin) → CRUD con DataTable + drawer.

| Recurso | Superficie | Crear | Ver / Editar | Patrón |
|---|---|---|---|---|
| **Conversation (Bandeja global)** | `/conversaciones/bandeja` — **2 paneles** (lista izq filtrable + hilo der), gated `CONVERSATIONS_READ` | — (las crea el webhook inbound) | panel derecho (hilo + composer + handoff); selección vía `?conv=<id>` | **bespoke: inbox 2-paneles** (la pieza central) |
| **Conversation (Mi bandeja)** | `/conversaciones/mis-conversaciones` — **mismo shell de 2 paneles**, pre-acotado a `assignee_user_id = yo` (`/me/conversations/list`), gated `MY_CONVERSATIONS_READ` | — | igual al global | reusa el shell del inbox con un fetcher distinto |
| **Message** | — (no tiene superficie propia) | dentro del **composer** del hilo | inmutable (audit; sin editar/eliminar) | burbujas en el hilo |
| **ChannelAccount (Canales)** | `/conversaciones/canales` — DataTable, gated `CHANNEL_ACCOUNTS_READ` (admin) | **drawer** | **drawer** (el secreto NO se muestra en claro) | molde `VerticalsClient`/`LeadStatusDrawer` |
| **ConversationAssignmentLog** | — | — (lo escribe el handoff) | dentro del hilo (panel "Historial de asignación", colapsable) | lista vertical simple, read-only |
| **MessageAttachment** | — (modelado; processing diferido a F4) | — | placeholder en la burbuja ("📎 Adjunto — disponible próximamente") | — |

### Por qué la bandeja es 2 paneles y no DataTable + página de detalle

| Opción | Veredicto |
|---|---|
| **A. Layout de 2 paneles** (lista izquierda + hilo derecha; selección por `?conv=`) — patrón universal de bandejas (Intercom/Front/Gmail/WhatsApp Web). El asesor barre la lista, abre un hilo, responde y vuelve sin perder el contexto de la lista; el polling refresca ambos paneles in-situ; los no-leídos se ven de un vistazo. | **Elegida** |
| B. DataTable de conversaciones → click navega a `/conversaciones/{id}` (página de detalle, molde `PersonDetailShell`) | Rechazada — obliga a ida-y-vuelta por cada hilo (rompe el ritmo del asesor que atiende N chats), pierde el contexto de la lista al abrir uno, y el polling de "la lista" y "el hilo" en páginas separadas duplica el estado. La bandeja es un workspace, no un listado-detalle. |
| C. Drawer `size=large` con el hilo sobre la lista | Rechazada — el hilo (feed largo + composer + handoff) no cabe cómodo en ~640 px; el overlay tapa la lista que el asesor necesita ver; z-index frágil con popovers de handoff. Mismo veredicto que el calendario de staff y el timeline de crm. |
| D. Acordeón inline (expandir el hilo dentro de la fila) | Rechazada — no escala a un hilo largo + composer; rompe la densidad de la lista. |

> El inbox **reusa el espíritu** del Timeline de crm (feed cronológico agrupado por día, client-only, polling/refetch, tarjetas tipadas, performance con `React.memo` + `content-visibility`) pero con dos paneles y burbujas izq/der en vez de tarjetas a ancho completo. **NO se usa librería externa de chat/timeline** — se construye con primitivos Fluent (`Card`, `Avatar`, `Badge`, `Textarea`, `Button`, `Menu`, `Spinner`, `Skeleton`, `MessageBar`, `Tooltip`) + tokens del design system + `makeStyles`.

### Por qué Mi bandeja reusa el mismo shell

`/conversaciones/mis-conversaciones` es **el mismo componente de 2 paneles** que la bandeja global, parametrizado con un **fetcher distinto** (`POST /conversaciones/me/conversations/list` en vez de `POST /conversaciones/list`) y **sin el filtro "asignadas a mí / sin asignar"** (ya están todas asignadas a mí). Misma lección que crm con el `TransitionControl`/`AssignmentControl` parametrizados (un componente, dos usos) — evita duplicar el inbox. El gate del nav cambia (`MY_CONVERSATIONS_READ`).

## Sidebar — extensión de `NAV_ITEMS` (grupo "Conversaciones", gated `MENU-CONVERSATIONS`)

> ⚠ **Textos UI en español**. `key` e `icon` se mantienen en inglés (identificadores de código). Solo `label` va en español.

Agregar un parent item `conversations` con 3 children, entre `crm` y `admin`:

```ts
{
  key: "conversations",
  label: "Conversaciones",
  icon: "ChatRegular",                       // verificar en la versión de Fluent; fallback "CommentRegular"
  children: [
    { key: "bandeja",            label: "Bandeja",     icon: "MailInboxRegular",   url: "/conversaciones/bandeja",            permissions: ["CONVERSATIONS_READ"] },
    { key: "mis-conversaciones", label: "Mi bandeja",  icon: "PersonMailRegular",  url: "/conversaciones/mis-conversaciones", permissions: ["MY_CONVERSATIONS_READ"] },
    { key: "canales",            label: "Canales",     icon: "ChannelRegular",     url: "/conversaciones/canales",            permissions: ["CHANNEL_ACCOUNTS_READ"] },
  ],
},
```

> El parent usa `MENU-CONVERSATIONS` como gate de visibilidad del grupo. Cada child gatea por **su** permiso de lectura para que un **ASESOR** (que tiene `MENU-CONVERSATIONS`, `CONVERSATIONS_{READ,TAKE,RELEASE,CLOSE}`, `MESSAGES_{READ,SEND}`, `MY_CONVERSATIONS_READ` — ver [`_seed-and-roles.md`](../_seed-and-roles.md) y la spec §10) vea **Bandeja** y **Mi bandeja**, pero **NO Canales** (no tiene `CHANNEL_ACCOUNTS_READ` — solo el ADMIN configura canales). El **DOCTOR** no tiene ningún permiso de conversations → no ve el grupo. Los permisos finos (`MESSAGES_SEND`, `CONVERSATIONS_TAKE`…) se chequean en `page.tsx` vía `requirePermission(...)` y dentro de los componentes vía `<PermissionGuard>` / `usePermissions()`.

> Iconos Fluent (verificar que existan en la versión instalada; usar fallback si no): `ChatRegular`/`CommentRegular` (grupo), `MailInboxRegular`/`InboxRegular` (Bandeja), `PersonMailRegular`/`MailRegular` (Mi bandeja), `ChannelRegular`/`PhoneRegular` (Canales). Mismo criterio de verificación que `crm` con `PeopleRegular` y `staff` con `DoctorRegular`.

## Pantallas

Para cada una: layout ASCII + estados (empty / loading / no-results / refetching / error / sin permiso / cerrada) + tabla de componentes Fluent.

1. **`/conversaciones/bandeja` — el INBOX de 2 paneles** (la pieza central: lista filtrable [polling] + hilo con burbujas en vivo [real-time Firestore] + composer + handoff).
2. **`/conversaciones/mis-conversaciones`** — mismo shell, pre-acotado al asesor logueado.
3. **`/conversaciones/canales`** — CRUD de `ChannelAccount` (DataTable + drawer; el secreto nunca en claro).

---

### Pantalla 1 — `/conversaciones/bandeja` (el INBOX de 2 paneles — la pieza central)

> **HONESTIDAD (binding por la spec §11)**: este inbox es el **componente más pesado de `conversations`** (análogo en peso, no en forma, al Timeline de `crm` y al calendario semanal de `staff`). Fluent UI 9 **no trae** un componente de "inbox" ni de "chat" — se construye con primitivos de Fluent (`Card`, `Avatar`, `Badge`, `Tab`/`TabList`, `Textarea`, `Input`, `Dropdown`, `Menu`, `Button`, `Spinner`, `Skeleton`, `MessageBar`, `Tooltip`, `Divider`) + **tokens del design system** (`tokens.*`, `makeStyles`). **NO se usa librería externa de chat.** El lenguaje visual se inspira en Intercom/Front/WhatsApp Web (lista de conversaciones con preview + no-leídos a la izquierda, hilo de burbujas a la derecha, composer abajo) pero **enteramente dentro de Fluent**. Se construye **incremental**: F2 = read-only (recibir + ver), F3 = composer + handoff. Ver "Plan incremental" al final de esta pantalla.

#### Anatomía — mockup del layout de 2 paneles (estado normal)

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ MainShell                                                                                  │
│ ┌────────────┐ ┌───────────────────────────────────────────────────────────────────────┐ │
│ │  Sidebar   │ │ TopBar                                                                  │ │
│ │            │ ├───────────────────────────────────────────────────────────────────────┤ │
│ │ ▸ Inicio   │ │  Bandeja                                                                │ │
│ │ ▸ Catálogo │ │  Atiende las conversaciones entrantes de tus canales.                   │ │
│ │ ▸ Clínica  │ ├──────────────────────────────────┬────────────────────────────────────┤ │
│ │ ▸ Staff    │ │  PANEL IZQUIERDO (lista ~360px)  │  PANEL DERECHO (hilo, resto)        │ │
│ │ ▸ CRM      │ │ ┌──────────────────────────────┐ │ ┌────────────────────────────────┐ │ │
│ │ ▾ Convers. │ │ │[Estado:Abiertas▾][Canal:T.▾] │ │ │ Ana Torres        ●Abierta      │ │ │
│ │  • Bandeja█│ │ │[● Sin asignar][● Mías]       │ │ │ 📱 WhatsApp · +51 999 111 222  │ │ │
│ │  • Mi band.│ │ │ 🔍 Buscar nombre/contacto…   │ │ │ Asignado a: Ana Pérez          │ │ │
│ │  • Canales │ │ ├──────────────────────────────┤ │ │ [Tomar][Liberar][Cerrar]  ⟳⏸ │ │ │
│ │ ▸ Admin    │ │ │▎Ana Torres      📱  hace 2m  │ │ ├────────────────────────────────┤ │ │
│ │            │ │ │  Hola, quería consultar…  ②  │ │ │ ── Hoy ──────────────────────  │ │ │
│ │            │ │ ├──────────────────────────────┤ │ │            ┌──────────────────┐ │ │ │
│ │            │ │ │ Luis Rojas      📱  hace 1h  │ │ │            │ Hola, quería con-│ │ │ │
│ │            │ │ │  Perfecto, gracias        ──  │ │ │            │ sultar precios.  │ │ │ │
│ │            │ │ ├──────────────────────────────┤ │ │            │        2:14 p. m.│ │ │ │
│ │            │ │ │ María Quispe    💬  ayer     │ │ │            └──────────────────┘ │ │ │
│ │            │ │ │  ⚙ Conversación cerrada   ──  │ │ │  ┌──────────────────┐          │ │ │
│ │            │ │ ├──────────────────────────────┤ │ │  │ Claro, con gusto │          │ │ │
│ │            │ │ │  … (scroll, refetch ~10s)    │ │ │  │ te ayudo.        │          │ │ │
│ │            │ │ │                              │ │ │  │ 2:15 p. m.   ✓✓  │ ← leído  │ │ │
│ │            │ │ │                              │ │ │  └──────────────────┘          │ │ │
│ │            │ │ │                              │ │ │      ── Sistema ──             │ │ │
│ │            │ │ │                              │ │ │   Ana Pérez tomó la conversa-  │ │ │
│ │            │ │ │                              │ │ │   ción · 2:15 p. m.            │ │ │
│ │            │ │ │                              │ │ ├────────────────────────────────┤ │ │
│ │            │ │ │                              │ │ │ ┌────────────────────────┐[Env]│ │ │
│ │            │ │ │                              │ │ │ │ Escribe un mensaje…    │ ↵   │ │ │
│ │            │ │ └──────────────────────────────┘ │ │ └────────────────────────┘     │ │ │
│ │            │ │  Mostrando 3 · ⟳ hace 4s         │ └────────────────────────────────┘ │ │
│ └────────────┘ └──────────────────────────────────┴────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

> Leyenda de la lista: `▎` = barra lateral de "seleccionada"; el número en círculo (`②`) = `unread_count`; `📱`/`💬` = `ChannelIcon` del canal; el texto bajo el nombre = `last_message_preview` (truncado); a la derecha = `formatRelative(last_message_at)` (**client-only**). `──` = sin no-leídos.

#### Panel izquierdo — lista de conversaciones (filtros + chips + búsqueda)

Lista vertical scrolleable (NO una `DataTable` — son "tarjetas-fila" densas tipo bandeja). Cada ítem mapea a `ConversationListItem` (ver [`backend.md`](./backend.md) y la spec §8).

**Filtros (deep-linkables, chip + ×)** — espejo del patrón `OfficesClient`/`PersonsClient`, traducidos a query params del `POST /conversaciones/list`:

- **Filtro Estado** (`<Dropdown>`): "Abiertas" (`?status=open`, **default**) / "Cerradas" (`?status=closed`) / "Todas". Sincronizado con `?status=` vía `nuqs useQueryState`. Chip "Estado: Abiertas ✕". `status` es columna real (`ALLOWED_FIELDS`) → filtra server-side.
- **Filtro Canal** (`<Dropdown>`): opciones de `GET /conversaciones/channel-accounts/active` → `ChannelAccountOption[]` (cada opción con su `ChannelIcon` + nombre). `null` = "Todos los canales". `?channel_account_id=X`. Chip "Canal: {nombre} ✕". `channel_account_id` es columna real → filtra server-side.
- **Toggle "Sin asignar"** (`<Switch>`/chip): `?unassigned=true` → el backend filtra `assignee_type='unassigned'`. Útil para que cualquier asesor "agarre" lo que está en la bandeja compartida.
- **Toggle "Mías"** (`<Switch>`/chip): `?assignee_user_id=<yo>` → filtra a las asignadas al asesor logueado. (En **Mi bandeja** este filtro NO aparece — ya están todas pre-acotadas; ver Pantalla 2.)
- **Búsqueda (client-side por nombre/identificador)**: el `<Input contentBefore={<SearchRegular/>}>` filtra **client-side** sobre las conversaciones ya cargadas, matcheando contra `person.full_name` **y** `last_message_preview` (denormalizados, **no** `ALLOWED_FIELDS`). Placeholder "Buscar nombre o contacto…". Lección hotfix `cd10c78` de staff: jamás server-sortear/filtrar por columna denormalizada → da 400.

> **Denormalización sin N+1 / ALLOWED_FIELDS** (spec §7): `person` (full_name), `channel_account` (name), `assignee_user` (full_name), `last_message_preview` se hidratan por **batch map** en el service. Estas columnas **NO** son server-sortable/filterable por su texto. Solo son `ALLOWED_FIELDS`: `status`, `assignee_type`, `assignee_user_id`, `channel_account_id`, `last_message_at`, `unread_count`, `created_on`. **`defaultSort = last_message_at desc`** (columna real; el prefetch del RSC y el `defaultSort` de la lista DEBEN coincidir — lección desync footer). El badge de no-leídos puede mostrarse arriba (sort secundario opcional client-side: no-leídas primero), pero el sort server-side base es `last_message_at desc`.

**Cada ítem de la lista** (componente `ConversationListItem`, memoizado):
- Barra lateral `▎` (color `tokens.colorBrandStroke1`) si es la conversación seleccionada (`?conv=<id>`).
- `ChannelIcon` (reuse de crm) + **nombre del contacto** (`person.full_name`; "Contacto (WhatsApp)" si la Person nació del webhook sin pushname — el placeholder de la spec §1).
- **Preview** = `last_message_preview` (1 línea, truncado con `…`); si la última actividad fue de sistema, prefijo `⚙` ("⚙ Conversación cerrada").
- **Timestamp** = `formatRelative(last_message_at)` (**client-only**): "ahora", "hace 2 min", "hace 1 h", "ayer", "12 may".
- **Badge de no-leídos**: `<Badge appearance="filled" color="brand">{unread_count}</Badge>` (círculo) si `unread_count > 0`; oculto si 0. Acento visual extra (nombre en `fontWeight semibold`) cuando hay no-leídos.
- **Mini-badge de asignación** (sutil, en hover o segunda línea): inicial del asesor o "Sin asignar".
- Estado **cerrada**: la fila se atenúa (`opacity 0.7`) y muestra un mini-badge "Cerrada".

#### Panel derecho — el hilo de la conversación seleccionada

Cuando hay `?conv=<id>`, se monta el hilo: header de conversación + feed de burbujas + composer + controles de handoff. El hilo es **real-time** (rediseño CQRS, ADR-011): se abre un listener `onSnapshot(collection(db, 'conversations', cid, 'messages'), orderBy('created_at'))` contra Firestore (read-only), de modo que los mensajes nuevos y sus cambios de estado aparecen **al instante**, sin polling del hilo. El token Firebase se obtiene server-side (`getRealtimeToken()` → `POST /conversaciones/realtime/token`, gated `CONVERSATIONS_READ`/`MY_CONVERSATIONS_READ`) y se usa con `signInWithCustomToken`; las Security Rules espejan el RBAC. **Las mutaciones (enviar/tomar/liberar/cerrar/reabrir/marcar-leída) NO tocan Firestore desde el browser** — van por el backend (Next server → FastAPI → Meta + Firestore vía Admin SDK).

**Header del hilo** (sticky arriba):
- **Nombre del contacto** (`person.full_name`) + click → (futuro) navega a `/crm/personas/{person_id}` (link al contacto en crm; MVP: link plano si hay `PERSONS_READ`, sino texto plano).
- Subtítulo: `ChannelIcon` + "{label del canal} · {external_identifier del contacto}" (ej. "WhatsApp · +51 999 111 222").
- **Badge de estado**: `●Abierta` (`tokens.colorPaletteGreenForeground1`) / `Cerrada` (`tokens.colorNeutralForeground3`).
- **Badge de asignación**: "Asignado a {nombre}" (avatar inicial) o "Sin asignar" (`tokens.colorNeutralForeground3`).
- **Controles de handoff** (`Tomar` / `Liberar` / `Cerrar` / `Reabrir`) — ver más abajo, gating por permiso + estado.
- **Controles de polling / estado live**: `⟳` (refrescar ahora) + `⏸/▶` (pausar/reanudar el polling **del listado**) + indicador sutil "⟳ hace 4s" del listado. El **hilo** ya no poll-ea (es real-time Firestore): junto a estos controles, un indicador sutil "● En vivo" cuando el listener está conectado (y "Reconectando…" si la suscripción se cae).
- (Colapsable) **Historial de asignación**: un `<Accordion>`/popover "Ver historial de asignación" que lista los `ConversationAssignmentLog` (`to_assignee` ← `from_assignee` · actor · fecha relativa; "Sistema" cuando `by_actor_user_id` es NULL). Read-only.

**Feed de mensajes** (burbujas, agrupado por día):

```
│ ── Hoy ──────────────────────────────────────────────────────────────────  │
│                                              ┌────────────────────────────┐ │  ← inbound (contacto): izquierda
│                                              │ Hola, quería consultar       │
│  (contacto, izq, fondo neutral)              │ precios de la limpieza.      │
│                                              │                  2:14 p. m.  │
│                                              └────────────────────────────┘ │
│  ┌────────────────────────────┐                                            │  ← outbound (asesor): derecha
│  │ Claro, con gusto te ayudo.   │                                            │
│  │ (asesor, der, fondo brand)   │                                            │
│  │                  2:15 p. m. ✓✓│ ← leído (✓✓ azul)                          │
│  └────────────────────────────┘                                            │
│  ┌────────────────────────────┐                                            │  ← outbound fallido
│  │ El precio base es S/ 120.    │                                            │
│  │                  2:16 p. m. ⚠ │ Falló el envío  [ Reintentar ]            │
│  └────────────────────────────┘                                            │
│              ── Sistema ──                                                  │  ← system: centrado, atenuado
│        ⚙  Ana Pérez tomó la conversación · 2:15 p. m.                       │
│ ── Ayer ─────────────────────────────────────────────────────────────────  │
│              ⚙  Conversación creada desde WhatsApp · ayer 9:00              │
```

> **HONESTIDAD**: orientación de las burbujas — la spec §11 dice "inbound (izq, contacto) / outbound (der, asesor)". Se respeta: **inbound = izquierda**, **outbound = derecha**, **system = centrado**. (En el mockup ASCII de arriba el inbound se dibuja desplazado por límites del arte; la implementación va inbound-izquierda.)

- **Burbuja inbound** (`direction=inbound`, `sender_type=contact`): alineada a la **izquierda**, fondo `tokens.colorNeutralBackground3`, esquinas redondeadas (esquina inferior-izq recta). Sin estado de entrega (los inbound no lo tienen). Timestamp `formatRelative`/hora (client-only).
- **Burbuja outbound** (`direction=outbound`, `sender_type=advisor`): alineada a la **derecha**, fondo `brandPalette.primary` (texto `colorNeutralForegroundOnBrand`). **Estado de mensaje** abajo-derecha (ver tabla de estados). Si `sender_type=bot` (futuro) → variante con avatar de bot.
- **Burbuja system** (`sender_type=system`, `content_type=system_notification`): **centrada**, sin burbuja "de chat" sino un chip atenuado (`tokens.colorNeutralForeground3`, ícono `⚙`), ancho intrínseco. Ejemplos del contenido (lo escribe el backend como `content` del system_notification): "Conversación creada desde WhatsApp", "Ana Pérez tomó la conversación", "Conversación liberada a la bandeja", "Conversación cerrada", "Conversación reabierta". (El backend emite `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED` a la timeline de **crm** — §1 de la spec; en el hilo de conversations estos hitos se ven como mensajes/notas de sistema.)
- **Adjuntos (F4, diferido)**: si `attachments[].length > 0` (no ocurre en MVP — texto primero), placeholder en la burbuja "📎 Adjunto — disponible próximamente". El render real (imagen/audio/documento) llega en F4.

**Estados de mensaje (outbound)** — chip/ícono abajo-derecha de la burbuja, mapeo `external_status` → glifo + copy + color:

| `external_status` | Glifo | Tooltip / copy | Color (token) |
|---|---|---|---|
| `NULL` (recién persistido, aún enviando) | `🕓` (reloj) | "Enviando…" | `tokens.colorNeutralForeground3` |
| `sent` | `✓` | "Enviado" | `tokens.colorNeutralForeground3` |
| `delivered` | `✓✓` | "Entregado" | `tokens.colorNeutralForeground2` |
| `read` | `✓✓` (azul) | "Leído" | `tokens.colorPaletteBlueForeground2` |
| `failed` | `⚠` | "Falló el envío" + acción **Reintentar** | `tokens.colorPaletteRedForeground1` |

> **HONESTIDAD (binding por la spec §1)**: un envío fallido **persiste el `Message`** con `failed_at`/`failure_reason` y el endpoint devuelve **200** (no 502), con el mensaje en estado `failed`. La UI lo muestra como burbuja con ⚠ + botón **"Reintentar"** que hace `POST /conversaciones/{id}/messages` con el mismo `content` (crea un mensaje nuevo; no re-envía el fallido — el fallido queda como audit inmutable, `Message` no tiene SoftDelete). Tooltip con `failure_reason` al hover sobre el ⚠.

**Day-groups + "Hoy/Ayer" (client-only — lección TZ)**:
- El feed se agrupa en secciones con encabezado **"Hoy" / "Ayer" / "{DD mmm YYYY}"**. El cálculo de qué es "hoy"/"ayer" se hace **client-only** (la lección recurrente de staff/crm: el servidor en UTC pondría la frontera del día 5 h corrida en Lima). Implementación: el componente que decide los grupos es `"use client"` y calcula `today`/`yesterday` con `new Date()` **dentro de un `useEffect`/`useMemo` montado en cliente** (no en el render del servidor), evitando el mismatch de hidratación.
- Dentro de cada grupo, los mensajes van **ascendentes por `sent_at`** (lo más nuevo abajo — orden natural de chat, contrario al timeline de crm que va descendente). El scroll arranca **pegado al fondo** (último mensaje visible); al llegar mensajes nuevos **por el listener Firestore** (real-time), si el usuario está al fondo → auto-scroll; si está leyendo arriba → badge flotante "↓ N mensajes nuevos" (no robar el scroll).

**Composer** (abajo del hilo, gated `MESSAGES_SEND` + ser el assignee):
- `<Textarea>` autosize (1–6 líneas) + botón **Enviar** (`<Button appearance="primary" icon={<SendRegular/>}>`). Enter envía, Shift+Enter = salto de línea.
- Al enviar: `POST /conversaciones/{id}/messages { content, content_type: "text" }` (server-side; el browser **no** escribe Firestore). El hilo es real-time: en cuanto el backend persiste el doc del mensaje (status `pending`), **el listener Firestore lo muestra solo** con estado `🕓 Enviando…`; cuando el backend actualiza el doc tras llamar a Meta, el mismo listener reconcilia `external_status` (sent/failed) **en vivo** — sin re-fetch del hilo. Opcionalmente se pinta una burbuja optimista local hasta que llega el snapshot. `router.refresh()` (o el polling del listado) refresca los denormalizados de la **lista** (`last_message_preview`/`last_message_at`).
- MVP solo texto: el composer **no** ofrece adjuntar (placeholder de ícono 📎 deshabilitado con tooltip "Adjuntos disponibles próximamente" — F4). Enviar otro `content_type` → backend `UNSUPPORTED_CONTENT_TYPE` (400); no ocurre desde la UI.

**Controles de handoff** (header del hilo) — botones gated por permiso **y** por estado de la conversación:

| Botón | Permiso | Visible / habilitado cuando | Endpoint | Efecto |
|---|---|---|---|---|
| **Tomar** | `CONVERSATIONS_TAKE` | conversación `open` y (sin asignar **o** asignada a otro) | `POST /conversaciones/{id}/take` | `assignee_user_id = yo`, resetea `unread_count`, emite `CONVERSATION_TAKEN` a crm + nota de sistema en el hilo |
| **Liberar** | `CONVERSATIONS_RELEASE` | conversación `open` y asignada (idealmente a mí) | `POST /conversaciones/{id}/release` con `{to_assignee_type, to_bot_configuration_id?, reason?}` | cambia el assignee (a `unassigned` por default en MVP — no hay bot), emite `CONVERSATION_RELEASED` |
| **Cerrar** | `CONVERSATIONS_CLOSE` | conversación `open` | `POST /conversaciones/{id}/close` | `status=closed`, `closed_at=now`, cierra el log de asignación vigente; oculta el composer |
| **Reabrir** | `CONVERSATIONS_TAKE` | conversación `closed` | `POST /conversaciones/{id}/reopen` | `status=open` (valida que no haya otra abierta para la misma Person+canal → `CONVERSATION_ALREADY_OPEN` 409) |
| **Marcar como leída** | `CONVERSATIONS_READ` | `unread_count > 0` | `POST /conversaciones/{id}/mark-read` | `unread_count=0` (se dispara también al abrir el hilo, opcional) |

> **Mutaciones de handoff hacen refetch de la lista Y `router.refresh()`** (lección crm F3): la conversación pinta datos **denormalizados** (badge "Asignado a X", estado, no-leídos) que el RSC y la lista del otro panel también muestran. Sin `router.refresh()`, el badge del header de la lista / del item queda **stale** (bug MAJOR cazado en crm F3). Tras cada take/release/close/reopen: re-fetch de la lista + `router.refresh()`. (El **hilo** no necesita refetch: el backend escribe la nota de sistema y el `conversation_upsert` a Firestore vía Admin SDK, y el listener del hilo + el badge del header de la conversación se actualizan **en vivo**.)

> **Release en MVP**: como `bots` no existe, "Liberar" en MVP siempre devuelve la conversación a `unassigned` (bandeja compartida). El `<Dialog>` de liberar puede ofrecer solo "Devolver a la bandeja" + un `reason?` opcional. El destino `bot` queda en el contrato (enum `AssigneeType`) pero deshabilitado en la UI del MVP.

#### Listado por polling (no SSE) + hilo por real-time Firestore — refresco silencioso

> **Binding por la spec §1 + rediseño CQRS (ADR-011)**: el **listado** (panel izquierdo) usa **polling**, NO SSE/WebSocket; el **hilo** (panel derecho) es **real-time** vía listener de Firestore (no poll-ea). Reglas del polling del listado:
- **Intervalo ~10 s** (configurable; constante `CONVERSATIONS_POLL_MS`). Un `useInterval`/`setInterval` en el componente cliente re-consulta **la lista del panel izquierdo** (`POST /conversaciones/list`). **El hilo ya NO se poll-ea**: el panel derecho se alimenta de un `onSnapshot` de Firestore (read-only) que entrega mensajes y cambios de estado al instante.
- **Refresco silencioso** (no flash): el refetch NO muestra spinner de carga completo (eso es solo el primer load); en su lugar, un indicador sutil "⟳ hace Ns" y, si la data cambió, se reconcilia in-place. (Lección crm F5: refetch silencioso sin flash — no remontar la lista entera, reconciliar por id.) El hilo se reconcilia análogamente por `id` desde el snapshot (no remonta).
- **Pausable**: botón `⏸/▶` en el header pausa/reanuda el **polling del listado** para que el asesor que está leyendo no sufra reordenamientos. El polling del listado se **pausa automáticamente** mientras el composer tiene foco/texto sin enviar. (El listener del hilo es live y barato; no se "pausa" — Firestore solo empuja deltas.)
- **Pausa en pestaña oculta**: si `document.visibilityState === "hidden"`, pausar el polling del listado (no golpear el backend con la pestaña en background); reanudar al volver al foco. (Lección crm F5 diferida: "reloj/label de tab ocioso" — aquí se aplica.) El listener Firestore puede detacharse en `hidden` y re-suscribirse al volver para ahorrar reads.
- **Sin polling concurrente**: si una request de polling del listado sigue en vuelo cuando toca la siguiente, se omite (no encolar). Al cambiar de conversación (`?conv=`), **detach del listener anterior** (`unsubscribe()`) antes de suscribir el nuevo; el `AbortController` cancela cualquier fetch fallback del hilo obsoleto.

#### Estados

**Loading (primera carga de la lista)**: panel izquierdo con 6–8 `ConversationListItem` skeletons (avatar + 2 líneas + badge); panel derecho con el empty "selecciona una conversación". El server-prefetch del `page.tsx` (primera página de `/conversaciones/list`) evita ver esto en el primer load del global.

**Loading (hilo, al seleccionar una conversación)**: panel derecho con 4–5 burbujas skeleton (alternando izq/der) + header ya poblado (viene del item de la lista). Composer deshabilitado hasta que cargue.

**Empty — sin conversaciones (bandeja vacía, sin filtro)**:
```
┌────────────────────────────────────────────────────────────────────┐
│                                                                      │
│                       📭  (MailInboxRegular)                         │
│                                                                      │
│                     Aún no hay conversaciones                        │
│      Cuando un contacto escriba a uno de tus canales, su             │
│      conversación aparecerá aquí.                                    │
│                                                                      │
└────────────────────────────────────────────────────────────────────┘
```

**Empty — sin selección (hay lista, no hay `?conv=`)**: el panel derecho muestra:
```
┌────────────────────────────────────────────────────────────────────┐
│                       💬  (ChatRegular)                              │
│                  Selecciona una conversación                         │
│         Elige una conversación de la izquierda para ver el hilo      │
│         y responder.                                                 │
└────────────────────────────────────────────────────────────────────┘
```

**Empty — filtros sin matches**:
- Estado=Cerradas sin matches: "No hay conversaciones cerradas."
- Canal sin matches: "Este canal no tiene conversaciones todavía."
- "Sin asignar" sin matches: "No hay conversaciones sin asignar."
- Búsqueda client-side sin matches: "No hay resultados con los filtros actuales." / "Prueba quitar algún criterio o revisa la ortografía."

**Refetching (background / polling)**: NO opacity-0.55 de toda la lista (sería distractor con polling cada 10 s). En su lugar, indicador sutil "⟳ hace Ns" en el pie del panel izquierdo; reconciliación in-place. (Diferencia deliberada con clinic/staff que sí atenúan en el refetch manual — aquí el refetch es automático y frecuente.)

**Error (5xx en la lista)**: panel izquierdo con `<MessageBar intent="error">"No se pudo cargar la bandeja. Reintentando…"` + el polling sigue intentando (auto-recupera). 5xx global → `error.tsx`.

**Error (5xx al cargar el hilo)**: panel derecho con `<MessageBar intent="error">"No se pudo cargar la conversación."` + botón "Reintentar".

**Sin permiso para enviar (composer deshabilitado)**: si el viewer **no** tiene `MESSAGES_SEND`, o **no es el assignee** de la conversación (la conversación está asignada a otro), el composer se renderiza **deshabilitado** con un hint: "Toma la conversación para responder." (si tiene `CONVERSATIONS_TAKE`) o "No tienes permiso para responder en esta conversación." (si no). El backend re-valida con `NOT_CONVERSATION_ASSIGNEE` (403) como defensa en profundidad.

**Conversación cerrada (composer oculto)**: si `status=closed`, el composer **no se renderiza**; en su lugar una barra: "Esta conversación está cerrada." + botón **"Reabrir"** (gated `CONVERSATIONS_TAKE`). Las burbujas siguen visibles (read-only).

**Mensaje fallido (outbound failed)**: burbuja con ⚠ + "Falló el envío" + botón **"Reintentar"** (ver tabla de estados). Tooltip con `failure_reason`.

**Conflicto al reabrir (409 `CONVERSATION_ALREADY_OPEN`)**: toast/`MessageBar` "Ya existe una conversación abierta con este contacto en este canal." (no debería ocurrir desde la UI porque la UNIQUE parcial lo garantiza, pero el backend lo valida).

#### Performance (reglas vercel-react — binding)

> El inbox puede tener cientos de conversaciones (listado, polling ~10 s) y un hilo de cientos de mensajes (real-time vía Firestore listener). Reglas (de la skill vercel-react-best-practices):
- **`ConversationListItem` y `MessageBubble` memoizadas** (`React.memo`) — ni el polling del listado ni los deltas del listener Firestore deben re-renderizar toda la lista/hilo cuando llega data igual. Reconciliar por `id`; props estables; handlers (seleccionar, reintentar) vía `useCallback`.
- **Listas largas con `content-visibility: auto`** + `contain-intrinsic-size` en cada item/burbuja (CSS via `makeStyles`) → el navegador no paga layout/paint de lo que está fuera del viewport. Approach barato (sin virtualización) suficiente para el volumen esperado; si explota, evaluar virtualización después.
- **Paginación / historial del hilo**: el listener Firestore se abre acotado a los mensajes recientes (ej. `limit(50)` + `orderBy('created_at')`); al hacer scroll hacia arriba se trae el lote anterior (segunda query Firestore o el fallback `POST /conversaciones/{id}/messages/list` server-side) y se **prepend**ea (preservar la posición de scroll). Los mensajes **nuevos** llegan por el listener, no por re-fetch del hilo.
- **`useMemo` para la agrupación por día** (no recomputar grupos en cada delta del listener; solo cuando cambia la lista de mensajes).
- **Listener con reconciliación, no remontaje**: el `onSnapshot` aplica solo los `docChanges()` (added/modified/removed) por `id` + `external_status`, evitando flash y re-layout completo. Al cambiar `?conv=`, `unsubscribe()` del listener anterior antes de suscribir el nuevo (y `AbortController` para cualquier fetch fallback obsoleto).
- **Sin waterfalls**: el `page.tsx` (RSC) prefetcha la primera página de la lista + las opciones de canal + el token realtime (vía `getRealtimeToken()` server-side); el listener del hilo se abre al seleccionar (no en el primer render). El composer no dispara re-fetch del hilo en cada tecla.

#### Componentes Fluent UI / del template (Inbox)

| Concepto UI | Componente |
|---|---|
| Layout shell | `MainShell` (del template) |
| Layout 2 paneles | `InboxShell` (custom) — grid `360px 1fr` (`makeStyles`), responsive (ver Mobile) |
| Filtro Estado / Canal | `<Dropdown>` + `nuqs useQueryState("status"/"channel_account_id")` (patrón `OfficesClient`) |
| Toggles "Sin asignar" / "Mías" | `<Switch>`/chip + `useQueryState("unassigned"/"assignee_user_id")` |
| Chip filtro | `styles.chip` + `<Button icon={<DismissRegular/>}/>` (patrón `OfficesClient`) |
| Búsqueda | `<Input contentBefore={<SearchRegular/>}>` (filtro client-side) |
| Ítem de lista | `ConversationListItem` (custom, memoizado) — `<Card>`/`<div>` + `<Avatar>` + `ChannelIcon` + `<Badge>` (no-leídos) + `formatRelative` |
| Ícono de canal | `<ChannelIcon channel={c.channel_type} />` (**reuse de crm**; mapea `ChannelType` → ícono + label) |
| Header del hilo | `<div>` sticky + `<Avatar>` + badges de estado/asignación + botonera handoff + controles de polling |
| Badge estado conversación | `<Badge>` "Abierta"/"Cerrada" (color por estado, tokens) |
| Badge asignación | "Asignado a {nombre}" (`<Avatar size={20}>`) / "Sin asignar" |
| Botones handoff | `<Button>` Tomar/Liberar/Cerrar/Reabrir (gated `<PermissionGuard>` + estado) + `<Dialog>` para Liberar con `reason?` |
| Historial de asignación | `<Accordion>`/`<Popover>` "Ver historial de asignación" — lista vertical de `ConversationAssignmentLogItem` |
| Burbuja de mensaje | `MessageBubble` (custom, memoizada) — variantes inbound/outbound/system |
| Estado de mensaje | chip/glifo (`✓`/`✓✓`/azul/`⚠`/`🕓`) + `<Tooltip>` con copy + `failure_reason` |
| Acción reintentar | `<Button appearance="subtle" size="small">` "Reintentar" en burbuja fallida |
| Encabezado de día | `DayGroup` (custom, "use client", cálculo hoy/ayer **client-only**) |
| Composer | `<Textarea>` autosize + `<Button appearance="primary" icon={<SendRegular/>}>`; gated `MESSAGES_SEND` + assignee |
| Timestamp relativo | `formatRelative(iso)` (**reuse**, client-only) + `<Tooltip>` con hora/fecha absoluta |
| Controles de polling (listado) | `<Button icon={<ArrowSyncRegular/>}>` (refrescar) + `<ToggleButton>` (pausar) + label "⟳ hace Ns" — gobiernan el polling de la **lista** |
| Real-time del hilo | `onSnapshot(...)` del Web SDK de Firestore (read-only) en un `useEffect`; `getRealtimeToken()` (server action) + `signInWithCustomToken` (`lib/firebase/client.ts`); indicador "● En vivo" / "Reconectando…" |
| Auto-scroll / nuevos | badge flotante "↓ N nuevos" (`<Button appearance="primary" shape="circular">`) al llegar mensajes por el listener |
| Skeletons | `<Skeleton>` + `<SkeletonItem>` (items de lista + burbujas) |
| Empty / error | `<EmptyState>` (del DataTable o custom) + `<MessageBar intent="error">` |
| Perf | `React.memo` + `useCallback` + CSS `contentVisibility:"auto"` + `containIntrinsicSize`; `AbortController` |

#### Plan incremental (binding — construir en este orden)

> El inbox es el mayor riesgo de frontend de `conversations`. Construirlo de una sola vez es la trampa (igual que el Timeline de crm). Orden recomendado, alineado a las fases del módulo:

1. **Iteración A — F2 (read-only, recibir + ver)**: `InboxShell` de 2 paneles; panel izq = lista (filtros estado/canal/sin-asignar/mías + chips + búsqueda client-side + estados loading/empty/no-results/error); panel der = hilo read-only (header + burbujas inbound/outbound/system + estados de mensaje + day-groups client-only + paginación scroll-up). **Polling** de la lista (silencioso, pausable, pausa en pestaña oculta) + **hilo real-time vía listener Firestore** (`getRealtimeToken` + `signInWithCustomToken` + `onSnapshot` read-only; `lib/firebase/client.ts`). SIN composer ni handoff (la conversación entra por webhook; el asesor solo la **ve**). Con esto la bandeja ya **muestra** todo lo que el pipe inbound persiste, en vivo.
2. **Iteración B — F3 (composer + handoff + outbound real)**: composer (`<Textarea>` + Enviar, gated `MESSAGES_SEND` + assignee, optimista + reconciliación con `external_status`); controles de handoff (Tomar/Liberar/Cerrar/Reabrir, gated + por estado, con refetch + `router.refresh()`); reintento de mensajes fallidos; estados "sin permiso para enviar"/"cerrada (composer oculto)"; nota de sistema "tomó/liberó/cerró" en el hilo. Cablea el envío **real** contra Meta (el endpoint ya existe en F3 backend).

> Si el tiempo aprieta dentro de F2, la Iteración A (read-only) ya es entregable: la bandeja muestra los hilos entrantes en vivo. La Iteración B (F3) es la que convierte al asesor en autor. **Mantenerse dentro de Fluent tokens**; no introducir una librería de chat.

---

### Pantalla 2 — `/conversaciones/mis-conversaciones` (mi bandeja)

**El mismo `InboxShell` de 2 paneles** que la Pantalla 1, con **dos diferencias**:
1. **Fetcher**: usa `POST /conversaciones/me/conversations/list` (gated `MY_CONVERSATIONS_READ`) — solo las conversaciones con `assignee_user_id = <yo>`.
2. **Sin el filtro "Mías" ni "Sin asignar"** (ya están pre-acotadas a mí; mostrarlos sería redundante). Sí conserva los filtros **Estado** y **Canal** + búsqueda client-side + polling.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  Mi bandeja                                                                                │
│  Las conversaciones que tienes asignadas.                                                  │
│ ┌──────────────────────────────────┬────────────────────────────────────────────────────┐ │
│ │ [Estado:Abiertas▾][Canal:Todos▾] │  (hilo idéntico al de la bandeja global)            │ │
│ │ 🔍 Buscar nombre/contacto…       │                                                     │ │
│ │ ┌──────────────────────────────┐ │                                                     │ │
│ │ │▎Ana Torres   📱 hace 2m   ②  │ │                                                     │ │
│ │ │ Hola, quería consultar…      │ │                                                     │ │
│ │ └──────────────────────────────┘ │                                                     │ │
│ └──────────────────────────────────┴────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Continuidad "mis leads = mis chats"** (spec §1.3): un asesor que en crm ve "Mis leads" ve acá las conversaciones de esos mismos contactos (auto-asignadas al dueño del lead al crearse). Cierra el bucle de continuidad.
- **Empty (sin mías)**: "No tienes conversaciones asignadas todavía. Cuando se te asigne una conversación aparecerá aquí." + (si el viewer tiene `CONVERSATIONS_READ`) hint "Revisa la Bandeja para tomar conversaciones sin asignar." con link a `/conversaciones/bandeja`.
- **Empty (sin selección)**: idéntico a la global.
- Resto de estados (loading, error, refetching/polling, composer gating, cerrada): **idénticos** a la Pantalla 1 (mismo shell).

#### Componentes Fluent UI (mi bandeja)

| Concepto UI | Componente |
|---|---|
| Todo | `InboxShell` (**reuse** de Pantalla 1) con `fetcher={listMyConversations}` y `showAssignmentFilters={false}` |
| Header | `<h1>` "Mi bandeja" + `<p>` "Las conversaciones que tienes asignadas." |
| Empty mías | `<EmptyState>` + link a `/conversaciones/bandeja` |

---

### Pantalla 3 — `/conversaciones/canales` (CRUD de ChannelAccount — admin)

Lista (DataTable, molde `VerticalsClient` de catalog) de las cuentas de canal de la clínica + drawer create/edit. Gated `CHANNEL_ACCOUNTS_READ` (solo ADMIN). **El secreto nunca se muestra ni se edita en claro** — solo se ve el `secret_name` (referencia al secreto en GCP Secret Manager) + un estado "configurado / sin configurar".

```
┌──────────────────────────────────────────────────────────────────────────────┐
│   Canales                                                                      │
│   Configura las cuentas de canal por las que recibes y envías mensajes.        │
│                                                          [ + Nuevo canal ]     │
│   ╭─ DataTable ──────────────────────────────────────────────────────────╮   │
│   │ ⋯ │ Nombre            │ Canal     │ Identificador │ Secreto    │ Estado │   │
│   ├───┼───────────────────┼───────────┼───────────────┼────────────┼────────┤   │
│   │ ⋯ │ WhatsApp Estética │ 📱WhatsApp│ 51999111222   │●Configurado│ Activo │   │
│   │ ⋯ │ WhatsApp Dental   │ 📱WhatsApp│ 51988222333   │○Sin config.│ Activo │   │
│   ╰──────────────────────────────────────────────────────────────────────╯   │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Columnas** (`key` en inglés, header en español) — mapean a `ChannelAccountItem`:

| `key` | Header | Tipo | Sortable | Render |
|---|---|---|---|---|
| `actions` | `""` | RowActions | — | menú `…` con Ver/Editar/Eliminar (gated) |
| `name` | Nombre | text | ✅ (server) | `ChannelAccount.name` |
| `channel_type` | Canal | badge + ícono | ❌ (deep-link/filtro) | `<ChannelIcon channel={c.channel_type}/>` + label ES |
| `external_identifier` | Identificador externo | text (mono) | ❌ | `external_identifier` (número WA Business) |
| `secret_status` | Secreto | badge | ❌ | "● Configurado" (verde) si `secret_name` set / "○ Sin configurar" (neutral) si NULL |
| `active` | Estado | badge | ❌ | "Activo"/"Inactivo" (`ActiveMixin`) |

> `ALLOWED_FIELDS` del repo: `name`, `channel_type`, `external_identifier`, `active`, `created_on`. `secret_status` es **derivado** (de `secret_name` IS NOT NULL) → NO sortable. `defaultSort = created_on desc` o `name asc`.

**RowActions** (gated por `usePermissions()`):
- 👁 **Ver** — `CHANNEL_ACCOUNTS_READ`. Abre el drawer en modo read.
- ✏ **Editar** — `CHANNEL_ACCOUNTS_UPDATE`. Abre el drawer en modo edit.
- 🗑 **Eliminar** — `CHANNEL_ACCOUNTS_DELETE`. Confirm dialog (soft-delete).

**Botón "+ Nuevo canal"**: gated `<PermissionGuard anyOf={["CHANNEL_ACCOUNTS_CREATE"]}>`. Abre `ChannelAccountDrawer` en create.

#### Drawer create/edit (`ChannelAccountDrawer`)

```
                  ┌─────────────────────────────────────────────────┐
                  │  Nuevo canal                                 ✕ │
                  ├─────────────────────────────────────────────────┤
                  │  Nombre *                                       │
                  │  [ WhatsApp Estética                          ] │
                  │  Tipo de canal *                                │
                  │  [ WhatsApp                                  ▾] │
                  │  Identificador externo *  (número WA Business)  │
                  │  [ 51999111222                                ] │
                  │  ID del número (phone_number_id)                │
                  │  [ 123456789012345                            ] │
                  │  ───────────────────────────────────────────   │
                  │  Credenciales                                   │
                  │  Nombre del secreto (GCP Secret Manager)        │
                  │  [ medisage-whatsapp-estetica-qa              ] │
                  │  Estado: ● Configurado                          │
                  │  ⓘ El contenido del secreto (token de acceso,   │
                  │     app secret) NO se muestra ni se edita aquí. │
                  │     Se gestiona en Secret Manager.              │
                  │  Token de verificación (webhook)                │
                  │  [ mi-verify-token-123                        ] │
                  │  ───────────────────────────────────────────   │
                  │  ☑ Activo                                       │
                  ├─────────────────────────────────────────────────┤
                  │                        [ Cancelar ] [ Crear ]  │
                  └─────────────────────────────────────────────────┘
```

**Campos y validación (Zod, `channelAccountSchema`)** — espejo de `ChannelAccountCreate/Update` (ver [`backend.md`](./backend.md) y la spec §2.1):
- `name` requerido (1–120).
- `channel_type` requerido (`<Dropdown>` de `ChannelType` — MVP solo "WhatsApp" seleccionable; el resto del enum se lista pero deshabilitado con "(próximamente)" para dejar claro el roadmap). Reuse del `ChannelType` de crm.
- `external_identifier` requerido (1–255; número WA Business). **Conflicto 409 `CHANNEL_ACCOUNT_EXTERNAL_TAKEN`** si `(channel_type, external_identifier)` ya existe (UNIQUE parcial) → error inline en el campo: "Ya existe un canal con este identificador para este tipo de canal."
- `phone_number_id` opcional (≤64; id del número en WhatsApp Cloud API, para construir la URL de envío). Hint: "Lo provee Meta; se usa para enviar mensajes."
- **`secret_name`** opcional (≤255). **El secreto en sí NUNCA viaja al front** — solo este nombre/referencia. Debajo, un badge **read-only** "● Configurado" (si `secret_name` set) / "○ Sin configurar" (si NULL) + un `<MessageBar intent="info">`: "El contenido del secreto (token de acceso, app secret) no se muestra ni se edita aquí. Se gestiona en GCP Secret Manager." (spec §6, §8). En **local/dev** sin `secret_name`, el backend cae a fallback por env (la UI muestra "○ Sin configurar — usando credenciales de entorno").
- `webhook_verify_token` opcional (≤255; el challenge que compara el GET de Meta). **Editable en claro** (no es un secreto duro — lo envía Meta en el query y se compara; spec §2.1). Hint: "Lo defines en Meta y aquí; deben coincidir."
- `bot_configuration_id` / `default_campaign_id`: **NO en el form del MVP** (FKs forward, hoy siempre NULL; bots #6 / marketing #8 no existen). Se omiten del drawer hasta que esos módulos lleguen.
- `active` (`<Switch>`).

> **HONESTIDAD (binding por la spec §8)**: `ChannelAccountDetail` **NUNCA expone el secreto** — solo `secret_name` y los flags de "configurado". `get_credentials(ca)` es server-only (lo usa el webhook/outbound). La UI jamás recibe `access_token`/`app_secret`. No agregar un campo "ver secreto"; si negocio lo pide, va contra Secret Manager directamente, no por esta UI.

**Modo del drawer**: `create` / `edit` / `read`. Títulos: "Nuevo canal" / "Editar canal" / "Canal" (read). Footer: `[ Cancelar ] [ Crear / Guardar ]` (`Creando…`/`Guardando…` en pending); en `read` solo `[ Cerrar ]`.

#### Estados

- **Empty (sin canales)**:
```
┌────────────────────────────────────────────────────────────────────┐
│                       📡  (ChannelRegular)                           │
│                       Aún no hay canales                             │
│      Crea un canal de WhatsApp para empezar a recibir y enviar       │
│      mensajes.                                                       │
└────────────────────────────────────────────────────────────────────┘
```
- **Loading (primera carga)**: DataTable con 5 skeleton rows.
- **No-results (búsqueda/filtro sin matches)**: "No hay canales con los filtros actuales."
- **Refetching (background)**: tabla `opacity: 0.55` + spinner top-right (igual que catalog/clinic — aquí sí, es CRUD manual, no polling).
- **Guardando (drawer)**: footer disabled (`useTransition`); fields disabled.
- **Error 409 (`CHANNEL_ACCOUNT_EXTERNAL_TAKEN`)**: `<MessageBar intent="error">` arriba del form + error inline en `external_identifier`: "Ya existe un canal con este identificador para este tipo de canal."
- **Error 422 (validation drift)**: improbable (mismo Zod). `detail` genérico + log.
- **Error de red**: `<MessageBar intent="error">"No se pudo guardar. Intenta de nuevo."`.
- **Eliminar**: `<ConfirmDialog destructive>` — "¿Eliminar el canal '{nombre}'? Dejará de recibir y enviar mensajes. Las conversaciones existentes se conservan." (soft-delete; las conversaciones quedan, solo el canal se oculta).

#### Componentes Fluent UI (Canales)

| Concepto UI | Componente |
|---|---|
| Lista | `<DataTable<ChannelAccountItem>>` + `useTableQuery({ queryKey: "conversations:channel-accounts" })` |
| Filtro tipo de canal (opcional) | `<Dropdown>` + `nuqs` (si se decide; MVP solo WhatsApp → puede omitirse) |
| Ícono de canal | `<ChannelIcon channel={c.channel_type}/>` (**reuse** de crm) |
| Badge secreto | `<Badge appearance="tint" color={configured?"success":"subtle"}>` "Configurado"/"Sin configurar" |
| Badge estado | `<StatusBadge>` "Activo"/"Inactivo" (**reuse** de crm) |
| Drawer | `<Drawer size="medium">` (del template) |
| Campos | `<FormField>` + `<Input>` / `<Dropdown>` / `<Switch>` vía `Controller` (react-hook-form) |
| Tipo de canal | `<Dropdown>` con `ChannelType` (MVP: solo `whatsapp` habilitado) |
| Aviso secreto | `<MessageBar intent="info">` (el secreto no se edita aquí) |
| Inline error 409 | `<MessageBar intent="error">` + error en `external_identifier` |
| Row menu | `<RowActions item={c} actions={rowActions} />` |
| Confirm delete | `<ConfirmDialog destructive />` |

---

## Decisiones de UI (cierres)

### La bandeja es un workspace de 2 paneles, no un listado-detalle
Misma regla-precedente de clinic/staff/crm: entidad con sub-recurso de interacción propia (hilo de mensajes en vivo + máquina de handoff + no-leídos) → superficie bespoke. Aquí el bespoke es un **inbox de 2 paneles** (lista + hilo), no una página con tabs (el contenido es un solo hilo lineal, no múltiples superficies densas). Seleccionar una conversación es URL state (`?conv=<id>`), no navegación — el asesor no pierde el contexto de la lista. **Mi bandeja reusa el mismo shell** con otro fetcher (un componente, dos usos — patrón crm).

### Hilo real-time (Firestore), listado por polling (binding spec §1 + rediseño CQRS ADR-011)
El **hilo** (panel derecho) es **real-time vía listeners de Firestore** (`onSnapshot`, read-only): mensajes y estados (✓/✓✓/leído/⚠) aparecen al instante, sin polling del hilo y sin SSE/WebSocket del backend. El browser solo **LEE** el stream que está autorizado a ver (`signInWithCustomToken` con un token minteado server-side + Security Rules que espejan el RBAC); **todas las escrituras (enviar/tomar/liberar/cerrar) siguen 100 % por el backend** (Next server → FastAPI → Meta + Firestore vía Admin SDK) — se preserva "el browser no muta el backend / JWT server-side / RBAC". El **listado** (panel izquierdo) sigue por **polling** (~10 s, pausable, pausa en pestaña oculta, reconciliación in-place sin flash) — Cloud Run con `min-instances 0` + cpu-throttling no favorece conexiones persistentes para las queries SQL del inbox; podría migrar a live (misma collection Firestore) más adelante. El polling del listado se **pausa** mientras el composer tiene foco/texto y en pestaña oculta (no golpear el backend ocioso).

### Estados de mensaje con glifos universales + tokens (sin colores hardcodeados)
`✓` enviado / `✓✓` entregado / `✓✓` azul leído / `⚠` falló / `🕓` enviando — el vocabulario universal de WhatsApp, ejecutado con tokens Fluent (`colorNeutralForeground3`, `colorPaletteBlueForeground2`, `colorPaletteRedForeground1`), **no** `brandPalette.accent` (que no existe). El estado viene del campo `external_status` del **doc Firestore del mensaje** (last status del provider, actualizado por el backend vía Admin SDK y empujado al cliente por el listener — los cambios delivered/read/failed se ven **en vivo**). El fallido muestra **Reintentar** (crea un mensaje nuevo con un `mid` nuevo; el fallido queda como audit inmutable — el doc no se borra).

### `router.refresh()` + refetch en toda mutación de denormalizados (lección crm F3)
Cada take/release/close/reopen/send toca datos **denormalizados** que la lista del otro panel y el header del hilo muestran (badge "Asignado a X", estado, `unread_count`, `last_message_preview`/`last_message_at`). Tras mutar: refetch del detalle + refetch de la lista + **`router.refresh()`** — sin esto el badge/preview queda **stale** (bug MAJOR cazado en crm F3 con el badge del header). El composer optimista reconcilia con `external_status` al volver el `MessageItem`.

### El secreto del canal nunca llega al front (binding spec §6/§8)
`ChannelAccountDetail` solo expone `secret_name` + flag "configurado/sin configurar"; el contenido (`access_token`/`app_secret`) se resuelve server-only vía `get_credentials` (Secret Manager SDK con cache TTL, fallback env en local; ADR-010). La UI **nunca** tiene un campo "ver/editar secreto en claro" — eso vive en GCP Secret Manager. El `webhook_verify_token` **sí** es editable (no es secreto duro; Meta lo envía y se compara).

### Búsqueda client-side por nombre/identificador (denormalizados)
`person.full_name` y `last_message_preview` son denormalizados; no están en `ALLOWED_FIELDS`. La búsqueda visible de la lista es **client-side** sobre lo cargado (matchea nombre + preview). Lección hotfix `cd10c78` de staff: nunca server-sortear/filtrar por columna denormalizada (da 400) — `defaultSort`/`isSortable`/`searchFields` solo columnas reales (`status`, `assignee_type`, `assignee_user_id`, `channel_account_id`, `last_message_at`, `unread_count`, `created_on`). Los deep-links por `*_id` se traducen a filtros en el repo.

### Deep-links por estado / canal / asignación
`status`, `channel_account_id`, `unassigned`, `assignee_user_id` y `conv` (la conversación abierta) son `useQueryState` (`nuqs`) con chip × y deep-link. Permite linkear "las conversaciones sin asignar del canal WhatsApp Estética" o abrir un hilo directo (`/conversaciones/bandeja?conv=abc`) desde un dashboard o desde el detalle de un contacto en crm (futuro). El `defaultSort=last_message_at desc` del prefetch RSC y de la lista **deben coincidir** (lección desync footer crm; `useTableQuery` con `defaultPageSize` = el `limit` del prefetch).

### "Hoy"/fechas relativas siempre client-only (TZ)
Toda fecha que afecte el render (agrupación del hilo por día, "hace 2 min", separador "Hoy"/"Ayer", "⟳ hace Ns") se computa **client-only** (`useEffect`/`useMemo` montados en cliente, no en SSR). Se **reusa** el helper `formatRelative(iso)` de `lib/utils/date.ts` (creado en crm). El servidor en UTC desfasaría el día en Lima (UTC-5) — bug recurrente de staff/crm.

### Sin i18n framework por ahora
Textos directos como strings en cada componente (misma decisión que catalog/clinic/staff/crm). Si negocio pide multilingüe, introducir `next-intl` después.

### Mobile / responsive
Mismo criterio que clinic/staff/crm (template optimizado para desktop interno): sidebar colapsado por default. El **inbox de 2 paneles** en pantallas angostas **colapsa a una vista** (lista O hilo, no ambos): sin `?conv=` se ve la lista a ancho completo; al seleccionar, el hilo ocupa todo + un back "← Volver a la bandeja" que limpia `?conv=`. (Patrón master-detail de WhatsApp/Gmail mobile.) El composer colapsa a una fila. La DataTable de Canales scrollea horizontal; el drawer va a 100 % del width en mobile.

### Accesibilidad básica
- La lista de conversaciones es navegable por teclado (`role="list"`/`listitem`, flechas ↑↓ para moverse, Enter para abrir); la conversación seleccionada tiene `aria-selected`.
- Las burbujas exponen su autor y hora a lectores de pantalla (`aria-label` "Mensaje de {autor}, {hora}, {estado}").
- El estado de mensaje (✓/✓✓/⚠) no se comunica **solo** por color/glifo: cada uno tiene `aria-label`/`<Tooltip>` con el texto ("Leído", "Falló el envío"). El no-leído tiene `aria-label` "N mensajes sin leer".
- El composer: `<Textarea>` con `aria-label` "Escribe un mensaje"; Enter envía, Shift+Enter nueva línea (documentado en un hint sutil). El polling no roba el foco del composer.
- Contraste de las burbujas outbound (texto sobre `brandPalette.primary`) verificado con `colorNeutralForegroundOnBrand`.

## Texto (UX writing)

Todo en **español**, tono profesional y breve. Identificadores de código (`key`, `code`, slugs, CSS classes) en inglés — solo los textos visibles van traducidos. Glosario y género en la tabla del inicio: **Conversación / Bandeja / Cuenta** femeninos; **Mensaje / Canal / Asesor / Contacto / Envío / Adjunto / Token / Secreto / Identificador** masculinos.

### Copy por contexto

| Contexto | Copy |
|---|---|
| — Nav — | |
| Grupo | "Conversaciones" |
| Item bandeja | "Bandeja" |
| Item mi bandeja | "Mi bandeja" |
| Item canales | "Canales" |
| — Bandeja (Pantalla 1) — | |
| Page title | "Bandeja" |
| Page subtitle | "Atiende las conversaciones entrantes de tus canales." |
| Filtro Estado (placeholder) | "Estado" → "Abiertas" / "Cerradas" / "Todas" |
| Filtro Canal (placeholder) | "Todos los canales" |
| Toggle | "Sin asignar" / "Mías" |
| Chip estado | "Estado: {valor} ✕" |
| Chip canal | "Canal: {nombre} ✕" |
| Search placeholder | "Buscar nombre o contacto…" |
| Item: contacto sin nombre | "Contacto (WhatsApp)" |
| Item: preview vacío | "Sin mensajes" |
| Badge no-leídos (aria) | "{n} mensajes sin leer" |
| Empty (sin conversaciones) | "Aún no hay conversaciones. Cuando un contacto escriba a uno de tus canales, su conversación aparecerá aquí." |
| Empty (sin selección) | "Selecciona una conversación. Elige una conversación de la izquierda para ver el hilo y responder." |
| Empty (cerradas sin matches) | "No hay conversaciones cerradas." |
| Empty (canal sin matches) | "Este canal no tiene conversaciones todavía." |
| Empty (sin asignar sin matches) | "No hay conversaciones sin asignar." |
| No-results (búsqueda) | "No hay resultados con los filtros actuales." / "Prueba quitar algún criterio o revisa la ortografía." |
| Error lista | "No se pudo cargar la bandeja. Reintentando…" |
| Error hilo | "No se pudo cargar la conversación." |
| — Header del hilo — | |
| Estado abierta | "Abierta" |
| Estado cerrada | "Cerrada" |
| Asignación | "Asignado a {nombre}" / "Sin asignar" |
| Botón tomar | "Tomar" |
| Botón liberar | "Liberar" |
| Botón cerrar | "Cerrar" |
| Botón reabrir | "Reabrir" |
| Botón marcar leída | "Marcar como leída" |
| Refrescar / pausar | "Refrescar" / "Pausar" / "Reanudar" |
| Label polling | "⟳ hace {n}s" |
| Ver historial | "Ver historial de asignación" |
| Historial actor sistema | "Sistema" |
| — Liberar (dialog) — | |
| Title | "Liberar conversación" |
| Body | "Se devolverá a la bandeja compartida para que otro asesor la atienda." |
| Label motivo | "Motivo (opcional)" |
| Botón confirmar | "Liberar" / "Liberando…" |
| — Hilo / burbujas — | |
| Encabezados de día | "Hoy" / "Ayer" / "{DD mmm YYYY}" |
| Separador sistema | "Sistema" |
| Mensaje sistema: creada | "Conversación creada desde {canal}" |
| Mensaje sistema: tomada | "{nombre} tomó la conversación" |
| Mensaje sistema: liberada | "{nombre} liberó la conversación a la bandeja" |
| Mensaje sistema: cerrada | "{nombre} cerró la conversación" |
| Mensaje sistema: reabierta | "{nombre} reabrió la conversación" |
| Estado enviando | "Enviando…" |
| Estado enviado | "Enviado" |
| Estado entregado | "Entregado" |
| Estado leído | "Leído" |
| Estado fallido | "Falló el envío" |
| Acción reintentar | "Reintentar" |
| Adjunto (F4, placeholder) | "📎 Adjunto — disponible próximamente" |
| Nuevos mensajes (badge flotante) | "↓ {n} mensajes nuevos" |
| — Composer — | |
| Placeholder | "Escribe un mensaje…" |
| Botón enviar | "Enviar" |
| Hint enviar | "Enter para enviar · Shift+Enter para nueva línea" |
| Adjuntar (deshabilitado) | "Adjuntos disponibles próximamente" |
| Composer sin permiso (con take) | "Toma la conversación para responder." |
| Composer sin permiso (sin take) | "No tienes permiso para responder en esta conversación." |
| Conversación cerrada (barra) | "Esta conversación está cerrada." |
| Error envío fallido (tooltip) | "{failure_reason}" |
| Error reabrir (409) | "Ya existe una conversación abierta con este contacto en este canal." |
| — Mi bandeja (Pantalla 2) — | |
| Page title | "Mi bandeja" |
| Page subtitle | "Las conversaciones que tienes asignadas." |
| Empty (sin mías) | "No tienes conversaciones asignadas todavía. Cuando se te asigne una conversación aparecerá aquí." |
| Empty hint (con CONVERSATIONS_READ) | "Revisa la Bandeja para tomar conversaciones sin asignar." |
| — Canales (Pantalla 3) — | |
| Page title | "Canales" |
| Page subtitle | "Configura las cuentas de canal por las que recibes y envías mensajes." |
| Botón crear | "+ Nuevo canal" |
| Columnas | "Nombre" / "Canal" / "Identificador externo" / "Secreto" / "Estado" |
| Drawer title | "Nuevo canal" / "Editar canal" / "Canal" |
| Label nombre | "Nombre" |
| Label tipo | "Tipo de canal" |
| Tipo opción deshabilitada | "{canal} (próximamente)" |
| Label identificador | "Identificador externo" |
| Hint identificador | "Número de WhatsApp Business (sin +)." |
| Label phone_number_id | "ID del número (phone_number_id)" |
| Hint phone_number_id | "Lo provee Meta; se usa para enviar mensajes." |
| Sección credenciales | "Credenciales" |
| Label secreto | "Nombre del secreto (GCP Secret Manager)" |
| Badge secreto | "Configurado" / "Sin configurar" |
| Badge secreto (local/env) | "Sin configurar — usando credenciales de entorno" |
| Aviso secreto | "El contenido del secreto (token de acceso, app secret) no se muestra ni se edita aquí. Se gestiona en GCP Secret Manager." |
| Label verify token | "Token de verificación (webhook)" |
| Hint verify token | "Lo defines en Meta y aquí; deben coincidir." |
| Toggle activo | "Activo" |
| Error 409 (identificador) | "Ya existe un canal con este identificador para este tipo de canal." |
| Confirm delete title | "¿Eliminar canal?" |
| Confirm delete body | "¿Eliminar el canal '{nombre}'? Dejará de recibir y enviar mensajes. Las conversaciones existentes se conservan." |
| Empty (sin canales) | "Aún no hay canales. Crea un canal de WhatsApp para empezar a recibir y enviar mensajes." |
| Botón guardar / guardando | "Crear" / "Creando…" · "Guardar" / "Guardando…" |
| Botón cancelar / cerrar | "Cancelar" / "Cerrar" |
| — Común — | |
| Pagination | "Mostrando {start}–{end} de {total}" / "Página {n} de {m}" |
| Status badge | "Activo" / "Inactivo" |
| Loading placeholder | "Cargando…" |
| Error de red genérico | "No se pudo guardar. Intenta de nuevo." |

### Concordancia de género

- **Conversación** es **femenino**: "la conversación", "esta conversación está cerrada", "tomó la conversación", "Marcar como leída".
- **Bandeja** es **femenino**: "la bandeja", "tu bandeja", "a la bandeja compartida".
- **Cuenta de canal** es **femenino** la entidad, pero el nav y los títulos usan **"Canal"** (masculino): "Nuevo canal", "Eliminar canal", "el canal '{nombre}'".
- **Mensaje** es **masculino**: "el mensaje", "un mensaje", "mensajes nuevos".
- **Canal / Asesor / Contacto / Envío / Adjunto / Token / Secreto / Identificador / Motivo** son **masculinos**: "este canal", "el asesor", "el contacto", "Falló el envío", "el token de verificación", "el nombre del secreto", "el identificador externo", "el motivo".

### Etiquetas de canal (`ChannelType`) — reuse de `ChannelIcon` de crm

`key` (slug) en inglés, etiqueta visible en español. Ícono Fluent por canal (verificar existencia en la versión instalada). **Se reusa el componente `ChannelIcon` y el mapeo ya creado en crm** — NO duplicar:

| `channel_type` | Etiqueta | Ícono Fluent (fallback) | MVP |
|---|---|---|---|
| `whatsapp` | "WhatsApp" | `ChatRegular` (no hay ícono de marca; genérico) | ✅ habilitado |
| `telegram` | "Telegram" | `SendRegular` | (próximamente) |
| `web` | "Web" | `GlobeRegular` | (próximamente) |
| `phone` | "Teléfono" | `CallRegular` | (próximamente) |
| `email` | "Email" | `MailRegular` | (próximamente) |
| `instagram` | "Instagram" | `CameraRegular` | (próximamente) |
| `facebook` | "Facebook" | `ChatRegular` | (próximamente) |
| `other` | "Otro" | `LinkRegular` | (próximamente) |

> No usar logos de marca (WhatsApp/Instagram/Facebook) — Fluent no los trae y meter SVGs de marca rompe la consistencia del design system. Íconos genéricos + etiqueta de texto bastan (misma decisión que crm).

## Mapeo a fases de implementación (checklist de UI F0–F3)

Las pantallas de este doc se construyen en el orden de fases del módulo (ver [`README.md`](./README.md), [`backend.md`](./backend.md) y la spec §12 F0–F4). Cada checkbox es una tarea de UI.

### F0 — Prep (sin pantallas funcionales)
- [ ] Sidebar: grupo "Conversaciones" en `NAV_ITEMS` con 3 children (Bandeja / Mi bandeja / Canales), gate `MENU-CONVERSATIONS` + permiso por child (`CONVERSATIONS_READ` / `MY_CONVERSATIONS_READ` / `CHANNEL_ACCOUNTS_READ`); íconos Fluent verificados con fallback (`ChatRegular`/`MailInboxRegular`/`PersonMailRegular`/`ChannelRegular`).
- [ ] `lib/constants/endpoints.ts`: bloque `ENDPOINTS.CONVERSATIONS` (channel-accounts, channel-accounts/active, list, {id}, {id}/messages, {id}/messages/list [fallback server-side; el path primario de lectura del hilo es el listener Firestore], realtime/token, take, release, close, reopen, mark-read, me/conversations/list). (Los webhooks NO van en el front — los llama Meta.)
- [ ] `types/conversations.types.ts`: todas las interfaces espejo de Pydantic (`ChannelAccountItem`/`Detail`/`Option`, `ConversationListItem`/`Detail`, `MessageItem`, `MessageAttachmentItem`, `ConversationAssignmentLogItem`, `MessageSendRequest`, `TakeConversationRequest`, `ReleaseConversationRequest`, enums `ConversationStatus`/`AssigneeType`/`MessageDirection`/`SenderType`/`ContentType`/`AttachmentType`/`MessageExternalStatus`; reuse `ChannelType` de crm.types).
- [ ] `lib/schemas/conversation.schema.ts`: Zod de `channelAccountSchema` + `messageSendSchema` + `releaseConversationSchema`.
- [ ] Confirmar **reuse** (no duplicar) de `StatusBadge`, `ChannelIcon` (de crm) y `formatRelative` (de `lib/utils/date.ts`). Si están acoplados a crm, extraerlos a `components/shared/` sin regresión.

### F1 — ChannelAccount (Canales)
- [ ] **Pantalla 3** `/conversaciones/canales`: lista (molde `VerticalsClient`) + `ChannelAccountDrawer` (create/edit/read) con el secreto **nunca en claro** (solo `secret_name` + badge "configurado/sin configurar" + aviso info) + `webhook_verify_token` editable + tipo de canal (solo WhatsApp habilitado) + dedup 409 inline + confirm delete + estados empty/loading/no-results/refetching/error.
- [ ] Migración backend `0015_conv_channel_account` (no toca UI).

### F2 — Inbox read-only (recibir + ver)
- [ ] **Pantalla 1 — Iteración A** `/conversaciones/bandeja`: `InboxShell` de 2 paneles; panel izq = lista (`ConversationListItem` memoizado, filtros estado/canal/sin-asignar/mías con chip + deep-link, búsqueda client-side, badge no-leídos, estados loading/empty/no-results/error) con **polling** silencioso (pausable, pausa en pestaña oculta, reconciliación in-place); panel der = hilo **read-only** (header con badges, `MessageBubble` inbound/outbound/system, estados de mensaje **en vivo**, `DayGroup` client-only, paginación scroll-up) alimentado por **listener Firestore real-time** (`getRealtimeToken` server action + `signInWithCustomToken` + `onSnapshot`); `?conv=` URL state; detach/`unsubscribe` del listener al cambiar de conversación; indicador "● En vivo"; estados empty (sin conversaciones / sin selección). SIN composer ni handoff.
- [ ] Dep frontend `firebase` (solo `firebase/app` + `firebase/auth` + `firebase/firestore`) + config pública `NEXT_PUBLIC_FIREBASE_*` (no son secretos); `lib/firebase/client.ts` (init + `signInWithCustomToken`) + server action `getRealtimeToken()` → `POST /conversaciones/realtime/token`.
- [ ] **Pantalla 2 — Iteración A** `/conversaciones/mis-conversaciones`: reuse del `InboxShell` con `fetcher=listMyConversations` y `showAssignmentFilters={false}` + empty propio.
- [ ] Migración backend `0016_conv_threads` (no toca UI).

### F3 — Composer + handoff + outbound real
- [ ] **Pantalla 1 — Iteración B** (composer): `<Textarea>` + Enviar (gated `MESSAGES_SEND` + assignee; el envío va server-side, NO escribe Firestore desde el browser; la burbuja y su `external_status` se reconcilian **en vivo por el listener Firestore**, con burbuja optimista local opcional hasta el primer snapshot), reintento de mensajes fallidos, estados "sin permiso para enviar"/"cerrada (composer oculto)", hint Enter/Shift+Enter.
- [ ] **Pantalla 1 — Iteración B** (handoff): controles Tomar/Liberar/Cerrar/Reabrir/Marcar-leída (gated por permiso + por estado), `<Dialog>` de Liberar con `reason?`, refetch + `router.refresh()` en cada mutación, notas de sistema en el hilo, "Ver historial de asignación".
- [ ] Continuidad "mis leads = mis chats" verificada en Mi bandeja (auto-asignación al dueño del lead).

### F4 — Adjuntos / media (DIFERIDA)
- [ ] Render real de `MessageAttachment` en la burbuja (imagen/audio/documento/ubicación) + composer con adjuntar. Fuera del MVP inicial; el placeholder "📎 Adjunto — disponible próximamente" se reemplaza al llegar F4.
