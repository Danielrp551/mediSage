# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Específico del frontend. Para contratos cross-cutting (envelopes, auth flow end-to-end, cómo agregar un módulo completo), leer primero el [CLAUDE.md raíz](../CLAUDE.md).

## Stack

- **Next.js 16** (App Router) + **React 19** + **TypeScript 5.7**
- **Fluent UI 9** (`@fluentui/react-components`) — no Material/shadcn. Componentes nuestros (`DataTable`, `Drawer`, `Pagination`, etc.) están construidos sobre Fluent.
- **TanStack Query 5** para cache + refetch (cliente)
- **nuqs** para URL state (paginación, filtros, sort)
- **react-hook-form 7** + **Zod 3** para forms (validación compartida client/server)
- **jose** para decode local del JWT (solo lee `exp`, no valida firma — eso es del backend)
- **eslint** (config Next 16) + **prettier**
- **turbopack** en dev

## Comandos

```bash
npm install
npm run dev           # next dev --turbopack
npm run build         # producción
npm run start         # serve build

npm run lint          # next lint (eslint)
npm run typecheck     # tsc --noEmit
npm run format        # prettier --write
npm run format:check  # prettier --check
```

`tsc --noEmit` y `next lint` corren en CI (`frontend-ci.yml`); ambos deben pasar antes de mergear.

## Estructura

```
src/
├── app/                Routes (App Router)
│   ├── (auth)/         Route group público
│   │   └── login/
│   ├── (main)/         Route group autenticado — layout llama requireAuth()
│   │   ├── dashboard/
│   │   └── admin/
│   ├── layout.tsx      Root: carga /auth/me en server, hidrata AuthProvider
│   ├── error.tsx       Error boundary global
│   └── not-found.tsx
├── actions/            Server Actions ("use server")
├── components/
│   ├── ui/             Componentes genéricos (DataTable, Drawer, …)
│   ├── layout/         Sidebar, TopBar
│   └── guards/         PermissionGuard
├── hooks/              Client hooks (useTableQuery, usePermissions, …)
├── lib/
│   ├── auth/           session.ts (server-only), jwt.ts
│   ├── constants/      endpoints, navigation, cookies
│   ├── schemas/        Zod
│   └── utils/          query-builder, cn, date
├── providers/          AppProviders, AuthProvider
├── services/
│   └── backend.client.ts   ← server-only HTTP a FastAPI
└── types/              Espejo de los Pydantic schemas

middleware.ts           ← edge middleware (en frontend/, NO en src/)
```

Convención: dentro de una ruta, los componentes locales viven en `_components/` (el underscore previene que Next los trate como rutas). Patrón en [`app/(auth)/login/_components/LoginForm.tsx`](src/app/(auth)/login/_components/LoginForm.tsx).

## Server vs Client — la división crítica

| Archivo / símbolo | Dónde corre | Notas |
|---|---|---|
| `page.tsx`, `layout.tsx`, `loading.tsx`, `error.tsx` | **Server** por default | Pueden ser `async`, llaman al backend directo |
| Cualquier archivo que importe `react-hook-form`, `useState`, `useQuery`, … | **Client** | Necesita `"use client"` al inicio |
| `actions/*.actions.ts` | **Server** (action runtime) | `"use server"` al inicio del archivo |
| `services/backend.client.ts` | **Server-only** (importa `"server-only"`) | Importarlo desde un client component **rompe el build** intencionalmente |
| `lib/auth/session.ts` | **Server-only** | Lee/escribe cookies, redirige |
| `middleware.ts` | **Edge runtime** | Sin Node APIs; solo Web APIs + `jose` |
| `providers/AuthProvider.tsx`, `usePermissions`, `useTableQuery` | **Client** | El provider se hidrata con datos del server |

**El navegador nunca debe ver el JWT.** Esto se hace cumplir así:
- Tokens viven en cookies `httpOnly` — JS del cliente no los puede leer.
- `BACKEND_URL` es server-only env (no `NEXT_PUBLIC_*`).
- `backend.client.ts` declara `import "server-only"` → import desde cliente falla al build.
- Si un componente cliente necesita hablar con el backend, lo hace **vía Server Action**, no vía `fetch` directo.

## Auth flow (cómo se compone)

```
Browser ──cookie─▶ middleware.ts (edge) ──[refresh si toca]──▶ RSC ──Bearer──▶ FastAPI
                       │                                         │
                       │ writes cookies on response              │ reads cookie via cookies()
                       │                                         │
                       └─ rewrites both cookies if refresh OK    └─ no puede SET cookies (Next 16: read-only en RSC)
```

**El middleware refresca proactivamente.** El backend client **no** intenta refresh on-401 porque `cookies().set()` desde un Server Component lanza en Next 16. La división de responsabilidades:

