# Seed de permisos y roles consolidado

> **Última actualización**: 2026-05-28
> **Propósito**: lista canónica de permisos y roles seed para todos los módulos de medisage. Es la **fuente de verdad** para extender `backend/app/core/seed.py`.

## Resumen

Medisage acumula **117 permisos** distribuidos en 9 módulos y **4 roles seed** (`ADMIN`, `DOCTOR`, `ASESOR`, `SYSTEM`). Este documento centraliza:

1. Tabla resumen por módulo.
2. Lista canónica de `SEED_PERMISSIONS` lista para pegar.
3. Matriz roles × permisos.
4. Definición del user `SYSTEM` y patches sugeridos a `seed.py`.

El template trae solo el seed del módulo `admin` (13 permisos + role `ADMIN`). El resto de módulos amplían `SEED_PERMISSIONS` y agregan funciones `_seed_<role>_role(...)` análogas a `_seed_admin_role`.

## Tabla resumen por módulo

| Módulo | # Permisos | Permiso de menú | Permisos de catálogo (READ/WRITE) |
|---|---|---|---|
| `admin` (template) | 13 | `MENU-ADMIN-*` | USERS, ROLES, PERMISSIONS |
| `catalog` | 13 | `MENU-CATALOG` | VERTICALS, SERVICES, PRODUCTS |
| `clinic` | 13 | `MENU-CLINIC` | BRANCHES, OFFICES, OFFICE_HOURS, OFFICE_CLOSURES |
| `staff` | 11 | `MENU-STAFF` | DOCTORS, DOCTOR_AVAILABILITY, MY_* (self-service) |
| `crm` | 16 | `MENU-CRM` | PERSONS, LEAD_STATUSES, CUSTOMER_STATUSES, LEAD_ASSIGNMENTS, LEAD_ACTIVITIES |
| `conversations` | 12 | `MENU-CONVERSATIONS` | CHANNEL_ACCOUNTS, CONVERSATIONS, MESSAGES |
| `bots` | 14 | `MENU-BOTS` | BOT_CONFIGURATIONS, BOT_TOOLS, BOT_STATE, BOT_EVENTS, BOT_ENGINE_INVOKE |
| `scheduling` | 13 | `MENU-SCHEDULING` | APPOINTMENT_STATUSES, APPOINTMENTS, AVAILABILITY |
| `marketing` | 12 | `MENU-MARKETING` | CAMPAIGNS, PROMOTIONS, PROMOTION_USAGES |
| **Total** | **117** | — | — |

## Roles seed

| Role | Descripción | Sobre quién |
|---|---|---|
| `ADMIN` | Acceso administrativo total. | Owners de la clínica, gerencia general. |
| `DOCTOR` | Profesional que atiende. Ve su agenda, edita su disponibilidad, marca atenciones. | Doctores asociados a `staff.Doctor`. |
| `ASESOR` | Gestiona leads y conversaciones. Toma conversaciones del bot, agenda citas, aplica promos. | Equipo comercial / SDRs. |
| `SYSTEM` | User técnico, no autenticable, usado como `created_by` de operaciones automáticas (bot agendando citas, transitions disparadas por sistema, etc.). | No humanos. `active=false`. |

## Lista canónica `SEED_PERMISSIONS`

Formato compatible con `app/core/seed.py:SEED_PERMISSIONS` actual (`{code, name, module}`). Para extender el seed, **agregar todas las filas siguientes** al final de la lista existente (las primeras 13 ya están en el template y se mantienen).

