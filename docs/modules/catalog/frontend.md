# Módulo `catalog` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-05-28
> **Audiencia**: developer implementando `frontend/src/.../catalog/`.
> **Pre-requisito**: leer [`README.md`](README.md), [`backend.md`](backend.md), [`ui.md`](ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md).

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   ├── catalog.types.ts                 ← Vertical*, Service*, Product*
│   └── index.ts                         ← re-export (si no existe ya)
├── lib/
│   ├── schemas/
│   │   ├── vertical.schema.ts
│   │   ├── service.schema.ts
│   │   └── product.schema.ts
│   └── constants/
│       ├── endpoints.ts                 ← EXTEND con catalog
│       ├── navigation.ts                ← EXTEND con catalog
│       └── catalog-iconography.ts       ← curated icon list para Vertical picker
├── actions/
│   ├── vertical.actions.ts
│   ├── service.actions.ts
│   └── product.actions.ts
└── app/(main)/catalog/
    ├── verticals/
    │   ├── page.tsx
    │   ├── loading.tsx
    │   └── _components/
    │       ├── VerticalsClient.tsx
    │       ├── VerticalDrawer.tsx
    │       ├── ColorPicker.tsx
    │       └── IconPicker.tsx
    ├── services/
    │   ├── page.tsx
    │   ├── loading.tsx
    │   └── _components/
    │       ├── ServicesClient.tsx
    │       └── ServiceDrawer.tsx
    └── products/
        ├── page.tsx
        ├── loading.tsx
        └── _components/
            ├── ProductsClient.tsx
            └── ProductDrawer.tsx
```

> **Por qué no hay `catalog/layout.tsx`**: las 3 páginas son hermanas, no comparten header ni state. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). Agregar layout intermedio solo aporta indirección.

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas. Mantiene componentes locales colocados con su page.

## Tipos TS — `types/catalog.types.ts`

Espejo de los Pydantic schemas del backend. Importable desde server actions y client components.

```ts
import type { UserAuditInfo } from "./audit.types";

// ── Vertical ────────────────────────────────────────────

