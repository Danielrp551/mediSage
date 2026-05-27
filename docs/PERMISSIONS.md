# Modelo de permisos (RBAC)

## Conceptos

- **Permission** — capacidad atómica. Identificada por un **código** (`USERS_CREATE`, `MENU-HOME`).
- **Role** — agrupa permisos. Un usuario puede tener N roles.
- **User → Permission directo** — además de heredar de roles, un usuario puede tener permisos extra (escape hatch para casos puntuales).

```
User ──┬─── Role ── Permission   (vía role_permission)
       └─── Permission           (vía user_permission, directo)
```

Permisos efectivos = `union(direct, ∪ por cada rol del usuario)`.

## Convenciones de naming

- **`MENU-<AREA>`** o **`MENU-<AREA>-<RECURSO>`** para visibility de navegación frontend.
- **`<RECURSO>_<ACCIÓN>`** para acciones backend (`USERS_CREATE`, `ROLES_UPDATE`, `INVOICES_DELETE`).

Mantén consistencia: el código del frontend que aparece en `lib/constants/navigation.ts` debe existir en BD (creado por `seed.py` o por un admin desde la UI).

## Enforcement: dónde se verifica qué

| Capa | Qué controla | Ejemplo |
|------|--------------|---------|
| Backend `RequirePermission("X")` | Acceso al endpoint | `POST /users` requiere `USERS_CREATE` |
| Frontend `middleware.ts` | Existe cookie (login) | Sin cookie → `/login` |
| Frontend `requireAuth()` / `requirePermission()` | RSC redirige si no autorizado | `/admin/users` redirige a `/dashboard` |
| Frontend `<PermissionGuard>` | Esconder UI (botones, links) | "New user" no aparece si no hay `USERS_CREATE` |
| Frontend `Sidebar` | Filtrar items de nav | Solo muestra items con permiso |

**Regla**: el backend es la fuente de verdad. El frontend solo pre-filtra UX. Nunca asumas que esconder un botón es suficiente — el backend debe rechazar la llamada.

## Cómo agregar un permiso nuevo

1. **Definir el código.** Ej: `INVOICES_APPROVE`.
2. **Seed** — agrega en `backend/app/core/seed.py:SEED_PERMISSIONS` para que existe desde el primer deploy.
3. **Backend enforcement** — en el router del recurso:
   ```python
   @router.post("/{id}/approve", dependencies=[Depends(RequirePermission("INVOICES_APPROVE"))])
   async def approve_invoice(...): ...
   ```
4. **Frontend gating** — donde corresponda:
   ```tsx
   <PermissionGuard anyOf={["INVOICES_APPROVE"]}>
     <Button>Approve</Button>
   </PermissionGuard>
   ```
5. **Asigna a un rol** (desde la UI `/admin/roles` o seed) para que alguien pueda usarlo.

## Cómo agregar un menú nuevo

1. Agrega un permiso `MENU-<AREA>` en el seed.
2. Agrégalo a `frontend/src/lib/constants/navigation.ts`:
   ```ts
   {
     key: "invoices",
     label: "Invoices",
     icon: "Document24Regular",
     url: "/invoices",
     permissions: ["MENU-INVOICES"],
   }
   ```
3. Crea la página correspondiente en `app/(main)/invoices/page.tsx` y al inicio llama `await requirePermission("MENU-INVOICES")`.

## Tokens y permisos

Los permisos viajan en el **access token** (JWT, claim `permissions`), no se leen de la BD por request. Esto significa:

- Si un admin **revoca un permiso a un usuario** activo, el cambio surte efecto cuando el access token caduque (≤ 15 min por default) o cuando se haga refresh.
- Para forzar logout inmediato, revoca la familia del refresh token (`revoked_token_family`) — la próxima vez que el cliente refresque, será rechazado.
- Los permisos directos a usuario son útiles para casos excepcionales; el caso normal es asignar roles.