```python
SEED_PERMISSIONS: list[dict[str, str]] = [
    # ── Module: admin (ya existentes en el template) ────────────────────
    {"code": "MENU-HOME",              "name": "Menu Home",              "module": "GENERAL"},
    {"code": "MENU-ADMIN-USERS",       "name": "Menu Admin Users",       "module": "ADMIN"},
    {"code": "MENU-ADMIN-ROLES",       "name": "Menu Admin Roles",       "module": "ADMIN"},
    {"code": "MENU-ADMIN-PERMISSIONS", "name": "Menu Admin Permissions", "module": "ADMIN"},
    {"code": "USERS_VIEW",             "name": "View users",             "module": "ADMIN"},
    {"code": "USERS_CREATE",           "name": "Create users",           "module": "ADMIN"},
    {"code": "USERS_UPDATE",           "name": "Update users",           "module": "ADMIN"},
    {"code": "ROLES_VIEW",             "name": "View roles",             "module": "ADMIN"},
    {"code": "ROLES_CREATE",           "name": "Create roles",           "module": "ADMIN"},
    {"code": "ROLES_UPDATE",           "name": "Update roles",           "module": "ADMIN"},
    {"code": "PERMISSIONS_VIEW",       "name": "View permissions",       "module": "ADMIN"},
    {"code": "PERMISSIONS_CREATE",     "name": "Create permissions",     "module": "ADMIN"},
    {"code": "PERMISSIONS_UPDATE",     "name": "Update permissions",     "module": "ADMIN"},

    # ── Module: catalog ─────────────────────────────────────────────────
    {"code": "MENU-CATALOG",     "name": "Menu Catalog",      "module": "CATALOG"},
    {"code": "VERTICALS_READ",   "name": "Read verticals",    "module": "CATALOG"},
    {"code": "VERTICALS_CREATE", "name": "Create verticals",  "module": "CATALOG"},
    {"code": "VERTICALS_UPDATE", "name": "Update verticals",  "module": "CATALOG"},
    {"code": "VERTICALS_DELETE", "name": "Delete verticals",  "module": "CATALOG"},
    {"code": "SERVICES_READ",    "name": "Read services",     "module": "CATALOG"},
    {"code": "SERVICES_CREATE",  "name": "Create services",   "module": "CATALOG"},
    {"code": "SERVICES_UPDATE",  "name": "Update services",   "module": "CATALOG"},
    {"code": "SERVICES_DELETE",  "name": "Delete services",   "module": "CATALOG"},
    {"code": "PRODUCTS_READ",    "name": "Read products",     "module": "CATALOG"},
    {"code": "PRODUCTS_CREATE",  "name": "Create products",   "module": "CATALOG"},
    {"code": "PRODUCTS_UPDATE",  "name": "Update products",   "module": "CATALOG"},
    {"code": "PRODUCTS_DELETE",  "name": "Delete products",   "module": "CATALOG"},

    # ── Module: clinic ──────────────────────────────────────────────────
    {"code": "MENU-CLINIC",            "name": "Menu Clinic",                    "module": "CLINIC"},
    {"code": "BRANCHES_READ",          "name": "Read branches",                  "module": "CLINIC"},
    {"code": "BRANCHES_CREATE",        "name": "Create branches",                "module": "CLINIC"},
    {"code": "BRANCHES_UPDATE",        "name": "Update branches",                "module": "CLINIC"},
    {"code": "BRANCHES_DELETE",        "name": "Delete branches",                "module": "CLINIC"},
    {"code": "OFFICES_READ",           "name": "Read offices",                   "module": "CLINIC"},
    {"code": "OFFICES_CREATE",         "name": "Create offices",                 "module": "CLINIC"},
    {"code": "OFFICES_UPDATE",         "name": "Update offices",                 "module": "CLINIC"},
    {"code": "OFFICES_DELETE",         "name": "Delete offices",                 "module": "CLINIC"},
    {"code": "OFFICE_HOURS_READ",      "name": "Read office operating hours",    "module": "CLINIC"},
    {"code": "OFFICE_HOURS_WRITE",     "name": "Write office operating hours",   "module": "CLINIC"},
    {"code": "OFFICE_CLOSURES_READ",   "name": "Read office closures",           "module": "CLINIC"},
    {"code": "OFFICE_CLOSURES_WRITE",  "name": "Write office closures",          "module": "CLINIC"},

    # ── Module: staff ───────────────────────────────────────────────────
    {"code": "MENU-STAFF",                "name": "Menu Staff",                    "module": "STAFF"},
    {"code": "DOCTORS_READ",              "name": "Read doctors",                  "module": "STAFF"},
    {"code": "DOCTORS_CREATE",            "name": "Create doctors",                "module": "STAFF"},
    {"code": "DOCTORS_UPDATE",            "name": "Update doctors",                "module": "STAFF"},
    {"code": "DOCTORS_DELETE",            "name": "Delete doctors",                "module": "STAFF"},
    {"code": "DOCTOR_AVAILABILITY_READ",  "name": "Read any doctor availability",  "module": "STAFF"},
    {"code": "DOCTOR_AVAILABILITY_WRITE", "name": "Write any doctor availability", "module": "STAFF"},
    {"code": "MY_DOCTOR_PROFILE_READ",    "name": "Read my doctor profile",        "module": "STAFF"},
    {"code": "MY_DOCTOR_PROFILE_WRITE",   "name": "Write my doctor profile",       "module": "STAFF"},
    {"code": "MY_AVAILABILITY_READ",      "name": "Read my availability",          "module": "STAFF"},
    {"code": "MY_AVAILABILITY_WRITE",     "name": "Write my availability",         "module": "STAFF"},

    # ── Module: crm ─────────────────────────────────────────────────────
    {"code": "MENU-CRM",                  "name": "Menu CRM",                   "module": "CRM"},
    {"code": "PERSONS_READ",              "name": "Read persons",               "module": "CRM"},
    {"code": "PERSONS_CREATE",            "name": "Create persons",             "module": "CRM"},
    {"code": "PERSONS_UPDATE",            "name": "Update persons",             "module": "CRM"},
    {"code": "PERSONS_DELETE",            "name": "Delete persons",             "module": "CRM"},
    {"code": "LEAD_STATUSES_READ",        "name": "Read lead statuses",         "module": "CRM"},
    {"code": "LEAD_STATUSES_WRITE",       "name": "Write lead statuses",        "module": "CRM"},
    {"code": "CUSTOMER_STATUSES_READ",    "name": "Read customer statuses",     "module": "CRM"},
    {"code": "CUSTOMER_STATUSES_WRITE",   "name": "Write customer statuses",    "module": "CRM"},
    {"code": "LEAD_ASSIGNMENTS_READ",     "name": "Read lead assignments",      "module": "CRM"},
    {"code": "LEAD_ASSIGNMENTS_WRITE",    "name": "Write lead assignments",     "module": "CRM"},
    {"code": "LEAD_ACTIVITIES_READ",      "name": "Read lead activities",       "module": "CRM"},
    {"code": "LEAD_ACTIVITIES_WRITE",     "name": "Write lead activities",      "module": "CRM"},
    {"code": "LEAD_STATUS_HISTORY_READ",  "name": "Read lead status history",   "module": "CRM"},
    {"code": "MY_LEADS_READ",             "name": "Read my assigned leads",     "module": "CRM"},

    # ── Module: conversations ───────────────────────────────────────────
    {"code": "MENU-CONVERSATIONS",     "name": "Menu Conversations",   "module": "CONVERSATIONS"},
    {"code": "CHANNEL_ACCOUNTS_READ",  "name": "Read channel accounts","module": "CONVERSATIONS"},
    {"code": "CHANNEL_ACCOUNTS_CREATE","name": "Create channel accounts","module": "CONVERSATIONS"},
    {"code": "CHANNEL_ACCOUNTS_UPDATE","name": "Update channel accounts","module": "CONVERSATIONS"},
    {"code": "CHANNEL_ACCOUNTS_DELETE","name": "Delete channel accounts","module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_READ",     "name": "Read conversations",   "module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_TAKE",     "name": "Take conversation",    "module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_RELEASE",  "name": "Release conversation", "module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_CLOSE",    "name": "Close conversation",   "module": "CONVERSATIONS"},
    {"code": "MESSAGES_READ",          "name": "Read messages",        "module": "CONVERSATIONS"},
    {"code": "MESSAGES_SEND",          "name": "Send messages",        "module": "CONVERSATIONS"},
    {"code": "MY_CONVERSATIONS_READ",  "name": "Read my conversations","module": "CONVERSATIONS"},

    # ── Module: bots ────────────────────────────────────────────────────
    {"code": "MENU-BOTS",                       "name": "Menu Bots",                       "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_READ",         "name": "Read bot configurations",         "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_CREATE",       "name": "Create bot configurations",       "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_UPDATE",       "name": "Update bot configurations",       "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_DELETE",       "name": "Delete bot configurations",       "module": "BOTS"},
    {"code": "BOT_CONFIGURATION_VERSIONS_READ", "name": "Read bot configuration versions", "module": "BOTS"},
    {"code": "BOT_CONFIGURATION_VERSIONS_WRITE","name": "Write bot configuration versions","module": "BOTS"},
    {"code": "BOT_TOOLS_READ",                  "name": "Read bot tools",                  "module": "BOTS"},
    {"code": "BOT_TOOLS_WRITE",                 "name": "Write bot tools",                 "module": "BOTS"},
    {"code": "BOT_STATE_READ",                  "name": "Read bot conversation state",     "module": "BOTS"},
    {"code": "BOT_STATE_WRITE",                 "name": "Reset bot conversation state",    "module": "BOTS"},
    {"code": "BOT_EVENTS_READ",                 "name": "Read bot events",                 "module": "BOTS"},
    {"code": "BOT_TOOL_CALLS_READ",             "name": "Read bot tool calls",             "module": "BOTS"},
    {"code": "BOT_ENGINE_INVOKE",               "name": "Invoke bot engine manually",      "module": "BOTS"},

    # ── Module: scheduling ──────────────────────────────────────────────
    {"code": "MENU-SCHEDULING",             "name": "Menu Scheduling",            "module": "SCHEDULING"},
    {"code": "APPOINTMENT_STATUSES_READ",   "name": "Read appointment statuses",  "module": "SCHEDULING"},
    {"code": "APPOINTMENT_STATUSES_WRITE",  "name": "Write appointment statuses", "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_READ",           "name": "Read appointments",          "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_CREATE",         "name": "Create appointments",        "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_UPDATE",         "name": "Update appointments",        "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_DELETE",         "name": "Delete appointments",        "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_TRANSITION",     "name": "Transition appointment",     "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_CANCEL",         "name": "Cancel appointments",        "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_CANCEL_OVERRIDE","name": "Override cancel limit",      "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_RESCHEDULE",     "name": "Reschedule appointments",    "module": "SCHEDULING"},
    {"code": "AVAILABILITY_READ",           "name": "Read availability",          "module": "SCHEDULING"},
    {"code": "MY_APPOINTMENTS_READ",        "name": "Read my appointments",       "module": "SCHEDULING"},

    # ── Module: marketing ───────────────────────────────────────────────
    {"code": "MENU-MARKETING",       "name": "Menu Marketing",       "module": "MARKETING"},
    {"code": "CAMPAIGNS_READ",       "name": "Read campaigns",       "module": "MARKETING"},
    {"code": "CAMPAIGNS_CREATE",     "name": "Create campaigns",     "module": "MARKETING"},
    {"code": "CAMPAIGNS_UPDATE",     "name": "Update campaigns",     "module": "MARKETING"},
    {"code": "CAMPAIGNS_DELETE",     "name": "Delete campaigns",     "module": "MARKETING"},
    {"code": "PROMOTIONS_READ",      "name": "Read promotions",      "module": "MARKETING"},
    {"code": "PROMOTIONS_CREATE",    "name": "Create promotions",    "module": "MARKETING"},
    {"code": "PROMOTIONS_UPDATE",    "name": "Update promotions",    "module": "MARKETING"},
    {"code": "PROMOTIONS_DELETE",    "name": "Delete promotions",    "module": "MARKETING"},
    {"code": "PROMOTION_VALIDATE",   "name": "Validate promotion",   "module": "MARKETING"},
    {"code": "PROMOTION_APPLY",      "name": "Apply promotion",      "module": "MARKETING"},
    {"code": "PROMOTION_USAGES_READ","name": "Read promotion usages","module": "MARKETING"},
]
```