export interface VerticalItem {
  id: string;
  code: string;
  name: string;
  description: string | null;
  color: string | null;
  icon: string | null;
  display_order: number;
  active: boolean;
  services_count: number;
  products_count: number;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export type VerticalDetail = VerticalItem;

export interface VerticalOption {
  id: string;
  code: string;
  name: string;
  color: string | null;
  icon: string | null;
}

export interface VerticalCreatePayload {
  code: string;
  name: string;
  description?: string | null;
  color?: string | null;
  icon?: string | null;
  display_order?: number;
}

export interface VerticalUpdatePayload {
  name?: string;
  description?: string | null;
  color?: string | null;
  icon?: string | null;
  display_order?: number;
  active?: boolean;
}

// ── Service ─────────────────────────────────────────────

export interface ServiceItem {
  id: string;
  vertical_id: string;
  vertical_name: string;
  code: string;
  name: string;
  description: string | null;
  display_order: number;
  active: boolean;
  products_count: number;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface ServiceDetail extends ServiceItem {
  vertical: VerticalOption;
}

export interface ServiceOption {
  id: string;
  vertical_id: string;
  code: string;
  name: string;
}

export interface ServiceCreatePayload {
  vertical_id: string;
  code: string;
  name: string;
  description?: string | null;
  display_order?: number;
}

export interface ServiceUpdatePayload {
  name?: string;
  description?: string | null;
  display_order?: number;
  active?: boolean;
}

// ── Product ─────────────────────────────────────────────

export interface ProductItem {
  id: string;
  service_id: string;
  service_name: string;
  vertical_id: string;
  vertical_name: string;
  code: string;
  name: string;
  description: string | null;
  base_price: string;          // backend returns Decimal as string
  currency: string;
  duration_min: number | null;
  requires_appointment: boolean;
  is_package: boolean;
  min_hours_to_cancel: number | null;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface ProductDetail extends ProductItem {
  service: ServiceOption;
  vertical: VerticalOption;
}

export interface ProductOption {
  id: string;
  service_id: string;
  code: string;
  name: string;
  base_price: string;
  currency: string;
  duration_min: number | null;
}

export interface ProductCreatePayload {
  service_id: string;
  code: string;
  name: string;
  description?: string | null;
  base_price: string;
  currency?: string;
  duration_min?: number | null;
  requires_appointment?: boolean;
  is_package?: boolean;
  min_hours_to_cancel?: number | null;
}

export interface ProductUpdatePayload {
  name?: string;
  description?: string | null;
  base_price?: string;
  currency?: string;
  duration_min?: number | null;
  requires_appointment?: boolean;
  is_package?: boolean;
  min_hours_to_cancel?: number | null;
  active?: boolean;
}
```

> **Nota sobre `Decimal`**: el backend FastAPI serializa `Decimal` como **string** ("350.00") para evitar pérdida de precisión en JavaScript. El frontend lo trata como string y solo lo parsea con `parseFloat` o `Intl.NumberFormat` al renderizar.

## Zod schemas

### `lib/schemas/vertical.schema.ts`

```ts
import { z } from "zod";

export const CODE_SLUG_REGEX = /^[a-z][a-z0-9_]{1,38}[a-z0-9]$/;
export const HEX_COLOR_REGEX = /^#[0-9A-Fa-f]{6}$/;

const codeField = z
  .string()
  .min(3, "Min 3 characters")
  .max(40, "Max 40 characters")
  .regex(
    CODE_SLUG_REGEX,
    "Lowercase slug: letters, digits, underscores. Start with letter.",
  );

const colorField = z
  .string()
  .regex(HEX_COLOR_REGEX, "Hex color like #RRGGBB")
  .nullable()
  .optional();

const verticalBase = z.object({
  name: z.string().min(1, "Required").max(120),
  description: z.string().max(500).nullable().optional(),
  color: colorField,
  icon: z.string().max(60).nullable().optional(),
  display_order: z.number().int().min(0).max(9999).default(0),
});

export const verticalCreateSchema = verticalBase.extend({
  code: codeField,
});

export const verticalUpdateSchema = verticalBase
  .partial()
  .extend({ active: z.boolean().optional() });

export type VerticalCreateInput = z.infer<typeof verticalCreateSchema>;
export type VerticalUpdateInput = z.infer<typeof verticalUpdateSchema>;
```

### `lib/schemas/service.schema.ts`

```ts
import { z } from "zod";

import { CODE_SLUG_REGEX } from "./vertical.schema";

const codeField = z
  .string()
  .min(3)
  .max(60)
  .regex(CODE_SLUG_REGEX, "Lowercase slug (a-z, 0-9, _)");

const serviceBase = z.object({
  name: z.string().min(1, "Required").max(120),
  description: z.string().max(500).nullable().optional(),
  display_order: z.number().int().min(0).max(9999).default(0),
});

export const serviceCreateSchema = serviceBase.extend({
  vertical_id: z.string().min(1, "Pick a vertical"),
  code: codeField,
});

export const serviceUpdateSchema = serviceBase
  .partial()
  .extend({ active: z.boolean().optional() });

export type ServiceCreateInput = z.infer<typeof serviceCreateSchema>;
export type ServiceUpdateInput = z.infer<typeof serviceUpdateSchema>;
```

### `lib/schemas/product.schema.ts`

```ts
import { z } from "zod";

import { CODE_SLUG_REGEX } from "./vertical.schema";

export const SUPPORTED_CURRENCIES = ["PEN", "USD", "EUR"] as const;
export type SupportedCurrency = (typeof SUPPORTED_CURRENCIES)[number];

const codeField = z
  .string()
  .min(3)
  .max(60)
  .regex(CODE_SLUG_REGEX, "Lowercase slug (a-z, 0-9, _)");

// Pricing accepts numeric strings to align with backend Decimal serialisation.
// Allow plain `123`, `123.45`, `123.4`, but reject more than 2 decimals.
const priceField = z
  .string()
  .regex(/^\d+(\.\d{1,2})?$/, "Use a number like 350 or 350.00")
  .refine((s) => parseFloat(s) >= 0, "Price must be >= 0")
  .refine((s) => parseFloat(s) < 10_000_000, "Max 9,999,999.99");

const productBase = z.object({
  name: z.string().min(1, "Required").max(160),
  description: z.string().max(1000).nullable().optional(),
  base_price: priceField,
  currency: z.enum(SUPPORTED_CURRENCIES).default("PEN"),
  duration_min: z.number().int().min(1).max(24 * 60).nullable().optional(),
  requires_appointment: z.boolean().default(true),
  is_package: z.boolean().default(false),
  min_hours_to_cancel: z.number().int().min(0).max(24 * 7).nullable().optional(),
});

function refineCancelRules<
  T extends {
    requires_appointment?: boolean;
    duration_min?: number | null;
    min_hours_to_cancel?: number | null;
  },
>(data: T, ctx: z.RefinementCtx): void {
  if (
    data.requires_appointment !== false &&
    (data.min_hours_to_cancel ?? null) !== null &&
    (data.duration_min ?? null) === null
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["duration_min"],
      message:
        "Duration is required when the product is bookable and has a cancellation deadline.",
    });
  }
}

export const productCreateSchema = productBase
  .extend({
    service_id: z.string().min(1, "Pick a service"),
    code: codeField,
  })
  .superRefine(refineCancelRules);

export const productUpdateSchema = productBase
  .partial()
  .extend({ active: z.boolean().optional() })
  .superRefine(refineCancelRules);

export type ProductCreateInput = z.infer<typeof productCreateSchema>;
export type ProductUpdateInput = z.infer<typeof productUpdateSchema>;
```

> **Convención**: misma estructura que `user.schema.ts` (base + `.partial()` para update + `superRefine` para cross-field).

## Iconografía curada — `lib/constants/catalog-iconography.ts`

Lista cerrada de íconos Fluent UI permitidos para `Vertical.icon`. **Cerrada** para que el admin no escriba un nombre que rompa el sidebar.

```ts
// Curated subset of Fluent UI icon names suitable for medical/clinic verticals.
// Each entry maps to a Fluent UI v9 icon component (suffix `Regular` or `Filled`).
export const VERTICAL_ICON_OPTIONS = [
  { key: "Sparkle24Regular",     label: "Sparkle"    },
  { key: "Heart24Regular",       label: "Heart"      },
  { key: "HeartPulse24Regular",  label: "Pulse"      },
  { key: "Stethoscope24Regular", label: "Stethoscope"},
  { key: "Tooth24Regular",       label: "Tooth"      },
  { key: "Eye24Regular",         label: "Eye"        },
  { key: "Brain24Regular",       label: "Brain"      },
  { key: "Leaf24Regular",        label: "Leaf"       },
  { key: "Beaker24Regular",      label: "Beaker"     },
  { key: "Pill24Regular",        label: "Pill"       },
  { key: "Syringe24Regular",     label: "Syringe"    },
  { key: "Bandage24Regular",     label: "Bandage"    },
  { key: "Person24Regular",      label: "Person"     },
  { key: "PersonHeart24Regular", label: "Caring"     },
  { key: "Baby24Regular",        label: "Baby"       },
  { key: "Drop24Regular",        label: "Drop"       },
  { key: "Star24Regular",        label: "Star"       },
  { key: "Crown24Regular",       label: "Premium"    },
  { key: "Wand24Regular",        label: "Wand"       },
  { key: "Flash24Regular",       label: "Flash"      },
] as const;

export type VerticalIconKey = (typeof VERTICAL_ICON_OPTIONS)[number]["key"];

// Curated palette for Vertical.color picker (light/dark friendly).
export const VERTICAL_COLOR_PALETTE = [
  "#EF4444", // red
  "#F59E0B", // amber
  "#22C55E", // green
  "#06B6D4", // cyan
  "#3B82F6", // blue
  "#8B5CF6", // violet
  "#EC4899", // pink
  "#FF6B6B", // coral
  "#10B981", // emerald
  "#F97316", // orange
  "#6366F1", // indigo
  "#6B7280", // gray
] as const;
```

> **Renderizar el ícono**: en `Sidebar.tsx` el `icon` viene como string. El sidebar tiene un map `iconMap` interno; agregar los íconos curados allí. Para el componente `IconPicker` del drawer, importar dinámicamente o tener el mismo map local.

## Endpoints constants — extender `lib/constants/endpoints.ts`

```ts
const ADMIN = "/api/v1/admin";
const CATALOG = "/api/v1/catalog";

export const ENDPOINTS = {
  AUTH: { /* existente */ },
  USERS: { /* existente */ },
  ROLES: { /* existente */ },
  PERMISSIONS: { /* existente */ },

  // ── NEW ───────────────────────────────────────────
  VERTICALS: {
    LIST:   `${CATALOG}/verticals/list`,
    ACTIVE: `${CATALOG}/verticals/active`,
    GET:    (id: string) => `${CATALOG}/verticals/${id}`,
    CREATE: `${CATALOG}/verticals`,
    UPDATE: (id: string) => `${CATALOG}/verticals/${id}`,
    DELETE: (id: string) => `${CATALOG}/verticals/${id}`,
  },
  SERVICES: {
    LIST:   `${CATALOG}/services/list`,
    ACTIVE: `${CATALOG}/services/active`,
    GET:    (id: string) => `${CATALOG}/services/${id}`,
    CREATE: `${CATALOG}/services`,
    UPDATE: (id: string) => `${CATALOG}/services/${id}`,
    DELETE: (id: string) => `${CATALOG}/services/${id}`,
  },
  PRODUCTS: {
    LIST:   `${CATALOG}/products/list`,
    ACTIVE: `${CATALOG}/products/active`,
    GET:    (id: string) => `${CATALOG}/products/${id}`,
    CREATE: `${CATALOG}/products`,
    UPDATE: (id: string) => `${CATALOG}/products/${id}`,
    DELETE: (id: string) => `${CATALOG}/products/${id}`,
  },
} as const;
```

> Las URLs `/active` aceptan query params (`?vertical_id=`, `?service_id=`). El `backendClient.get` los pasa como segundo argumento de `URLSearchParams` o se concatenan en la cadena del endpoint en el action.

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés. Los items existentes del template (`Home`, `Administration`, `Users`, etc.) también se traducen — ver TODO al final del documento.

Insertar el item `catalog` entre `home` y `admin`:

```ts
export const NAV_ITEMS: NavItem[] = [
  {
    key: "home",
    label: "Inicio",                  // ← era "Home"
    icon: "HomeRegular",
    url: "/dashboard",
    permissions: ["MENU-HOME"],
  },
  // ── NEW ───────────────────────────────────────────
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
    key: "admin",
    label: "Administración",         // ← era "Administration"
    icon: "SettingsRegular",
    children: [
      { key: "users",       label: "Usuarios", /* etc */ },     // ← era "Users"
      { key: "roles",       label: "Roles", /* etc */ },        // ← se mantiene
      { key: "permissions", label: "Permisos", /* etc */ },     // ← era "Permissions"
    ],
  },
];
```

> El sidebar (`components/layout/Sidebar/Sidebar.tsx`) ya filtra los items por `permissions` vs `useAuth().permissions`. Si el user no tiene `MENU-CATALOG`, no ve el grupo.

## Server Actions

### `actions/vertical.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import {
  verticalCreateSchema,
  verticalUpdateSchema,
} from "@/lib/schemas/vertical.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type {
  VerticalDetail,
  VerticalItem,
  VerticalOption,
} from "@/types/catalog.types";
import type { QueryRequest } from "@/types/query.types";

