# Módulo `conversations` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-06-03
> **Audiencia**: developer implementando `frontend/src/.../conversaciones/`.

> ⚠ **REDISEÑO de arquitectura (2026-06-03, brief `C:/tmp/conversations_firestore_redesign.md`, confirmado por el usuario)**: el **stream de mensajes** pasa de Postgres a **Cloud Firestore** con arquitectura **CQRS** (Postgres = control plane / fuente de verdad: `ChannelAccount`, `Conversation`, `ConversationAssignmentLog`, `message_outbox`; Firestore = data plane / read-model real-time del stream). Impacto en el **frontend**: el **hilo de la conversación (right pane) se lee en TIEMPO REAL vía Firestore `onSnapshot` (READ-ONLY)** — reemplaza el polling del hilo. El **inbox LIST (left pane) sigue por polling Postgres** (opcionalmente también live vía la colección `conversations`). El **path de escritura NO cambia**: todo write (enviar, tomar, liberar, cerrar, reabrir) sigue siendo `browser → Next server action → backend → Meta + Firestore (Admin SDK)`; **el cliente NUNCA escribe Firestore**, solo abre listeners read-only autorizados por **Custom Token minteado por el backend + Security Rules** (espejan el RBAC). Esto **preserva** el principio del template (el browser solo LEE lo que está autorizado a ver; el backend muta; JWT server-side; RBAC fuente de verdad). Todo lo NO relacionado a la lectura real-time del hilo (canales CRUD, nav, types, polling del listado, perf rules, TZ, handoff por server actions) **se mantiene** como ya estaba. Ver [ConversationThread](#conversationthreadtsx-panel-derecho) y [Lectura real-time del hilo (Firestore)](#lectura-real-time-del-hilo-firestore).
> **Pre-requisito**: leer [`README.md`](./README.md), [`backend.md`](./backend.md), [`ui.md`](./ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md), y como molde de referencia el frontend de [`../crm/frontend.md`](../crm/frontend.md) (módulo completo más reciente del que `conversations` copia patrones — el **timeline rico** de crm es el molde directo del **hilo de la conversación** + el **inbox**) y [`../staff/frontend.md`](../staff/frontend.md) (CRUD/detalle con sub-recursos, la lección `cd10c78`).

> **Contrato autoritativo**: este doc respeta la spec compartida de `conversations` (`C:/tmp/conversations_spec.md`, consolidada en [`README.md`](./README.md)) — nombres de entidades, campos, endpoints, permisos, enums y códigos de error son **vinculantes** y deben coincidir con [`backend.md`](./backend.md) y [`ui.md`](./ui.md). Donde haya tensión, manda la spec. **Decisiones confirmadas con el usuario 2026-06-02** (spec §1) — NO re-litigar.

> **Posición del módulo** (spec §0): `conversations` es el **#5** (catalog→clinic→staff→crm **COMPLETOS en prod**; sigue conversations; luego bots #6, scheduling #7, marketing #8). Es el **dueño del pipe de mensajería multicanal**: recibe inbound desde webhooks de proveedores (WhatsApp Cloud API en el MVP), persiste, identifica al `Person` vía `crm.find_by_identifier_or_create`, lo deja en la bandeja del asesor, y envía outbound real contra Meta. El frontend NO toca los webhooks (esos son top-level sin JWT, lado servidor) — consume los **endpoints autenticados** `/api/v1/conversations/*`.

> **Decisiones de modelo confirmadas** (spec §1, NO re-litigar):
> 1. **MVP = WhatsApp entrante + saliente REALES**. El front renderiza inbound (contacto) + outbound (asesor) + system (notificaciones); el composer envía outbound real (el backend habla con Meta Graph API).
> 2. **Listado del inbox en vivo = polling** (refetch periódico, pausable), NO SSE/WebSocket (Cloud Run con `min-instances 0` + cpu-throttling no los favorece). El front implementa el loop de polling de la **lista** con `setInterval` + pausa + refetch silencioso sin flash. **⚠ Rediseño 2026-06-03**: esto aplica al **LISTADO** (left pane, sigue por polling Postgres). El **HILO** (right pane) pasa a **real-time vía Firestore `onSnapshot`** (READ-ONLY) — el stream de mensajes vive en Firestore (CQRS), ver [Lectura real-time del hilo](#lectura-real-time-del-hilo-firestore). No re-litigar el resto de §11 del brief (los 12 permisos, las 4 decisiones de negocio, webhook síncrono, polling del listado, PUT, UI español).
> 3. **Asignación de conversación nueva = AUTO al dueño del lead** (round-robin de crm), con fallback a `unassigned` (bandeja compartida). El asesor reasigna/toma igual. Continuidad "mis leads = mis chats" (`/me/conversations` + `/me/leads`).
> 4. **Adjuntos = texto primero**. `MessageAttachment` está MODELADO en el contrato (tipos TS + render placeholder) pero el processing (download/render real de media) es **F4 diferida**. En el MVP el composer solo envía `content_type=text`; el hilo muestra un placeholder "📎 Adjunto (no disponible aún)" si llegara un attachment.
> 5. **Outbound fallido** se persiste igual (estado `failed`); el endpoint devuelve **200** con el message fallido. La UI muestra un estado ⚠ "Falló el envío" + botón **Reintentar** (re-`POST /messages` con el mismo content).
> 6. **Emisión a la timeline de crm**: solo `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED` (no `MESSAGE_SENT` por-mensaje). El front NO muestra el timeline de crm — pero los controles de handoff disparan esa emisión cross-módulo server-side (ver [Handoff](#controles-de-handoff)).

> **Convenciones heredadas de catalog/clinic/staff/crm shipped** (el lector debe tenerlas presentes desde ya):
> 1. **Verbos HTTP**: updates completos usan **`PUT`** (no `PATCH`). Aquí casi todo son **acciones** (`POST /take`, `/release`, `/close`, `/reopen`, `/mark-read`, `/messages`) y el único `PUT` es `channel-accounts/{id}` (update completo).
> 2. **Dropdowns/listas planas de activos** = endpoint **`/active`** (lista CRUDA, `response_model=list[...]`, sin envelope `SingleResponse`). Aquí: `GET /channel-accounts/active` → `ChannelAccountOption[]`.
> 3. **Listados paginados** = `POST /<recurso>/list` con `QueryRequest`. Aquí: `/channel-accounts/list`, `/list` (inbox global), `/{id}/messages/list`, `/me/conversations/list`.
> 4. **Lección hotfix `cd10c78` de staff** (crítica para conversations, que tiene muchos denormalizados en el inbox): `defaultSort`, columnas `isSortable` y `searchFields` **SOLO** sobre columnas reales de `ALLOWED_FIELDS`. Ordenar/filtrar server-side por un denormalizado (`person.full_name`, `channel name`, `assignee full_name`, `last_message_preview`) devuelve **400 → error boundary del RSC**. `ALLOWED_FIELDS` de `conversation` = `status`, `assignee_type`, `assignee_user_id`, `channel_account_id`, `last_message_at`, `created_on`, `unread_count` (spec §7). `defaultSort = last_message_at desc` (columna real); **el prefetch del RSC y el `defaultSort` del client DEBEN coincidir** (sino flash + refetch). Búsqueda por nombre/identificador = **client-side** (denormalizados, no whitelistados); deep-links por `*_id` traducidos a filtros en el repo.

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── conversations.types.ts            ← ChannelAccount*, Conversation*, Message*,
│                                            MessageAttachment*, ConversationAssignmentLog*,
│                                            enums TS (ConversationStatus/AssigneeType/
│                                            MessageDirection/SenderType/ContentType/
│                                            AttachmentType/MessageExternalStatus), request bodies.
│                                            REUSA ChannelType de crm.types + UserAuditInfo de audit.types
├── lib/
│   ├── firebase/
│   │   └── client.ts                     ← NUEVO (redesign): init Firebase Web SDK (firebase/app
│   │                                        + firebase/auth + firebase/firestore) con config pública
│   │                                        NEXT_PUBLIC_FIREBASE_* + signInWithCustomToken(token del
│   │                                        backend) → getFirestore() para listeners READ-ONLY del hilo
│   ├── schemas/
│   │   ├── channel-account.schema.ts     ← channelAccountCreate/Update (channel_type enum,
│   │   │                                    external_identifier, secret_name?, webhook_verify_token?)
│   │   └── message.schema.ts             ← messageSend (content no-vacío + content_type=text MVP)
│   └── constants/
│       ├── endpoints.ts                  ← EXTEND con bloque CONVERSATIONS (CHANNEL_ACCOUNTS,
│       │                                    CONVERSATIONS list/get/messages/take/release/close/
│       │                                    reopen/mark-read, ME_CONVERSATIONS)
│       ├── navigation.ts                 ← EXTEND con grupo 'Conversaciones' (MENU-CONVERSATIONS)
│       └── conversations.ts              ← NUEVO: CHANNEL_TYPE_META (reusa de crm si conviene),
│                                            ASSIGNEE_TYPE_META, MESSAGE_STATUS_META (ícono+label ES
│                                            por estado sent/delivered/read/failed), SENDER_TYPE_META,
│                                            CONVERSATION_STATUS_META, INBOX_FILTER_PRESETS
├── actions/
│   ├── channel-account.actions.ts        ← list/active/get/create/update/delete (tag conversations:channel-accounts)
│   ├── realtime.actions.ts               ← NUEVO (redesign): getRealtimeToken() → POST
│   │                                        /conversations/realtime/token (server-side con el JWT);
│   │                                        devuelve { token, firebase_config? } para el Web SDK
│   └── conversation.actions.ts           ← listConversations/getConversation/listMessages(fallback)/
│                                            sendMessage/take/release/close/reopen/markRead/
│                                            listMyConversations (tags conversations:list,
│                                            conversations:thread:{id})
└── app/(main)/conversaciones/
    ├── canales/
    │   ├── page.tsx                      ← RSC prefetch (ChannelAccount list) — molde Verticals
    │   └── _components/
    │       ├── ChannelAccountsClient.tsx ← DataTable + RowActions
    │       └── ChannelAccountDrawer.tsx  ← create/edit (secreto NUNCA en claro)
    ├── bandeja/
    │   ├── page.tsx                      ← RSC inbox GLOBAL (prefetch lista + canales activos)
    │   └── _components/
    │       └── (reusa InboxShell, scope="all")
    ├── mis-conversaciones/
    │   ├── page.tsx                      ← RSC mi bandeja (prefetch /me/conversations)
    │   └── _components/
    │       └── (reusa InboxShell, scope="mine")
    └── _components/                       ← compartidos por bandeja + mis-conversaciones (NO rutas)
        ├── InboxShell.tsx                ← layout 2-paneles; orquesta lista (polling) + hilo
        │                                    (real-time Firestore) + getRealtimeToken + URL state
        ├── ConversationList.tsx          ← panel izquierdo: filtros + búsqueda client-side + filas
        ├── ConversationListItemRow.tsx   ← fila memoizada (avatar, nombre, preview, badge sin-leer, hora)
        ├── ConversationThread.tsx        ← panel derecho: header + hilo REAL-TIME (Firestore
        │                                    onSnapshot READ-ONLY) + handoff + composer
        ├── useThreadMessages.ts          ← NUEVO (redesign): hook que abre el listener Firestore
        │                                    (onSnapshot collection conversations/{cid}/messages
        │                                    orderBy created_at) y expone messages en vivo
        ├── ThreadHeader.tsx              ← contacto + canal + estado + AssigneeBadge + HandoffControls
        ├── MessageDayGroup.tsx           ← sección "Hoy"/"Ayer"/fecha (client-only por TZ)
        ├── MessageBubble.tsx             ← burbuja memoizada (React.memo): in/out/system + estado msg
        ├── MessageStatusTicks.tsx        ← ✓ / ✓✓ / leído / ⚠ + Reintentar (outbound)
        ├── Composer.tsx                  ← textarea + enviar (useTransition; gated MESSAGES_SEND + assignee)
        └── HandoffControls.tsx           ← Tomar/Liberar/Cerrar/Reabrir + AssigneeBadge
```

> **Componentes compartidos entre `bandeja` y `mis-conversaciones`** (no rutas — `_components/` colocados en `conversaciones/_components/`, un nivel arriba de las dos páginas): `InboxShell` y toda su cascada. Las dos páginas son **el mismo shell** parametrizado por `scope: "all" | "mine"` (qué action de listado usa y qué permiso gatea). El detalle del hilo NO es una ruta propia — la conversación seleccionada vive en el **URL state** (`?c=<id>` con `nuqs`), igual que el `?tab=` del detalle de Person en crm. Esto da un inbox 2-paneles deep-linkable (`/conversaciones/bandeja?c=abc&status=open`) sin sub-rutas.

> **Por qué NO hay `conversaciones/layout.tsx`**: igual que en catalog/clinic/staff/crm — `canales`, `bandeja`, `mis-conversaciones` son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El inbox 2-paneles sí tiene un shell propio (`InboxShell`), pero es un **componente cliente** dentro de cada `page.tsx`, no un `layout.tsx` de ruta — la conversación seleccionada vive en una sola URL (`?c=`), no en sub-rutas (mismo criterio que `PersonDetailShell` con `?tab=`).

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas. Mantiene componentes locales colocados con sus pages. El `_components/` raíz de `conversaciones/` aloja lo compartido por `bandeja`+`mis-conversaciones`; `canales/_components/` aloja lo propio de canales.

> **Sobre `loading.tsx`**: catalog/clinic/staff/crm shipped **no** incluyeron `loading.tsx` (el `DataTable` ya renderiza su skeleton vía `isLoading`). `conversations` sigue ese criterio en `canales`. Para el **inbox**, el primer paint viene del prefetch RSC (lista inicial) → el `InboxShell` arranca con datos; el hilo carga en cliente al seleccionar (con su propio skeleton de burbujas). No se crean `loading.tsx`.

## Tipos TS — `types/conversations.types.ts`

Espejo **exacto** de los Pydantic schemas del backend (ver [`backend.md`](./backend.md#schemas-pydantic) y spec §8). Importable desde server actions y client components. **Reusa** `UserAuditInfo` de `audit.types.ts` y `ChannelType` de `crm.types.ts` — NO se redefinen (la spec §3 dice explícitamente que `ChannelType` se REUSA de crm, single source of truth; el docstring de `crm/enums.py` confirma "the slug crosses with conversations.ChannelAccount.channel_type"). Las dos columnas forward (`bot_configuration_id`, `default_campaign_id`) son strings opacos de solo lectura (bots/marketing no existen — ADR-009).

```ts
import type { UserAuditInfo } from "./audit.types";
// ChannelType se REUSA de crm (single source of truth; spec §3). NO redefinir.
import type { ChannelType } from "./crm.types";

// ── Enums (espejo de conversations/enums.py; valores EXACTOS) ─────────

// Estado del hilo. closed = cerrado (soft, vía status; el hilo NO se soft-deletea).
export type ConversationStatus = "open" | "closed";
export const CONVERSATION_STATUSES: readonly ConversationStatus[] = ["open", "closed"] as const;

// A quién está asignada la conversación. advisor ⟺ assignee_user_id NOT NULL.
export type AssigneeType = "bot" | "advisor" | "unassigned";
export const ASSIGNEE_TYPES: readonly AssigneeType[] = ["bot", "advisor", "unassigned"] as const;

// Dirección del mensaje (relativo a la clínica).
export type MessageDirection = "inbound" | "outbound";

// Quién originó el mensaje. advisor ⟺ sender_user_id NOT NULL.
export type SenderType = "contact" | "bot" | "advisor" | "system";

// Tipo de contenido. MVP solo emite/acepta "text" (composer) y "system_notification"
// (eventos de handoff renderizados como burbuja centrada). El resto está en el
// contrato para cuando F4 cablee media; el front sabe pintar un placeholder.
export type ContentType =
  | "text"
  | "image"
  | "audio"
  | "video"
  | "document"
  | "location"
  | "sticker"
  | "contact_card"
  | "system_notification";

// Tipo de adjunto (modelado; processing diferido a F4 — spec §1.4 / §2.4).
export type AttachmentType =
  | "image"
  | "audio"
  | "video"
  | "document"
  | "location"
  | "sticker"
  | "contact_card";

// Estados conocidos del provider en external_status (la columna es varchar libre,
// pero estos son los valores que el front sabe renderizar con ticks/íconos).
export type MessageExternalStatus = "sent" | "delivered" | "read" | "failed";

// ── ChannelAccount ──────────────────────────────────────

// Fila de listado (tabla de Canales). El secreto NUNCA viaja (spec §8): Detail/Item
// exponen `secret_name` (solo el nombre del secreto en GCP Secret Manager) y un flag
// `credentials_configured` derivado server-side — el token/app_secret jamás salen.
export interface ChannelAccountItem {
  id: string;
  channel_type: ChannelType;
  name: string; // nombre humano ("WhatsApp Estética")
  external_identifier: string; // número WA Business (ej. "51999111222")
  secret_name: string | null; // nombre del secreto en Secret Manager (NO el secreto)
  credentials_configured: boolean; // derivado: secret_name set || fallback env disponible
  phone_number_id: string | null; // id del número en WhatsApp Cloud API (para la URL de envío)
  // Forward FKs (bots #6 / marketing #8 — varchar opaco, solo lectura; ADR-009).
  bot_configuration_id: string | null; // hoy SIEMPRE null
  default_campaign_id: string | null; // hoy null
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detalle = Item + el webhook_verify_token (editable; NO es secreto duro — lo envía
// Meta y se compara). El secreto SIGUE sin exponerse (solo secret_name + flag).
export interface ChannelAccountDetail extends ChannelAccountItem {
  webhook_verify_token: string | null;
}

// Para dropdowns/filtros (selección de canal en el inbox). Lista CRUDA (sin envelope).
export interface ChannelAccountOption {
  id: string;
  name: string;
  channel_type: ChannelType;
  external_identifier: string;
}

export interface ChannelAccountCreatePayload {
  channel_type: ChannelType;
  name: string;
  external_identifier: string;
  secret_name?: string | null; // nombre del secreto en Secret Manager (NO el valor)
  webhook_verify_token?: string | null;
  phone_number_id?: string | null;
  // bot_configuration_id / default_campaign_id NO se exponen en el create del MVP
  // (módulos no existen); quedan null. Se podrán setear cuando bots/marketing existan.
}

export interface ChannelAccountUpdatePayload {
  name?: string;
  external_identifier?: string;
  secret_name?: string | null;
  webhook_verify_token?: string | null;
  phone_number_id?: string | null;
  active?: boolean;
}

// ── Subsets denormalizados embebidos en Conversation/Message ──

// Persona denormalizada (subset, vía batch map de crm). null en la ventana corta
// antes de resolver (en práctica siempre poblado tras find_or_create). El front
// NO importa PersonOption de crm aquí — define el subset que el backend embebe.
export interface ConversationPersonRef {
  id: string;
  full_name: string;
  primary_identifier: ConversationContactIdentifier | null;
}

// Contacto principal embebido (ícono de canal + valor).
export interface ConversationContactIdentifier {
  channel_type: ChannelType;
  identifier: string;
  verified: boolean;
}

// ── Conversation ────────────────────────────────────────

// Fila del inbox. Optimizada para la lista (person/canal/assignee denormalizados vía
// batch maps de crm/admin, sin N+1). NINGUNO de los denormalizados está en
// ALLOWED_FIELDS → NO server-sortable/filterable (lección cd10c78). Filtros de
// estado/canal/asignación = deep-link traducido a FilterCondition sobre columnas
// REALES (status, channel_account_id, assignee_user_id, assignee_type); búsqueda por
// nombre/identificador = client-side sobre la página visible.
export interface ConversationListItem {
  id: string;
  channel_account: ChannelAccountOption;
  person: ConversationPersonRef | null;
  status: ConversationStatus;
  assignee_type: AssigneeType;
  assignee_user: UserAuditInfo | null; // null si bot/unassigned
  last_message_preview: string | null; // primeros 255 chars del último mensaje
  last_message_at: string | null; // timestamptz ISO 8601 (denormalizado; sort real)
  unread_count: number; // incrementa por inbound; resetea en mark-read/take
  created_on: string;
}

// Detalle = ListItem + campos del hilo + el historial de handoff. El listado de
// mensajes NO viaja inflando el detalle (se pide por POST /{id}/messages/list, igual
// que la disponibilidad NO viaja en DoctorDetail).
export interface ConversationDetail extends ConversationListItem {
  bot_configuration_id: string | null; // forward FK (varchar opaco; hoy null)
  opened_at: string; // timestamptz ISO 8601
  closed_at: string | null;
  assignment_history: ConversationAssignmentLogItem[];
}

// ── Message ─────────────────────────────────────────────

// Mensaje (audit inmutable; SIN soft-delete en backend). attachments inline.
export interface MessageItem {
  id: string;
  conversation_id: string;
  direction: MessageDirection;
  sender_type: SenderType;
  sender_user: UserAuditInfo | null; // null salvo sender_type='advisor'
  content_type: ContentType;
  content: string | null; // texto / transcripción / cuerpo del system_notification
  external_id: string | null; // wamid (WA) — idempotencia
  external_status: MessageExternalStatus | string | null; // last status del provider (varchar libre)
  sent_at: string; // timestamptz ISO 8601
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  failure_reason: string | null;
  attachments: MessageAttachmentItem[]; // [] en el MVP (texto primero)
  created_on: string;
}

// ── MessageAttachment (modelado; processing diferido F4 — spec §1.4 / §2.4) ──

export interface MessageAttachmentItem {
  id: string;
  message_id: string;
  attachment_type: AttachmentType;
  url: string | null; // decisión de storage en F4 (lazy proxy vs GCS); hoy null
  mime_type: string | null;
  size_bytes: number | null;
  duration_sec: number | null;
  latitude: number | null; // location
  longitude: number | null;
  address_label: string | null;
  original_filename: string | null;
  external_media_id: string | null; // id del medio en el provider
  metadata: Record<string, unknown> | null; // JSONB
  created_on: string;
}

// ── ConversationAssignmentLog (audit inmutable de handoff) ──

export interface ConversationAssignmentLogItem {
  id: string;
  conversation_id: string;
  from_assignee_type: AssigneeType | null; // null en el primer log
  from_assignee_user: UserAuditInfo | null;
  to_assignee_type: AssigneeType;
  to_assignee_user: UserAuditInfo | null;
  started_at: string; // timestamptz ISO 8601
  ended_at: string | null; // null = vigente
  by_actor_user: UserAuditInfo | null; // null = automático (sistema)
  reason: string | null;
}

// ── Request bodies (acciones) ───────────────────────────

// Enviar outbound. MVP solo text → el backend rechaza otros content_type con
// UNSUPPORTED_CONTENT_TYPE (400); el Zod lo previene en español.
export interface MessageSendRequest {
  content: string;
  content_type?: ContentType; // default "text"; MVP solo "text"
}

// Tomar la conversación (assignee = actor). reason opcional (queda en el log).
export interface TakeConversationRequest {
  reason?: string | null;
}

// Liberar: a quién pasa. to_assignee_type ∈ {bot, unassigned} en el MVP (no hay
// "advisor" sin user; reasignar a otro asesor sería un flujo aparte si se agrega).
// to_bot_configuration_id solo si to_assignee_type='bot' (no aplica en MVP).
export interface ReleaseConversationRequest {
  to_assignee_type: AssigneeType;
  to_bot_configuration_id?: string | null;
  reason?: string | null;
}
```

> **Nota sobre las clases de tiempo** (igual que clinic/staff/crm, ver [`../staff/frontend.md`](../staff/frontend.md)):
> - Todas las columnas de tiempo de `conversations` (`last_message_at`, `opened_at`, `closed_at`, `sent_at`, `delivered_at`, `read_at`, `failed_at`, `started_at`, `ended_at`, `created_on`) son `timestamptz` → ISO 8601 con offset → se formatean con `lib/utils/date.ts` (`formatDate` / hora local / relativa). **No hay** fechas `date`-sin-TZ en este módulo (a diferencia de `Person.birth_date`).
> - El **hilo** muestra timestamps de hora local ("14:32") y agrupa por día — el cálculo de "Hoy"/"Ayer" es **client-only** (ver [MessageDayGroup](#messagedaygrouptsx)). El **inbox** muestra la hora del último mensaje (relativa "hace 5 min" / hora si es hoy / fecha si es otro día) — también client-only para la parte relativa.

> **Por qué `ConversationListItem` denormaliza tanto** (`channel_account`, `person`, `assignee_user`, `last_message_preview`, `last_message_at`): el inbox no quiere joins por fila. El backend los resuelve con batch maps (sin N+1, patrón clinic/staff/crm — `person` viene del batch map de crm). **Implicancia crítica de cache + sort**: estos campos **no** están en `ALLOWED_FIELDS` de `conversation` → **no** son server-sortable ni server-filterable (lección `cd10c78`). El `defaultSort` del inbox = `last_message_at` (columna **real** denormalizada pero whitelistada en `ALLOWED_FIELDS` — spec §7) — ordenar por `last_message_at` SÍ está permitido; ordenar por `person.full_name` o `assignee_user.full_name` NO. Renombrar a la persona o reasignar deja stale el denormalizado de un inbox cacheado hasta que el tag se invalida — lo cubren los tags `conversations:list` / `conversations:thread:{id}` (ver [Server Actions](#server-actions)) **más** el polling (refetch periódico que re-pide la lista fresca).

> **`ChannelType` se reusa, los otros enums son conversations-owned**: `ConversationStatus`/`AssigneeType`/`MessageDirection`/`SenderType`/`ContentType`/`AttachmentType`/`MessageExternalStatus` viven en `conversations.types.ts` (espejo de `conversations/enums.py`). `ChannelType` se importa de `crm.types.ts`. Si se quiere el alias `import { ChannelType } from "@/types/conversations.types"`, re-exportar (`export type { ChannelType } from "./crm.types"`) — pero **no** redefinir los 8 valores (drift).

## Zod schemas

> **Regla del template** ([frontend/CLAUDE.md](../../../frontend/CLAUDE.md)): los Zod viven en `src/lib/schemas/` y los importan **tanto el form (cliente) como el Server Action (server)** → drift imposible. Los mensajes visibles van en **español** (el usuario los lee); los `path` y nombres de campo en inglés.

### `lib/schemas/channel-account.schema.ts`

CRUD de cuentas de canal (admin). El `channel_type` es un **enum cerrado** (`ChannelType`, reuse de crm); en el MVP el único valor seleccionable es `whatsapp` (el form ofrece solo WhatsApp, pero el schema acepta los 8 para no bloquear futuros canales). El **secreto NUNCA se valida ni viaja en claro** — el form solo captura `secret_name` (el nombre del secreto en GCP Secret Manager, ej. `medisage-whatsapp-estetica-qa`). El `webhook_verify_token` es editable (no es secreto duro). Validaciones de largo espejan los `varchar(...)` del modelo (spec §2.1).

```ts
import { z } from "zod";

import { CHANNEL_TYPES } from "@/types/crm.types"; // reuse del enum de canal

const channelAccountBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  external_identifier: z
    .string()
    .min(1, "Obligatorio")
    .max(255, "Máximo 255 caracteres"),
  // Nombre del secreto en Secret Manager (NO el secreto). Opcional: null = fallback a
  // env en local/dev (spec §6). NO es el access_token/app_secret.
  secret_name: z.string().max(255, "Máximo 255 caracteres").nullable().optional().or(z.literal("")),
  // Challenge de verificación de Meta (GET webhook). Editable en claro (no secreto duro).
  webhook_verify_token: z
    .string()
    .max(255, "Máximo 255 caracteres")
    .nullable()
    .optional()
    .or(z.literal("")),
  // id del número en WhatsApp Cloud API (para construir la URL /{phone_number_id}/messages).
  phone_number_id: z.string().max(64, "Máximo 64 caracteres").nullable().optional().or(z.literal("")),
});

export const channelAccountCreateSchema = channelAccountBase.extend({
  channel_type: z.enum(CHANNEL_TYPES, {
    errorMap: () => ({ message: "Canal no válido" }),
  }),
});

export const channelAccountUpdateSchema = channelAccountBase.partial().extend({
  active: z.boolean().optional(),
  // channel_type NO se edita (define la cuenta; espeja el backend, que no lo permite
  // en el update — cambiar de canal = cuenta nueva). No se incluye en el update.
});

export type ChannelAccountCreateInput = z.infer<typeof channelAccountCreateSchema>;
export type ChannelAccountUpdateInput = z.infer<typeof channelAccountUpdateSchema>;
```

> **Lo que Zod NO puede validar** (queda como error de servidor en español): `CHANNEL_ACCOUNT_EXTERNAL_TAKEN` (409, viola la UNIQUE parcial `(channel_type, external_identifier) WHERE deleted_at IS NULL` contra BD — el front no conoce las otras cuentas) y `CHANNEL_CREDENTIALS_MISSING` (500/400, si el `secret_name` apunta a un secreto inexistente/vacío y no hay fallback env — se descubre recién al enviar). Se muestran en `MessageBar`.

> **El secreto JAMÁS se captura en claro en el front**: la decisión (spec §1.2 / ADR-010) es que las credenciales (`access_token`, `app_secret`) viven en GCP Secret Manager y se resuelven server-only por el `secret_resolver`. El admin captura el **nombre** del secreto (`secret_name`); crear/rotar el secreto en sí es una tarea de ops (gcloud), NO un campo del drawer. El drawer muestra un estado "Credenciales: configuradas / sin configurar" derivado de `credentials_configured` (read-only).

### `lib/schemas/message.schema.ts`

Enviar un mensaje outbound. MVP solo `content_type=text` → el Zod fija el default y rechaza otros (espeja el `UNSUPPORTED_CONTENT_TYPE` 400 del backend). `content` no-vacío + largo razonable (WhatsApp tope ~4096 chars por mensaje de texto).

```ts
import { z } from "zod";

export const messageSendSchema = z.object({
  content: z
    .string()
    .trim()
    .min(1, "Escribe un mensaje")
    .max(4096, "Máximo 4096 caracteres"), // tope de WhatsApp text
  // MVP solo texto. El backend rechaza otros con UNSUPPORTED_CONTENT_TYPE (400); lo
  // fijamos a "text" para no permitir enviar otra cosa desde el composer.
  content_type: z.literal("text").default("text"),
});

export type MessageSendInput = z.infer<typeof messageSendSchema>;
```

> **`content` se `.trim()` en el Zod** (no se envían mensajes en blanco/solo-espacios). El composer también deshabilita el botón "Enviar" si el textarea está vacío tras trim (defensa de UX antes del submit). Adjuntos (F4) agregarán `attachments` a este schema; hoy no existen.

## Constantes de presentación — `lib/constants/conversations.ts`

Metadata de presentación: ícono Fluent, label en español y color (token Fluent — **NO** `brandPalette.accent`, que no existe; ver [`ui.md`](./ui.md)). **Nuevo** (conversations necesita su propia tabla: estados de mensaje, tipos de sender, tipos de assignee). El `CHANNEL_TYPE_META` se **reusa de crm** (`lib/constants/crm.ts`) — NO se duplica.

```ts
import {
  CheckmarkRegular,
  CheckmarkCircleRegular,
  ErrorCircleRegular,
  ClockRegular,
  BotRegular,
  PersonRegular,
  PersonQuestionMarkRegular,
  ChatRegular,
} from "@fluentui/react-icons";
import { tokens } from "@fluentui/react-components";

import type {
  AssigneeType,
  ConversationStatus,
  MessageExternalStatus,
  SenderType,
} from "@/types/conversations.types";

// Reuse del CHANNEL_TYPE_META de crm (ícono + label ES por canal). NO duplicar.
export { CHANNEL_TYPE_META } from "@/lib/constants/crm";

// ── Estado de mensaje (outbound) ─────────────────────────
// El "tick" estilo WhatsApp: ✓ enviado, ✓✓ entregado, ✓✓ azul leído, ⚠ fallido,
// 🕓 en tránsito (optimista, antes del 200 del backend). Color con tokens semánticos.
export const MESSAGE_STATUS_META: Record<
  MessageExternalStatus | "pending",
  { label: string; icon: React.FC; color: string }
> = {
  pending: { label: "Enviando…", icon: ClockRegular, color: tokens.colorNeutralForeground3 },
  sent: { label: "Enviado", icon: CheckmarkRegular, color: tokens.colorNeutralForeground3 },
  delivered: { label: "Entregado", icon: CheckmarkCircleRegular, color: tokens.colorNeutralForeground3 },
  read: { label: "Leído", icon: CheckmarkCircleRegular, color: tokens.colorPaletteBlueForeground2 },
  failed: { label: "Falló el envío", icon: ErrorCircleRegular, color: tokens.colorPaletteRedForeground1 },
};

// ── Tipo de sender (para la burbuja: alineación + etiqueta del autor) ──
export const SENDER_TYPE_META: Record<SenderType, { label: string; align: "start" | "end" | "center" }> = {
  contact: { label: "Contacto", align: "start" }, // inbound izq
  advisor: { label: "Asesor", align: "end" }, // outbound der
  bot: { label: "Bot", align: "end" }, // outbound der (no aplica en MVP)
  system: { label: "Sistema", align: "center" }, // notificación centrada y atenuada
};

// ── Tipo de assignee (badge del header del hilo + filtro) ──
export const ASSIGNEE_TYPE_META: Record<
  AssigneeType,
  { label: string; icon: React.FC; color: string }
> = {
  advisor: { label: "Asignado a", icon: PersonRegular, color: tokens.colorPaletteGreenForeground2 },
  bot: { label: "Atiende el bot", icon: BotRegular, color: tokens.colorPaletteBlueForeground2 },
  unassigned: { label: "Sin asignar", icon: PersonQuestionMarkRegular, color: tokens.colorNeutralForeground3 },
};

// ── Estado de la conversación (badge) ────────────────────
export const CONVERSATION_STATUS_META: Record<
  ConversationStatus,
  { label: string; color: string }
> = {
  open: { label: "Abierta", color: tokens.colorPaletteGreenForeground2 },
  closed: { label: "Cerrada", color: tokens.colorNeutralForeground3 },
};

// ── Presets de filtro del inbox (panel izquierdo) ────────
// Cada preset = combinación de filtros sobre columnas REALES. "Todas" = sin filtro.
// scope="mine" añade implícito assignee_user_id=<actor> server-side (vía /me/conversations).
export const INBOX_FILTER_PRESETS: {
  key: string;
  label: string;
  // status / assignment se traducen a FilterCondition sobre columnas reales.
  status?: ConversationStatus;
  assignment?: "mine" | "unassigned"; // mine se resuelve con el id del actor
}[] = [
  { key: "all", label: "Todas" },
  { key: "open", label: "Abiertas", status: "open" },
  { key: "unassigned", label: "Sin asignar", status: "open", assignment: "unassigned" },
  { key: "mine", label: "Asignadas a mí", status: "open", assignment: "mine" },
  { key: "closed", label: "Cerradas", status: "closed" },
];
```

> **Verificar los íconos en la versión instalada de `@fluentui/react-icons`** (mismo paso que catalog/clinic/staff/crm): `CheckmarkRegular`, `CheckmarkCircleRegular`, `ErrorCircleRegular`, `ClockRegular`, `BotRegular`, `PersonRegular`, `PersonQuestionMarkRegular`, `ChatRegular`. Si alguno no resuelve: `PersonQuestionMarkRegular` → `PersonRegular`; `BotRegular` → `ChatRegular`; `CheckmarkCircleRegular` → dos `CheckmarkRegular` superpuestos o `CheckmarkRegular` para "entregado". **No** introducir librerías de íconos nuevas. El doble-tick "✓✓" se compone con dos íconos o un ícono dedicado si existe; documentar el fallback.

> **`brandPalette` NO tiene `accent`** (lección operativa transversal): para colores que no sean primary/primaryHover/primaryPressed/primarySelected, usar tokens Fluent semánticos (`tokens.colorPaletteRedForeground1`, `tokens.colorPaletteBlueForeground2`, etc.) como arriba. Los rojos de "fallido" = `tokens.colorPaletteRedForeground1`.

## Endpoints constants — extender `lib/constants/endpoints.ts`

Bloque CONVERSATIONS completo (todas las URLs autenticadas de la spec §7). Los **webhooks** (spec §5, top-level `/api/v1/webhooks/whatsapp/{id}`, sin JWT) **NO van acá** — los consume Meta directo contra el backend, el frontend nunca los llama (N/A front). Convención: `POST /<recurso>/list`; `PUT` para update completo de channel-account; `/active` lista cruda.

```ts
const CONVERSATIONS = "/api/v1/conversations"; // ← NEW

export const ENDPOINTS = {
  // … AUTH, USERS, ROLES, PERMISSIONS, VERTICALS, SERVICES, PRODUCTS,
  //   BRANCHES, OFFICES, DOCTORS, ME, CRM (existentes) …

  // ── Conversations module ─────────────────────────────────
  CHANNEL_ACCOUNTS: {
    LIST: `${CONVERSATIONS}/channel-accounts/list`,
    CREATE: `${CONVERSATIONS}/channel-accounts`,
    GET: (id: string) => `${CONVERSATIONS}/channel-accounts/${id}`,
    UPDATE: (id: string) => `${CONVERSATIONS}/channel-accounts/${id}`, // ← PUT
    DELETE: (id: string) => `${CONVERSATIONS}/channel-accounts/${id}`, // soft delete
    ACTIVE: `${CONVERSATIONS}/channel-accounts/active`, // raw ChannelAccountOption list
  },
  REALTIME: {
    // NUEVO (redesign Firestore): minta un Firebase Custom Token (server-side, con el JWT)
    // para que el browser abra listeners READ-ONLY sobre el stream de mensajes. Gated
    // CONVERSATIONS_READ o MY_CONVERSATIONS_READ (no es un permiso nuevo — reusa los existentes).
    TOKEN: `${CONVERSATIONS}/realtime/token`, // POST → { token, firebase_config? }
  },
  CONVERSATIONS_API: {
    LIST: `${CONVERSATIONS}/list`, // inbox global. PaginatedResponse[ConversationListItem]
    GET: (id: string) => `${CONVERSATIONS}/${id}`, // SingleResponse[ConversationDetail]
    // MESSAGES_LIST es ahora un FALLBACK server-side (lee Firestore vía Admin SDK). El path
    // PRIMARIO de lectura del hilo es el cliente Firestore real-time (onSnapshot). Útil para
    // SSR/degradación si el Web SDK no carga.
    MESSAGES_LIST: (id: string) => `${CONVERSATIONS}/${id}/messages/list`, // POST + QueryRequest (FALLBACK)
    SEND_MESSAGE: (id: string) => `${CONVERSATIONS}/${id}/messages`, // POST outbound (real Meta + Firestore via Admin SDK)
    TAKE: (id: string) => `${CONVERSATIONS}/${id}/take`, // POST
    RELEASE: (id: string) => `${CONVERSATIONS}/${id}/release`, // POST
    CLOSE: (id: string) => `${CONVERSATIONS}/${id}/close`, // POST
    REOPEN: (id: string) => `${CONVERSATIONS}/${id}/reopen`, // POST
    MARK_READ: (id: string) => `${CONVERSATIONS}/${id}/mark-read`, // POST
  },
  ME_CONVERSATIONS: {
    LIST: `${CONVERSATIONS}/me/conversations/list`, // POST + QueryRequest — mi bandeja
  },
} as const;
```

> **`CONVERSATIONS_API` (no `CONVERSATIONS`) como key**: la const string `CONVERSATIONS = "/api/v1/conversations"` ya ocupa ese identificador en el módulo; el objeto de endpoints de conversaciones se llama `CONVERSATIONS_API` para no colisionar (mismo patrón que `ME_CRM` en crm). Ajustar al gusto del template si hay otra convención (ej. anidar todo bajo una key `CONVERSATIONS_MODULE`), pero mantener la separación const-string vs objeto.

> **`/active` devuelve lista CRUDA** (`response_model=list[ChannelAccountOption]`, sin envelope) — no se lee `.data`. El resto (`/list`, `GET /{id}`, `POST`, `PUT`, acciones) usa los envelopes del template (`PaginatedResponse` / `SingleResponse`) y se lee con `.data`. Las **acciones** (`take`/`release`/`close`/`reopen`/`mark-read`) devuelven `SingleResponse[ConversationDetail]` (la conversación actualizada, para refetch local) — confirmar el shape exacto con [`backend.md`](./backend.md#endpoints).

> **Deep-links del inbox NO son query params del endpoint**: `?channel_account_id=`/`?status=`/`?assignee_user_id=`/`?unassigned` (spec §7) se traducen a `FilterCondition` sobre columnas REALES en el page RSC (ver [Pages](#pages-rsc)), **no** a query string del endpoint. El `POST /list` recibe `QueryRequest` con esos filtros en el body.

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `conversations` entre `crm` y `admin` (orden de módulos: catalog→clinic→staff→crm→**conversations**→admin):

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … */ },
  { key: "catalog", /* … */ },
  { key: "clinic", /* … */ },
  { key: "staff", /* … */ },
  { key: "crm", /* … */ },

  // ── NEW ───────────────────────────────────────────
  {
    key: "conversations",
    label: "Conversaciones",
    icon: "ChatRegular",
    children: [
      {
        key: "inbox",
        label: "Bandeja",
        icon: "MailInboxRegular",
        url: "/conversaciones/bandeja",
        permissions: ["CONVERSATIONS_READ"],
      },
      {
        key: "my-conversations",
        label: "Mi bandeja",
        icon: "PersonMailRegular",
        url: "/conversaciones/mis-conversaciones",
        permissions: ["MY_CONVERSATIONS_READ"],
      },
      {
        key: "channels",
        label: "Canales",
        icon: "PlugConnectedRegular",
        url: "/conversaciones/canales",
        permissions: ["CHANNEL_ACCOUNTS_READ"],
      },
    ],
  },

  { key: "admin", /* … */ },
];
```

> **Gating del grupo vs items** (spec §11): el grupo "Conversaciones" está gated `MENU-CONVERSATIONS` (lo tiene ADMIN + ASESOR; DOCTOR no — spec §10). Cada item lleva además su permiso fino: Bandeja `CONVERSATIONS_READ`, Mi bandeja `MY_CONVERSATIONS_READ`, Canales `CHANNEL_ACCOUNTS_READ`. El page RSC valida con `requirePermission(...)`. El `ASESOR` ve Bandeja + Mi bandeja (tiene `CONVERSATIONS_READ` + `MY_CONVERSATIONS_READ`) pero **NO** Canales (no tiene `CHANNEL_ACCOUNTS_*` — solo admin configura canales, spec §10). El **grupo** se muestra si el usuario tiene alguno de los permisos hijos (el Sidebar colapsa grupos sin hijos visibles); `MENU-CONVERSATIONS` es el toggle "de entrada" del módulo. **No** redefinir los 12 permisos aquí — son canónicos en [`../_seed-and-roles.md`](../_seed-and-roles.md) / spec §10.

> **Íconos** (verificar que existan en `@fluentui/react-icons` v9; fallback si no): grupo Conversaciones `ChatRegular`, Bandeja `MailInboxRegular`, Mi bandeja `PersonMailRegular`, Canales `PlugConnectedRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que catalog/clinic/staff/crm). Alternativas: `MailInboxRegular` → `MailRegular`; `PersonMailRegular` → `MailRegular`/`PersonRegular`; `PlugConnectedRegular` → `PlugRegular`/`ChannelRegular`. **Verificar `ChannelRegular`** (mencionado en spec §11 como candidato) — si existe, es buen candidato para "Canales".

> El sidebar (`components/layout/Sidebar/Sidebar.tsx`) ya filtra items por `permissions` vs `useAuth().permissions`. El detalle de la conversación NO está en `NAV_ITEMS` (vive en `?c=` dentro de Bandeja/Mi bandeja) — su gating es el del page contenedor.

## Lectura real-time del hilo (Firestore)

> **Pieza nueva del rediseño 2026-06-03** (brief §3/§4). El **stream de mensajes vive en Cloud Firestore** (read-model CQRS). El **hilo (right pane)** lo lee el browser **en tiempo real** con el Firebase **Web SDK** vía `onSnapshot` — **READ-ONLY** (el cliente NUNCA escribe Firestore). La autorización del listener la da un **Custom Token** que mintea el backend (con el JWT/RBAC como fuente de verdad) + **Security Rules** que espejan el RBAC. Nada de esto rompe el contrato del template: el browser sigue sin mutar el backend; todo write pasa por Next server action → backend.

### Dependencia nueva: `firebase` (Web SDK)

- `npm i firebase` (solo se importan tres sub-paths: `firebase/app`, `firebase/auth`, `firebase/firestore`). **No** se agrega `firebase/storage` ni otros (adjuntos = F4, vía GCS server-side, no Web SDK).
- **Config pública** del Firebase project en envs `NEXT_PUBLIC_FIREBASE_*` (apiKey, authDomain, projectId, etc.). **NO son secretos** — son config de cliente (el `apiKey` de Firebase Web identifica el proyecto, no autoriza nada por sí solo; la autorización real la dan el Custom Token + las Security Rules). Por eso van con prefijo `NEXT_PUBLIC_` (expuestas al browser, a diferencia de `BACKEND_URL` / el JWT que son server-only). El backend puede además devolver el `firebase_config` en la respuesta del token (campo `firebase_config?`) para no duplicar la config — el cliente puede usar el de env o el del backend.
- Variables esperadas (espejo de la config del Firebase project linkeado a `proyecto-ifc-497317`): `NEXT_PUBLIC_FIREBASE_API_KEY`, `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN`, `NEXT_PUBLIC_FIREBASE_PROJECT_ID`, `NEXT_PUBLIC_FIREBASE_APP_ID`, y `NEXT_PUBLIC_FIREBASE_DATABASE_ID` (= `medisage-qa` / `medisage` — named DB por entorno, brief §1; `getFirestore(app, databaseId)`).

### `lib/firebase/client.ts` (init + sign-in)

Init **lazy + singleton** del Firebase app (un solo `initializeApp` por sesión del browser; `getApps()` evita doble init con HMR). Hace `signInWithCustomToken` con el token que mintó el backend → un `User` de Firebase Auth cuyo ID token (1h, auto-refresh) porta los `developer_claims` (`scope: "conversations"`, `is_advisor`, `can_read_all`) que las Security Rules evalúan. Expone `getFirestore(app, databaseId)` para los listeners.

```ts
"use client";

import { initializeApp, getApps, getApp, type FirebaseApp } from "firebase/app";
import { getAuth, signInWithCustomToken, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

// Config PÚBLICA (no secreta) — viene de NEXT_PUBLIC_FIREBASE_* (o del firebase_config
// que devuelve el backend en /realtime/token). El apiKey identifica el proyecto; NO
// autoriza por sí mismo (la autorización la dan el Custom Token + las Security Rules).
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY!,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN!,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID!,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID!,
};
// named DB por entorno (medisage-qa / medisage) — brief §1.
const DATABASE_ID = process.env.NEXT_PUBLIC_FIREBASE_DATABASE_ID!;

function getFirebaseApp(): FirebaseApp {
  // Singleton: un único initializeApp por sesión (getApps() evita doble init con HMR).
  return getApps().length ? getApp() : initializeApp(firebaseConfig);
}

let signInPromise: Promise<Firestore> | null = null;

// Idempotente: la primera llamada hace signInWithCustomToken; las siguientes reusan la
// promesa (un solo sign-in por sesión del browser). El token lo trae getRealtimeToken().
export async function getRealtimeDb(token: string): Promise<Firestore> {
  if (signInPromise) return signInPromise;
  signInPromise = (async () => {
    const app = getFirebaseApp();
    const auth: Auth = getAuth(app);
    await signInWithCustomToken(auth, token); // ID token 1h, auto-refresh mientras la sesión viva
    return getFirestore(app, DATABASE_ID); // listeners READ-ONLY (Security Rules: write=false)
  })();
  return signInPromise;
}
```

> **El cliente Firebase NUNCA escribe** (brief §3): no se exponen helpers de `setDoc`/`addDoc`/`updateDoc` desde `client.ts` — solo lectura (`onSnapshot`/`getDocs`). Las Security Rules ya bloquean todo write (`allow write: if false`), pero la **disciplina del front es no llamarlas** — todo write pasa por server action → backend (Admin SDK). Si el ID token expira o las Security Rules niegan (ej. cambió la asignación y el `uid` ya no está en `allowed_reader_ids`), el `onSnapshot` emite un error `permission-denied` → el componente cae al fallback (ver [ConversationThread](#conversationthreadtsx-panel-derecho)).

### Server action `getRealtimeToken()` — `actions/realtime.actions.ts`

Mintea el Custom Token **server-side** (con el JWT del usuario en la cookie httpOnly). Es el único punto donde el front obtiene credencial de Firebase; el browser jamás llama directo al endpoint (igual que todo el resto — pasa por Next server). Gated por el backend con `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` (no es un permiso nuevo; reusa los existentes — brief §3/§5). Los `developer_claims` (`is_advisor`, `can_read_all`) los decide el backend según el RBAC del actor (`can_read_all=true` para quien tiene `CONVERSATIONS_READ` = bandeja global/supervisor; los demás solo sus conversaciones asignadas).

```ts
"use server";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { MutationResult } from "./user.actions";

// Shape del token de Firebase. firebase_config es opcional (el cliente puede usar los
// NEXT_PUBLIC_FIREBASE_* en su lugar). El token es de un solo uso para signInWithCustomToken.
export interface RealtimeToken {
  token: string;
  firebase_config?: {
    apiKey: string;
    authDomain: string;
    projectId: string;
    appId: string;
    databaseId: string;
  } | null;
}

// NO se taggea ni se cachea — es una credencial efímera (custom token, ~1h de validez del
// ID token resultante). El cliente la pide al montar el inbox y reusa el sign-in (idempotente).
export async function getRealtimeToken(): Promise<MutationResult<RealtimeToken>> {
  try {
    const res = await backendClient.post<ApiSingle<RealtimeToken>>(ENDPOINTS.REALTIME.TOKEN, {});
    return { ok: true, data: res.data };
  } catch (e) {
    // 403 si el actor no tiene CONVERSATIONS_READ ni MY_CONVERSATIONS_READ (en español).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **El token se obtiene una vez por sesión de inbox** (`InboxShell` lo pide al montar y lo pasa al `ConversationThread`/`useThreadMessages`). El `signInWithCustomToken` produce un ID token con auto-refresh (mientras la sesión medisage viva) → no hace falta re-pedir el custom token en cada conversación. Si el sign-in falla (token inválido/expirado, o el backend lo niega), el hilo cae al **fallback** `listMessages` (lectura server-side de Firestore vía Admin SDK) — el inbox sigue funcionando, sin real-time.

> **Logout / revocación**: al cerrar sesión en medisage (o si se revocan permisos), el backend hace `revoke_refresh_tokens(uid)` (brief §3) → el ID token de Firebase deja de refrescarse → los listeners se cierran/niegan. El front no necesita lógica extra de logout de Firebase más allá de no re-mintar el token; opcionalmente `signOut(auth)` en el cleanup del inbox.

## Server Actions

Mismo molde que clinic/catalog/staff/crm: validar con Zod en el action → llamar backend client → `revalidateTag(TAG, "max")`. Reusa el `MutationResult<T>` exportado por `user.actions.ts` (no se redefine). **Next 16 exige el 2º argumento de `revalidateTag`** (`"max"`) — lección del template ([feedback Next.js 16](../_seed-and-roles.md)); omitirlo es error de tipos/runtime.

> **Polling (LISTA) vs real-time Firestore (HILO) vs cache de Server Actions** (clave en este módulo, redesign 2026-06-03):
> - **El HILO (right pane) NO se poléa** — se lee en **tiempo real vía Firestore `onSnapshot`** (ver [Lectura real-time del hilo](#lectura-real-time-del-hilo-firestore) y [ConversationThread](#conversationthreadtsx-panel-derecho)). `getConversation` (el detail/handoff/header) se carga al seleccionar y se refetcha tras una mutación propia (handoff). `listMessages` queda como **fallback** server-side, no como loop de polling.
> - **La LISTA (left pane / inbox) sigue por polling Postgres** (`listConversations` / `listMyConversations`, spec §1 default). El polling re-invoca esas actions cada ~10 s con un `cache: "no-store"` efectivo (o re-fetch que ignora el cache RSC) para traer datos frescos del backend, no del cache de Next. (Opción futura: también live vía la colección `conversations` de Firestore — mismo mecanismo del hilo; el listado live es secundario, el hilo es lo prioritario.)
> - Las lecturas (`listConversations`, `getConversation`, `listMyConversations`, y el fallback `listMessages`) llevan `tags` para que las **mutaciones** (send/take/release/close/reopen/mark-read) las invaliden con `revalidateTag`. El tag es el mecanismo de invalidación tras una mutación propia; el polling (lista) y el listener Firestore (hilo) son los mecanismos de "tiempo real". Si el backend client cachea agresivamente, el polling de la lista pasa `{ revalidate: 0 }` / `{ cache: "no-store" }` para esa llamada (confirmar el contrato del `backendClient` con el template).

### Tags

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `conversations:channel-accounts` | listas y detalle de cuentas de canal, `/active` | crear/editar/borrar una cuenta de canal |
| `conversations:list` | inbox global + mi bandeja (listas de conversaciones) | enviar mensaje, take/release/close/reopen/mark-read (afectan preview/unread/assignee/status denormalizados en la lista) |
| `conversations:thread:{conversationId}` | detalle + mensajes de UNA conversación | enviar mensaje, take/release/close/reopen/mark-read de esa conversación |

> **Por qué tag por-conversación** (`conversations:thread:{id}`): el tag `conversations:thread:{id}` cubre el **`ConversationDetail`** (header/handoff/`assignment_history`) y el **fallback** `listMessages` — **NO** el stream real-time de mensajes (ese vive en Firestore y se actualiza por el listener, no por el cache de Next; redesign 2026-06-03). El hilo de una conversación es independiente del de otra; taggear por id evita invalidar el cache del detail de todas al mutar una (mismo criterio que `crm:lead:{id}` / `staff:availability:{doctorId}`). **Cross-tag**: enviar un mensaje o tomar una conversación afecta **tanto** `conversations:thread:{id}` (el detail: nuevo log de handoff, assignee) **como** `conversations:list` (el inbox: `last_message_preview`/`last_message_at`/`unread_count`/`assignee` denormalizados). Cada action de mutación revalida los dos. **No hay** tag por-mensaje (los mensajes son inmutables): el mensaje nuevo aparece en el hilo por el **listener Firestore** (no por revalidación del tag), y los cambios de `external_status` (sent→delivered→read→failed, que el backend escribe al doc Firestore vía Admin SDK) llegan **en vivo** por el mismo listener — **ya no** por el próximo polling.

### `actions/channel-account.actions.ts`

Molde directo de `lead-status.actions.ts` de crm (catálogo admin). `/active` devuelve lista cruda.

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  channelAccountCreateSchema,
  channelAccountUpdateSchema,
} from "@/lib/schemas/channel-account.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  ChannelAccountDetail,
  ChannelAccountItem,
  ChannelAccountOption,
} from "@/types/conversations.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const TAG = "conversations:channel-accounts";

export async function listChannelAccounts(
  query: QueryRequest,
): Promise<ApiPaginated<ChannelAccountItem>> {
  return backendClient.post<ApiPaginated<ChannelAccountItem>>(
    ENDPOINTS.CHANNEL_ACCOUNTS.LIST,
    query,
    { tags: [TAG] },
  );
}

export async function listActiveChannelAccounts(): Promise<ChannelAccountOption[]> {
  // `/active` devuelve lista CRUDA (sin envelope) — NO se lee `.data`.
  return backendClient.get<ChannelAccountOption[]>(ENDPOINTS.CHANNEL_ACCOUNTS.ACTIVE, {
    tags: [TAG],
  });
}

export async function getChannelAccount(id: string): Promise<ApiSingle<ChannelAccountDetail>> {
  return backendClient.get<ApiSingle<ChannelAccountDetail>>(ENDPOINTS.CHANNEL_ACCOUNTS.GET(id), {
    tags: [TAG],
  });
}

export async function createChannelAccount(
  input: unknown,
): Promise<MutationResult<ApiSingle<ChannelAccountDetail>>> {
  const parsed = channelAccountCreateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.post<ApiSingle<ChannelAccountDetail>>(
      ENDPOINTS.CHANNEL_ACCOUNTS.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN (mismo channel_type+external_identifier) en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateChannelAccount(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<ChannelAccountDetail>>> {
  const parsed = channelAccountUpdateSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    const data = await backendClient.put<ApiSingle<ChannelAccountDetail>>(
      ENDPOINTS.CHANNEL_ACCOUNTS.UPDATE(id), // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteChannelAccount(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.CHANNEL_ACCOUNTS.DELETE(id)); // soft delete
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 si hay conversaciones/colgadas (confirmar con backend si el delete bloquea).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/conversation.actions.ts`

El corazón del módulo: lecturas del inbox (taggeadas + polleadas por la lista) + el `detail` de la conversación (`getConversation`) + el **fallback** `listMessages` (el path primario del hilo es el listener Firestore — ver [Lectura real-time del hilo](#lectura-real-time-del-hilo-firestore)) + las acciones de handoff/outbound (mutaciones que cruzan `conversations:list` + `conversations:thread:{id}`).

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { messageSendSchema } from "@/lib/schemas/message.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  ConversationDetail,
  ConversationListItem,
  MessageItem,
  ReleaseConversationRequest,
  TakeConversationRequest,
} from "@/types/conversations.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const LIST_TAG = "conversations:list";
const threadTag = (id: string) => `conversations:thread:${id}`;

// ── Lecturas (taggeadas; el polling las re-invoca sin depender del tag) ──

export async function listConversations(
  query: QueryRequest,
): Promise<ApiPaginated<ConversationListItem>> {
  return backendClient.post<ApiPaginated<ConversationListItem>>(
    ENDPOINTS.CONVERSATIONS_API.LIST,
    query,
    { tags: [LIST_TAG] },
  );
}

export async function listMyConversations(
  query: QueryRequest,
): Promise<ApiPaginated<ConversationListItem>> {
  // El backend resuelve el asesor del token (assignee_user_id = actor).
  return backendClient.post<ApiPaginated<ConversationListItem>>(
    ENDPOINTS.ME_CONVERSATIONS.LIST,
    query,
    { tags: [LIST_TAG] },
  );
}

export async function getConversation(id: string): Promise<ApiSingle<ConversationDetail>> {
  // Detail incluye assignment_history (para el panel de handoff).
  return backendClient.get<ApiSingle<ConversationDetail>>(ENDPOINTS.CONVERSATIONS_API.GET(id), {
    tags: [threadTag(id)],
  });
}

// FALLBACK (redesign Firestore): el path PRIMARIO de lectura del hilo es el cliente
// Firestore real-time (onSnapshot — ver `useThreadMessages`). Esta action lee Firestore
// vía Admin SDK server-side y se usa solo como degradación (SSR / si el Web SDK no carga /
// si el custom token falla). El backend devuelve el mismo shape MessageItem (snake_case).
export async function listMessages(
  conversationId: string,
  query: QueryRequest,
): Promise<ApiPaginated<MessageItem>> {
  return backendClient.post<ApiPaginated<MessageItem>>(
    ENDPOINTS.CONVERSATIONS_API.MESSAGES_LIST(conversationId),
    query,
    { tags: [threadTag(conversationId)] },
  );
}

// ── Outbound (envío real contra Meta; el backend persiste y devuelve el message) ──

export async function sendMessage(
  conversationId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<MessageItem>>> {
  const parsed = messageSendSchema.safeParse(input);
  if (!parsed.success) return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  try {
    // IMPORTANTE: el backend devuelve 200 incluso si Meta falló — el MessageItem viene
    // con failed_at/failure_reason set y external_status="failed". NO es un throw.
    // El componente inspecciona data.data para mostrar el estado fallido + Reintentar.
    const data = await backendClient.post<ApiSingle<MessageItem>>(
      ENDPOINTS.CONVERSATIONS_API.SEND_MESSAGE(conversationId),
      parsed.data,
    );
    revalidateTag(threadTag(conversationId), "max");
    revalidateTag(LIST_TAG, "max"); // last_message_preview/at en el inbox
    return { ok: true, data };
  } catch (e) {
    // throw real = 400 CONVERSATION_NOT_OPEN / 403 NOT_CONVERSATION_ASSIGNEE /
    // 400 UNSUPPORTED_CONTENT_TYPE / 404 CONVERSATION_NOT_FOUND — en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

// ── Handoff (emite CONVERSATION_TAKEN/RELEASED a la timeline de crm server-side) ──

export async function takeConversation(
  conversationId: string,
  input: TakeConversationRequest = {},
): Promise<MutationResult<ApiSingle<ConversationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.TAKE(conversationId),
      input,
    );
    // assignee=actor + reset unread + emite CONVERSATION_TAKEN (crm). Cruza ambos tags.
    revalidateTag(threadTag(conversationId), "max");
    revalidateTag(LIST_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 400 INVALID_ASSIGNEE / 400 CONVERSATION_NOT_OPEN en español.
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function releaseConversation(
  conversationId: string,
  input: ReleaseConversationRequest,
): Promise<MutationResult<ApiSingle<ConversationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.RELEASE(conversationId),
      input,
    );
    // Emite CONVERSATION_RELEASED (crm) + cierra log vigente + abre uno nuevo.
    revalidateTag(threadTag(conversationId), "max");
    revalidateTag(LIST_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function closeConversation(
  conversationId: string,
): Promise<MutationResult<ApiSingle<ConversationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.CLOSE(conversationId),
      {},
    );
    // status=closed + cierra el ConversationAssignmentLog vigente (ended_at=now).
    revalidateTag(threadTag(conversationId), "max");
    revalidateTag(LIST_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function reopenConversation(
  conversationId: string,
): Promise<MutationResult<ApiSingle<ConversationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.REOPEN(conversationId),
      {},
    );
    revalidateTag(threadTag(conversationId), "max");
    revalidateTag(LIST_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    // 409 CONVERSATION_ALREADY_OPEN si ya hay otra open para (person, channel_account).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function markRead(
  conversationId: string,
): Promise<MutationResult<ApiSingle<ConversationDetail>>> {
  try {
    const data = await backendClient.post<ApiSingle<ConversationDetail>>(
      ENDPOINTS.CONVERSATIONS_API.MARK_READ(conversationId),
      {},
    );
    revalidateTag(threadTag(conversationId), "max");
    revalidateTag(LIST_TAG, "max"); // unread_count del inbox
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **`sendMessage` NO lanza ante fallo de envío** (spec §1.5 / §5 outbound): el endpoint devuelve **200** con el `MessageItem` en estado `failed` (`failed_at`/`failure_reason`/`external_status="failed"`). El action devuelve `{ ok: true, data }` con ese message — el componente inspecciona `data.data.external_status === "failed"` para pintar el estado ⚠ + botón **Reintentar**. Solo lanza (→ `{ ok: false, error }`) ante errores de pre-condición: `CONVERSATION_NOT_OPEN` (400), `NOT_CONVERSATION_ASSIGNEE` (403), `UNSUPPORTED_CONTENT_TYPE` (400), `CONVERSATION_NOT_FOUND` (404). **Reintentar** = volver a llamar `sendMessage` con el mismo `content` (crea un nuevo Message; el fallido queda en el hilo como audit — no se borra, es inmutable).

> **Las acciones devuelven el `ConversationDetail` actualizado**: take/release/close/reopen/mark-read devuelven `SingleResponse[ConversationDetail]` (confirmar shape con backend.md). El componente usa ese retorno para un **refetch local optimista** (actualiza el hilo abierto sin esperar el próximo polling) **y** dispara `router.refresh()` para re-pintar lo que venga de un RSC (lección crm F3: la conversación pinta datos denormalizados — assignee badge, status — que un cache RSC stale dejaría desactualizados). Ver [Controles de handoff](#controles-de-handoff).

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/conversaciones/canales/page.tsx`

Molde directo de `crm/estados-lead/page.tsx` / `catalog` Verticals: RSC con `requirePermission` + prefetch de la primera página. CRUD simple (tabla + drawer). `defaultSort` sobre columna real (`created_on` o `name` si está en `ALLOWED_FIELDS`; confirmar con backend).

```tsx
import { listChannelAccounts } from "@/actions/channel-account.actions";
import { requirePermission } from "@/lib/auth/session";

import { ChannelAccountsClient } from "./_components/ChannelAccountsClient";

export const metadata = { title: "Canales" };

export default async function ChannelAccountsPage() {
  await requirePermission("CHANNEL_ACCOUNTS_READ");
  const initialData = await listChannelAccounts({
    pagination: { skip: 0, limit: 50 }, // catálogo chico; una página suele bastar
    sorting: { sort_by: "created_on", sort_order: "desc" }, // columna real; coincide con el client
    filters: null,
  });
  return <ChannelAccountsClient initialData={initialData} />;
}
```

### `app/(main)/conversaciones/bandeja/page.tsx` (inbox GLOBAL)

El inbox global (todas las conversaciones, gated `CONVERSATIONS_READ`). Prefetch de la primera página de la lista + los canales activos (para el filtro de canal). **Deep-link**: `?channel_account_id=`/`?status=`/`?assignee_user_id=`/`?unassigned`/`?c=<conversationId>` traducidos a `FilterCondition` sobre columnas REALES (el repo NO los traduce a EXISTS — son columnas directas de `conversation`, a diferencia de los virtuales de crm) y a la conversación pre-seleccionada (`?c=`). El `defaultSort` del prefetch usa `last_message_at` (columna real whitelistada) — DEBE coincidir con el `defaultSort` del client (lección `cd10c78`).

```tsx
import { listActiveChannelAccounts } from "@/actions/channel-account.actions";
import { listConversations } from "@/actions/conversation.actions";
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { InboxShell } from "../_components/InboxShell";

export const metadata = { title: "Bandeja" };

interface PageProps {
  searchParams: Promise<{
    channel_account_id?: string;
    status?: string;
    assignee_user_id?: string;
    unassigned?: string;
    c?: string; // conversación pre-seleccionada (deep-link)
  }>;
}

export default async function InboxPage({ searchParams }: PageProps) {
  await requirePermission("CONVERSATIONS_READ");
  const { channel_account_id, status, assignee_user_id, unassigned, c } = await searchParams;

  // Deep-link → FilterCondition sobre columnas REALES de ALLOWED_FIELDS (status,
  // channel_account_id, assignee_user_id, assignee_type). NO son denormalizados.
  const conditions: FilterCondition[] = [];
  if (status) conditions.push({ field: "status", operator: "eq", value: status });
  if (channel_account_id)
    conditions.push({ field: "channel_account_id", operator: "eq", value: channel_account_id });
  if (assignee_user_id)
    conditions.push({ field: "assignee_user_id", operator: "eq", value: assignee_user_id });
  if (unassigned === "true")
    conditions.push({ field: "assignee_type", operator: "eq", value: "unassigned" });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  const [initialData, channelAccounts] = await Promise.all([
    listConversations({
      pagination: { skip: 0, limit: 30 }, // inbox: página más grande que un CRUD (lista scrolleable)
      // defaultSort = last_message_at (columna REAL whitelistada). DEBE coincidir con
      // el defaultSort del InboxShell (sino flash + refetch en el primer paint).
      sorting: { sort_by: "last_message_at", sort_order: "desc" },
      filters,
    }),
    listActiveChannelAccounts(),
  ]);

  return (
    <InboxShell
      scope="all"
      initialData={initialData}
      channelAccounts={channelAccounts}
      initialSelectedId={c ?? null}
    />
  );
}
```

> **Por qué los filtros del inbox SÍ son columnas reales** (a diferencia de crm, donde eran virtuales): `status`, `channel_account_id`, `assignee_user_id`, `assignee_type` son **columnas directas** de la tabla `conversation` (spec §2.2) y están en `ALLOWED_FIELDS` (spec §7) → se filtran/ordenan server-side sin traducción a EXISTS. Lo que NO se puede ordenar/filtrar server-side es lo **denormalizado** (`person.full_name`, `channel_account.name`, `assignee_user.full_name`, `last_message_preview`) — eso es búsqueda **client-side** sobre la página visible (lección `cd10c78`). `last_message_at` SÍ es ordenable (columna real denormalizada whitelistada) y es el `defaultSort`.

> **`initialSelectedId` (`?c=`) hace al inbox deep-linkable**: abrir `/conversaciones/bandeja?c=abc123` selecciona la conversación `abc123` en el panel derecho al cargar. El `InboxShell` la sincroniza con `nuqs` (`useQueryState("c")`) — seleccionar otra conversación actualiza la URL sin recargar, y la URL sobrevive refresh/compartir.

### `app/(main)/conversaciones/mis-conversaciones/page.tsx` (mi bandeja)

Idéntico a `bandeja` pero con `listMyConversations` (el backend filtra `assignee_user_id = actor` del token) + `requirePermission("MY_CONVERSATIONS_READ")` + `scope="mine"`. El filtro "asignadas a mí" es implícito (lo resuelve `/me/conversations`), así que el preset de filtro de asignación se ajusta (no muestra "Asignadas a mí" — ya lo está todo; muestra solo estado + canal).

```tsx
import { listActiveChannelAccounts } from "@/actions/channel-account.actions";
import { listMyConversations } from "@/actions/conversation.actions";
import { requirePermission } from "@/lib/auth/session";
import type { FilterCondition, QueryRequest } from "@/types/query.types";

import { InboxShell } from "../_components/InboxShell";

export const metadata = { title: "Mi bandeja" };

interface PageProps {
  searchParams: Promise<{ channel_account_id?: string; status?: string; c?: string }>;
}

export default async function MyConversationsPage({ searchParams }: PageProps) {
  await requirePermission("MY_CONVERSATIONS_READ");
  const { channel_account_id, status, c } = await searchParams;

  const conditions: FilterCondition[] = [];
  if (status) conditions.push({ field: "status", operator: "eq", value: status });
  if (channel_account_id)
    conditions.push({ field: "channel_account_id", operator: "eq", value: channel_account_id });
  const filters: QueryRequest["filters"] =
    conditions.length > 0 ? { filters: [{ operator: "AND", conditions }] } : null;

  const [initialData, channelAccounts] = await Promise.all([
    listMyConversations({
      pagination: { skip: 0, limit: 30 },
      sorting: { sort_by: "last_message_at", sort_order: "desc" }, // columna real; coincide con el client
      filters,
    }),
    listActiveChannelAccounts(),
  ]);

  return (
    <InboxShell
      scope="mine"
      initialData={initialData}
      channelAccounts={channelAccounts}
      initialSelectedId={c ?? null}
    />
  );
}
```

> **`scope` distingue qué action de listado usa el `InboxShell`** (`listConversations` vs `listMyConversations`) y qué presets de filtro muestra. Todo lo demás (hilo, composer, handoff, polling) es idéntico — por eso `InboxShell` es compartido y vive en `conversaciones/_components/`, no dentro de una de las dos rutas.

## Client components — esqueletos

> **No reproduzco los archivos completos** — el inbox 2-paneles sigue el patrón del **timeline de crm** (`ActivityTimeline` + sub-componentes memoizados + fetch-token + agrupación client-only) y los CRUD siguen `crm/estados-lead` + `admin/users/UserDrawer`. Documento estructura de componentes + estado + las decisiones específicas a conversations. La UI detallada (mockups, copy) vive en [`ui.md`](./ui.md). El **`InboxShell` + `ConversationThread` son las piezas sustancialmente nuevas** y se detallan aparte.

### `ChannelAccountsClient.tsx`

Molde de `LeadStatusesClient.tsx` (crm) / `VerticalsClient.tsx` (catalog): tabla + drawer CRUD.

- `useTableQuery`: `queryKey: "conversations:channel-accounts"`, `fetcher: listChannelAccounts`, `defaultSort: { field: "created_on", order: "desc" }` (**columna real**, coincide con el prefetch RSC), `searchFields: ["name", "external_identifier"]` (**client-side** — denormalizados/no whitelistados; busca sobre la página visible), `initialData`.
- Columns: `actions`, `name` (Nombre), `channel_type` (badge con `CHANNEL_TYPE_META` — ícono + label ES, ej. WhatsApp), `external_identifier` (Número), `credentials_configured` (Badge "Configurado" verde / "Sin configurar" gris — derivado; NO muestra el secreto), `active` (Badge "Activo"/"Inactivo"). **Ninguna columna denormalizada es `isSortable`**; solo `created_on`/`name`/`channel_type` (si el backend las whitelista).
- **RowActions**: Editar (gated `CHANNEL_ACCOUNTS_UPDATE`) → `ChannelAccountDrawer`; Eliminar (gated `CHANNEL_ACCOUNTS_DELETE`, danger). El delete es soft; `ConfirmDialog`: "Se eliminará el canal. Las conversaciones existentes dejarán de recibir/enviar por este canal." Si el backend bloquea por conversaciones vivas → mostrar el 409 en `MessageBar`.
- Botón "Nuevo canal" gated `CHANNEL_ACCOUNTS_CREATE` → abre `ChannelAccountDrawer`.

### `ChannelAccountDrawer.tsx`

Drawer create/edit. Molde de `LeadStatusDrawer` (crm). `useForm` con `channelAccountCreateSchema`/`channelAccountUpdateSchema`. Campos:

- **`channel_type`** (Dropdown; solo en create, disabled en edit): en el MVP solo la opción **WhatsApp** (los 8 valores están en el enum, pero el form ofrece solo `whatsapp` — los demás llegan cuando se cablee otro canal). Espeja el backend (channel_type no editable en update).
- **`name`** (Input — "WhatsApp Estética").
- **`external_identifier`** (Input — número WA Business "51999111222").
- **`phone_number_id`** (Input — id del número en WhatsApp Cloud API; hint "Lo da Meta en la configuración del número").
- **`webhook_verify_token`** (Input — editable en claro; hint "Token que pones en la verificación del webhook en Meta").
- **`secret_name`** (Input — "Nombre del secreto en Secret Manager, ej. `medisage-whatsapp-estetica-qa`"; hint "El access token / app secret se guardan en Secret Manager, no aquí"). **NO** hay campo para el secreto en claro.
- **Estado de credenciales** (read-only, solo en edit): "Credenciales: configuradas / sin configurar" derivado de `credentials_configured`. Si "sin configurar" → hint en ámbar "Configura el secreto en Secret Manager antes de enviar mensajes."
- **`active`** (Switch — solo en edit).
- **Errores de servidor**: `409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN` (mismo canal + número ya existe) → `MessageBar intent="error"` sin cerrar el drawer.
- En `onSuccess`: cerrar el drawer + `router.refresh()` (la tabla se re-pinta vía el tag invalidado).

> **El webhook URL es informativo, no editable**: tras crear un canal, el admin necesita la URL del webhook (`/api/v1/webhooks/whatsapp/{channel_account_id}`) para pegarla en Meta. El drawer (en edit) puede **mostrar** esa URL armada (read-only, con botón "Copiar") como ayuda de configuración — pero NO es un campo (la ruta la define el backend, spec §5). Documentar como mejora de UX opcional.

### `InboxShell.tsx` — el inbox 2-paneles (pieza nueva, molde del timeline crm)

> **Honestidad (igual que pide la spec / como el timeline de crm)**: este inbox (lista filtrable + hilo con burbujas agrupadas por día + composer + handoff + **polling**) es **bespoke** dentro de Fluent UI 9 — se miran patrones de inboxes modernos (Intercom/Crisp/WhatsApp Web) pero se ejecutan **DENTRO de Fluent** (tokens, primitivas propias, sin librería de chat). Es **el componente más complejo de conversations** (como el `ActivityTimeline` lo es de crm). Construirlo **incrementalmente**: F2 = lista + hilo read-only + polling (recibir y ver); F3 = composer (enviar) + handoff (Tomar/Liberar/Cerrar/Reabrir). La capa de datos (listar, seleccionar, cargar hilo, pollear) es la misma en ambas etapas.

Props: `{ scope: "all" | "mine"; initialData: ApiPaginated<ConversationListItem>; channelAccounts: ChannelAccountOption[]; initialSelectedId: string | null }`.

**Layout 2-paneles** (Fluent `makeStyles`, grid o flex): izquierda = `ConversationList` (ancho fijo ~360px, scrolleable); derecha = `ConversationThread` (flex-1) o un estado vacío "Selecciona una conversación" si no hay ninguna seleccionada. Responsive (MVP desktop; en móvil se diferirá a un patrón master-detail apilado — TODO).

**Estado central** (lo orquesta `InboxShell`):

```ts
// Conversación seleccionada, sincronizada con la URL (?c=) vía nuqs. Deep-linkable.
const [selectedId, setSelectedId] = useQueryState("c", { defaultValue: initialSelectedId ?? "" });
// Filtros del panel izquierdo, sincronizados con la URL (?status=, ?channel_account_id=,
// ?unassigned=). El preset activo deriva de estos. Búsqueda = client-side (NO en URL).
const [statusFilter, setStatusFilter] = useQueryState("status");
const [channelFilter, setChannelFilter] = useQueryState("channel_account_id");
const [search, setSearch] = useState(""); // client-side; NO va al server ni a la URL
// Polling pausable de la LISTA (pausa al perder foco). El HILO ya no se poléa (Firestore).
const [pollingPaused, setPollingPaused] = useState(false);
// Token de Firebase para los listeners real-time del hilo (redesign). Se pide UNA vez al
// montar el inbox (con getRealtimeToken — server action) y se pasa al ConversationThread.
// null mientras carga o si falla (→ el hilo cae a fallback listMessages, sin real-time).
const [realtimeToken, setRealtimeToken] = useState<string | null>(null);
```

```ts
// Mintar el Custom Token al montar el inbox (una sola vez por sesión de inbox). El
// signInWithCustomToken interno es idempotente (lib/firebase/client.ts) — no hace falta
// re-pedirlo por conversación. Si falla, el hilo degrada a fallback (no rompe el inbox).
useEffect(() => {
  let cancelled = false;
  void getRealtimeToken().then((res) => {
    if (cancelled) return;
    if (res.ok) setRealtimeToken(res.data.token);
    // si !res.ok: realtimeToken queda null → ConversationThread usa el fallback server-side.
  });
  return () => { cancelled = true; };
}, []);
```

- **Lista (panel izquierdo)**: usa `useTableQuery` (o un fetch propio si la lista es scroll-infinito en vez de paginada) con `fetcher = scope === "mine" ? listMyConversations : listConversations`, `defaultSort: { field: "last_message_at", order: "desc" }` (**columna real**, coincide con el prefetch RSC — lección `cd10c78`), `searchFields` vacío (la búsqueda es client-side, ver abajo), `initialData`. Los filtros de estado/canal se traducen a `FilterCondition` (columnas reales) y van al server; la búsqueda por nombre/identificador filtra **client-side** sobre la página cargada.
- **Polling de la LISTA** (ver [Polling de la lista](#polling-de-la-lista)): un `useEffect` con `setInterval` re-fetcha **solo la lista** cada ~10 s, **refetch silencioso** (no muestra spinner, no descarta el scroll, no parpadea — actualiza el estado solo si cambió). Pausable. **El hilo abierto NO se poléa** — se actualiza en vivo por el listener Firestore del `ConversationThread` (redesign 2026-06-03).
- **Selección**: clic en una fila → `setSelectedId(conv.id)` (actualiza `?c=`) → `ConversationThread` carga ese hilo. Al seleccionar una conversación con `unread_count > 0`, dispara `markRead(conv.id)` (resetea el badge) — opcional/configurable: marcar leído al abrir.

### `ConversationList.tsx` (panel izquierdo)

- **Toolbar**: presets de filtro (`INBOX_FILTER_PRESETS` → chips/SegmentedControl: Todas / Abiertas / Sin asignar / Asignadas a mí / Cerradas — en `scope="mine"` se omiten "Asignadas a mí"), Dropdown de canal (`channelAccounts` → `CHANNEL_TYPE_META`), `SearchBox` (búsqueda **client-side** por nombre/identificador sobre la página visible). Chips "Filtrado por: …" con ✕ que limpian (mismo flujo que el filtro de sede en `DoctorsClient`).
- **Filas**: `ConversationListItemRow` memoizada por conversación. La búsqueda client-side se aplica con un `useMemo` sobre `items.filter(c => matchesSearch(c, search))`.
- **Estados** (español): loading (skeletons de filas), vacío ("No hay conversaciones" / "No tienes conversaciones asignadas" según scope), error (`MessageBar`).

### `ConversationListItemRow.tsx` (fila memoizada)

```tsx
export const ConversationListItemRow = React.memo(function ConversationListItemRow({
  conversation,
  selected,
  onSelect,
}: {
  conversation: ConversationListItem;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  // avatar (inicial del person.full_name) + ícono de canal (CHANNEL_TYPE_META),
  // person.full_name ?? "Contacto desconocido", last_message_preview (truncado),
  // hora relativa de last_message_at (formatRelative CLIENT-ONLY), badge unread_count
  // (si > 0), estado closed atenuado, AssigneeBadge mini (assignee_user.full_name o
  // "Sin asignar"). Resaltado si `selected`.
  return (/* … Fluent, tokens, sin brandPalette.accent … */);
});
```

> **`ConversationListItemRow` memoizada** (regla vercel-react): el inbox puede tener decenas de filas y se re-renderiza en cada polling. `React.memo` evita re-render de las filas que no cambiaron (compara `conversation` por referencia — el polling solo reemplaza las filas que mutaron, las demás conservan su referencia). El `onSelect` se pasa como callback estable (`useCallback` en el padre) para no romper la memoización.

### `ConversationThread.tsx` (panel derecho)

El hilo de la conversación seleccionada. **Redesign 2026-06-03**: los **mensajes** se leen **en tiempo real desde Firestore** vía `onSnapshot` (READ-ONLY) — **ya NO por polling/refetch del hilo**. El **`ConversationDetail`** (header/handoff/`assignment_history`) sí se carga por server action (`getConversation`) al seleccionar y se refetcha tras una mutación de handoff. Estructura:

```
ConversationThread          (orquesta: detail por action + mensajes REAL-TIME por Firestore listener)
├── ThreadHeader            (contacto + canal + estado + AssigneeBadge + HandoffControls)
├── (scroll de mensajes)
│   └── MessageDayGroup[]   (una sección por día: "Hoy"/"Ayer"/"12 may" — client-only)
│       └── MessageBubble[] (burbuja memoizada: in/out/system + MessageStatusTicks)
└── Composer                (textarea + enviar; gated MESSAGES_SEND + ser el assignee)
```

**Props**: `{ conversationId: string; scope: "all" | "mine"; realtimeToken: string | null; onMutated: () => void }` (`realtimeToken` lo provee `InboxShell` desde `getRealtimeToken()`; `onMutated` refresca la lista tras una mutación que cambia el preview/unread/assignee).

**Estado del detail** (molde del `ActivityTimeline`; SOLO el detail, NO los mensajes):

```ts
const [detail, setDetail] = useState<ConversationDetail | null>(null);
const [loading, setLoading] = useState(true);
const [detailError, setDetailError] = useState<string | null>(null);
// Token monotónico: al cambiar de conversación rápido, una respuesta vieja no pisa la nueva
// (idéntico a OfficeClosuresTab / ActivityTimeline de crm).
const reqIdRef = useRef(0);

// Carga del DETAIL (header/handoff) por server action. Reutilizable tras un handoff.
const loadDetail = useCallback((silent = false) => {
  const reqId = ++reqIdRef.current;
  if (!silent) setLoading(true);
  setDetailError(null);
  void getConversation(conversationId)
    .then((detailRes) => {
      if (reqId !== reqIdRef.current) return; // respuesta superada → descartar
      setDetail(detailRes.data);
      setLoading(false);
    })
    .catch(() => {
      if (reqId !== reqIdRef.current) return;
      setDetailError("No se pudo cargar la conversación. Intenta de nuevo.");
      setLoading(false);
    });
}, [conversationId]);

useEffect(() => { loadDetail(); }, [loadDetail]); // reset al cambiar de conversación
```

**Mensajes en vivo** (Firestore listener — el cambio sustancial del rediseño). Los mensajes vienen del hook `useThreadMessages` (ver abajo), **no** del `getConversation` ni de `listMessages`:

```ts
const { messages, status: msgStatus } = useThreadMessages(conversationId, realtimeToken);
// messages: Record<string, MessageItem> (indexado por id = mid). El listener Firestore
// los entrega en vivo: un inbound nuevo, un outbound recién enviado, o un cambio de
// external_status (sent→delivered→read→failed) aparece SIN polling, SIN refetch.
// msgStatus: "live" | "loading" | "fallback" | "error" (ver useThreadMessages).
```

### `useThreadMessages.ts` (hook del listener Firestore — pieza nueva)

Abre el listener real-time sobre `conversations/{cid}/messages` y expone los mensajes indexados por id. **READ-ONLY** — el hook solo lee; cualquier write pasa por las server actions (composer/handoff). Maneja el sign-in (idempotente, vía `lib/firebase/client.ts`), el cleanup del listener al cambiar de conversación, y la **degradación a fallback** (`listMessages` server-side) si Firebase no está disponible o el custom token falla.

```ts
"use client";

import { useEffect, useRef, useState } from "react";
import { collection, onSnapshot, orderBy, query } from "firebase/firestore";

import { getRealtimeDb } from "@/lib/firebase/client";
import { listMessages } from "@/actions/conversation.actions";
import type { MessageItem } from "@/types/conversations.types";

type ThreadStatus = "loading" | "live" | "fallback" | "error";

export function useThreadMessages(conversationId: string, realtimeToken: string | null) {
  const [messages, setMessages] = useState<Record<string, MessageItem>>({});
  const [status, setStatus] = useState<ThreadStatus>("loading");
  const reqIdRef = useRef(0); // descarta listeners viejos al cambiar de conversación

  useEffect(() => {
    const reqId = ++reqIdRef.current;
    setMessages({}); // reset al cambiar de conversación
    setStatus("loading");
    let unsubscribe: (() => void) | undefined;

    (async () => {
      // Fallback server-side si no hay token (sign-in falló / sin Firebase): lee Firestore
      // vía Admin SDK por el endpoint /messages/list. El inbox sigue, sin real-time.
      if (!realtimeToken) {
        const res = await listMessages(conversationId, {
          pagination: { skip: 0, limit: 50 },
          sorting: { sort_by: "created_at", sort_order: "asc" },
          filters: null,
        });
        if (reqId !== reqIdRef.current) return;
        setMessages(indexById(res.data.items));
        setStatus("fallback");
        return;
      }
      try {
        const db = await getRealtimeDb(realtimeToken); // signInWithCustomToken (idempotente)
        if (reqId !== reqIdRef.current) return;
        // READ-ONLY: collection messages del doc de la conversación, orden cronológico.
        const q = query(
          collection(db, "conversations", conversationId, "messages"),
          orderBy("created_at", "asc"),
        );
        unsubscribe = onSnapshot(
          q,
          (snap) => {
            if (reqId !== reqIdRef.current) return;
            // Cada doc = un MessageItem (mismo shape snake_case, brief §6). Indexa por id.
            const next: Record<string, MessageItem> = {};
            snap.forEach((d) => { next[d.id] = { id: d.id, ...d.data() } as MessageItem; });
            setMessages(next);
            setStatus("live");
          },
          () => {
            // permission-denied (asignación cambió / token expiró) o red → degradar.
            if (reqId !== reqIdRef.current) return;
            setStatus("error");
          },
        );
      } catch {
        if (reqId !== reqIdRef.current) return;
        setStatus("error"); // sign-in falló → el componente puede caer a listMessages
      }
    })();

    return () => { unsubscribe?.(); }; // cleanup del listener al cambiar de conversación/desmontar
  }, [conversationId, realtimeToken]);

  return { messages, status };
}
```

> **El listener Firestore reemplaza el polling del hilo** (brief §4): el inbound nuevo del contacto, el outbound recién escrito por el backend (status `pending` → el asesor lo ve **instantáneo**), y los cambios de `external_status` (sent→delivered→read→failed, que el backend escribe al doc Firestore vía Admin SDK al recibir el status callback de Meta) llegan **en vivo** — sin `setInterval`, sin refetch, sin latencia de ~10 s. El `onSnapshot` entrega el set completo de la colección (o solo los `docChanges()` si se optimiza); indexar por id conserva el merge incremental (las burbujas que no cambiaron mantienen su referencia → `React.memo` evita re-render — ver [MessageBubble](#messagebubbletsx-memoizada)). El scroll "stick to bottom" condicional se mantiene igual (no arrastra al usuario que lee arriba).

> **El cliente NUNCA escribe Firestore** (brief §3): `useThreadMessages` solo usa `onSnapshot`/`query`/`collection` (lectura). Enviar un mensaje = `Composer` → `sendMessage` server action → backend (Admin SDK escribe el doc) → el listener lo ve aparecer. No hay `setDoc`/`addDoc` en el front. Las Security Rules además bloquean todo write del cliente (`allow write: if false`).

> **Orden por `created_at`** (campo del doc Firestore, brief §1): el listener ordena por `created_at asc` (cronológico, más antiguo arriba — como un chat). **Nota de mapeo**: en el modelo previo el sort del hilo era `sent_at asc` sobre la tabla Postgres; en el doc Firestore el campo de orden es **`created_at`** (el timestamp de creación del mensaje en el read-model). El shape del resto de campos del doc (`direction`, `sender_type`, `content`, `external_status`, `sent_at`, `delivered_at`, `read_at`, `failed_at`, …) es **el mismo `MessageItem`** (snake_case, brief §6) que devolvía la API — el render de las burbujas no cambia. El **fallback** `listMessages` usa el mismo `created_at asc` (el backend lee Firestore vía Admin SDK y respeta el mismo orden). Confirmar el nombre exacto del campo de orden con [`backend.md`](./backend.md) (brief §1 lo nombra `created_at`).

> **Degradación a fallback sin real-time**: si `getRealtimeToken()` falla, el Web SDK no carga, o el `onSnapshot` emite `permission-denied` (la asignación cambió y el `uid` ya no está en `allowed_reader_ids`), `useThreadMessages` cae a `listMessages` (lectura server-side de Firestore vía Admin SDK). El hilo sigue mostrándose (snapshot puntual, sin updates en vivo); un `MessageBar` informativo opcional ("Sin actualización en vivo — recarga para ver mensajes nuevos") avisa el modo degradado. El inbox **nunca** queda inutilizable por un fallo de Firebase.

### `ThreadHeader.tsx`

Cabecera del hilo: avatar + `person.full_name` (o "Contacto desconocido"), `primary_identifier` (ícono de canal `CHANNEL_TYPE_META` + valor), `channel_account.name`, **badge de estado** (`CONVERSATION_STATUS_META` — "Abierta"/"Cerrada"), **`AssigneeBadge`** (`ASSIGNEE_TYPE_META` — "Asignado a X" / "Atiende el bot" / "Sin asignar"), y los **`HandoffControls`** (botonera). Opcional: link "Ver contacto" → `/crm/personas/{person.id}` (cruza a crm si el asesor tiene `PERSONS_READ`). El `assignment_history` (del `ConversationDetail`) se puede mostrar en un popover "Historial de asignación" (timeline simple de `ConversationAssignmentLogItem`: from→to, `started_at`/`ended_at`, `by_actor_user.full_name ?? "Sistema"`, `reason`).

### `MessageDayGroup.tsx`

Agrupación de burbujas por día. **`new Date()` client-only** (lección TZ recurrente — el SSR en UTC desfasaría "Hoy"/"Ayer" en TZ negativas como Lima `-05:00`):

```ts
// Computado en el cliente (ConversationThread es "use client") con la TZ del navegador.
const dayGroups = useMemo(() => {
  const list = Object.values(messages).sort(
    (a, b) => new Date(a.sent_at).getTime() - new Date(b.sent_at).getTime(), // cronológico
  );
  // groupByDay devuelve [{ label: "Hoy"|"Ayer"|"12 may", items: [...] }] usando new Date()
  // (hoy del navegador). NO se hace en SSR.
  return groupByDay(list, (m) => m.sent_at);
}, [messages]);
```

El separador de día es una píldora centrada y atenuada ("Hoy", "Ayer", "12 may 2026"). Reusa `groupByDay` del timeline de crm (si se promovió a `lib/utils/date.ts`) o lo replica.

> **El day-grouping NO cambia con el rediseño**: `messages` ahora proviene del listener Firestore (`useThreadMessages`), pero sigue siendo el mismo `Record<string, MessageItem>` (shape idéntico, snake_case). La agrupación por día y la hora de cada burbuja se computan **client-only** sobre `sent_at` (timestamp del mensaje, campo del doc) — el orden de llegada del listener es por `created_at`, pero el render agrupa/ordena por `sent_at` igual que antes (la lección TZ se mantiene intacta).

### `MessageBubble.tsx` (memoizada)

```tsx
export const MessageBubble = React.memo(function MessageBubble({
  message,
  canRetry,
  onRetry,
}: {
  message: MessageItem;
  canRetry: boolean; // outbound fallido + soy el assignee + MESSAGES_SEND
  onRetry: (m: MessageItem) => void;
}) {
  const sender = SENDER_TYPE_META[message.sender_type];
  // - sender_type=contact (inbound): burbuja IZQUIERDA, fondo neutral.
  // - sender_type=advisor (outbound): burbuja DERECHA, fondo primary tint, + MessageStatusTicks.
  // - sender_type=bot: derecha (no aplica en MVP).
  // - sender_type=system (content_type=system_notification): CENTRADA, atenuada, sin burbuja
  //   (ej. "— Conversación tomada por Ana —", "— Conversación cerrada —").
  // content_type=text → render del content. Otros content_type (image/audio/…) → placeholder
  // "📎 Adjunto (no disponible aún)" + attachment_type (F4 cablea el render real).
  // hora local de sent_at (formatTime CLIENT-ONLY), NO toISOString para render.
  return (/* … Fluent, tokens, sin brandPalette.accent … */);
});
```

> **`MessageBubble` memoizada + estado por id** (regla vercel-react): el hilo recibe updates **en vivo del listener Firestore** (`onSnapshot`); `React.memo` + el estado indexado por id (las burbujas que no cambiaron conservan su referencia entre snapshots) evita re-renderizar todo el hilo. Solo la burbuja nueva (inbound/outbound recién llegado) o la que cambió de `external_status` (sent→delivered→read→failed, escrito al doc por el backend) se re-renderiza. `onRetry` se pasa como callback estable.

> **Burbujas de sistema** (`sender_type=system`, `content_type=system_notification`): los eventos de handoff (tomar/liberar/cerrar/reabrir) pueden materializarse como mensajes de sistema en el hilo (centrados, atenuados) — confirmar con backend.md si el backend inserta un `Message(sender_type=system)` por handoff o si solo emite a la timeline de crm. Si el backend NO inserta mensajes de sistema por handoff, el hilo se entera del cambio por el `assignment_history` del detail (popover), no por una burbuja. Anotar en deviations.

### `MessageStatusTicks.tsx` (estado del mensaje outbound + reintento)

El "tick" estilo WhatsApp para mensajes **outbound** (no aplica a inbound). Deriva el estado del mensaje:

```ts
// Prioridad: failed > read > delivered > sent > pending (optimista).
function deriveStatus(m: MessageItem): MessageExternalStatus | "pending" {
  if (m.failed_at || m.external_status === "failed") return "failed";
  if (m.read_at || m.external_status === "read") return "read";
  if (m.delivered_at || m.external_status === "delivered") return "delivered";
  if (m.external_id || m.external_status === "sent") return "sent";
  return "pending"; // optimista: enviado al backend, sin confirmación de Meta aún
}
```

- **pending** 🕓 "Enviando…" (gris) — estado optimista entre el submit y el 200 del backend.
- **sent** ✓ "Enviado" (gris).
- **delivered** ✓✓ "Entregado" (gris).
- **read** ✓✓ "Leído" (azul, `tokens.colorPaletteBlueForeground2`).
- **failed** ⚠ "Falló el envío" (rojo) + botón **"Reintentar"** (gated `canRetry`) → `onRetry(m)` → re-`sendMessage(conversationId, { content: m.content })`. El mensaje fallido queda en el hilo (audit inmutable); el reintento crea un mensaje nuevo. Si `failure_reason` viene, mostrarlo en un tooltip ("Número no válido", "Fuera de la ventana de 24h", etc.).

> **El estado `read` (✓✓ azul) y `delivered` llegan por el status callback de Meta** (webhook `statuses[]`, spec §5 paso 5) → el backend actualiza el **doc Firestore** del mensaje (`delivered_at`/`read_at`/`external_status`) vía Admin SDK → el **listener `onSnapshot`** del hilo trae el cambio **en vivo** (no hay polling de ~10 s) → la burbuja se re-renderiza con el tick actualizado. Latencia ms–seg (proyección eventual Postgres→Firestore + push del listener), no el ciclo de ~10 s del polling previo — pero sigue siendo eventual (depende de cuándo Meta envía el callback), no instantáneo en el sentido de "garantizado al toque".

### Composer.tsx (enviar outbound)

Gated por `MESSAGES_SEND` **y** por ser el assignee (`detail.assignee_type === "advisor" && detail.assignee_user?.id === currentUser.id`, con `currentUser` de `useAuth()`) **y** `detail.status === "open"`. Si no se cumple, el composer se reemplaza por un hint:

- No es el assignee → "Toma la conversación para responder." + botón "Tomar" (si tiene `CONVERSATIONS_TAKE`).
- Conversación cerrada → "Esta conversación está cerrada. Reábrela para responder." + botón "Reabrir" (si tiene `CONVERSATIONS_TAKE` — reopen usa ese permiso, spec §7).
- Sin `MESSAGES_SEND` → composer ausente (solo lectura).

Implementación:

```tsx
const [content, setContent] = useState("");
const [isPending, startTransition] = useTransition(); // useTransition para el envío (no bloquea UI)
const [sendError, setSendError] = useState<string | null>(null);

const handleSend = () => {
  const trimmed = content.trim();
  if (!trimmed) return;
  setSendError(null);
  startTransition(async () => {
    const result = await sendMessage(conversationId, { content: trimmed, content_type: "text" });
    if (!result.ok) {
      setSendError(result.error ?? "No se pudo enviar.");
      return; // pre-condición fallida (no-open, no-assignee, etc.) — NO limpia el textarea
    }
    // result.ok aunque Meta haya fallado: el MessageItem puede venir failed.
    setContent(""); // limpia el textarea (el mensaje ya está en el hilo, fallido o no)
    // NO hace falta refetch del hilo: el backend escribió el doc Firestore y el listener
    // onSnapshot lo trae en vivo (status pending → sent/failed según el resultado de Meta).
    onMutated(); // refresca la LISTA del inbox (preview/last_message_at — sigue por polling Postgres)
  });
};
```

- **`useTransition`** para que el envío no congele la UI (el botón muestra spinner via `isPending`; el resto del hilo sigue interactivo). Regla vercel-react.
- **Enter para enviar / Shift+Enter para nueva línea** (textarea con `onKeyDown`). Botón "Enviar" deshabilitado si `!content.trim() || isPending`.
- **Optimismo opcional** (mejora): insertar una burbuja `pending` localmente antes del 200 y reconciliarla con el `MessageItem` real — MVP puede omitirlo: el **listener Firestore** trae el doc real (status `pending` que escribe el backend) casi al instante, sin esperar el 200 del action. Documentar como TODO si se omite.
- **Pausa del polling de la LISTA mientras se escribe** (menos crítico tras el rediseño): el textarea ya **no** lo afecta el hilo (el listener Firestore no resetea ni toca el composer — solo el listado se poléa). Aun así, `InboxShell` puede pausar el polling de la lista al perder foco (`visibilitychange`) para ahorrar requests; el listener Firestore se mantiene (o se puede pausar en background como mejora). `InboxShell` expone `setPollingPaused` para la lista.

### Controles de handoff (`HandoffControls.tsx`)

Botonera en el `ThreadHeader`, gated por permisos finos. Cada acción hace **refetch local** (usa el `ConversationDetail` que devuelve la action) **y** `router.refresh()` (lección crm F3: la conversación pinta datos denormalizados — assignee badge, status, unread — que un cache RSC stale dejaría desactualizados):

- **"Tomar"** (gated `CONVERSATIONS_TAKE`; visible si no soy el assignee o está unassigned/bot): `takeConversation(id)` → assignee=actor + reset unread + emite `CONVERSATION_TAKEN` a crm. Tras el retorno, `setDetail(result.data.data)` + `onMutated()` + `router.refresh()`.
- **"Liberar"** (gated `CONVERSATIONS_RELEASE`; visible si soy el assignee): abre un popover con `to_assignee_type` (en MVP: "Devolver a sin asignar" → `unassigned`; "Pasar al bot" → `bot`, no aplica en MVP) + `reason?` → `releaseConversation(id, { to_assignee_type, reason })` → emite `CONVERSATION_RELEASED`.
- **"Cerrar"** (gated `CONVERSATIONS_CLOSE`; visible si está open): `closeConversation(id)` → status=closed + cierra el log vigente. `ConfirmDialog`: "¿Cerrar esta conversación? Podrás reabrirla luego."
- **"Reabrir"** (gated `CONVERSATIONS_TAKE`; visible si está closed): `reopenConversation(id)` → valida que no haya otra open para (person, channel_account) (`CONVERSATION_ALREADY_OPEN` 409 → `MessageBar`). status=open.

> **Todas las acciones de handoff hacen `setDetail(result.data.data)` + `router.refresh()`** (lección crm F3 — el badge "Asignado a X" / "Sin asignar" del header y el estado "Abierta"/"Cerrada" son denormalizados; el refetch local los actualiza al instante, el `router.refresh()` re-pinta cualquier RSC stale). El `onMutated()` refresca la lista del inbox (la conversación cambia de assignee/status → puede salir/entrar de un filtro). Errores de dominio (`INVALID_ASSIGNEE`, `CONVERSATION_NOT_OPEN`, `CONVERSATION_ALREADY_OPEN`, `NOT_CONVERSATION_ASSIGNEE`) en `MessageBar`, en español.

### Polling de la lista

> **Tras el rediseño 2026-06-03 el polling cubre SOLO el LISTADO** (left pane). El **hilo** (right pane) es **real-time vía Firestore `onSnapshot`** (ver [Lectura real-time del hilo](#lectura-real-time-del-hilo-firestore)) — no se poléa. El polling del listado sigue el default de la spec §1 (polling, NO SSE/WebSocket para la lista — Cloud Run con `min-instances 0` + cpu-throttling no los favorece). Opción futura: el listado también live vía la colección `conversations` de Firestore (mismo mecanismo del hilo); por ahora la lista es polling Postgres.

Implementación en `InboxShell` (solo la lista; el `ConversationThread` se actualiza por su listener Firestore, no por este intervalo):

```ts
// Intervalo de polling de la LISTA. ~10s es un balance entre frescura y carga (ajustable).
const POLL_INTERVAL_MS = 10_000;

useEffect(() => {
  if (pollingPaused) return; // pausado: pestaña sin foco, etc.
  const id = setInterval(() => {
    // Refetch SILENCIOSO de la LISTA: no muestra spinner, no descarta scroll, merge por id.
    refetchList({ silent: true }); // SOLO la lista del inbox — el hilo va por Firestore listener
  }, POLL_INTERVAL_MS);
  return () => clearInterval(id);
}, [pollingPaused, refetchList]);

// Pausar cuando la pestaña pierde foco (no pollear la lista en background — ahorra requests).
useEffect(() => {
  const onVisibility = () => setPollingPaused(document.hidden);
  document.addEventListener("visibilitychange", onVisibility);
  return () => document.removeEventListener("visibilitychange", onVisibility);
}, []);
```

> **Refetch silencioso = sin flash** (lección crm F5: refetch silencioso sin parpadeo): el polling de la lista NO setea `loading=true` (que mostraría skeletons); hace el fetch en segundo plano y reemplaza el estado **solo si cambió** (merge por id que conserva referencias). El usuario no ve el inbox "saltar" cada 10 s — solo aparecen conversaciones nuevas suavemente. El primer load (no-polling) SÍ muestra skeletons. (Los mensajes nuevos del **hilo** aparecen aún más suavemente — por el listener Firestore, no por este ciclo.)

> **El polling de la lista pausa cuando**: (1) la pestaña pierde foco (`document.hidden` → no gastar requests en background). (El composer con texto sin enviar ya **no** obliga a pausar el hilo — el listener Firestore no toca el textarea; ver [Composer](#composertsx-enviar-outbound).) Documentar estas reglas; el detalle de UX vive en [`ui.md`](./ui.md). El **listener Firestore del hilo** se puede pausar/cerrar en background como mejora (desuscribir al ocultar la pestaña), pero el MVP puede mantenerlo abierto (Firestore optimiza listeners ociosos).

> **`new Date()` / relojes en el polling = client-only**: el cálculo de "hace X min" (hora relativa del `last_message_at` en la lista) y "Hoy"/"Ayer" (separadores del hilo) usan `new Date()` (hoy del navegador) → **client-only** (lección TZ recurrente — SSR en UTC desfasa el día en TZ negativas). El `InboxShell`/`ConversationThread` son `"use client"`; estos cálculos NUNCA se hacen en SSR. Para evitar mismatch de hidratación con un "reloj" que cambia, el primer render del relativo puede usar `useState(null) + useEffect` (renderiza la hora absoluta o un placeholder en SSR, el relativo tras montar) — mismo patrón que el timeline de crm.

## Reglas de performance (vercel-react-best-practices)

| Regla | Aplicación en conversations |
|---|---|
| **Evitar waterfalls de datos** | El RSC de bandeja/mis-conversaciones hace `Promise.all([listConversations, listActiveChannelAccounts])` (paralelo, no secuencial). El `ConversationThread` carga el `detail` por `getConversation`; los **mensajes** llegan por el listener Firestore (no por un fetch encadenado). El `getRealtimeToken` se mintea una vez al montar el inbox (en paralelo a la carga de la lista, no por conversación). |
| **Memoizar lo que se re-renderiza con updates en vivo** | `ConversationListItemRow` (polling de la lista) y `MessageBubble` (snapshots del listener Firestore) son `React.memo`. El estado indexado por id conserva referencias → solo lo que cambió se re-renderiza. `onSelect`/`onRetry`/`onMutated` son `useCallback` estables. |
| **Defer reads (cargar el hilo solo al seleccionar)** | El hilo NO se prefetcha en el RSC para todas las conversaciones — solo se abre el listener Firestore de la conversación seleccionada (`?c=`) y se carga su `detail`. El RSC solo prefetcha la **lista** (página inicial) + los canales. El listener se desuscribe al cambiar de conversación (cleanup del `useEffect` en `useThreadMessages`). |
| **Un solo sign-in de Firebase por sesión** | `getRealtimeDb` cachea la promesa de `signInWithCustomToken` (singleton) → no re-autentica por conversación. Un único `initializeApp` (`getApps()` guard). |
| **`useTableQuery` con `defaultPageSize` = `limit` del prefetch** | El RSC prefetcha `limit: 30` (inbox) / `limit: 50` (canales) → el `useTableQuery`/fetch de la lista usa `defaultPageSize: 30`/`50` (lección desync footer de crm: si difieren, el footer desincroniza + flash). |
| **No definir componentes inline** | `ConversationListItemRow`/`MessageBubble`/`MessageDayGroup`/etc. se definen a nivel de módulo (no dentro del render del padre) — sino se re-crean en cada render y rompen la memoización. |
| **`useTransition` para el envío** | El composer envía con `startTransition` → no congela el hilo; el botón muestra `isPending`. |
| **Polling de la lista silencioso + pausable; listener del hilo desuscribible** | El polling de la lista no muestra spinner (refetch silencioso) y pausa en background (`visibilitychange`). El listener Firestore del hilo se desuscribe al cambiar de conversación/desmontar (y opcionalmente en background) — minimiza re-renders y conexiones inútiles. |

## Lección TZ (recap, crítica en este módulo)

> Cualquier reloj/`now` del cliente que afecte el render = **client-only** (lección TZ recurrente de staff/crm; SSR en UTC desfasa el día en TZ negativas como Lima `-05:00`).

- **Separadores "Hoy"/"Ayer"/fecha del hilo** (`MessageDayGroup`): `new Date()` (hoy del navegador), computado en `"use client"`, NUNCA en SSR.
- **Hora relativa del inbox** ("hace 5 min", `last_message_at`): client-only; para evitar mismatch de hidratación, `useState(null) + useEffect` (render absoluto/placeholder en SSR, relativo tras montar).
- **Hora local de cada burbuja** (`sent_at` → "14:32"): formatear en **local** del navegador, NUNCA con `toISOString()` (que muestra UTC). Usar `lib/utils/date.ts` (`formatTime`/`formatDate`).
- **El composer no compone fechas** (a diferencia del `scheduled_for` del timeline de crm) — el `sent_at` lo pone el backend. No hay `datetime-local` en este módulo.

## Manejo de estados de mensaje + reintento de outbound

Resumen del ciclo de vida de un mensaje outbound (visto desde el front):

1. **Asesor escribe + Enviar** → `sendMessage(id, { content, content_type: "text" })` con `useTransition`. (Optimismo casi innecesario: el backend escribe el doc Firestore con status `pending` y el **listener** lo trae casi al instante — el asesor ve la burbuja aparecer sin esperar el 200.)
2. **Backend persiste el Message** (escribe outbox + doc Firestore vía Admin SDK, direction=outbound, sender_type=advisor) + llama Meta Graph API (spec §5 / brief §2 outbound). Devuelve **200** con el `MessageItem`; **el doc Firestore se actualiza** con el resultado:
   - **Éxito** → `external_id` (wamid), `external_status="sent"`, `sent_at` escritos al doc → el listener actualiza la burbuja a ✓ "Enviado".
   - **Falla de Meta** → `failed_at`, `failure_reason`, `external_status="failed"` escritos al doc. **El endpoint igual devuelve 200** (spec §1.5). La burbuja (vía listener) muestra ⚠ "Falló el envío" + **Reintentar**.
3. **Status callbacks de Meta** (webhook `statuses[]`, asíncronos) → el backend actualiza el **doc Firestore** del mensaje (`delivered_at`/`read_at`/`external_status`) vía Admin SDK. El **listener `onSnapshot`** del hilo trae el cambio **en vivo** → la burbuja pasa a ✓✓ "Entregado" → ✓✓ azul "Leído". Latencia ms–seg (ya no el ciclo de ~10 s del polling previo); sigue siendo eventual (depende de cuándo Meta envía el callback).
4. **Reintento** (mensaje fallido) → botón "Reintentar" → re-`sendMessage` con el mismo `content`. Crea un **nuevo** Message con un `mid` nuevo (uuid; el fallido queda como audit inmutable — el doc Firestore se escribe con `set(doc_id=mid)` create-if-absent, sin borrado ni edición destructiva — brief §2 outbound paso 4). El nuevo mensaje aparece por el listener. Gated por `MESSAGES_SEND` + ser el assignee + conversación open.

> **Pre-condiciones de envío** (el backend rechaza con throw, NO 200): conversación cerrada (`CONVERSATION_NOT_OPEN` 400), no soy el assignee (`NOT_CONVERSATION_ASSIGNEE` 403), tipo no soportado (`UNSUPPORTED_CONTENT_TYPE` 400), no existe (`CONVERSATION_NOT_FOUND` 404). El front previene la mayoría gateando el composer (solo visible si open + soy assignee + `MESSAGES_SEND`), pero muestra el error en `MessageBar` si la pre-condición cambió entre el render y el submit (defensa — ej. otro asesor la tomó, o se cerró).

> **El `detail` del hilo (estado/assignee que gatea el composer) NO se poléa tras el rediseño** (el polling cubre solo la lista; el listener Firestore cubre los mensajes). Si **otro** asesor toma/cierra la conversación abierta mientras la tengo en pantalla, mi `detail` queda momentáneamente stale (el badge/gating del composer no se actualiza solo). Mitigación: (a) el backend rechaza el envío con `NOT_CONVERSATION_ASSIGNEE`/`CONVERSATION_NOT_OPEN` → el front muestra el error en `MessageBar` y puede recargar el `detail` (`getConversation`) en ese momento; (b) la **lista** (polleada) refleja el cambio de assignee/status y, si se mantiene el `detail` espejado con la fila seleccionada, se refresca. Opción futura: reflejar el `conversations/{cid}` doc de Firestore (que el backend mantiene vía `conversation_upsert`) con un segundo listener para el header en vivo. **Anotar en deviations** — el MVP acepta el stale del `detail` ajeno (el composer falla de forma controlada).

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| Inbox 2-paneles compartido (`InboxShell` con `scope`) entre Bandeja y Mi bandeja | Misma UI; solo cambia la action de listado (`listConversations` vs `listMyConversations`) y los presets de filtro. Evita duplicar la pieza más compleja del módulo. Vive en `conversaciones/_components/` (un nivel arriba de las dos rutas). |
| Conversación seleccionada en `?c=` (URL state, nuqs) — NO sub-ruta | Un solo shell sirve a la lista + el hilo; deep-linkable (`/bandeja?c=abc&status=open`); sobrevive refresh; sin `layout.tsx` extra. Mismo criterio que `?tab=` del detalle de Person en crm. |
| **Hilo = real-time Firestore; LISTA = polling (NO SSE/WebSocket)** | **Redesign 2026-06-03** (brief §0/§4): el **stream de mensajes vive en Firestore** (CQRS read-model) → el hilo se lee en vivo por `onSnapshot` READ-ONLY (mensajes nuevos + cambios de `external_status` sin polling ni latencia de ~10 s). La **lista** sigue por polling Postgres ~10 s (Cloud Run con `min-instances 0` no favorece conexiones persistentes para el listado SQL; opción futura: lista live vía colección `conversations`). SSE/WebSocket ya no hace falta para el hilo. |
| Cliente Firebase READ-ONLY + Custom Token + Security Rules | **Brief §3**: el browser solo LEE Firestore (listeners), autorizado por un Custom Token que mintea el backend (JWT/RBAC = fuente de verdad) + Security Rules que espejan el RBAC (`allowed_reader_ids`, `can_read_all`). TODO write (enviar/tomar/liberar/cerrar/reabrir) sigue browser → Next server action → backend → Meta + Firestore (Admin SDK). Preserva el principio del template (browser no muta el backend; JWT server-side). |
| `getRealtimeToken()` una vez por sesión de inbox; sign-in idempotente | El custom token se mintea al montar el inbox (server action con el JWT); `signInWithCustomToken` produce un ID token con auto-refresh → no se re-pide por conversación. Si falla, el hilo cae a fallback `listMessages` (server-side, sin real-time) — el inbox nunca queda inutilizable. |
| Refetch silencioso (lista) + listener en vivo (hilo), sin spinner | Lección crm F5 (refetch silencioso sin parpadeo): la **lista** no "salta" cada 10 s (refetch silencioso, merge por id); el **hilo** recibe updates en vivo del listener Firestore (solo lo nuevo/cambiado). `React.memo` en filas/burbujas conserva referencias. |
| **`defaultSort`/`isSortable`/`searchFields` SOLO sobre columnas reales de `ALLOWED_FIELDS`** | **Lección hotfix `cd10c78` de staff**: ordenar/filtrar server-side por un denormalizado (`person.full_name`, `assignee_user.full_name`, `last_message_preview`) devuelve 400. Inbox `defaultSort = last_message_at` (columna real whitelistada); hilo `sent_at asc`. El `defaultSort` del client DEBE coincidir con el `sorting` del prefetch RSC (sino flash + refetch). |
| Filtros del inbox (estado/canal/asignación) = columnas REALES (no virtuales) | A diferencia de crm (donde `lead_status_id`/`advisor_user_id` eran campos virtuales → EXISTS), aquí `status`/`channel_account_id`/`assignee_user_id`/`assignee_type` son columnas directas de `conversation` en `ALLOWED_FIELDS` → `FilterCondition` directo, sin traducción. |
| Búsqueda por nombre/identificador = **client-side** | `person.full_name` y los identificadores son denormalizados (no whitelistados). Filtra sobre la página visible; no genera `FilterCondition` server-side. |
| **`sendMessage` NO lanza ante fallo de Meta** | Spec §1.5: el endpoint devuelve 200 con el message en estado `failed`. El front inspecciona `external_status==="failed"` → muestra ⚠ + Reintentar. Solo lanza ante pre-condiciones (no-open, no-assignee, etc.). |
| Outbound fallido → Reintentar crea un mensaje NUEVO | `Message` es audit inmutable (sin SoftDelete); el fallido queda en el hilo. Reintentar = nuevo `POST /messages` con el mismo content. |
| Estado de mensaje derivado (failed>read>delivered>sent>pending) + ticks WhatsApp | El status llega por callback de Meta (asíncrono) → el backend lo escribe al doc Firestore → el **listener `onSnapshot`** lo trae en vivo (latencia ms–seg, ya no el ciclo de ~10 s del polling). `pending` 🕓 lo escribe el backend al doc antes de llamar a Meta (el asesor lo ve casi al instante por el listener). |
| Handoff (take/release/close/reopen) → `setDetail(result.data)` + `router.refresh()` | **Lección crm F3**: el badge "Asignado a X" / estado "Abierta/Cerrada" son denormalizados; el refetch local los actualiza al instante, `router.refresh()` re-pinta RSC stale, `onMutated()` refresca la lista del inbox. |
| Composer gated `MESSAGES_SEND` + ser el assignee + open | Espeja la autorización del backend (`NOT_CONVERSATION_ASSIGNEE` 403). Si no, hint "Toma la conversación para responder" + botón Tomar. |
| **Burbujas + filas memoizadas (`React.memo`) + estado por id** | El listener Firestore entrega snapshots del hilo y el polling re-fetcha la lista; sin memo, re-render total + flash. Estado indexado por id conserva referencias → solo lo nuevo/cambiado se re-renderiza (reglas vercel-react). |
| **Agrupación "Hoy"/"Ayer" + hora relativa = client-only** | `new Date()` que afecta render = client-only (lección TZ; SSR en UTC desfasa el día en TZ Lima `-05:00`). El inbox es `"use client"`; relativos con `useState(null)+useEffect` para evitar mismatch de hidratación. |
| Hora de burbuja en LOCAL, nunca `toISOString()` | `toISOString()` muestra UTC → desfase visible. Formatear con `lib/utils/date.ts` en local del navegador. |
| El secreto del canal NUNCA en el front | Spec §1.2 / ADR-010: las credenciales viven en GCP Secret Manager, se resuelven server-only. El drawer captura solo `secret_name` (nombre) + muestra "Configurado/Sin configurar". |
| `ChannelType` reusado de crm; demás enums conversations-owned | Spec §3: single source of truth. Importar `ChannelType` de `crm.types`; NO redefinir los 8 valores. |
| Adjuntos modelados pero render = placeholder (F4 diferida) | Spec §1.4: `MessageAttachment` en el contrato (tipos TS); el processing/render real de media es F4. Hoy `content_type=text` + placeholder para otros tipos. |
| Tags por-conversación (`conversations:thread:{id}`) + cross-tag con `conversations:list` | El tag cubre el `ConversationDetail` (header/handoff) + el fallback `listMessages` — **NO** el stream de mensajes (ese vive en Firestore, se actualiza por el listener). Taggear por id evita invalidar el detail de todas. Una mutación (send/handoff) cruza tags (detail + lista por los denormalizados preview/unread/assignee); el mensaje nuevo aparece por el listener Firestore, no por la revalidación. |
| `revalidateTag(TAG, "max")` (2º arg) | Next 16 exige el 2º argumento; omitirlo es error (lección del template). Todos los actions lo pasan. |
| No emite a la timeline de crm desde el front | El backend emite `CONVERSATION_TAKEN`/`RELEASED` server-side (en take/release). El front NO escribe en crm; solo dispara las acciones. (No `MESSAGE_SENT` por-mensaje — spec §1.6.) |
| Sin bulk actions, sin notas internas, sin plantillas de respuesta | Postergados al MVP+1 (igual que catalog/clinic/staff/crm). |

## Checklist de implementación (mapeado a fases F0–F4)

> Las fases espejan el plan de [`README.md`](./README.md#fases) / [`backend.md`](./backend.md#checklist-de-implementación) y [`ui.md`](./ui.md) (spec §12). Cada checkbox es lado frontend. **F4 (adjuntos/media) está DIFERIDA** — fuera del MVP inicial.

### F0 — Prep (andamiaje compartido, sin migración)

- [ ] Extender `src/lib/constants/endpoints.ts` con el bloque `CONVERSATIONS` (`CHANNEL_ACCOUNTS` con list/create/get/update/delete/active, `CONVERSATIONS_API` con list/get/messages/take/release/close/reopen/mark-read, `ME_CONVERSATIONS`). Verbos: `PUT` para channel-account update; acciones `POST`; `/active` cruda. (Los webhooks NO van al front — N/A.)
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `conversations` ("Conversaciones" → Bandeja `CONVERSATIONS_READ`, Mi bandeja `MY_CONVERSATIONS_READ`, Canales `CHANNEL_ACCOUNTS_READ`; grupo gated `MENU-CONVERSATIONS`).
- [ ] Registrar íconos `ChatRegular`/`MailInboxRegular`/`PersonMailRegular`/`PlugConnectedRegular` en el `iconMap` del `Sidebar.tsx` (con fallbacks verificados).
- [ ] Crear `src/types/conversations.types.ts` (TODAS las interfaces + enums conversations-owned; **reusa** `ChannelType` de crm.types + `UserAuditInfo` de audit.types).
- [ ] Crear `src/lib/constants/conversations.ts` (`MESSAGE_STATUS_META`, `SENDER_TYPE_META`, `ASSIGNEE_TYPE_META`, `CONVERSATION_STATUS_META`, `INBOX_FILTER_PRESETS`; re-export `CHANNEL_TYPE_META` de crm).
- [ ] **(redesign)** Extender `endpoints.ts` con `REALTIME.TOKEN` (`POST /conversations/realtime/token`). Agregar las envs `NEXT_PUBLIC_FIREBASE_*` (apiKey/authDomain/projectId/appId/databaseId — config pública, NO secretos) a `.env.example` + Vercel (qa/prod). (El cableado del cliente Firebase + el listener = F2.)
- [ ] **Permisos test (F0)**: como user con `MENU-CONVERSATIONS` (rol ASESOR), el grupo "Conversaciones" aparece con Bandeja + Mi bandeja (NO Canales — sin `CHANNEL_ACCOUNTS_*`). Como ADMIN, aparece también Canales. Sin `MENU-CONVERSATIONS` (DOCTOR), el grupo no aparece. (Los 12 permisos + roles ya están en `seed.py` — ver [`../_seed-and-roles.md`](../_seed-and-roles.md), backend F0.)

### F1 — ChannelAccount (CRUD de canales)

- [ ] Crear `src/lib/schemas/channel-account.schema.ts` (channel_type enum reuse, external_identifier, secret_name?, webhook_verify_token?, phone_number_id?; el secreto NUNCA en claro).
- [ ] Crear `src/actions/channel-account.actions.ts` (list/active/get/create/update/delete; tag `conversations:channel-accounts`).
- [ ] Crear `src/app/(main)/conversaciones/canales/page.tsx` (`metadata.title = "Canales"`, prefetch `defaultSort = created_on`, `requirePermission("CHANNEL_ACCOUNTS_READ")`) + `_components/ChannelAccountsClient.tsx` (tabla: name/channel_type badge/external_identifier/credentials_configured/active; búsqueda client-side) + `ChannelAccountDrawer.tsx` (create/edit; secreto solo por `secret_name`; webhook_verify_token editable; estado "Configurado/Sin configurar").
- [ ] **Smoke test (F1)**: `/conversaciones/canales` → "Nuevo canal" → WhatsApp + nombre + número + `secret_name` → crear → aparece en la tabla con badge WhatsApp + "Sin configurar" (si no hay secreto) → editar (cambiar `webhook_verify_token`, activar) → soft-delete con confirm.
- [ ] **Error test (F1)**: crear un canal con el mismo `channel_type`+`external_identifier` de otro → `409 CHANNEL_ACCOUNT_EXTERNAL_TAKEN` en `MessageBar` sin cerrar el drawer.
- [ ] **Permisos test (F1)**: sin `CHANNEL_ACCOUNTS_CREATE` no aparece "Nuevo canal"; sin `_UPDATE` no aparece Editar; sin `_DELETE` no aparece Eliminar; sin `CHANNEL_ACCOUNTS_READ` el RSC redirige. El ASESOR NO ve esta página.

### F2 — Inbox (recibir + ver, read-only) + hilo real-time Firestore

- [ ] Crear `src/actions/conversation.actions.ts` (lecturas: `listConversations`/`listMyConversations`/`getConversation`/`listMessages` **fallback**; tags `conversations:list`/`conversations:thread:{id}`). (Las mutaciones de envío/handoff = F3.)
- [ ] **(redesign)** `npm i firebase`. Crear `src/lib/firebase/client.ts` (init Firebase Web SDK con `NEXT_PUBLIC_FIREBASE_*` + `signInWithCustomToken` idempotente + `getFirestore(app, databaseId)`; **solo lectura**) + `src/actions/realtime.actions.ts` (`getRealtimeToken()` → `POST /conversations/realtime/token`).
- [ ] Crear `src/app/(main)/conversaciones/bandeja/page.tsx` (`metadata.title = "Bandeja"`, `requirePermission("CONVERSATIONS_READ")`, prefetch lista `defaultSort = last_message_at desc` + canales activos; deep-link `?status=`/`?channel_account_id=`/`?assignee_user_id=`/`?unassigned=`/`?c=` → `FilterCondition` columnas reales + selección).
- [ ] Crear `src/app/(main)/conversaciones/mis-conversaciones/page.tsx` (`metadata.title = "Mi bandeja"`, `requirePermission("MY_CONVERSATIONS_READ")`, `listMyConversations`, `scope="mine"`).
- [ ] Crear `conversaciones/_components/InboxShell.tsx` (2-paneles, `scope`, URL state `?c=`+filtros con nuqs, **polling pausable SOLO de la lista**, mintea `getRealtimeToken` al montar y lo pasa al hilo) + `ConversationList.tsx` (filtros preset + canal + búsqueda client-side) + `ConversationListItemRow.tsx` (memoizada) + `ConversationThread.tsx` (carga `detail` por action; **mensajes en vivo vía `useThreadMessages`**) + `useThreadMessages.ts` (**listener Firestore `onSnapshot` READ-ONLY** + fallback `listMessages`) + `ThreadHeader.tsx` (read-only: contacto/canal/estado/AssigneeBadge) + `MessageDayGroup.tsx` (client-only) + `MessageBubble.tsx` (memoizada: in/out/system) + `MessageStatusTicks.tsx` (ticks de estado, sin reintento aún).
- [ ] **Smoke test (F2)**: con un canal configurado, enviar un WhatsApp real al número → el webhook persiste (Postgres outbox + relay a Firestore) → la conversación aparece en `/conversaciones/bandeja` (auto-asignada al dueño del lead o "Sin asignar") con badge sin-leer → seleccionar (`?c=` se setea, se abre el listener Firestore) → el hilo muestra la burbuja inbound (izquierda) con hora local → enviar otro WhatsApp real → aparece **en vivo** por el listener (sin recargar, sin flash, sin esperar ~10 s). `/conversaciones/mis-conversaciones` muestra solo las del asesor logueado.
- [ ] **Real-time test (F2)**: dejar el hilo abierto → un nuevo inbound aparece **al instante** (push del `onSnapshot`, no ~10 s) sin recargar ni parpadear. Verificar en Network/DevTools que la conexión a Firestore está activa y que el cliente NO hace writes a Firestore. La **lista** sigue refrescando por polling (~10 s); al cambiar de pestaña, el polling de la lista pausa.
- [ ] **(redesign) Auth/Rules test (F2)**: el `getRealtimeToken` devuelve un custom token; un asesor sin `CONVERSATIONS_READ` global solo ve por el listener sus conversaciones asignadas (`allowed_reader_ids` / `can_read_all=false`) — intentar leer una conversación ajena por Firestore da `permission-denied` (Security Rules). Con el token revocado/expirado o sin Firebase, el hilo cae a **fallback** `listMessages` (snapshot sin real-time) y el inbox sigue usable.
- [ ] **Filtro/deep-link test (F2)**: `/conversaciones/bandeja?status=open` filtra + chip; `?channel_account_id=X` combina; `?unassigned=true` muestra solo sin asignar; búsqueda por nombre/número filtra client-side la página visible; ✕ limpia. **NO ordenar por columna denormalizada** (no rompe a 400).
- [ ] **TZ test (F2)**: con el reloj cerca de medianoche en TZ Lima (`-05:00`), un mensaje recibido "hoy" aparece bajo "Hoy" (no "Ayer") en el hilo — confirma agrupación client-only.
- [ ] **Permisos test (F2)**: sin `CONVERSATIONS_READ` la Bandeja redirige; sin `MY_CONVERSATIONS_READ` Mi bandeja redirige. El `getRealtimeToken` exige `CONVERSATIONS_READ` **o** `MY_CONVERSATIONS_READ` (sin ninguno → 403 → el hilo no abre listener ni fallback). El fallback `listMessages` queda gated `MESSAGES_READ` como antes (lee Firestore vía Admin SDK server-side); el listener real-time queda acotado por las Security Rules (`allowed_reader_ids` / `can_read_all`).

### F3 — Handoff + outbound (completa el human-inbox MVP, sin migración)

- [ ] Crear `src/lib/schemas/message.schema.ts` (messageSend: content no-vacío + `.trim()` + content_type=text literal).
- [ ] Completar `src/actions/conversation.actions.ts` con las mutaciones: `sendMessage` (200 con message fallido = ok, NO throw), `takeConversation`/`releaseConversation`/`closeConversation`/`reopenConversation`/`markRead` (devuelven `ConversationDetail`; cross-tag `conversations:thread:{id}` + `conversations:list`).
- [ ] Implementar `Composer.tsx` (textarea + `useTransition` + Enter/Shift+Enter; gated `MESSAGES_SEND` + ser assignee + open; hint "Toma para responder" si no) + `HandoffControls.tsx` (Tomar/Liberar/Cerrar/Reabrir gated por permisos finos; `setDetail(result.data)` + `router.refresh()` + `onMutated()`) + `MessageStatusTicks.tsx` con **Reintentar** (outbound fallido).
- [ ] **Smoke test (F3)**: en una conversación open sin asignar → "Tomar" (gated `CONVERSATIONS_TAKE`) → assignee=yo + unread=0 + el header muestra "Asignado a {yo}" → escribir + Enviar → la burbuja outbound (derecha) aparece **en vivo por el listener Firestore** (status `pending` → ✓ "Enviado") → el listener actualiza a ✓✓ "Entregado"/"Leído" cuando el backend escribe el status callback de Meta al doc (en vivo, no ~10 s) → "Liberar" (devolver a sin asignar) → "Cerrar" → estado "Cerrada", composer reemplazado por "Reabrir" → "Reabrir" → vuelve a open. Verificar en crm que se emitió `CONVERSATION_TAKEN`/`CONVERSATION_RELEASED` en la timeline de la Person.
- [ ] **Outbound fallido test (F3)**: forzar un fallo de Meta (número inválido / secreto mal) → el doc Firestore del mensaje se actualiza a ⚠ "Falló el envío" (endpoint devuelve 200; el listener lo trae en vivo) → botón "Reintentar" → re-envía (nuevo `mid`/doc); el fallido queda en el hilo (audit inmutable). `failure_reason` en tooltip.
- [ ] **Error test (F3)**: enviar a una conversación que otro asesor tomó (no soy assignee) → `403 NOT_CONVERSATION_ASSIGNEE` en `MessageBar`; enviar a una cerrada → `400 CONVERSATION_NOT_OPEN`; reabrir cuando ya hay otra open para (person, canal) → `409 CONVERSATION_ALREADY_OPEN`. Todos en español.
- [ ] **Permisos test (F3)**: sin `MESSAGES_SEND` el composer no aparece (solo lectura); sin `CONVERSATIONS_TAKE` no aparece "Tomar"/"Reabrir"; sin `CONVERSATIONS_RELEASE` no aparece "Liberar"; sin `CONVERSATIONS_CLOSE` no aparece "Cerrar".

### F4 — Adjuntos/media (DIFERIDA, fuera del MVP)

- [ ] Cablear el render real de `MessageAttachment` en `MessageBubble` (imagen inline, audio player, descarga de documento, mapa de location) — hoy es un placeholder "📎 Adjunto (no disponible aún)".
- [ ] Extender `message.schema.ts`/`Composer` para enviar adjuntos (subida + `content_type` ≠ text).
- [ ] La decisión de storage (lazy proxy vs GCS) se re-confirma al llegar a F4 (spec §1.4). Fuera del MVP inicial.

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog**. Para `conversations` no hay deuda de traducción del template — todos los strings nuevos nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Canales", "Bandeja", "Mi bandeja").
- [ ] Todos los `label` de `NAV_ITEMS.conversations` en español ("Conversaciones", "Bandeja", "Mi bandeja", "Canales").
- [ ] Glosario UI (spec §11): **Conversación · Mensaje · Canal · Bandeja · Tomar · Liberar · Cerrar · Reabrir · Asignado a · Sin asignar · Sin leer · Entregado · Leído · Enviado · Falló el envío · Reintentar** — usados consistentemente en burbujas, badges, botones, empty states, confirm dialogs.
- [ ] Empty states/placeholders en español: "Selecciona una conversación", "No hay conversaciones", "No tienes conversaciones asignadas", "Contacto desconocido", "Toma la conversación para responder.", "Esta conversación está cerrada. Reábrela para responder.", "📎 Adjunto (no disponible aún)".
- [ ] Mensajes de error de dominio que vienen del backend ya en español (`CHANNEL_ACCOUNT_NOT_FOUND`, `CHANNEL_ACCOUNT_EXTERNAL_TAKEN`, `CHANNEL_CREDENTIALS_MISSING`, `CONVERSATION_NOT_FOUND`, `CONVERSATION_NOT_OPEN`, `CONVERSATION_ALREADY_OPEN`, `INVALID_ASSIGNEE`, `NOT_CONVERSATION_ASSIGNEE`, `MESSAGE_NOT_FOUND`, `UNSUPPORTED_CONTENT_TYPE`) — los `detail` se devuelven en español para mostrarse directo; el `code` queda en inglés (coordinar con [`backend.md`](./backend.md#códigos-de-error) / spec §9). `WEBHOOK_SIGNATURE_INVALID` es del router top-level (no lo ve el front).

## TODOs deliberados (postergados al MVP+1)

- [ ] **F4 — Adjuntos/media** (render + envío) — modelado en el contrato, processing diferido (spec §1.4 / §12).
- [ ] **Lista (left pane) también live vía Firestore** (colección `conversations`, mismo mecanismo del hilo) en vez de polling Postgres — opción del brief §4. El MVP deja la lista por polling; el hilo ya es real-time Firestore. (El SSE/WebSocket que se contemplaba para el hilo **ya no hace falta** — el listener Firestore lo cubre.)
- [ ] **Optimismo de envío** (burbuja `pending` local antes del 200) — casi innecesario tras el rediseño: el backend escribe el doc Firestore con status `pending` y el listener lo trae casi al instante. El optimismo local reconciliado queda como micro-mejora.
- [ ] **Pausar/cerrar el listener Firestore en background** (desuscribir al ocultar la pestaña, re-suscribir al volver) — micro-optimización de conexiones; el MVP puede mantenerlo abierto (Firestore optimiza listeners ociosos).
- [ ] **Reasignar a OTRO asesor** (no solo a sin-asignar/bot) en "Liberar" — requeriría un dropdown de asesores (reusar `/crm/advisors/active` si se expone) y `to_assignee_type='advisor'` + `to_assignee_user_id`. MVP libera a `unassigned`.
- [ ] **Vista responsive del inbox** (master-detail apilado en móvil) — el MVP asume desktop (2-paneles).
- [ ] **Plantillas de respuesta / respuestas rápidas / notas internas** — refinamientos de productividad del asesor.
- [ ] **Resolver el `bot_configuration_id`/`default_campaign_id`** (forward FKs) a entidades cuando existan bots #6 / marketing #8 (ADR-009). Hoy strings opacos.
- [ ] **Indicador "escribiendo…" / presencia** — requeriría SSE/WebSocket; fuera del MVP polling.
- [ ] **Marcar leído automático al abrir** vs botón explícito — confirmar el comportamiento deseado con UX (el MVP puede disparar `markRead` al seleccionar una conversación con `unread_count > 0`).