## Matriz roles × permisos

Leyenda: ✅ = el role tiene el permiso. — = no.

### `ADMIN`
Tiene **todos los permisos** de la lista. El seed actual (`_seed_admin_role`) ya hace esto:

```python
existing_or_new_admin.permissions = permissions  # todos los SEED_PERMISSIONS
```

### `DOCTOR`

Permisos del doctor (15 permisos):

```python
DOCTOR_PERMISSION_CODES: set[str] = {
    # Home / catálogo (consulta)
    "MENU-HOME",
    "MENU-CATALOG", "VERTICALS_READ", "SERVICES_READ", "PRODUCTS_READ",
    # Clínica (estructura, solo lectura)
    "BRANCHES_READ", "OFFICES_READ", "OFFICE_HOURS_READ", "OFFICE_CLOSURES_READ",
    # Staff (su propio perfil + agenda)
    "MENU-STAFF", "DOCTORS_READ",
    "MY_DOCTOR_PROFILE_READ", "MY_DOCTOR_PROFILE_WRITE",
    "MY_AVAILABILITY_READ", "MY_AVAILABILITY_WRITE",
    # CRM (lee paciente al atender)
    "PERSONS_READ",
    # Scheduling (su agenda + atenciones)
    "MENU-SCHEDULING", "APPOINTMENT_STATUSES_READ",
    "APPOINTMENTS_READ", "APPOINTMENTS_TRANSITION",
    "AVAILABILITY_READ", "MY_APPOINTMENTS_READ",
}
```

