/**
 * Single source of truth for the sidebar AND for client-side route
 * permission checks. Codes must match `seed.py` / the `permission` table.
 *
 * Convención: `key`, `icon`, `url` y `permissions` son identificadores de
 * código (inglés). `label` es texto visible al usuario (español).
 */

export interface NavItem {
  key: string;
  label: string;
  icon: string;
  url?: string;
  permissions?: string[];
  children?: NavItem[];
}

export const NAV_ITEMS: NavItem[] = [
  {
    key: "home",
    label: "Inicio",
    icon: "HomeRegular",
    url: "/dashboard",
    permissions: ["MENU-HOME"],
  },
  {
    key: "catalog",
    label: "Catálogo",
    icon: "AppsListRegular",
    children: [
      {
        key: "verticals",
        label: "Verticales",
        icon: "TagRegular",
        url: "/catalog/verticals",
        permissions: ["MENU-CATALOG"],
      },
      {
        key: "services",
        label: "Servicios",
        icon: "BriefcaseRegular",
        url: "/catalog/services",
        permissions: ["MENU-CATALOG"],
      },
      {
        key: "products",
        label: "Productos",
        icon: "BoxRegular",
        url: "/catalog/products",
        permissions: ["MENU-CATALOG"],
      },
    ],
  },
  {
    key: "clinic",
    label: "Clínica",
    icon: "BuildingMultipleRegular",
    children: [
      {
        key: "branches",
        label: "Sedes",
        icon: "BuildingRegular",
        url: "/clinic/branches",
        permissions: ["MENU-CLINIC"],
      },
      {
        key: "offices",
        label: "Consultorios",
        icon: "ConferenceRoomRegular",
        url: "/clinic/offices",
        permissions: ["MENU-CLINIC"],
      },
    ],
  },
  {
    key: "staff",
    label: "Staff",
    icon: "PeopleTeamRegular",
    children: [
      {
        key: "doctors",
        label: "Doctores",
        icon: "DoctorRegular",
        url: "/staff/doctors",
        permissions: ["MENU-STAFF"],
      },
      // F3 — self-service del doctor logueado. El role DOCTOR tiene los MY_*; un
      // admin con ese permiso pero sin perfil de doctor verá el item, pero el RSC
      // muestra el estado vacío NOT_A_DOCTOR (no 404, no crash).
      {
        key: "my-profile",
        label: "Mi perfil",
        icon: "PersonRegular",
        url: "/staff/me/perfil",
        permissions: ["MY_DOCTOR_PROFILE_READ"],
      },
      {
        key: "my-agenda",
        label: "Mi agenda",
        icon: "CalendarLtrRegular",
        url: "/staff/me/agenda",
        permissions: ["MY_AVAILABILITY_READ"],
      },
    ],
  },
  {
    key: "crm",
    label: "CRM",
    icon: "PeopleRegular", // icono del grupo (no se renderiza; sólo label + chevron)
    children: [
      {
        key: "persons",
        label: "Contactos",
        icon: "ContactCardRegular",
        url: "/crm/personas",
        permissions: ["MENU-CRM"],
      },
      {
        key: "lead-statuses",
        label: "Estados de lead",
        icon: "TagRegular",
        url: "/crm/estados-lead",
        permissions: ["LEAD_STATUSES_READ"],
      },
      {
        key: "customer-statuses",
        label: "Estados de cliente",
        icon: "TagMultipleRegular",
        url: "/crm/estados-cliente",
        permissions: ["CUSTOMER_STATUSES_READ"],
      },
      // F3 — bandeja del asesor logueado (sus leads asignados).
      {
        key: "my-leads",
        label: "Mis leads",
        icon: "PersonRegular",
        url: "/crm/mis-leads",
        permissions: ["MY_LEADS_READ"],
      },
    ],
  },
  {
    key: "conversations",
    label: "Conversaciones",
    icon: "ChatRegular", // icono del grupo (sólo label + chevron en el sidebar)
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
  {
    key: "bots",
    label: "Bots",
    icon: "BotRegular", // icono del grupo (sólo label + chevron en el sidebar)
    children: [
      // F0 declara SOLO Configuraciones (lo entrega F1). "Tools" (F2) y la
      // "Depuración" por conversación (F3) se agregan en su fase para no dejar
      // links muertos prolongados (lección crm). La Depuración además se entra
      // desde el inbox/config, no necesita item propio de menú obligatorio.
      {
        key: "bot-configurations",
        label: "Configuraciones",
        icon: "BotRegular",
        url: "/bots/configuraciones",
        permissions: ["BOT_CONFIGURATIONS_READ"],
      },
      // F2 — catálogo de herramientas invocables (solo ADMIN; el ASESOR no tiene
      // BOT_TOOLS_READ, así que no ve este item).
      {
        key: "bot-tools",
        label: "Herramientas",
        icon: "WrenchRegular",
        url: "/bots/tools",
        permissions: ["BOT_TOOLS_READ"],
      },
      // F3a — panel de observabilidad read-only por conversación (estado + traza).
      // El ASESOR tiene BOT_EVENTS_READ → ve este item; el item abre la pantalla
      // sin ?conv= (selector). También se entra contextualmente desde el inbox.
      {
        key: "bot-debug",
        label: "Depuración",
        icon: "BugRegular",
        url: "/bots/depuracion",
        permissions: ["BOT_EVENTS_READ"],
      },
    ],
  },
  {
    key: "admin",
    label: "Administración",
    icon: "SettingsRegular",
    children: [
      {
        key: "users",
        label: "Usuarios",
        icon: "PeopleRegular",
        url: "/admin/users",
        permissions: ["MENU-ADMIN-USERS"],
      },
      {
        key: "roles",
        label: "Roles",
        icon: "ShieldRegular",
        url: "/admin/roles",
        permissions: ["MENU-ADMIN-ROLES"],
      },
      {
        key: "permissions",
        label: "Permisos",
        icon: "LockClosedRegular",
        url: "/admin/permissions",
        permissions: ["MENU-ADMIN-PERMISSIONS"],
      },
    ],
  },
];
