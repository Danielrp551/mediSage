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
      // F2 agregará "Estados de lead" (/crm/estados-lead, LEAD_STATUSES_READ) y
      // "Estados de cliente" (/crm/estados-cliente, CUSTOMER_STATUSES_READ);
      // F3 agregará "Mis leads" (/crm/mis-leads, MY_LEADS_READ). Se suman recién
      // cuando existan sus páginas (mismo patrón que staff, que añadió los me/*
      // recién en F3).
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