const TAG = "catalog:verticals";

export async function listVerticals(
  query: QueryRequest,
): Promise<ApiPaginated<VerticalItem>> {
  return backendClient.post<ApiPaginated<VerticalItem>>(
    ENDPOINTS.VERTICALS.LIST,
    query,
    { tags: [TAG] },
  );
}

export async function listActiveVerticals(): Promise<VerticalOption[]> {
  const res = await backendClient.get<ApiSingle<VerticalOption[]>>(
    ENDPOINTS.VERTICALS.ACTIVE,
    { tags: [TAG] },
  );
  return res.data;
}

export async function getVertical(id: string): Promise<ApiSingle<VerticalDetail>> {
  return backendClient.get<ApiSingle<VerticalDetail>>(
    ENDPOINTS.VERTICALS.GET(id),
    { tags: [TAG] },
  );
}

export interface MutationResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  fieldErrors?: Record<string, string[]>;
}

export async function createVertical(
  input: unknown,
): Promise<MutationResult<ApiSingle<VerticalDetail>>> {
  const parsed = verticalCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<VerticalDetail>>(
      ENDPOINTS.VERTICALS.CREATE,
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}

export async function updateVertical(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<VerticalDetail>>> {
  const parsed = verticalUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.patch<ApiSingle<VerticalDetail>>(
      ENDPOINTS.VERTICALS.UPDATE(id),
      parsed.data,
    );
    revalidateTag(TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}

export async function deleteVertical(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.VERTICALS.DELETE(id));
    revalidateTag(TAG, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}
```

### `actions/service.actions.ts`

Mismo molde. Tag: `catalog:services`. Endpoints: `ENDPOINTS.SERVICES.*`. Schema: `serviceCreateSchema` / `serviceUpdateSchema`. `listActiveServices(verticalId?: string)` agrega query param:

```ts
export async function listActiveServices(
  verticalId?: string,
): Promise<ServiceOption[]> {
  const url = verticalId
    ? `${ENDPOINTS.SERVICES.ACTIVE}?vertical_id=${encodeURIComponent(verticalId)}`
    : ENDPOINTS.SERVICES.ACTIVE;
  const res = await backendClient.get<ApiSingle<ServiceOption[]>>(url, {
    tags: [TAG],
  });
  return res.data;
}
```

### `actions/product.actions.ts`

Mismo molde. Tag: `catalog:products`. `listActiveProducts(serviceId?: string)` análogo.

> **Cross-tag invalidation**: cuando se actualiza un vertical o service, no se invalidan los tags de productos. El `service_name`/`vertical_name` denormalizados en ProductItem **pueden quedar stale** hasta que el cache de productos expire o se invalide manualmente. Mitigación al actualizar Vertical/Service: agregar `revalidateTag("catalog:services", "max")` y `revalidateTag("catalog:products", "max")` también, **solo si** el campo afectado es `name`. Documentar el patrón en cada action.

```ts
// En updateVertical, después de éxito:
revalidateTag("catalog:verticals", "max");
if ("name" in parsed.data) {
  revalidateTag("catalog:services", "max");
  revalidateTag("catalog:products", "max");
}
```

Análogo en `updateService` para invalidar `catalog:products`.

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/catalog/verticals/page.tsx`

```tsx
import { listVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { VerticalsClient } from "./_components/VerticalsClient";

export const metadata = { title: "Verticales" };

export default async function VerticalsPage() {
  await requirePermission("MENU-CATALOG");

  const initialData = await listVerticals({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "display_order", sort_order: "asc" },
  });

  return <VerticalsClient initialData={initialData} />;
}
```

### `app/(main)/catalog/services/page.tsx`

```tsx
import { listServices } from "@/actions/service.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { ServicesClient } from "./_components/ServicesClient";

export const metadata = { title: "Servicios" };

interface PageProps {
  searchParams: Promise<{ vertical_id?: string }>;
}

export default async function ServicesPage({ searchParams }: PageProps) {
  await requirePermission("MENU-CATALOG");
  const { vertical_id } = await searchParams;

  const [initialData, verticals] = await Promise.all([
    listServices({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "display_order", sort_order: "asc" },
      filters: vertical_id
        ? {
            filters: [
              {
                operator: "AND",
                conditions: [
                  { field: "vertical_id", operator: "eq", value: vertical_id },
                ],
              },
            ],
          }
        : null,
    }),
    listActiveVerticals(),
  ]);

  return (
    <ServicesClient
      initialData={initialData}
      verticals={verticals}
      initialVerticalId={vertical_id ?? null}
    />
  );
}
```

### `app/(main)/catalog/products/page.tsx`

Similar a services con `vertical_id` y `service_id` en query params. Hace `Promise.all([listProducts(filters), listActiveVerticals(), listActiveServices(vertical_id)])`.

```tsx
export const metadata = { title: "Productos" };

interface PageProps {
  searchParams: Promise<{ vertical_id?: string; service_id?: string }>;
}

export default async function ProductsPage({ searchParams }: PageProps) {
  await requirePermission("MENU-CATALOG");
  const { vertical_id, service_id } = await searchParams;

  const filters: QueryRequest["filters"] = service_id
    ? { filters: [{ operator: "AND", conditions: [{ field: "service_id", operator: "eq", value: service_id }] }] }
    : vertical_id
      ? { filters: [{ operator: "AND", conditions: [{ field: "vertical_id", operator: "eq", value: vertical_id }] }] }
      : null;

  const [initialData, verticals, services] = await Promise.all([
    listProducts({ pagination: { skip: 0, limit: 10 }, sorting: { sort_by: "name", sort_order: "asc" }, filters }),
    listActiveVerticals(),
    listActiveServices(vertical_id),
  ]);

  return (
    <ProductsClient
      initialData={initialData}
      verticals={verticals}
      services={services}
      initialVerticalId={vertical_id ?? null}
      initialServiceId={service_id ?? null}
    />
  );
}
```

## Loading states

`loading.tsx` para cada página simplemente renderiza el shell con un placeholder del DataTable skeleton. Patrón mínimo:

```tsx
// app/(main)/catalog/verticals/loading.tsx
import { Skeleton, SkeletonItem } from "@fluentui/react-components";

export default function Loading() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Skeleton><SkeletonItem size={32} style={{ width: 200 }} /></Skeleton>
      <Skeleton><SkeletonItem size={16} style={{ width: 400 }} /></Skeleton>
      <Skeleton><SkeletonItem shape="rectangle" size={400} /></Skeleton>
    </div>
  );
}
```

## Client components — esqueletos

> **No reproduzco aquí los archivos completos** — siguen el patrón exacto de `admin/users/_components/UsersClient.tsx` y `UserDrawer.tsx` (que el implementador puede usar como template). Documento las diferencias específicas a catalog.

### `VerticalsClient.tsx`

Sigue el patrón de `UsersClient.tsx`. Diferencias:

- `queryKey: "catalog:verticals"`.
- `fetcher: listVerticals`.
- `searchFields: ["code", "name"]`.
- `defaultSort: { field: "display_order", order: "asc" }`.
- Columns: ver [`ui.md`](ui.md#columnas-de-la-tabla).
- RowActions: `view`, `edit` (gated `VERTICALS_UPDATE`), `delete` (gated `VERTICALS_DELETE`, abre `ConfirmDialog`).
- Botón "New vertical" gated `VERTICALS_CREATE`.

**`ConfirmDialog`** para delete: usar `components/ui/ConfirmDialog/ConfirmDialog.tsx` del template. Si el delete falla con `409 VERTICAL_HAS_ACTIVE_CHILDREN`, mostrar el `error` del `MutationResult` dentro del dialog (no cerrar) o como toast.

### `VerticalDrawer.tsx`

Sigue el patrón de `UserDrawer.tsx`. Diferencias:

- 2 tabs: `Details` + `Audit` (sin Access).
- Sin `SearchableOptionList` (vertical no tiene M:N propias).
- Sub-componentes nuevos: `ColorPicker` y `IconPicker` (ver abajo).
- En modo `edit` y `view`, `code` queda disabled.
- `form.reset` después de `getVertical(id)`:
  ```ts
  form.reset({
    name: res.data.name,
    description: res.data.description ?? undefined,
    color: res.data.color ?? undefined,
    icon: res.data.icon ?? undefined,
    display_order: res.data.display_order,
  });
  ```

### `ColorPicker.tsx`

```tsx
"use client";
import { useState } from "react";
import { Button, Input, Popover, PopoverSurface, PopoverTrigger } from "@fluentui/react-components";
import { VERTICAL_COLOR_PALETTE } from "@/lib/constants/catalog-iconography";

interface Props {
  value: string | null;
  onChange: (v: string | null) => void;
  disabled?: boolean;
}

export function ColorPicker({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={(_, d) => setOpen(d.open)}>
      <PopoverTrigger disableButtonEnhancement>
        <Button disabled={disabled} style={{ minWidth: 130, justifyContent: "flex-start" }}>
          <span style={{
            display: "inline-block", width: 12, height: 12, borderRadius: "50%",
            background: value ?? "transparent",
            border: value ? "none" : "1px dashed currentColor",
            marginRight: 8,
          }}/>
          {value ?? "Pick…"}
        </Button>
      </PopoverTrigger>
      <PopoverSurface>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 24px)", gap: 8 }}>
          {VERTICAL_COLOR_PALETTE.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => { onChange(c); setOpen(false); }}
              style={{
                width: 24, height: 24, borderRadius: "50%", border: c === value ? "2px solid #000" : "1px solid #ddd",
                background: c, cursor: "pointer",
              }}
              aria-label={`Pick ${c}`}
            />
          ))}
        </div>
        <Input
          size="small"
          placeholder="#RRGGBB"
          value={value ?? ""}
          onChange={(_, d) => onChange(d.value || null)}
          style={{ marginTop: 8 }}
        />
      </PopoverSurface>
    </Popover>
  );
}
```

### `IconPicker.tsx`

Similar a `ColorPicker` pero renderiza los íconos curados de `VERTICAL_ICON_OPTIONS` en un grid. Usa import dinámico de Fluent icons:

```tsx
import * as Icons from "@fluentui/react-icons";
// ...
const IconComp = Icons[value as keyof typeof Icons] as React.ComponentType | undefined;
```

> ⚠ Verificar el tree-shaking: usar `import * as Icons` puede inflar el bundle. **Mejor pattern**: importar solo los íconos del listado curado:
> ```tsx
> import { Sparkle24Regular, Heart24Regular, /* ... */ } from "@fluentui/react-icons";
> const ICON_MAP: Record<VerticalIconKey, React.ComponentType> = {
>   "Sparkle24Regular": Sparkle24Regular,
>   /* ... */
> };
> ```

### `ServicesClient.tsx`

Sigue patrón `VerticalsClient`. Diferencias:

- Recibe `verticals: VerticalOption[]` como prop.
- State adicional para `verticalFilter: string | null` sincronizado con URL (`useQueryState` de `nuqs`).
- Vertical Dropdown en toolbar arriba del search.
- Chip "Filtered by: …" cuando hay filtro activo.
- Columns: ver [`ui.md`](ui.md).
- `searchFields: ["code", "name"]`.
- `defaultSort: { field: "display_order", order: "asc" }`.

### `ServiceDrawer.tsx`

Similar a `VerticalDrawer` con un Dropdown `Vertical *` adicional. En `edit` mode el dropdown queda disabled.

### `ProductsClient.tsx`

Más complejo: 2 dropdowns encadenados (Vertical → Service).

```tsx
const [verticalFilter, setVerticalFilter] = useQueryState("vertical_id");
const [serviceFilter, setServiceFilter] = useQueryState("service_id");
const [serviceOptions, setServiceOptions] = useState<ServiceOption[]>(initialServices);

useEffect(() => {
  // When vertical changes, fetch services for that vertical and reset service filter.
  if (verticalFilter !== null) {
    void listActiveServices(verticalFilter).then(setServiceOptions);
    // If current serviceFilter doesn't belong to new vertical, clear it.
    if (serviceFilter && !serviceOptions.some((s) => s.id === serviceFilter && s.vertical_id === verticalFilter)) {
      void setServiceFilter(null);
    }
  } else {
    void listActiveServices().then(setServiceOptions);
  }
}, [verticalFilter]);
```

### `ProductDrawer.tsx`

Sigue patrón con **4 tabs**: `Details`, `Pricing`, `Booking`, `Audit`. Los tabs son strings `TabId = "details" | "pricing" | "booking" | "audit"`.

`Details` tab:
- Dropdown `Vertical *` (controla el filtro del Service dropdown).
- Dropdown `Service *`.
- Input `code` (slug regex, disabled en edit).
- Input `name`.
- Textarea `description`.
- Checkbox `active`.

`Pricing` tab:
- Input `base_price` (numeric, mantiene como string).
- Dropdown `currency` con `SUPPORTED_CURRENCIES`.

`Booking` tab:
- Checkbox `requires_appointment`.
- Input `duration_min` numeric.
- Checkbox `is_package`.
- Input `min_hours_to_cancel` numeric.
- Inline `MessageBar intent="warning"` cuando `requires_appointment && min_hours_to_cancel && !duration_min` (la regla del Zod `superRefine`).

`Audit` tab: idéntico patrón a otros drawers.

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| 3 páginas separadas en sidebar | Consistencia con admin/users/roles/permissions; cada CRUD es independiente. |
| `code` immutable post-create | El backend lo prohibe; el form lo refleja con disabled en `edit`. |
| `vertical_id` / `service_id` immutable post-create | Mover entre padres requeriría endpoint `/move`; postergado. |
| Decimal → string en wire | Evita pérdida de precisión en JS. `Intl.NumberFormat` formatea al renderizar. |
| Icon picker con galería curada | Evita rompimiento del sidebar y mantiene consistencia visual. |
| Color picker con paleta + hex manual | Balance entre guía y flexibilidad. |
| Cross-tag invalidation en updates | Vertical/Service rename invalida también `catalog:services`/`catalog:products` porque tienen el `name` denormalizado. |
| RowActions con `delete` que abre ConfirmDialog | `409` con `code` específico se muestra dentro del dialog sin cerrarlo. |
| Sin bulk actions, sin duplicar, sin import CSV | Postergados al MVP+1. |

## Checklist de implementación

- [ ] Crear `src/types/catalog.types.ts` con todas las interfaces.
- [ ] Crear `src/lib/schemas/{vertical,service,product}.schema.ts`.
- [ ] Crear `src/lib/constants/catalog-iconography.ts` (colores + íconos curados).
- [ ] Extender `src/lib/constants/endpoints.ts` con `VERTICALS`, `SERVICES`, `PRODUCTS`.
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `catalog`.
- [ ] Registrar los íconos curados en el `iconMap` del Sidebar.
- [ ] Crear `src/actions/{vertical,service,product}.actions.ts`.
- [ ] Crear `src/app/(main)/catalog/{verticals,services,products}/{page.tsx,loading.tsx}`.
- [ ] Crear `_components/` de cada página (`Client.tsx` y `Drawer.tsx`).
- [ ] Crear `ColorPicker.tsx` y `IconPicker.tsx` reutilizables.
- [ ] **Smoke test**: con admin logueado, navegar `/catalog/verticals` → ver tabla vacía → crear primera vertical → ver fila → editar → soft-delete → tabla vacía de nuevo. Verificar todos los `revalidateTag` funcionando (la tabla refleja cambios sin refresh).
- [ ] **Permisos test**: como usuario sin `VERTICALS_CREATE`, el botón "+ New vertical" no aparece. Como usuario sin `VERTICALS_UPDATE`, el menú row no muestra "Edit".
- [ ] **Deep-link test**: navegar a `/catalog/services?vertical_id=X` → ver tabla filtrada + chip. Click ✕ del chip → tabla sin filtro.
- [ ] **Error 409 test**: crear service `S1` en vertical `V1`. Intentar delete `V1` → ConfirmDialog muestra error "Can't delete — vertical has 1 active service".
- [ ] **Validación inline test**: en ProductDrawer Booking tab, marcar `requires_appointment + min_hours_to_cancel=24`, dejar `duration_min` vacío, submit → error inline en `duration_min`.

## Tareas adicionales (traducción del template existente)

Al implementar este módulo, también traducir los textos UI del template existente a español:

- [ ] **`lib/constants/navigation.ts`**: `"Home"` → `"Inicio"`, `"Administration"` → `"Administración"`, `"Users"` → `"Usuarios"`, `"Roles"` → `"Roles"` (igual), `"Permissions"` → `"Permisos"`.
- [ ] **`app/(main)/dashboard/page.tsx`**: `metadata.title` y cualquier título en cuerpo.
- [ ] **`app/(main)/admin/users/page.tsx`**: `metadata = { title: "Usuarios" }`. UsersClient: header `"Users"` → `"Usuarios"`, subtitle, botón `"+ New user"` → `"+ Nuevo usuario"`, columns, empty state, drawer.
- [ ] **`app/(main)/admin/roles/page.tsx`**: idem para roles.
- [ ] **`app/(main)/admin/permissions/page.tsx`**: idem para permisos.
- [ ] **`(auth)/login/_components/LoginForm.tsx`**: labels, placeholders, botón "Sign in" → "Iniciar sesión".
- [ ] **`components/layout/TopBar/TopBar.tsx`**: si tiene strings ("Sign out", "Account", etc.) → "Cerrar sesión", "Cuenta".
- [ ] **`components/ui/DataTable/DataTable.tsx`**: defaults de `emptyTitle="Nothing here yet"` y `emptyMessage="Items you create will show up..."` → traducir a `"Aún no hay elementos"` y `"Los elementos que crees aparecerán aquí."`. También los textos del estado "no results match".
- [ ] **`components/ui/Pagination/Pagination.tsx`**: si tiene strings hardcoded.
- [ ] **`components/ui/ConfirmDialog/ConfirmDialog.tsx`**: defaults de botones "Confirm" / "Cancel" → "Confirmar" / "Cancelar".
- [ ] **`app/error.tsx`** y **`app/not-found.tsx`**: mensajes de error globales.
- [ ] **`app/layout.tsx`**: `metadata.title.default` / `metadata.description` en español.

> Esta traducción **se hace en el mismo PR** que la implementación de `catalog` (o en un PR previo dedicado, según preferencia). No queda pendiente — afecta consistencia de la UI desde el primer día de medisage.

## TODOs deliberados (postergados al MVP+1)

- [ ] **Importar catálogo desde CSV** — si la clínica tiene 50+ productos preexistentes, sería útil un endpoint y UI para CSV import. Postergar.
- [ ] **Drag & drop reorder** para `display_order` — UX más fluida que editar manualmente. Postergar.
- [ ] **Pre-built templates** (e.g. "Plantilla clínica dental: importar verticales + services típicos") — útil para nuevos clientes onboarding. Postergar.
- [ ] **Vista "Tree explorer"** alternativa para users que prefieren explorar la jerarquía. Postergar; los chips de drill-down basta para MVP.
- [ ] **i18n framework** (`next-intl` o similar) — si más adelante medisage soporta clínicas en otros idiomas. Por ahora todos los strings son literales en español directo en componentes. Postergar.
