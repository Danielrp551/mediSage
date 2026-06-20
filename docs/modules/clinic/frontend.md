# Módulo `clinic` — Frontend (Next.js) deep-dive

> **Última actualización**: 2026-05-29
> **Audiencia**: developer implementando `frontend/src/.../clinic/`.
> **Pre-requisito**: leer [`README.md`](README.md), [`backend.md`](backend.md), [`ui.md`](ui.md), [`../../../frontend/CLAUDE.md`](../../../frontend/CLAUDE.md).

> **Alineación con catalog (shipped)**: este módulo replica el patrón del módulo `catalog` ya en producción, con **dos diferencias deliberadas** que el lector debe tener presentes desde ya:
> 1. **Verbos HTTP**: los updates completos usan **`PUT`** (no `PATCH`). El borrador de `clinic.md` decía `PATCH`; se alinea a la convención shipped (`vertical.actions.ts` ya usa `backendClient.put(...)`). El bulk de horarios es `PUT /offices/{id}/operating-hours`.
> 2. **Dropdowns**: los endpoints de "lista plana de activos" se llaman **`/active`** (no `/options`). El borrador decía `/branches/options`; se alinea a `/branches/active`, `/offices/active?branch_id=&vertical_id=`.
> 3. **Detalle de Office = página dedicada** `/clinic/offices/{id}` con tabs (Detalles · Horarios · Excepciones · Auditoría), **no** un drawer. Las **Sedes** (`Branch`) sí siguen el patrón drawer de catalog. La **lista** de consultorios conserva un drawer de creación; ver/editar uno navega a su página de detalle.

## Estructura de archivos a crear

```
frontend/src/
├── types/
│   └── clinic.types.ts                  ← Branch*, Office*, OfficeOperatingHours*, OfficeClosure*
├── lib/
│   ├── schemas/
│   │   ├── branch.schema.ts
│   │   ├── office.schema.ts
│   │   ├── office-hours.schema.ts
│   │   └── office-closure.schema.ts
│   └── constants/
│       ├── endpoints.ts                 ← EXTEND con CLINIC
│       ├── navigation.ts                ← EXTEND con grupo 'Clínica'
│       └── timezones.ts                 ← lista curada de IANA timezones (Branch picker)
├── actions/
│   ├── branch.actions.ts
│   ├── office.actions.ts
│   ├── office-hours.actions.ts
│   └── office-closure.actions.ts
└── app/(main)/clinic/
    ├── branches/
    │   ├── page.tsx
    │   └── _components/
    │       ├── BranchesClient.tsx
    │       └── BranchDrawer.tsx
    └── offices/
        ├── page.tsx                     ← LISTA de consultorios (drawer de creación)
        ├── _components/
        │   ├── OfficesClient.tsx
        │   └── OfficeCreateDrawer.tsx   ← solo create; ver/editar navega al detalle
        └── [id]/
            ├── page.tsx                 ← PÁGINA DE DETALLE con tab routing
            └── _components/
                ├── OfficeDetailShell.tsx
                ├── OfficeDetailsTab.tsx
                ├── OfficeHoursTab.tsx
                ├── OfficeClosuresTab.tsx
                └── OfficeAuditTab.tsx
```

