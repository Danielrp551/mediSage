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