**Lo que NO tiene** (explícitamente):
- Crear/editar/borrar usuarios, roles, permisos, catálogo, sedes, consultorios, otros doctores.
- Editar disponibilidad de otros doctores (`DOCTOR_AVAILABILITY_WRITE`).
- Tomar conversaciones del bot, enviar mensajes (`CONVERSATIONS_*`, `MESSAGES_*`) — no es su rol.
- Editar bots, configurar campañas, aplicar promociones.
- Cancelar / reagendar citas (`APPOINTMENTS_CANCEL`, `_RESCHEDULE`) — eso es del asesor.
- Crear citas (`APPOINTMENTS_CREATE`) — eso es del asesor o del bot.

### `ASESOR`

Permisos del asesor (37 permisos):

```python
ASESOR_PERMISSION_CODES: set[str] = {
    # Home / catálogo (consulta)
    "MENU-HOME",
    "MENU-CATALOG", "VERTICALS_READ", "SERVICES_READ", "PRODUCTS_READ",
    # Clínica (consulta para responder al lead)
    "MENU-CLINIC", "BRANCHES_READ", "OFFICES_READ",
    # Staff (sabe qué doctores hay y su agenda para agendar)
    "DOCTORS_READ", "DOCTOR_AVAILABILITY_READ",
    # CRM (corazón de su trabajo)
    "MENU-CRM",
    "PERSONS_READ", "PERSONS_CREATE", "PERSONS_UPDATE",
    "LEAD_STATUSES_READ", "CUSTOMER_STATUSES_READ",
    "LEAD_ASSIGNMENTS_READ", "LEAD_ASSIGNMENTS_WRITE",
    "LEAD_ACTIVITIES_READ", "LEAD_ACTIVITIES_WRITE",
    "LEAD_STATUS_HISTORY_READ",
    "MY_LEADS_READ",
    # Conversations (toma chat del bot, envía mensajes)
    "MENU-CONVERSATIONS",
    "CONVERSATIONS_READ", "CONVERSATIONS_TAKE",
    "CONVERSATIONS_RELEASE", "CONVERSATIONS_CLOSE",
    "MESSAGES_READ", "MESSAGES_SEND",
    "MY_CONVERSATIONS_READ",
    # Bots (debug, ver qué hizo el bot en una conversación que tomó)
    "BOT_CONFIGURATIONS_READ", "BOT_STATE_READ",
    "BOT_EVENTS_READ", "BOT_TOOL_CALLS_READ",
    # Scheduling (agenda citas para sus leads)
    "MENU-SCHEDULING", "APPOINTMENT_STATUSES_READ",
    "APPOINTMENTS_READ", "APPOINTMENTS_CREATE", "APPOINTMENTS_UPDATE",
    "APPOINTMENTS_TRANSITION", "APPOINTMENTS_CANCEL",
    "APPOINTMENTS_RESCHEDULE",
    "AVAILABILITY_READ",
    # Marketing (consulta promos para ofrecer al lead)
    "MENU-MARKETING", "CAMPAIGNS_READ",
    "PROMOTIONS_READ", "PROMOTION_VALIDATE", "PROMOTION_APPLY",
    "PROMOTION_USAGES_READ",
}
```