- **`middleware.ts`** (edge): chequea `access_token`, si está por expirar (skew 30 s) llama `/auth/refresh`, escribe ambas cookies en la response, deja pasar. Si no hay refresh, redirige a `/login`.
- **`services/backend.client.ts`** (server): solo lee la cookie actual e inyecta `Bearer …`. Si recibe 401, **deja que el error propague** — la próxima request del usuario pasará por middleware y se refrescará ahí.
- **`lib/auth/session.ts`**: helpers para Server Actions (`writeSession`, `clearSession`, `requireAuth`, `requirePermission`). `writeSession` solo se usa después de `/auth/login` (la única operación que el middleware no puede hacer).

## El JWT y AuthProvider

- **Root layout** ([`app/layout.tsx`](src/app/layout.tsx)) llama `backendClient.get("/auth/me")` en server, pasa el resultado como `initialUser` a `AppProviders`.
- **`AuthProvider`** crea un Context con `user`, `permissions` (Set), `hasPermission`, `hasAnyPermission`, `hasAllPermissions`. **El cliente nunca decodifica el JWT** — usa los permisos que el server ya extrajo.
- Para chequeos en cliente: `useAuth()` o `usePermissions()`.
- Para gating UI: `<PermissionGuard anyOf={["X"]}>...</PermissionGuard>`.

**Stale permissions**: si un admin revoca un permiso, el `permissions` del `AuthProvider` sigue mostrando el viejo valor hasta que la página se recargue Y el access token se rote (≤ 15 min default). Documentado, esperado.

## Server Actions — el patrón

Todas las mutaciones (create, update, delete, login, logout) son **Server Actions**, no llamadas HTTP del cliente. Estructura canónica ([`actions/user.actions.ts`](src/actions/user.actions.ts)):

```ts
"use server";

export async function createUser(input: unknown): Promise<MutationResult<UserCreatedResponse>> {
  const parsed = userCreateSchema.safeParse(input);                    // 1. Validar con Zod (mismo schema que el form)
  if (!parsed.success) return { ok: false, fieldErrors: ... };
  try {
    const data = await backendClient.post(ENDPOINTS.USERS.CREATE, parsed.data);  // 2. Llamar backend
    revalidateTag("admin:users");                                       // 3. Invalidar cache
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e instanceof HttpError ? e.message : "Unexpected error" };
  }
}
```

Convenciones:
- **Validar con Zod en el action** aunque el form ya lo haga — defensa en profundidad si alguien arma el form-data manualmente.
- **`revalidateTag(...)`** después de un mutate exitoso. Los reads que usan ese tag (vía `backend.client.ts` con `tags: [...]`) se invalidan automáticamente.
- **Returns**: `{ ok, data?, error?, fieldErrors? }` para mutaciones. Para acciones que redirigen (login/logout), llamar `redirect(...)` **fuera del try/catch** (es una excepción que Next captura).

## Listados paginados — el patrón `useTableQuery`

Patrón de referencia: [`admin/users/page.tsx`](src/app/(main)/admin/users/page.tsx). Tres piezas:

1. **Server Component** (`page.tsx`) pre-fetcha la primera página y revalida con tag:
   ```tsx
   await requirePermission("MENU-USERS");
   const initialData = await listUsers({
     pagination: { skip: 0, limit: 10 },
     sorting: { sort_by: "created_on", sort_order: "desc" },
     filters: null,
   });
   return <UsersTable initialData={initialData} />;
   ```

2. **Server Action** (`listUsers`) llama backend con `tags: ["admin:users"]`.

3. **Client Component** (`UsersTable`) usa `useTableQuery`:
   ```tsx
   const { query, page, setPage, setSearch, setSort } = useTableQuery({
     queryKey: "admin:users",
     fetcher: listUsers,
     searchFields: ["email", "first_name", "last_name"],
     defaultSort: { field: "created_on", order: "desc" },
     initialData,                       // ← server-prefetched payload
   });
   ```

`useTableQuery` sincroniza paginación / search / sort con la URL via `nuqs` (sobrevive refresh, comparable por link). El `initialData` se usa **solo** mientras la URL refleja el request default; al primer cambio TanStack Query refetcha.

## Construcción del `QueryRequest` — `QueryParamsBuilder`

Espejo del backend (`app/shared/base_schemas.py:QueryRequest`). API fluent:

```ts
const payload = new QueryParamsBuilder()
  .page(2, 25)
  .sort("created_on", "desc")
  .where("active", "eq", true)
  .whereOr([{ field: "first_name", operator: "contains", value: "ana" }])
  .build();
```

- **Valores vacíos** (`null`, `undefined`, `""`) se ignoran — no genera filtros muertos.
- **`where` agrega un AND group**, **`whereOr` agrega un OR group**. Ambos pueden coexistir; el backend los combina con AND entre grupos.
- Operadores válidos: `eq, neq, contains, starts_with, gt, gte, lt, lte`. Para agregar uno, primero actualizar el enum en `app/shared/base_schemas.py:FilterOperator` (backend) y luego `types/query.types.ts`.