> **Por qué no hay `clinic/layout.tsx`**: igual que en catalog — `branches` y `offices` (lista) son hermanas sin header compartido. El `(main)/layout.tsx` del template ya envuelve con `MainShell` (Sidebar + TopBar). El detalle del office sí tiene un shell propio (`OfficeDetailShell`), pero es un **componente cliente** dentro de `[id]/page.tsx`, no un `layout.tsx` de ruta — los tabs viven en una sola URL, no en sub-rutas (ver [Detalle de Office](#página-de-detalle-del-office-apt-mainclinicofficesid)).

> **Por qué `_components/`** (underscore): convención del template — Next no trata folders con `_` como rutas. Mantiene componentes locales colocados con su page.

> **Sobre `loading.tsx`**: el módulo `catalog` shipped **no** incluyó `loading.tsx` (el `DataTable` ya renderiza su propio skeleton vía `isLoading`). `clinic` sigue ese mismo criterio: no se crean `loading.tsx`. El estado de carga del detalle del office se maneja dentro de `OfficeDetailShell` (ver mockups en [`ui.md`](ui.md)).

## Tipos TS — `types/clinic.types.ts`

Espejo de los Pydantic schemas del backend (ver [`backend.md`](backend.md#schemas-pydantic-v2--completos)). Importable desde server actions y client components. Reusa `VerticalOption` de `catalog.types.ts` para la M:N office↔vertical.

```ts
import type { UserAuditInfo } from "./audit.types";
import type { VerticalOption } from "./catalog.types";

// ── Branch (Sede) ───────────────────────────────────────

export interface BranchItem {
  id: string;
  code: string;
  name: string;
  address_line: string;
  district: string | null;
  city: string;
  region: string | null;
  country: string; // ISO 3166-1 alpha-2, default "PE"
  postal_code: string | null;
  latitude: string | null; // backend serializes numeric(9,6) as string
  longitude: string | null;
  phone: string | null;
  email: string | null;
  timezone: string; // IANA, default "America/Lima"
  active: boolean;
  offices_count: number; // denormalized — mirrors catalog's services_count
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

// Detail currently adds no extra relations vs Item — alias for non-breaking
// future widening (same convention as VerticalDetail).
export type BranchDetail = BranchItem;

export interface BranchOption {
  id: string;
  code: string;
  name: string;
  city: string;
  timezone: string;
}

export interface BranchCreatePayload {
  code: string;
  name: string;
  address_line: string;
  district?: string | null;
  city: string;
  region?: string | null;
  country?: string;
  postal_code?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  phone?: string | null;
  email?: string | null;
  timezone?: string;
}

export interface BranchUpdatePayload {
  name?: string;
  address_line?: string;
  district?: string | null;
  city?: string;
  region?: string | null;
  country?: string;
  postal_code?: string | null;
  latitude?: string | null;
  longitude?: string | null;
  phone?: string | null;
  email?: string | null;
  timezone?: string;
  active?: boolean;
}

// ── Office (Consultorio) ────────────────────────────────

export interface OfficeItem {
  id: string;
  branch_id: string;
  branch_name: string; // denormalized — avoids a join in the table (mirrors vertical_name)
  code: string;
  name: string;
  room_number: string | null;
  floor: string | null;
  description: string | null;
  active: boolean;
  verticals_count: number; // denormalized — # of apt verticals
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface OfficeDetail extends OfficeItem {
  branch: BranchOption;
  verticals: VerticalOption[]; // soft-deleted verticals filtered out server-side
}

export interface OfficeOption {
  id: string;
  branch_id: string;
  code: string;
  name: string;
}

export interface OfficeCreatePayload {
  branch_id: string;
  code: string;
  name: string;
  room_number?: string | null;
  floor?: string | null;
  description?: string | null;
  vertical_ids: string[]; // M:N office_vertical assignment at create time
}

export interface OfficeUpdatePayload {
  name?: string;
  room_number?: string | null;
  floor?: string | null;
  description?: string | null;
  vertical_ids?: string[]; // full replace of the M:N when present
  active?: boolean;
}

// ── OfficeOperatingHours (patrón semanal) ───────────────
// Managed via BULK PUT atomic replace — there is no per-row create/update/delete.

export interface OfficeOperatingHoursItem {
  // day_of_week uses the Python datetime.weekday() convention: 0 = lunes … 6 = domingo.
  day_of_week: number; // 0..6
  opens_at: string; // local time "HH:MM" (no TZ — interpreted in branch.timezone)
  closes_at: string; // local time "HH:MM"; backend CHECK closes_at > opens_at
}

// Wire shape for the GET (read) — each persisted block carries its id.
export interface OfficeOperatingHoursRow extends OfficeOperatingHoursItem {
  id: string;
}

// Body of PUT /offices/{id}/operating-hours — the FULL weekly pattern.
export interface OfficeOperatingHoursReplacePayload {
  hours: OfficeOperatingHoursItem[];
}

// ── OfficeClosure (excepción ad-hoc) ────────────────────
// Individual CRUD nested under /offices/{id}/closures.

export interface OfficeClosureItem {
  id: string;
  office_id: string;
  starts_at: string; // timestamptz — ISO 8601 with offset
  ends_at: string; // backend CHECK ends_at > starts_at
  is_closed: boolean; // true = cierre, false = apertura extraordinaria
  reason: string;
  active: boolean;
  created_on: string;
  created_by: string;
  created_by_user: UserAuditInfo | null;
  updated_on: string;
  updated_by: string;
  updated_by_user: UserAuditInfo | null;
}

export interface OfficeClosureCreatePayload {
  starts_at: string; // ISO 8601 with offset
  ends_at: string;
  is_closed: boolean;
  reason: string;
}
```

> **Nota sobre `Decimal` → string**: `latitude`/`longitude` son `numeric(9,6)` en BD y el backend FastAPI los serializa como **string** ("−12.046374") para evitar pérdida de precisión en JS — mismo criterio que `Product.base_price` en catalog. El frontend los trata como string y solo los parsea con `parseFloat` al validar/renderizar.

> **Nota sobre las tres clases de tiempo** (ver [`README.md`](README.md#timezone--datetimes--cómo-se-resuelve-la-representación-de-horas)):
> - `OfficeOperatingHours.opens_at/closes_at` → `time` **sin TZ**, viajan como `"HH:MM"`. La UI los muestra tal cual; se interpretan en `office.branch.timezone`. **No** se pasan por `new Date()`.
> - `OfficeClosure.starts_at/ends_at` → `timestamptz`, viajan ISO 8601 con offset. La UI los formatea con `lib/utils/date.ts` (`new Date()`), igual que el resto del template.

## Zod schemas

### `lib/schemas/branch.schema.ts`

```ts
import { z } from "zod";

import { CODE_SLUG_REGEX } from "./vertical.schema"; // reuse the 3–40 char slug regex

/** ISO 3166-1 alpha-2, two uppercase letters. */
export const COUNTRY_REGEX = /^[A-Z]{2}$/;
/** Decimal-as-string for lat/long; up to 6 decimal places. */
export const LATLONG_REGEX = /^-?\d{1,3}(\.\d{1,6})?$/;

const codeField = z
  .string()
  .min(3, "Mínimo 3 caracteres")
  .max(40, "Máximo 40 caracteres")
  .regex(
    CODE_SLUG_REGEX,
    "Slug en minúsculas: letras, dígitos, '_'. Empieza con letra, termina con letra o dígito.",
  );

const latitudeField = z
  .string()
  .regex(LATLONG_REGEX, "Latitud como -12.046374")
  .refine((s) => Math.abs(parseFloat(s)) <= 90, "La latitud va de -90 a 90")
  .nullable()
  .optional();

const longitudeField = z
  .string()
  .regex(LATLONG_REGEX, "Longitud como -77.042793")
  .refine((s) => Math.abs(parseFloat(s)) <= 180, "La longitud va de -180 a 180")
  .nullable()
  .optional();

const branchBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  address_line: z.string().min(1, "Obligatorio").max(255, "Máximo 255 caracteres"),
  district: z.string().max(120).nullable().optional(),
  city: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  region: z.string().max(120).nullable().optional(),
  country: z.string().regex(COUNTRY_REGEX, "Código ISO de 2 letras (ej. PE)").default("PE"),
  postal_code: z.string().max(20).nullable().optional(),
  latitude: latitudeField,
  longitude: longitudeField,
  phone: z.string().max(40).nullable().optional(),
  email: z.string().email("Correo inválido").max(255).nullable().optional().or(z.literal("")),
  // Validated against the curated IANA list; free-form fallback allowed but
  // the picker only offers the curated set.
  timezone: z.string().min(1, "Obligatorio").max(60).default("America/Lima"),
});

export const branchCreateSchema = branchBase.extend({
  code: codeField,
});

export const branchUpdateSchema = branchBase.partial().extend({ active: z.boolean().optional() });

export type BranchCreateInput = z.infer<typeof branchCreateSchema>;
export type BranchUpdateInput = z.infer<typeof branchUpdateSchema>;
```

> **Sobre `latitude`/`longitude` opcionales pero acoplados**: si el negocio luego exige "ambos o ninguno", agregar un `.superRefine` que valide que `latitude` y `longitude` estén ambos set o ambos null. Por ahora son independientemente opcionales (la geo es de mejor esfuerzo para el MVP).

### `lib/schemas/office.schema.ts`

```ts
import { z } from "zod";

import { CODE_SLUG_REGEX } from "./vertical.schema";

const codeField = z
  .string()
  .min(2, "Mínimo 2 caracteres")
  .max(40, "Máximo 40 caracteres")
  .regex(
    CODE_SLUG_REGEX,
    "Slug en minúsculas: letras, dígitos, '_'. Empieza con letra, termina con letra o dígito.",
  );

const officeBase = z.object({
  name: z.string().min(1, "Obligatorio").max(120, "Máximo 120 caracteres"),
  room_number: z.string().max(20).nullable().optional(),
  floor: z.string().max(20).nullable().optional(),
  description: z.string().max(500, "Máximo 500 caracteres").nullable().optional(),
  // M:N apt verticals. Empty is allowed (an office not yet apt for anything),
  // but the create form nudges the user to pick at least one.
  vertical_ids: z.array(z.string()).default([]),
});

export const officeCreateSchema = officeBase.extend({
  branch_id: z.string().min(1, "Elige una sede"),
  code: codeField,
});

// On update, vertical_ids is optional: when present the backend does a full
// replace of office_vertical; when omitted the M:N is left untouched.
export const officeUpdateSchema = officeBase
  .partial()
  .extend({ active: z.boolean().optional() });

export type OfficeCreateInput = z.infer<typeof officeCreateSchema>;
export type OfficeUpdateInput = z.infer<typeof officeUpdateSchema>;
```

> **`branch_id` inmutable post-create** (igual que `vertical_id` en service): mover un consultorio entre sedes requeriría un endpoint `/move`; postergado. El form deshabilita el dropdown de sede en `edit`.

> **`code` único por sede** (`(branch_id, code)`): la validación de unicidad la hace el backend (`409 ALREADY_EXISTS`); el Zod solo valida la forma del slug. El form deshabilita `code` en `edit`.

### `lib/schemas/office-hours.schema.ts`

```ts
import { z } from "zod";

// "HH:MM" 24h, 00:00–23:59. Stored as `time` (no TZ) on the backend.
export const TIME_HHMM_REGEX = /^([01]\d|2[0-3]):[0-5]\d$/;

const timeField = z.string().regex(TIME_HHMM_REGEX, "Hora como HH:MM (24h)");

const hoursBlockSchema = z
  .object({
    // 0 = lunes … 6 = domingo (Python datetime.weekday()).
    day_of_week: z.number().int().min(0, "Día inválido").max(6, "Día inválido"),
    opens_at: timeField,
    closes_at: timeField,
  })
  .superRefine((block, ctx) => {
    // Mirror of the backend CHECK closes_at > opens_at. A block never crosses
    // midnight; if needed, model it as two blocks across two days.
    if (block.closes_at <= block.opens_at) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["closes_at"],
        message: "La hora de cierre debe ser mayor que la de apertura.",
      });
    }
  });

// Body of the bulk PUT. Multiple blocks per day are allowed (mañana + tarde).
// The array can be empty (office with no recurring pattern → driven only by
// closures / always-closed until a pattern is set).
export const officeHoursReplaceSchema = z.object({
  hours: z.array(hoursBlockSchema),
});

export type OfficeHoursBlockInput = z.infer<typeof hoursBlockSchema>;
export type OfficeHoursReplaceInput = z.infer<typeof officeHoursReplaceSchema>;
```

> **Validación por bloque + no-overlap por día**: cada bloque valida `closes_at > opens_at` con un `superRefine` local. Además, `officeHoursReplaceSchema` lleva un `superRefine` **a nivel de `hours`** que rechaza bloques solapados del mismo día (agrupa por `day_of_week`, ordena por apertura, marca `cur.opens < prev.closes`; **adyacentes `next.opens == prev.closes` son válidos**) — **espeja el validador `OfficeOperatingHoursReplace._no_overlaps` del backend** (decisión F3, alineada al review adversario), para que el error se prevenga en cliente en español en vez de mostrar el 422 en inglés del backend. Se permiten **varias filas por día** (no hay unique sobre `(office_id, day_of_week)`), pero no pueden solaparse. `OfficeHoursTab` deshabilita "Guardar horarios" y marca inline los bloques solapados.

### `lib/schemas/office-closure.schema.ts`

```ts
import { z } from "zod";

export const officeClosureCreateSchema = z
  .object({
    // datetime-local inputs produce "YYYY-MM-DDTHH:MM"; the action converts to
    // ISO 8601 with offset before sending. Keep as string here.
    starts_at: z.string().min(1, "Obligatorio"),
    ends_at: z.string().min(1, "Obligatorio"),
    is_closed: z.boolean().default(true),
    reason: z.string().min(1, "Obligatorio").max(255, "Máximo 255 caracteres"),
  })
  .superRefine((data, ctx) => {
    // Mirror of the backend CHECK ends_at > starts_at.
    if (new Date(data.ends_at).getTime() <= new Date(data.starts_at).getTime()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["ends_at"],
        message: "El fin debe ser posterior al inicio.",
      });
    }
  });

export type OfficeClosureCreateInput = z.infer<typeof officeClosureCreateSchema>;
```

> **Convención**: misma estructura que `product.schema.ts` (base + `.partial()` para update + `superRefine` para cross-field). `OfficeClosure` solo necesita create + delete (no update individual — para corregir, se borra y se recrea), así que no hay `...UpdateSchema`.

## Timezones curados — `lib/constants/timezones.ts`

Lista cerrada de IANA timezones ofrecidos en el `Branch` picker. **Cerrada** para que el admin no escriba un nombre inválido que rompa la resolución de horas en `scheduling`.

```ts
// Curated subset of IANA timezones relevant to LatAm clinics. The Branch
// picker offers these; the Zod schema still accepts any string ≤ 60 chars as
// a fallback, but the UI nudges towards the curated set.
export const TIMEZONE_OPTIONS = [
  { key: "America/Lima", label: "Lima (Perú, UTC-5)" },
  { key: "America/Bogota", label: "Bogotá (Colombia, UTC-5)" },
  { key: "America/Mexico_City", label: "Ciudad de México (UTC-6)" },
  { key: "America/Santiago", label: "Santiago (Chile, UTC-4/-3)" },
  { key: "America/Argentina/Buenos_Aires", label: "Buenos Aires (UTC-3)" },
  { key: "America/Guayaquil", label: "Guayaquil (Ecuador, UTC-5)" },
  { key: "America/La_Paz", label: "La Paz (Bolivia, UTC-4)" },
  { key: "America/Caracas", label: "Caracas (Venezuela, UTC-4)" },
  { key: "America/Asuncion", label: "Asunción (Paraguay, UTC-4/-3)" },
  { key: "America/Montevideo", label: "Montevideo (Uruguay, UTC-3)" },
] as const;

export type TimezoneKey = (typeof TIMEZONE_OPTIONS)[number]["key"];

// Localized labels for the weekly pattern. Index = Python weekday (0=Mon..6=Sun).
export const WEEKDAY_LABELS = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
] as const;
```

> **`WEEKDAY_LABELS` indexado por convención Python** (0=lunes): el `day_of_week` que viaja del backend es 0..6 con 0=lunes. `WEEKDAY_LABELS[block.day_of_week]` da la etiqueta correcta sin conversión. **No** usar `toLocaleDateString` con un `Date` para esto — `Date.getDay()` usa 0=domingo y se desfasa.

## Endpoints constants — extender `lib/constants/endpoints.ts`

```ts
const ADMIN = "/api/v1/admin";
const CATALOG = "/api/v1/catalog";
const CLINIC = "/api/v1/clinic"; // ← NEW

export const ENDPOINTS = {
  AUTH: { /* existente */ },
  USERS: { /* existente */ },
  ROLES: { /* existente */ },
  PERMISSIONS: { /* existente */ },
  VERTICALS: { /* existente (catalog) */ },
  SERVICES: { /* existente (catalog) */ },
  PRODUCTS: { /* existente (catalog) */ },

  // ── Clinic module ─────────────────────────────────────────
  BRANCHES: {
    LIST: `${CLINIC}/branches/list`,
    ACTIVE: `${CLINIC}/branches/active`, // ← /active (NOT /options), aligned to catalog
    GET: (id: string) => `${CLINIC}/branches/${id}`,
    CREATE: `${CLINIC}/branches`,
    UPDATE: (id: string) => `${CLINIC}/branches/${id}`, // ← PUT (NOT PATCH)
    DELETE: (id: string) => `${CLINIC}/branches/${id}`,
  },
  OFFICES: {
    LIST: `${CLINIC}/offices/list`,
    ACTIVE: `${CLINIC}/offices/active`, // accepts ?branch_id= & ?vertical_id=
    GET: (id: string) => `${CLINIC}/offices/${id}`,
    CREATE: `${CLINIC}/offices`,
    UPDATE: (id: string) => `${CLINIC}/offices/${id}`, // ← PUT
    DELETE: (id: string) => `${CLINIC}/offices/${id}`,
    // Nested: operating hours (una key para GET + PUT bulk replace).
    OPERATING_HOURS: (id: string) => `${CLINIC}/offices/${id}/operating-hours`,
    // Nested: closures (una key para LIST + CREATE; CLOSURE para el DELETE por id).
    CLOSURES: (id: string) => `${CLINIC}/offices/${id}/closures`,
    CLOSURE: (id: string, closureId: string) =>
      `${CLINIC}/offices/${id}/closures/${closureId}`,
  },
} as const;
```

> **Query params**: `BRANCHES.ACTIVE` no toma params. `OFFICES.ACTIVE` acepta `?branch_id=` y/o `?vertical_id=` — se concatenan en el action (ver `listActiveOffices`). `CLOSURES` acepta `?from=&to=` para acotar el rango — se concatenan en `listClosures`.

## Navigation — extender `lib/constants/navigation.ts`

> ⚠ Textos UI en español ([[feedback-medisage-spanish-ui]]). Identificadores (`key`, `icon`, `url`, `permissions`) en inglés.

Insertar el grupo `clinic` entre `catalog` y `admin`:

```ts
export const NAV_ITEMS: NavItem[] = [
  { key: "home", /* … existente … */ },
  { key: "catalog", /* … existente … */ },

  // ── NEW ───────────────────────────────────────────
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

  { key: "admin", /* … existente … */ },
];
```

> **Íconos** (todos existen en `@fluentui/react-icons` v9): grupo `BuildingMultipleRegular`, Sedes `BuildingRegular`, Consultorios `ConferenceRoomRegular`. Registrarlos en el `iconMap` del `Sidebar.tsx` (mismo paso que se hizo para los íconos de catalog). Alternativas válidas si alguno no resuelve: `LocationRegular` (Sedes), `DoorRegular` (Consultorios).

> El sidebar (`components/layout/Sidebar/Sidebar.tsx`) ya filtra items por `permissions` vs `useAuth().permissions`. Si el user no tiene `MENU-CLINIC`, no ve el grupo. El detalle del office (`/clinic/offices/[id]`) **no** está en `NAV_ITEMS` (no es navegable desde el sidebar; se llega desde la lista) — su gating es `requirePermission("OFFICES_READ")` en el RSC.

## Server Actions

Mismo molde que catalog: validar con Zod en el action → llamar backend client → `revalidateTag(...)`. Tags:

| Tag | Cubre | Se invalida cuando |
|---|---|---|
| `clinic:branches` | listas y detalle de sedes | crear/editar/borrar sede |
| `clinic:offices` | listas y detalle de consultorios | crear/editar/borrar consultorio **Y** al renombrar una sede (cross-tag, ver abajo) |
| `clinic:office-hours` | patrón semanal de un office | bulk PUT de horarios |
| `clinic:office-closures` | excepciones de un office | crear/borrar una excepción |

### `actions/branch.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { branchCreateSchema, branchUpdateSchema } from "@/lib/schemas/branch.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiPaginated, type ApiSingle } from "@/types/api.types";
import type { BranchDetail, BranchItem, BranchOption } from "@/types/clinic.types";
import type { QueryRequest } from "@/types/query.types";
import type { MutationResult } from "./user.actions";

const BRANCHES_TAG = "clinic:branches";
// OfficeItem denormalizes the branch's `name` (OfficeItem.branch_name) and the
// office detail eager-loads branch (BranchOption). A branch rename must
// invalidate the offices cache too.
const OFFICES_TAG = "clinic:offices";

export async function listBranches(query: QueryRequest): Promise<ApiPaginated<BranchItem>> {
  return backendClient.post<ApiPaginated<BranchItem>>(ENDPOINTS.BRANCHES.LIST, query, {
    tags: [BRANCHES_TAG],
  });
}

export async function listActiveBranches(): Promise<BranchOption[]> {
  // `/active` returns a RAW list (response_model=list[...]), not a
  // `{success, data}` envelope — read the array directly, no `.data`.
  return backendClient.get<BranchOption[]>(ENDPOINTS.BRANCHES.ACTIVE, { tags: [BRANCHES_TAG] });
}

export async function getBranch(id: string): Promise<ApiSingle<BranchDetail>> {
  return backendClient.get<ApiSingle<BranchDetail>>(ENDPOINTS.BRANCHES.GET(id), {
    tags: [BRANCHES_TAG],
  });
}

export async function createBranch(
  input: unknown,
): Promise<MutationResult<ApiSingle<BranchDetail>>> {
  const parsed = branchCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.post<ApiSingle<BranchDetail>>(
      ENDPOINTS.BRANCHES.CREATE,
      parsed.data,
    );
    revalidateTag(BRANCHES_TAG, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function updateBranch(
  id: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<BranchDetail>>> {
  const parsed = branchUpdateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<BranchDetail>>(
      ENDPOINTS.BRANCHES.UPDATE(id), // ← PUT, not PATCH
      parsed.data,
    );
    revalidateTag(BRANCHES_TAG, "max");
    // Cross-tag: a renamed branch makes the denormalized `branch_name` in
    // cached offices stale.
    if ("name" in parsed.data) {
      revalidateTag(OFFICES_TAG, "max");
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteBranch(id: string): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.BRANCHES.DELETE(id));
    revalidateTag(BRANCHES_TAG, "max");
    return { ok: true };
  } catch (e) {
    // 409 BRANCH_HAS_ACTIVE_CHILDREN surfaces here as e.message; the
    // ConfirmDialog shows it without closing (same pattern as catalog).
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

### `actions/office.actions.ts`

Mismo molde. Tag: `clinic:offices`. `listActiveOffices` concatena los dos query params opcionales:

```ts
const OFFICES_TAG = "clinic:offices";

export async function listOffices(query: QueryRequest): Promise<ApiPaginated<OfficeItem>> {
  return backendClient.post<ApiPaginated<OfficeItem>>(ENDPOINTS.OFFICES.LIST, query, {
    tags: [OFFICES_TAG],
  });
}

export async function listActiveOffices(
  branchId?: string,
  verticalId?: string,
): Promise<OfficeOption[]> {
  const params = new URLSearchParams();
  if (branchId) params.set("branch_id", branchId);
  if (verticalId) params.set("vertical_id", verticalId);
  const qs = params.toString();
  const url = qs ? `${ENDPOINTS.OFFICES.ACTIVE}?${qs}` : ENDPOINTS.OFFICES.ACTIVE;
  // `/active` returns a RAW list (response_model=list[...]) — no envelope.
  return backendClient.get<OfficeOption[]>(url, { tags: [OFFICES_TAG] });
}

export async function getOffice(id: string): Promise<ApiSingle<OfficeDetail>> {
  // OfficeDetail includes `branch` (BranchOption) and `verticals`
  // (VerticalOption[]) — soft-deleted verticals are filtered out server-side
  // via a join on `vertical.deleted_at IS NULL`. The frontend trusts that.
  return backendClient.get<ApiSingle<OfficeDetail>>(ENDPOINTS.OFFICES.GET(id), {
    tags: [OFFICES_TAG],
  });
}

// createOffice / updateOffice / deleteOffice follow the branch.actions.ts mold.
// - createOffice: officeCreateSchema (includes vertical_ids[]).
// - updateOffice: officeUpdateSchema; PUT; vertical_ids[] (when present) is a
//   full replace of office_vertical.
// - deleteOffice: soft delete; offices have no domain children, so no 409 guard.
```

> **Reusa `VerticalOption[]` para poblar el multi-select del office form**: el create/edit del office necesita la lista de verticales activas para el `SearchableOptionList`. Se obtiene con `listActiveVerticals()` de `catalog` (`@/actions/vertical.actions`) — no se duplica un endpoint en `clinic`. Es el único acoplamiento cross-módulo del frontend de `clinic`, y es de solo lectura.

### `actions/office-hours.actions.ts`

```ts
"use server";

import { revalidateTag } from "next/cache";

import { ENDPOINTS } from "@/lib/constants/endpoints";
import { officeHoursReplaceSchema } from "@/lib/schemas/office-hours.schema";
import { backendClient } from "@/services/backend.client";
import { HttpError, type ApiSingle } from "@/types/api.types";
import type { OfficeOperatingHoursRow } from "@/types/clinic.types";
import type { MutationResult } from "./user.actions";

const HOURS_TAG = "clinic:office-hours";

export async function listOfficeHours(officeId: string): Promise<OfficeOperatingHoursRow[]> {
  // GET devuelve un envelope SingleResponse ({success, data:[...]}), una fila por
  // bloque (ordenadas día → opens_at). Se lee `data`.
  const res = await backendClient.get<ApiSingle<OfficeOperatingHoursRow[]>>(
    ENDPOINTS.OFFICES.OPERATING_HOURS(officeId),
    { tags: [HOURS_TAG, `clinic:office-hours:${officeId}`] },
  );
  return res.data;
}

// Bulk atomic replace — the ENTIRE weekly pattern is sent and replaces what
// exists. There is no per-row create/update/delete (mirrors backend decision).
export async function replaceOfficeHours(
  officeId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<OfficeOperatingHoursRow[]>>> {
  const parsed = officeHoursReplaceSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    const data = await backendClient.put<ApiSingle<OfficeOperatingHoursRow[]>>(
      ENDPOINTS.OFFICES.OPERATING_HOURS(officeId), // ← PUT bulk
      parsed.data, // { hours: [...] }
    );
    revalidateTag(`clinic:office-hours:${officeId}`, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **Tag por-office** (`clinic:office-hours:${officeId}`): el patrón de un office es independiente del de otro. Taggear por id evita invalidar el cache de todos los offices al guardar uno. El tag genérico `clinic:office-hours` se mantiene para invalidaciones masivas si se necesitaran.

### `actions/office-closure.actions.ts`

```ts
"use server";

const CLOSURES_TAG = "clinic:office-closures";

export async function listClosures(
  officeId: string,
  from?: string,
  to?: string,
): Promise<OfficeClosureItem[]> {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  const base = ENDPOINTS.OFFICES.CLOSURES(officeId);
  const url = qs ? `${base}?${qs}` : base;
  // GET devuelve un envelope SingleResponse ({success, data:[...]}). Se lee `data`.
  const res = await backendClient.get<ApiSingle<OfficeClosureItem[]>>(url, {
    tags: [CLOSURES_TAG, `clinic:office-closures:${officeId}`],
  });
  return res.data;
}

export async function createClosure(
  officeId: string,
  input: unknown,
): Promise<MutationResult<ApiSingle<OfficeClosureItem>>> {
  const parsed = officeClosureCreateSchema.safeParse(input);
  if (!parsed.success) {
    return { ok: false, fieldErrors: parsed.error.flatten().fieldErrors };
  }
  try {
    // The datetime-local strings are converted to ISO 8601 with offset before
    // sending so the backend stores correct timestamptz instants.
    const payload = {
      ...parsed.data,
      starts_at: new Date(parsed.data.starts_at).toISOString(),
      ends_at: new Date(parsed.data.ends_at).toISOString(),
    };
    const data = await backendClient.post<ApiSingle<OfficeClosureItem>>(
      ENDPOINTS.OFFICES.CLOSURES(officeId),
      payload,
    );
    revalidateTag(`clinic:office-closures:${officeId}`, "max");
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}

export async function deleteClosure(
  officeId: string,
  closureId: string,
): Promise<MutationResult<null>> {
  try {
    await backendClient.delete(ENDPOINTS.OFFICES.CLOSURE(officeId, closureId));
    revalidateTag(`clinic:office-closures:${officeId}`, "max");
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Error inesperado" };
  }
}
```

> **Cross-tag invalidation recap**: la única dependencia denormalizada en `clinic` es `OfficeItem.branch_name` ← `Branch.name`. Por eso `updateBranch` invalida `clinic:offices` **solo cuando** `"name" in parsed.data` (mismo patrón condicional que `updateVertical` → `catalog:services`/`catalog:products` en el código shipped). Horarios y closures no denormalizan nada de otra entidad, así que solo invalidan su propio tag por-office.

## Pages (RSC)

> ⚠ `metadata.title` aparece en la pestaña del browser → debe estar en español.

### `app/(main)/clinic/branches/page.tsx`

Idéntico al patrón de `catalog/verticals/page.tsx` (drawer-based, sin filtros):

```tsx
import { listBranches } from "@/actions/branch.actions";
import { requirePermission } from "@/lib/auth/session";
import { BranchesClient } from "./_components/BranchesClient";

export const metadata = { title: "Sedes" };

export default async function BranchesPage() {
  await requirePermission("MENU-CLINIC");

  const initialData = await listBranches({
    pagination: { skip: 0, limit: 10 },
    sorting: { sort_by: "name", sort_order: "asc" },
  });

  return <BranchesClient initialData={initialData} />;
}
```

### `app/(main)/clinic/offices/page.tsx` (LISTA)

Análogo a `catalog/services/page.tsx` (filtro por `branch_id` en query param). El create vive en un drawer; ver/editar navega al detalle.

```tsx
import { listActiveBranches } from "@/actions/branch.actions";
import { listOffices } from "@/actions/office.actions";
import { requirePermission } from "@/lib/auth/session";
import type { QueryRequest } from "@/types/query.types";

import { OfficesClient } from "./_components/OfficesClient";

export const metadata = { title: "Consultorios" };

interface PageProps {
  searchParams: Promise<{ branch_id?: string }>;
}

export default async function OfficesPage({ searchParams }: PageProps) {
  await requirePermission("MENU-CLINIC");
  const { branch_id } = await searchParams;

  const filters: QueryRequest["filters"] = branch_id
    ? {
        filters: [
          {
            operator: "AND",
            conditions: [{ field: "branch_id", operator: "eq", value: branch_id }],
          },
        ],
      }
    : null;

  const [initialData, branches] = await Promise.all([
    listOffices({
      pagination: { skip: 0, limit: 10 },
      sorting: { sort_by: "name", sort_order: "asc" },
      filters,
    }),
    listActiveBranches(),
  ]);

  return <OfficesClient initialData={initialData} branches={branches} />;
}
```

### Página de detalle del Office — `app/(main)/clinic/offices/[id]/page.tsx`

**Nuevo vs catalog** (que era drawer-only). El detalle de un consultorio es una **página dedicada con tabs**, porque agrupa cuatro vistas que no caben cómodas en un drawer (Detalles · **Horarios** semanales editables · **Excepciones** con calendario · Auditoría) y es reutilizable como patrón "entidad con sub-recursos" para módulos futuros (`staff`, `scheduling`).

```tsx
import { notFound } from "next/navigation";

import { getOffice } from "@/actions/office.actions";
import { listActiveVerticals } from "@/actions/vertical.actions";
import { requirePermission } from "@/lib/auth/session";
import { HttpError } from "@/types/api.types";

import { OfficeDetailShell } from "./_components/OfficeDetailShell";

interface PageProps {
  params: Promise<{ id: string }>;
  // Tab routing lives in a query param, NOT a sub-route: ?tab=hours|closures|audit.
  // One URL, deep-linkable, no nested layout.tsx needed.
  searchParams: Promise<{ tab?: string }>;
}

export async function generateMetadata({ params }: PageProps) {
  const { id } = await params;
  try {
    const res = await getOffice(id);
    return { title: `${res.data.name} · Consultorio` };
  } catch {
    return { title: "Consultorio" };
  }
}

export default async function OfficeDetailPage({ params, searchParams }: PageProps) {
  await requirePermission("OFFICES_READ");
  const { id } = await params;
  const { tab } = await searchParams;

  let office;
  try {
    office = await getOffice(id);
  } catch (e) {
    if (e instanceof HttpError && e.status === 404) notFound();
    throw e; // let error.tsx handle anything else
  }

  // The verticals list feeds the Details tab's multi-select (reused from catalog).
  const verticals = await listActiveVerticals();

  return (
    <OfficeDetailShell
      office={office.data}
      verticals={verticals}
      initialTab={tab === "hours" || tab === "closures" || tab === "audit" ? tab : "details"}
    />
  );
}
```

> **Por qué tab en query param y no sub-rutas** (`/offices/[id]/hours`): un solo `getOffice` poblando el header (código, sede, estado) sirve a las cuatro vistas; sub-rutas duplicarían ese fetch o forzarían un `layout.tsx` con su propio data-loading. El query param `?tab=` es deep-linkable, sobrevive refresh y no exige `layout.tsx`. Cada tab carga **sus propios datos en el cliente** (`listOfficeHours`, `listClosures`) cuando se selecciona, no en el RSC — así el primer paint es instantáneo y los sub-recursos se hidratan on-demand.

## Client components — esqueletos

> **No reproduzco aquí los archivos completos** — siguen el patrón exacto de `catalog/verticals/_components/VerticalsClient.tsx` + `admin/users/_components/UserDrawer.tsx`. Documento las diferencias específicas a clinic.

### `BranchesClient.tsx`

Sigue el patrón de `VerticalsClient.tsx` (drawer-based). Diferencias:

- `queryKey: "clinic:branches"`.
- `fetcher: listBranches`.
- `searchFields: ["code", "name", "city"]`.
- `defaultSort: { field: "name", order: "asc" }`.
- Columns: `actions`, `code`, `name`, `city`, `offices_count` (numeric), `active` (Badge "Activa"/"Deshabilitada"), `updated_on`. Ver [`ui.md`](ui.md#pantallas).
- RowActions: `view` (abre drawer `view`), `edit` (gated `BRANCHES_UPDATE`), `delete` (gated `BRANCHES_DELETE`, abre `ConfirmDialog`).
- Botón "Nueva sede" gated `BRANCHES_CREATE`.
- **`ConfirmDialog`** para delete: si el delete falla con `409 BRANCH_HAS_ACTIVE_CHILDREN`, mostrar `result.error` dentro del dialog **sin cerrarlo** (mismo flujo que `VerticalsClient` con su 409). El backend devuelve el mensaje "No se puede eliminar — la sede tiene N consultorios activos".

### `BranchDrawer.tsx`

Sigue el patrón de `VerticalDrawer.tsx`. 2 tabs: `Details` + `Audit` (sin Access; Branch no tiene M:N propias). Diferencias:

- Más campos que vertical → `Details` tab con grid de 2 columnas:
  - `code` (slug, **disabled en edit/view**), `name`.
  - `address_line` (full width), `district`, `city`, `region`, `country` (2 letras, default "PE"), `postal_code`.
  - `latitude`, `longitude` (numeric strings).
  - `phone`, `email`.
  - `timezone` → **Dropdown** poblado con `TIMEZONE_OPTIONS` (no input libre).
- `form.reset` después de `getBranch(id)` mapea `null → undefined` en los opcionales (mismo patrón que `UserDrawer`):
  ```ts
  form.reset({
    name: res.data.name,
    address_line: res.data.address_line,
    district: res.data.district ?? undefined,
    city: res.data.city,
    region: res.data.region ?? undefined,
    country: res.data.country,
    postal_code: res.data.postal_code ?? undefined,
    latitude: res.data.latitude ?? undefined,
    longitude: res.data.longitude ?? undefined,
    phone: res.data.phone ?? undefined,
    email: res.data.email ?? undefined,
    timezone: res.data.timezone,
  });
  ```
- `Audit` tab idéntico al de `UserDrawer` (`created_on/by`, `updated_on/by`, Badge de estado).

### `OfficesClient.tsx`

Sigue el patrón de `ServicesClient.tsx`. Diferencias clave:

- Recibe `branches: BranchOption[]` como prop (para el filtro y para el create drawer).
- State `branchFilter: string | null` sincronizado con URL (`nuqs`); Dropdown de sede en toolbar + chip "Filtrado por: Sede X" con ✕.
- `queryKey: "clinic:offices"`, `searchFields: ["code", "name"]`, `defaultSort: { field: "name", order: "asc" }`.
- Columns: `actions`, `code`, `name`, `branch_name` (denormalizado — sin join), `verticals_count` (numeric), `active` (Badge), `updated_on`. Ver [`ui.md`](ui.md#pantallas).
- **RowActions = navegación, no drawer**:
  ```ts
  {
    key: "view",
    label: "Ver",
    icon: <EyeRegular />,
    onSelect: (o) => router.push(`/clinic/offices/${o.id}`),
  },
  {
    key: "edit",
    label: "Editar",
    icon: <EditRegular />,
    permissions: ["OFFICES_UPDATE"],
    onSelect: (o) => router.push(`/clinic/offices/${o.id}?tab=details`),
  },
  {
    key: "delete",
    label: "Eliminar",
    icon: <DeleteRegular />,
    permissions: ["OFFICES_DELETE"],
    danger: true,
    onSelect: (o) => { setDeleteError(null); setDeleteTarget(o); },
  },
  ```
  (También se puede hacer la fila completa clicable → `router.push(/clinic/offices/${o.id})`.)
- Botón "Nuevo consultorio" gated `OFFICES_CREATE` → abre `OfficeCreateDrawer`. **El create sigue siendo drawer** (rápido, no necesita las tabs de sub-recursos hasta que el office existe).

### `OfficeCreateDrawer.tsx`

Drawer **solo-create** (no edit/view). Sigue `ServiceDrawer` + el `SearchableOptionList` de `UserDrawer`. Campos:

- Dropdown `Sede *` (poblado con `branches: BranchOption[]`).
- Input `code` (slug).
- Input `name`.
- Inputs `room_number`, `floor`.
- Textarea `description`.
- **Multi-select de verticales aptas** vía `SearchableOptionList` (el helper de `UserDrawer.tsx`), poblado con `listActiveVerticals()`:
  ```tsx
  <Controller
    control={form.control}
    name="vertical_ids"
    render={({ field }) => (
      <SearchableOptionList
        options={verticals.map((v) => ({ id: v.id, primary: v.name, secondary: v.code }))}
        selected={field.value}
        disabled={false}
        onToggle={(id) => {
          const next = field.value.includes(id)
            ? field.value.filter((x) => x !== id)
            : [...field.value, id];
          field.onChange(next);
        }}
        searchPlaceholder="Buscar verticales…"
        emptyMessage="Ninguna vertical coincide con la búsqueda."
      />
    )}
  />
  ```
- En `onSuccess`: cerrar el drawer y `router.push(/clinic/offices/${result.data.data.id})` para llevar al usuario directo al detalle recién creado (donde configurará horarios y excepciones).

### `OfficeDetailShell.tsx`

Cliente. Recibe `office: OfficeDetail`, `verticals: VerticalOption[]`, `initialTab`. Responsabilidades:

- Header con: nombre del office, badge de estado, `code`, sede (link a `/clinic/offices?branch_id=${office.branch_id}`), botón "Volver a consultorios".
- `TabList` (Fluent) con 4 tabs: **Detalles · Horarios · Excepciones · Auditoría**. Al cambiar de tab, actualizar `?tab=` con `nuqs` (`useQueryState`) para que sea deep-linkable.
- Renderiza el tab activo. Cada tab carga sus propios datos:
  ```tsx
  type TabId = "details" | "hours" | "closures" | "audit";

  {tab === "details" ? (
    <OfficeDetailsTab office={office} verticals={verticals} />
  ) : tab === "hours" ? (
    <OfficeHoursTab officeId={office.id} branchTimezone={office.branch.timezone} />
  ) : tab === "closures" ? (
    <OfficeClosuresTab officeId={office.id} branchTimezone={office.branch.timezone} />
  ) : (
    <OfficeAuditTab office={office} />
  )}
  ```
- Tabs `Horarios`/`Excepciones` se ocultan o muestran como solo-lectura según permisos: si el user no tiene `OFFICE_HOURS_WRITE`, el tab Horarios se ve en modo lectura (sin botón Guardar); igual para `OFFICE_CLOSURES_WRITE`. Usar `usePermissions()`.

### `OfficeDetailsTab.tsx`

Form de edición del office (los campos no-sub-recurso). Reusa el patrón `VerticalDrawer`/`ServiceDrawer` pero **inline en la página** (no drawer). Diferencias:

- `branch_id` se muestra como texto fijo (la sede, **disabled** — branch es inmutable post-create), `code` también disabled.
- Inputs editables: `name`, `room_number`, `floor`, `description`, `active` (Checkbox).
- **Multi-select de verticales aptas** (`SearchableOptionList`, mismo helper) precargado con `office.verticals.map(v => v.id)`. Al guardar manda `vertical_ids` completo → backend reemplaza la M:N.
- Submit → `updateOffice(office.id, values)`; en éxito, `router.refresh()` para re-pintar el header con los datos nuevos.

### `OfficeHoursTab.tsx` (Horarios)

El editor del **patrón semanal**, gobernado por el **bulk PUT atómico**. Pieza más nueva del módulo.

- Carga inicial: `listOfficeHours(officeId)` (en `useEffect` o `useQuery`), agrupa por `day_of_week`.
- UI: 7 secciones (Lunes…Domingo, usando `WEEKDAY_LABELS`). Cada día lista sus bloques (`opens_at`–`closes_at`) con un "+" para agregar bloque y "🗑" para quitarlo. **Varios bloques por día permitidos** (mañana + tarde).
- El estado vive en un array local `blocks: OfficeHoursBlockInput[]`. **No se persiste bloque a bloque** — hay un único botón **"Guardar horarios"** (gated `OFFICE_HOURS_WRITE`) que envía **todo el patrón** vía `replaceOfficeHours(officeId, { hours: blocks })`.
- Validación con `officeHoursReplaceSchema` antes de enviar; errores por bloque (`closes_at > opens_at`) se muestran inline en la fila del bloque.
- Mensaje aclaratorio (`MessageBar intent="info"`): "Las horas se interpretan en la zona horaria de la sede ({office.branch.timezone}). Guardar reemplaza todo el horario semanal."
- Esqueleto del submit:
  ```tsx
  const onSave = () => {
    setServerError(null);
    startTransition(async () => {
      const result = await replaceOfficeHours(officeId, { hours: blocks });
      if (!result.ok) {
        setServerError(result.error ?? "No se pudieron guardar los horarios");
        setFieldErrors(result.fieldErrors ?? null);
        return;
      }
      // success toast / refresh; the per-office tag was revalidated server-side
    });
  };
  ```

> **Por qué "guardar todo" y no auto-save por bloque**: el patrón semanal es un agregado coherente; editar bloques individuales abre la puerta a estados intermedios inválidos ("borré tarde antes de crear la nueva"). Es la misma decisión que el backend (bulk replace) reflejada en la UX. Ver [`README.md`](README.md#officeoperatinghours-se-gestiona-con-bulk-put-reemplazo-atómico-no-crud-individual).

### `OfficeClosuresTab.tsx` (Excepciones)

CRUD individual de excepciones (cierres / aperturas extra).

- Carga: `listClosures(officeId, from?, to?)`. Por defecto un rango (ej. próximos 90 días); filtros de rango opcionales.
- Lista/tabla de excepciones: `starts_at`–`ends_at` (formateados con `lib/utils/date.ts` — son `timestamptz`), Badge "Cierre" (rojo) / "Apertura extra" (verde) según `is_closed`, `reason`, acción "Eliminar" (gated `OFFICE_CLOSURES_WRITE`).
- Botón "Agregar excepción" (gated `OFFICE_CLOSURES_WRITE`) → abre un sub-drawer/dialog con el form (`officeClosureCreateSchema`):
  - `starts_at`, `ends_at` → `Input type="datetime-local"`.
  - `is_closed` → `RadioGroup` "Cierre" / "Apertura extraordinaria" (default Cierre).
  - `reason` → Input (obligatorio).
  - Submit → `createClosure(officeId, values)` (el action convierte a ISO con offset).
- Delete → `ConfirmDialog` + `deleteClosure(officeId, closureId)`.
- `MessageBar intent="info"`: explica los dos casos — "Un cierre bloquea la atención en ese rango; una apertura extra habilita atención fuera del horario semanal."

### `OfficeAuditTab.tsx`

Idéntico al `AuditTab` de `UserDrawer.tsx`: estado (Badge), id, `created_on/by`, `updated_on/by`. Reusa el mismo layout de grid.

## Decisiones del frontend (recap)

| Decisión | Por qué |
|---|---|
| `PUT` para updates (no `PATCH`) | Alineación a catalog shipped (`backendClient.put`); evita drift back↔front. |
| `/active` para dropdowns (no `/options`) | Misma convención que `ROLES.ACTIVE`/`VERTICALS.ACTIVE` shipped. |
| Branches drawer-based; Office detail = página | El office tiene 4 sub-vistas (Detalles/Horarios/Excepciones/Auditoría) que no caben en un drawer; reusable como patrón "entidad con sub-recursos". |
| Office list conserva drawer de creación | Crear es rápido y no necesita las tabs hasta que el office existe; tras crear, navega al detalle. |
| Tab del detalle en `?tab=` (query param) | Un solo `getOffice` sirve a las 4 vistas; deep-linkable; sin `layout.tsx` extra. |
| Sub-recursos cargan en cliente, no en RSC | Primer paint instantáneo; horarios/closures se hidratan on-demand al abrir su tab. |
| `code`/`branch_id` inmutables post-create | El backend lo prohibe; el form lo refleja con `disabled` en edit. |
| Horarios = bulk "Guardar todo", no auto-save | Patrón semanal es un agregado coherente; evita estados intermedios inválidos. |
| `vertical_ids` full-replace en update | Refleja el reemplazo atómico de `office_vertical` del backend. |
| Multi-select de verticales reusa `SearchableOptionList` | Mismo helper que roles/permisos en `UserDrawer`; cero código nuevo. |
| Verticales soft-deleted filtradas server-side | El backend hace el join `deleted_at IS NULL`; el frontend confía. No se extiende el guard de delete de catalog (evita acoplamiento). |
| lat/long como string en wire | Evita pérdida de precisión en JS; `parseFloat` al validar/render. |
| Horas (`time`) NO pasan por `new Date()` | Son local-time sin TZ; instantes (`timestamptz`) sí usan `lib/utils/date.ts`. |
| `WEEKDAY_LABELS` indexado por convención Python (0=lunes) | El `day_of_week` viaja 0=lunes; usar `Date.getDay()` (0=domingo) se desfasaría. |
| Timezone como Dropdown curado | Evita strings IANA inválidos que romperían `scheduling`. |
| Cross-tag: rename de Branch invalida `clinic:offices` | `OfficeItem.branch_name` está denormalizado (mismo patrón que `updateVertical`). |
| Sin bulk actions, sin duplicar, sin import CSV | Postergados al MVP+1 (igual que catalog). |

## Checklist de implementación (mapeado a fases F0–F4)

> Las fases espejan el plan por entidad de [`backend.md`](backend.md#checklist-de-implementación) y [`ui.md`](ui.md). Cada checkbox es lado frontend.

### F0 — Prep (andamiaje compartido)

- [ ] Extender `src/lib/constants/endpoints.ts` con `BRANCHES` + `OFFICES` (incluye nested `HOURS_*`, `CLOSURES_*`). Verbos `PUT`, rutas `/active`.
- [ ] Extender `src/lib/constants/navigation.ts` con el grupo `clinic` ("Clínica" → Sedes, Consultorios), `permissions: ["MENU-CLINIC"]`.
- [ ] Registrar íconos `BuildingRegular`, `BuildingMultipleRegular`, `ConferenceRoomRegular` en el `iconMap` del `Sidebar.tsx`.
- [ ] Crear `src/types/clinic.types.ts` (todas las interfaces; reusa `VerticalOption`).
- [ ] Crear `src/lib/constants/timezones.ts` (`TIMEZONE_OPTIONS`, `WEEKDAY_LABELS`).
- [ ] **Permisos test (F0)**: como user con `MENU-CLINIC`, el grupo "Clínica" aparece con Sedes y Consultorios. Sin `MENU-CLINIC`, no aparece.

### F1 — Branch (Sede)

- [ ] Crear `src/lib/schemas/branch.schema.ts` (code/country/timezone/lat-long).
- [ ] Crear `src/actions/branch.actions.ts` (list/active/get/create/update[PUT]/delete; cross-tag `clinic:offices` en rename).
- [ ] Crear `src/app/(main)/clinic/branches/page.tsx` (`metadata.title = "Sedes"`, prefetch).
- [ ] Crear `_components/BranchesClient.tsx` (tabla drawer-based) + `BranchDrawer.tsx` (Details + Audit, timezone Dropdown).
- [ ] **Smoke test (F1)**: navegar `/clinic/branches` → tabla vacía → crear sede → ver fila → editar → soft-delete → tabla vacía. `revalidateTag("clinic:branches")` refleja cambios sin refresh.
- [ ] **Permisos test (F1)**: sin `BRANCHES_CREATE` no aparece "Nueva sede"; sin `BRANCHES_UPDATE` el menú row no muestra "Editar"; sin `BRANCHES_DELETE` no muestra "Eliminar".

### F2 — Office + M:N + detail shell

- [ ] Crear `src/lib/schemas/office.schema.ts` (`vertical_ids[]`, `branch_id`).
- [ ] Crear `src/actions/office.actions.ts` (list/active[branch_id,vertical_id]/get/create/update[PUT]/delete).
- [ ] Crear `src/app/(main)/clinic/offices/page.tsx` (lista, filtro `branch_id`) + `_components/OfficesClient.tsx` (RowActions navegan) + `OfficeCreateDrawer.tsx` (multi-select verticales vía `SearchableOptionList`).
- [ ] Crear `src/app/(main)/clinic/offices/[id]/page.tsx` (detail RSC, `?tab=` routing, `getOffice` + `listActiveVerticals`) + `_components/OfficeDetailShell.tsx` + `OfficeDetailsTab.tsx` + `OfficeAuditTab.tsx` (shells de Horarios/Excepciones placeholder hasta F3/F4).
- [ ] **Smoke test (F2)**: crear office en una sede → al guardar navega a `/clinic/offices/{id}` → editar nombre y verticales → ver header actualizado.
- [ ] **Cross-tag test (F2)**: renombrar una sede → la columna `branch_name` en la lista de consultorios refleja el nombre nuevo (cache `clinic:offices` invalidado).
- [ ] **Error 409 test (F2)**: crear office activo `O1` en sede `S1`. Intentar delete `S1` → `ConfirmDialog` muestra "No se puede eliminar — la sede tiene 1 consultorio activo" sin cerrarse (`BRANCH_HAS_ACTIVE_CHILDREN`).
- [ ] **Deep-link test (F2)**: navegar a `/clinic/offices?branch_id=X` → tabla filtrada + chip. Click ✕ → tabla sin filtro. Navegar a `/clinic/offices/{id}?tab=details` directo → abre el tab Detalles.
- [ ] **Permisos test (F2)**: sin `OFFICES_CREATE` no aparece "Nuevo consultorio"; sin `OFFICES_READ` el RSC del detalle redirige (requirePermission).

### F3 — OfficeOperatingHours (Horarios tab, bulk PUT)

- [ ] Crear `src/lib/schemas/office-hours.schema.ts` (`day_of_week` 0..6, `closes_at > opens_at` superRefine, varios bloques/día).
- [ ] Crear `src/actions/office-hours.actions.ts` (`listOfficeHours`, `replaceOfficeHours` [PUT bulk], tag por-office).
- [ ] Crear `_components/OfficeHoursTab.tsx` (7 días con `WEEKDAY_LABELS`, +/− bloques, un único "Guardar horarios").
- [ ] **Smoke test (F3)**: en un office, agregar Lunes 8:00–13:00 y 16:00–20:00, Martes 9:00–18:00 → "Guardar horarios" → recargar el tab → bloques persisten. Cambiar uno → guardar → reemplazo atómico verificado (no quedan bloques viejos).
- [ ] **Validación inline test (F3)**: poner `closes_at` ≤ `opens_at` en un bloque → error inline en `closes_at`, submit bloqueado.
- [ ] **Permisos test (F3)**: con `OFFICE_HOURS_READ` pero sin `OFFICE_HOURS_WRITE`, el tab Horarios se ve en solo-lectura (sin botón Guardar, sin +/−).

### F4 — OfficeClosure (Excepciones tab, CRUD)

- [ ] Crear `src/lib/schemas/office-closure.schema.ts` (`ends_at > starts_at` superRefine).
- [ ] Crear `src/actions/office-closure.actions.ts` (`listClosures[from,to]`, `createClosure` [convierte a ISO], `deleteClosure`, tag por-office).
- [ ] Crear `_components/OfficeClosuresTab.tsx` (lista con Badge Cierre/Apertura, form en sub-drawer, delete con ConfirmDialog).
- [ ] **Smoke test (F4)**: agregar un cierre ("Feriado 28 julio", `is_closed=true`) y una apertura extra (`is_closed=false`) → ambos aparecen con su Badge correcto → eliminar uno → desaparece (cache por-office invalidado).
- [ ] **Validación inline test (F4)**: poner `ends_at` ≤ `starts_at` → error inline en `ends_at`, submit bloqueado.
- [ ] **Permisos test (F4)**: con `OFFICE_CLOSURES_READ` pero sin `OFFICE_CLOSURES_WRITE`, el tab muestra la lista pero oculta "Agregar excepción" y "Eliminar".

## Tareas adicionales (traducción del template existente)

La traducción del template (`navigation.ts`, `DataTable`, `ConfirmDialog`, login, etc.) **ya se hizo en el PR de catalog** (ver [`../catalog/frontend.md`](../catalog/frontend.md#tareas-adicionales-traducción-del-template-existente)). Para `clinic` no hay deuda de traducción del template — todos los strings nuevos de este módulo nacen en español. Verificar al implementar:

- [ ] `metadata.title` de cada página en español ("Sedes", "Consultorios", "{nombre} · Consultorio").
- [ ] Todos los `label` de `NAV_ITEMS.clinic` en español ("Clínica", "Sedes", "Consultorios").
- [ ] Empty states, placeholders, badges (`Activa`/`Deshabilitada`, `Cierre`/`Apertura extra`), confirm dialogs y `MessageBar` informativos en español (ver tabla de copy en [`ui.md`](ui.md#texto-ux-writing)).
- [ ] Mensajes de error del 409 `BRANCH_HAS_ACTIVE_CHILDREN` que vienen del backend ya en español (coordinar con [`backend.md`](backend.md) — los `detail` de las excepciones de dominio se devuelven en español para mostrarse directo).

## TODOs deliberados (postergados al MVP+1)

- [ ] **Mapa interactivo** para `latitude`/`longitude` (Leaflet / Google Maps embed en el `BranchDrawer`) en vez de inputs numéricos. Postergar.
- [ ] **Copiar horario** de un office a otro (o "aplicar a todos los días L-V") — atajo UX para el editor de horarios. Postergar; el +/− por día basta para MVP.
- [ ] **Vista calendario** para las excepciones (en vez de tabla) — útil cuando un office acumula muchos cierres. Postergar; la tabla con filtro de rango basta.
- [ ] **Indicador "horario efectivo hoy"** en el detalle del office (cruzando patrón + closures) — adelanto de lo que hará `scheduling`. Postergar hasta tener `scheduling`.
- [ ] **i18n framework** (`next-intl` o similar) — por ahora todos los strings son literales en español directo en componentes. Postergar (mismo criterio que catalog).