**Lo que NO tiene** (explícitamente):
- Crear/editar usuarios, roles, permisos.
- Editar catálogos comerciales (verticales, servicios, productos).
- Editar sedes/consultorios/horarios.
- Editar perfiles de doctor o su disponibilidad.
- Configurar canales (`CHANNEL_ACCOUNTS_*`), bots (`BOT_CONFIGURATIONS_CREATE/UPDATE/DELETE`), versiones, tools.
- `APPOINTMENTS_DELETE` (eso es "fue error de captura", solo admin).
- `APPOINTMENTS_CANCEL_OVERRIDE` (solo admin puede saltarse `min_hours_to_cancel`).
- Crear campañas/promociones.

### `SYSTEM`

User técnico no autenticable. **Sin permisos asignados al role**. Su uso es como `created_by` / `actor_id` para operaciones automáticas. El backend NUNCA debería resolver `CurrentAuth` a este user — el active=false lo impide via el login normal.

```python
SYSTEM_PERMISSION_CODES: set[str] = set()  # vacío explícitamente
```

## Patches sugeridos a `app/core/seed.py`

El template tiene un `_seed_admin_role` único. Para medisage, extender así:

```python
async def _seed_role(
    db: AsyncSession,
    actor_id: str,
    role_name: str,
    role_description: str,
    permission_codes: set[str],
    all_permissions: list[Permission],
) -> Role:
    """Generic: idempotently seed a role with a subset of permissions."""
    perms = [p for p in all_permissions if p.code in permission_codes]
    existing = (
        await db.execute(select(Role).where(Role.name == role_name))
    ).scalars().first()
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.permissions = perms
        existing.description = role_description
        return existing
    role = Role(
        id=str(uuid.uuid4()),
        name=role_name,
        description=role_description,
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        permissions=perms,
    )
    db.add(role)
    logger.info("seed.role.created name=%s", role_name)
    return role


async def _seed_system_user(db: AsyncSession, actor_id: str) -> User:
    """User técnico para audit columns de operaciones automáticas (bot, sistema).
    Marcado active=false para que no pueda autenticarse."""
    SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000002"
    existing = (
        await db.execute(select(User).where(User.id == SYSTEM_USER_ID))
    ).scalars().first()
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    user = User(
        id=SYSTEM_USER_ID,
        email="system@medisage.internal",
        password_hash=hash_password(uuid.uuid4().hex),  # unguessable, no usable
        first_name="System",
        last_name="Internal",
        active=False,  # cannot log in
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        roles=[],
    )
    db.add(user)
    logger.info("seed.user.created email=system@medisage.internal active=false")
    return user


# En `seed()`:
async def seed() -> None:
    actor_id = "00000000-0000-0000-0000-000000000001"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            perms = await _seed_permissions(db, actor_id)
            await db.flush()

            admin_role = await _seed_role(
                db, actor_id, "ADMIN", "Full administrative access",
                {p.code for p in perms}, perms,
            )
            doctor_role = await _seed_role(
                db, actor_id, "DOCTOR", "Médico — agenda propia + atenciones",
                DOCTOR_PERMISSION_CODES, perms,
            )
            advisor_role = await _seed_role(
                db, actor_id, "ASESOR", "Asesor comercial — leads + conversaciones + citas",
                ASESOR_PERMISSION_CODES, perms,
            )
            system_role = await _seed_role(
                db, actor_id, "SYSTEM", "User técnico no autenticable",
                set(), perms,
            )
            await db.flush()

            await _seed_admin_user(db, admin_role, actor_id)
            await _seed_system_user(db, actor_id)

            # Seed de catálogos configurables (estados):
            await _seed_lead_statuses(db, actor_id)
            await _seed_customer_statuses(db, actor_id)
            await _seed_appointment_statuses(db, actor_id)
```

