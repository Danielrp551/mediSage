/**
 * Single source of truth for the sidebar AND for client-side route
 * permission checks. Codes must match `seed.py` / the `permission` table.
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
    label: "Home",
    icon: "HomeRegular",
    url: "/dashboard",
    permissions: ["MENU-HOME"],
  },
  {
    key: "admin",
    label: "Administration",
    icon: "SettingsRegular",
    children: [
      {
        key: "users",
        label: "Users",
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
        label: "Permissions",
        icon: "LockClosedRegular",
        url: "/admin/permissions",
        permissions: ["MENU-ADMIN-PERMISSIONS"],
      },
    ],
  },
];
