/**
 * Single source of truth for backend paths consumed by `services/backend.client.ts`.
 */

const ADMIN = "/api/v1/admin";
const CATALOG = "/api/v1/catalog";
const CLINIC = "/api/v1/clinic";
const STAFF = "/api/v1/staff";
const CRM = "/api/v1/crm";
const CONVERSATIONS = "/api/v1/conversations";
const BOTS = "/api/v1/bots";

export const ENDPOINTS = {
  AUTH: {
    LOGIN: `${ADMIN}/auth/login`,
    REFRESH: `${ADMIN}/auth/refresh`,
    LOGOUT: `${ADMIN}/auth/logout`,
    ME: `${ADMIN}/auth/me`,
  },
  USERS: {
    LIST: `${ADMIN}/users/list`,
    CREATE: `${ADMIN}/users`,
    GET: (id: string) => `${ADMIN}/users/${id}`,
    UPDATE: (id: string) => `${ADMIN}/users/${id}`,
    CHANGE_PASSWORD: `${ADMIN}/users/me/change-password`,
  },
  ROLES: {
    LIST: `${ADMIN}/roles/list`,
    ACTIVE: `${ADMIN}/roles/active`,
    GET: (id: string) => `${ADMIN}/roles/${id}`,
    CREATE: `${ADMIN}/roles`,
    UPDATE: (id: string) => `${ADMIN}/roles/${id}`,
  },
  PERMISSIONS: {
    LIST: `${ADMIN}/permissions/list`,
    ACTIVE: `${ADMIN}/permissions/active`,
    GET: (id: string) => `${ADMIN}/permissions/${id}`,
    CREATE: `${ADMIN}/permissions`,
    UPDATE: (id: string) => `${ADMIN}/permissions/${id}`,
  },
  // ── Catalog module ───────────────────────────────────────
  VERTICALS: {
    LIST: `${CATALOG}/verticals/list`,
    ACTIVE: `${CATALOG}/verticals/active`,
    GET: (id: string) => `${CATALOG}/verticals/${id}`,
    CREATE: `${CATALOG}/verticals`,
    UPDATE: (id: string) => `${CATALOG}/verticals/${id}`,
    DELETE: (id: string) => `${CATALOG}/verticals/${id}`,
  },
  SERVICES: {
    LIST: `${CATALOG}/services/list`,
    ACTIVE: `${CATALOG}/services/active`,
    GET: (id: string) => `${CATALOG}/services/${id}`,
    CREATE: `${CATALOG}/services`,
    UPDATE: (id: string) => `${CATALOG}/services/${id}`,
    DELETE: (id: string) => `${CATALOG}/services/${id}`,
  },
  PRODUCTS: {
    LIST: `${CATALOG}/products/list`,
    ACTIVE: `${CATALOG}/products/active`,
    GET: (id: string) => `${CATALOG}/products/${id}`,
    CREATE: `${CATALOG}/products`,
    UPDATE: (id: string) => `${CATALOG}/products/${id}`,
    DELETE: (id: string) => `${CATALOG}/products/${id}`,
  },
  // ── Clinic module ────────────────────────────────────────
  BRANCHES: {
    LIST: `${CLINIC}/branches/list`,
    ACTIVE: `${CLINIC}/branches/active`,
    GET: (id: string) => `${CLINIC}/branches/${id}`,
    CREATE: `${CLINIC}/branches`,
    UPDATE: (id: string) => `${CLINIC}/branches/${id}`,
    DELETE: (id: string) => `${CLINIC}/branches/${id}`,
  },
  OFFICES: {
    LIST: `${CLINIC}/offices/list`,
    // ACTIVE accepts optional ?branch_id= & ?vertical_id= query params.
    ACTIVE: `${CLINIC}/offices/active`,
    GET: (id: string) => `${CLINIC}/offices/${id}`,
    CREATE: `${CLINIC}/offices`,
    UPDATE: (id: string) => `${CLINIC}/offices/${id}`,
    DELETE: (id: string) => `${CLINIC}/offices/${id}`,
    // Nested sub-resources (phases 3 & 4).
    OPERATING_HOURS: (id: string) => `${CLINIC}/offices/${id}/operating-hours`,
    CLOSURES: (id: string) => `${CLINIC}/offices/${id}/closures`,
    CLOSURE: (id: string, closureId: string) => `${CLINIC}/offices/${id}/closures/${closureId}`,
  },
  // ── Staff module ─────────────────────────────────────────
  DOCTORS: {
    LIST: `${STAFF}/doctors/list`,
    // ACTIVE accepts optional ?branch_id= & ?vertical_id= ; raw DoctorOption list.
    ACTIVE: `${STAFF}/doctors/active`,
    GET: (id: string) => `${STAFF}/doctors/${id}`,
    CREATE: `${STAFF}/doctors`, // NESTED user+doctor → 201
    UPDATE: (id: string) => `${STAFF}/doctors/${id}`, // PUT (not PATCH)
    DELETE: (id: string) => `${STAFF}/doctors/${id}`, // soft delete (does NOT touch the User)
    // Nested: availability of one doctor (admin) — phase 2.
    AVAILABILITY_LIST: (id: string) => `${STAFF}/doctors/${id}/availability`, // ?from=&to=
    AVAILABILITY_CREATE: (id: string) => `${STAFF}/doctors/${id}/availability`, // bulk
    AVAILABILITY_UPDATE: (id: string, blockId: string) =>
      `${STAFF}/doctors/${id}/availability/${blockId}`, // PUT
    AVAILABILITY_DELETE: (id: string, blockId: string) =>
      `${STAFF}/doctors/${id}/availability/${blockId}`,
  },
  // ── Self-service (the logged-in doctor) — phase 3 ────────
  ME: {
    DOCTOR_GET: `${STAFF}/me/doctor`,
    DOCTOR_UPDATE: `${STAFF}/me/doctor`, // PUT (only bio/photo/signature/slot)
    AVAILABILITY_LIST: `${STAFF}/me/availability`, // ?from=&to=
    AVAILABILITY_CREATE: `${STAFF}/me/availability`, // bulk
    AVAILABILITY_UPDATE: (blockId: string) => `${STAFF}/me/availability/${blockId}`, // PUT
    AVAILABILITY_DELETE: (blockId: string) => `${STAFF}/me/availability/${blockId}`,
  },
  // ── CRM module ───────────────────────────────────────────
  PERSONS: {
    LIST: `${CRM}/persons/list`,
    CREATE: `${CRM}/persons`,
    GET: (id: string) => `${CRM}/persons/${id}`,
    UPDATE: (id: string) => `${CRM}/persons/${id}`, // PUT (not PATCH)
    DELETE: (id: string) => `${CRM}/persons/${id}`, // soft delete
    ACTIVE: `${CRM}/persons/active`, // raw list — PersonOption[]
    SEARCH: `${CRM}/persons/search`, // ?q=&channel_type=&identifier= (lo usa el bot; raw list)
    // Nested: identificadores multicanal de UNA persona.
    IDENTIFIERS: (id: string) => `${CRM}/persons/${id}/identifiers`, // GET (list) / POST (create)
    IDENTIFIER: (id: string, identId: string) => `${CRM}/persons/${id}/identifiers/${identId}`, // PUT / DELETE
    // Nested: estado lead + transición + history + promote.
    LEAD_STATUS: (id: string) => `${CRM}/persons/${id}/lead-status`, // GET / POST (crear lead)
    LEAD_TRANSITION: (id: string) => `${CRM}/persons/${id}/lead-status/transition`, // POST
    LEAD_HISTORY: (id: string) => `${CRM}/persons/${id}/lead-status/history`, // GET
    PROMOTE: (id: string) => `${CRM}/persons/${id}/promote-to-customer`, // POST
    // Nested: estado cliente + transición + history.
    CUSTOMER_STATUS: (id: string) => `${CRM}/persons/${id}/customer-status`, // GET
    CUSTOMER_TRANSITION: (id: string) => `${CRM}/persons/${id}/customer-status/transition`, // POST
    CUSTOMER_HISTORY: (id: string) => `${CRM}/persons/${id}/customer-status/history`, // GET
    // Nested: asignación (owner).
    ASSIGNMENT: (id: string) => `${CRM}/persons/${id}/assignment`, // GET / PUT (manual / "asignarme")
    ASSIGNMENT_AUTO: (id: string) => `${CRM}/persons/${id}/assignment/auto`, // POST (round-robin)
    // Nested: timeline de actividad.
    ACTIVITIES_LIST: (id: string) => `${CRM}/persons/${id}/activities/list`, // POST (filtros en body)
    ACTIVITIES_CREATE: (id: string) => `${CRM}/persons/${id}/activities`, // POST
    ACTIVITY: (id: string, actId: string) => `${CRM}/persons/${id}/activities/${actId}`, // PUT / DELETE (active=false)
  },
  LEAD_STATUSES: {
    LIST: `${CRM}/lead-statuses/list`,
    CREATE: `${CRM}/lead-statuses`,
    GET: (id: string) => `${CRM}/lead-statuses/${id}`,
    UPDATE: (id: string) => `${CRM}/lead-statuses/${id}`, // PUT (not PATCH)
    DELETE: (id: string) => `${CRM}/lead-statuses/${id}`, // 409 LEAD_STATUS_IN_USE si referenciado
    ACTIVE: `${CRM}/lead-statuses/active`, // raw list — LeadStatusOption[]
    TRANSITIONS: (id: string) => `${CRM}/lead-statuses/${id}/transitions`, // GET (destinos) / PUT (reemplaza aristas)
  },
  CUSTOMER_STATUSES: {
    LIST: `${CRM}/customer-statuses/list`,
    CREATE: `${CRM}/customer-statuses`,
    GET: (id: string) => `${CRM}/customer-statuses/${id}`,
    UPDATE: (id: string) => `${CRM}/customer-statuses/${id}`, // PUT (not PATCH)
    DELETE: (id: string) => `${CRM}/customer-statuses/${id}`, // 409 CUSTOMER_STATUS_IN_USE
    ACTIVE: `${CRM}/customer-statuses/active`, // raw list — CustomerStatusOption[]
    TRANSITIONS: (id: string) => `${CRM}/customer-statuses/${id}/transitions`, // GET / PUT
  },
  ADVISORS: {
    // raw list — AdvisorOption[] (asesores; LEAD_ASSIGNMENTS_READ). crm-owned, NO admin/users.
    ACTIVE: `${CRM}/advisors/active`,
  },
  ME_CRM: {
    LEADS_LIST: `${CRM}/me/leads/list`, // POST + QueryRequest — leads del asesor logueado (MY_LEADS_READ)
  },
  // ── Conversations module ─────────────────────────────────
  // Webhooks (top-level /api/v1/webhooks/whatsapp/{id}, sin JWT) NO van acá: los
  // consume Meta directo contra el backend; el frontend nunca los llama.
  CHANNEL_ACCOUNTS: {
    LIST: `${CONVERSATIONS}/channel-accounts/list`,
    CREATE: `${CONVERSATIONS}/channel-accounts`,
    GET: (id: string) => `${CONVERSATIONS}/channel-accounts/${id}`,
    UPDATE: (id: string) => `${CONVERSATIONS}/channel-accounts/${id}`, // PUT (not PATCH)
    DELETE: (id: string) => `${CONVERSATIONS}/channel-accounts/${id}`, // soft delete
    ACTIVE: `${CONVERSATIONS}/channel-accounts/active`, // raw ChannelAccountOption[] list
  },
  // `CONVERSATIONS_API` (no `CONVERSATIONS`): la const string ya ocupa ese
  // identificador (mismo patrón que `ME_CRM` en crm).
  CONVERSATIONS_API: {
    LIST: `${CONVERSATIONS}/list`, // inbox global. PaginatedResponse[ConversationListItem]
    GET: (id: string) => `${CONVERSATIONS}/${id}`, // SingleResponse[ConversationDetail]
    MESSAGES_LIST: (id: string) => `${CONVERSATIONS}/${id}/messages/list`, // POST + QueryRequest
    // Custom Token de Firebase para los listeners READ-ONLY del hilo (ADR-011).
    // POST → SingleResponse<{ token, firebase_config: null }>. Gated CONVERSATIONS_READ
    // o MY_CONVERSATIONS_READ (reusa permisos existentes; NO es un permiso nuevo).
    REALTIME_TOKEN: `${CONVERSATIONS}/realtime/token`,
    SEND_MESSAGE: (id: string) => `${CONVERSATIONS}/${id}/messages`, // POST outbound (real Meta)
    TAKE: (id: string) => `${CONVERSATIONS}/${id}/take`, // POST
    RELEASE: (id: string) => `${CONVERSATIONS}/${id}/release`, // POST
    CLOSE: (id: string) => `${CONVERSATIONS}/${id}/close`, // POST
    REOPEN: (id: string) => `${CONVERSATIONS}/${id}/reopen`, // POST
    MARK_READ: (id: string) => `${CONVERSATIONS}/${id}/mark-read`, // POST
  },
  ME_CONVERSATIONS: {
    LIST: `${CONVERSATIONS}/me/conversations/list`, // POST + QueryRequest — mi bandeja
  },
  // ── Bots module (#6) ─────────────────────────────────────
  // Declarado en F0 (Prep), INERTE: ninguna pantalla lo consume aún. Las rutas
  // backend se montan por fase (config+versiones F1, tools F2, engine+trace F3).
  // `/engine/dispatch` (target de Cloud Tasks, top-level interno sin JWT) NO va acá:
  // lo invoca Cloud Tasks contra el backend; el frontend nunca lo llama.
  BOT_CONFIGURATIONS: {
    LIST: `${BOTS}/configurations/list`, // POST + QueryRequest. PaginatedResponse[BotConfigurationItem]
    CREATE: `${BOTS}/configurations`,
    GET: (id: string) => `${BOTS}/configurations/${id}`, // SingleResponse[BotConfigurationDetail]
    UPDATE: (id: string) => `${BOTS}/configurations/${id}`, // PUT (not PATCH)
    DELETE: (id: string) => `${BOTS}/configurations/${id}`, // soft delete
    ACTIVE: `${BOTS}/configurations/active`, // raw BotConfigurationOption[] (dropdown)
    // Versiones (tab del drawer de configuración)
    VERSIONS_LIST: (id: string) => `${BOTS}/configurations/${id}/versions`, // GET
    VERSION_CREATE: (id: string) => `${BOTS}/configurations/${id}/versions`, // POST → nueva versión
    VERSION_GET: (id: string, vid: string) => `${BOTS}/configurations/${id}/versions/${vid}`, // GET
    ACTIVATE_VERSION: (id: string, vid: string) =>
      `${BOTS}/configurations/${id}/activate-version/${vid}`, // POST → promueve a vigente
    // M:N tools del bot (editor multiselect)
    TOOLS_LIST: (id: string) => `${BOTS}/configurations/${id}/tools`, // GET → BotToolOption[] asignadas
    TOOLS_UPDATE: (id: string) => `${BOTS}/configurations/${id}/tools`, // PUT bulk {tool_ids:[]}
  },
  BOT_TOOLS: {
    LIST: `${BOTS}/tools/list`, // POST + QueryRequest. PaginatedResponse[BotToolItem]
    CREATE: `${BOTS}/tools`,
    UPDATE: (id: string) => `${BOTS}/tools/${id}`, // PUT
    DELETE: (id: string) => `${BOTS}/tools/${id}`, // soft delete
  },
  // Depuración por conversación (paneles read-only del inbox / config)
  BOT_TRACE: {
    STATE: (cid: string) => `${BOTS}/conversations/${cid}/state`, // GET ConversationBotState
    STATE_RESET: (cid: string) => `${BOTS}/conversations/${cid}/state/reset`, // POST
    EVENTS: (cid: string) => `${BOTS}/conversations/${cid}/events`, // GET BotEventItem[]
    TOOL_CALLS: (cid: string) => `${BOTS}/conversations/${cid}/tool-calls`, // GET BotToolCallItem[]
  },
  BOT_ENGINE: {
    DISPATCH_MANUAL: `${BOTS}/engine/dispatch-manual`, // POST (RBAC BOT_ENGINE_INVOKE) — debugging
  },
} as const;