## Catálogos configurables seed

Además de permisos, hay tres catálogos en BD que se seedean al boot. Las listas exactas están en sus fichas:

- **LeadStatus** seed (7 entries) — [`crm.md`](crm.md#leadstatus-catlogo-configurable).
- **CustomerStatus** seed (5 entries) — [`crm.md`](crm.md#customerstatus-catlogo-configurable).
- **AppointmentStatus** seed (8 entries) — [`scheduling.md`](scheduling.md#appointmentstatus-catlogo).

Cada uno se implementa como `_seed_<catalog>_statuses(db, actor_id)` análogo a `_seed_permissions`, idempotente.

## Checklist de verificación al implementar

- [ ] `SEED_PERMISSIONS` tiene los 117 códigos (13 existentes + 104 nuevos).
- [ ] Existen 4 roles seed (`ADMIN`, `DOCTOR`, `ASESOR`, `SYSTEM`).
- [ ] El user `system@medisage.internal` existe con `active=false` y sin password usable.
- [ ] Catálogos seedeados: `lead_status` (7), `customer_status` (5), `appointment_status` (8).
- [ ] Test smoke: login con admin bootstrap funciona y los 3 roles aparecen en `/roles/list`.
- [ ] Test smoke: el JWT del admin contiene los 117 permisos como claims.
- [ ] Si se asignan los roles `DOCTOR` o `ASESOR` a un nuevo user, el JWT contiene exactamente el subset documentado arriba.

## Mantenimiento futuro

- **Agregar un permiso**: agregarlo a `SEED_PERMISSIONS` Y a los `_PERMISSION_CODES` de los roles que correspondan. Idempotente: el seed solo crea filas faltantes.
- **Cambiar el subset de un role**: editar `<ROLE>_PERMISSION_CODES`. El seed pisa los permisos del role en el próximo arranque.
- **Si se quita un permiso del seed**: las filas viejas quedan en BD (el seed no borra). Para limpiar, hacer migración explícita.
- **Si se quita un permiso de un role**: el seed reasigna `role.permissions = subset` en cada arranque, así que se quita automáticamente.