## Errores y `HttpError`

`backend.client.ts` lanza `HttpError(status, body)` con `body.detail` como `message`. Patrones:

- **Server Action** ([`actions/user.actions.ts`](src/actions/user.actions.ts)): capturar `HttpError`, devolver `{ ok: false, error: e.message }`. El form muestra el `error` con un `<MessageBar>`.
- **Server Component**: **no capturar** — dejar que `error.tsx` lo agarre. Si el status es 401, `middleware.ts` en el próximo request redirige a `/login`.
- **422 (validación)**: el backend devuelve `errors: [...]` con la lista de Pydantic. El frontend valida con Zod antes de mandar, así que llegar aquí es un drift schema — loguear y tratarlo como error genérico.

## Forms — `react-hook-form` + Zod

Patrón en [`(auth)/login/_components/LoginForm.tsx`](src/app/(auth)/login/_components/LoginForm.tsx):

```tsx
"use client";
const form = useForm<LoginInput>({
  resolver: zodResolver(loginSchema),   // ← el MISMO schema que el Server Action usa
  defaultValues: { email: "", password: "" },
});

const [state, action, pending] = useActionState(loginAction, null);
// state.fieldErrors → mostrar bajo cada input
// state.error → MessageBar
```

- **Schemas Zod** viven en `src/lib/schemas/` y son importados tanto por el form (cliente) como por el Server Action (server) → drift imposible.
- **`useActionState`** (React 19) reemplaza a `useFormState`. Maneja `pending` automáticamente — no agregar otro `useState` para loading.
- **FormField** ([`components/ui/Form/FormField.tsx`](src/components/ui/Form/FormField.tsx)) es nuestro wrapper de Fluent `Field` + `Input` con manejo de errores. Usar este, no Fluent directo.

## Cookies (lo que importa para escribir código)

| Cookie | TTL | Set/Clear |
|---|---|---|
| `access_token` (httpOnly) | Mirror de `exp` del JWT (~15 min) | `writeSession` después de login; `middleware.ts` después de refresh; `clearSession` en logout |
| `refresh_token` (httpOnly) | Mirror de `exp` (~7 d) | Igual que arriba |

- `secure` depende de `AUTH_COOKIE_SECURE` (default: `NODE_ENV === "production"`).
- `SameSite=Lax` siempre.
- `domain` opcional via `AUTH_COOKIE_DOMAIN` (para subdominios).
- **Importante**: `cookies().set()` solo funciona dentro de **Server Actions / Route Handlers / Middleware**. En un Server Component es read-only — por eso `backend.client.ts` no intenta refrescar.

## Cómo agregar un módulo nuevo (lado frontend)

Versión solo-frontend del workflow (el end-to-end está en el [CLAUDE.md raíz](../CLAUDE.md#cómo-extender-el-template-workflow-nuevo-módulo)):

1. **`types/<recurso>.types.ts`** — espejo de los Pydantic schemas del backend. Si el back devuelve `UserItem` / `UserDetail` / `UserCreatedResponse`, declarar los mismos en TS.
2. **`lib/schemas/<recurso>.schema.ts`** — Zod schemas para create/update.
3. **`lib/constants/endpoints.ts`** — agregar `ENDPOINTS.<RECURSO> = { LIST: "/api/v1/.../list", GET: (id) => ..., CREATE: ..., UPDATE: (id) => ..., DELETE: (id) => ... }`.
4. **`lib/constants/navigation.ts`** — item con `permissions: ["MENU-<X>"]` (el Sidebar filtra solo).
5. **`actions/<recurso>.actions.ts`** — `"use server"`. Funciones: `list<X>`, `get<X>`, `create<X>`, `update<X>`, `delete<X>`. Usar `tags: ["admin:<x>"]` en los reads y `revalidateTag("admin:<x>")` después de mutaciones.
6. **`app/(main)/<x>/page.tsx`** — server component con `await requirePermission("MENU-<X>")` + prefetch.
7. **`app/(main)/<x>/_components/<X>Table.tsx`** — client component con `useTableQuery`.
8. Forms: `_components/<X>Form.tsx` (client) que envuelve `react-hook-form` + el Zod schema compartido.

## Decisiones que el código no expresa solo

- **Fluent UI 9**: no es shadcn/Tailwind/Material. Si necesitas un componente no listado en `components/ui/`, mirar primero `@fluentui/react-components` antes de construir uno nuevo.
- **`reactStrictMode: true`** en `next.config.ts` — algunos efectos correrán dos veces en dev. Es esperado.
- **`serverActions.bodySizeLimit: "2mb"`** — Server Actions pueden devolver listas paginadas grandes; sin esto, 1 MB es el cap por defecto.
- **`poweredByHeader: false`** — no exponer `X-Powered-By: Next.js`.
- **AuthProvider hidratado con `initialUser`, no fetcheado en cliente**: evita un flash de UI no autenticada al primer render.
