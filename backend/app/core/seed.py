"""
Idempotent seed: creates the canonical permissions, the base roles (ADMIN with
all permissions, DOCTOR and ASESOR with their subset, SYSTEM with none), the
bootstrap admin user and the SYSTEM technical user. The SYSTEM role/user is
introduced with the crm module (F0): it is the created_by / actor_id of the
module's automated operations (find_by_identifier_or_create, system-triggered
status transitions and round-robin assignment).

Run with: ``python -m app.core.seed`` (Dockerfile invokes it on container start).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.modules.admin.models.permission import Permission
from app.modules.admin.models.role import Role
from app.modules.admin.models.user import User
from app.modules.bots.models.bot_tool import BotTool
from app.modules.crm.models.customer_status import CustomerStatus
from app.modules.crm.models.customer_status_transition import CustomerStatusTransition
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_transition import LeadStatusTransition
from app.modules.scheduling.models.appointment_status import AppointmentStatus
from app.modules.scheduling.models.appointment_status_transition import (
    AppointmentStatusTransition,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# Bootstrap permissions — keep in sync with the frontend's `NAV_ITEMS`.
SEED_PERMISSIONS: list[dict[str, str]] = [
    {"code": "MENU-HOME", "name": "Menu Home", "module": "GENERAL"},
    {"code": "MENU-ADMIN-USERS", "name": "Menu Admin Users", "module": "ADMIN"},
    {"code": "MENU-ADMIN-ROLES", "name": "Menu Admin Roles", "module": "ADMIN"},
    {"code": "MENU-ADMIN-PERMISSIONS", "name": "Menu Admin Permissions", "module": "ADMIN"},
    {"code": "USERS_VIEW", "name": "View users", "module": "ADMIN"},
    {"code": "USERS_CREATE", "name": "Create users", "module": "ADMIN"},
    {"code": "USERS_UPDATE", "name": "Update users", "module": "ADMIN"},
    {"code": "ROLES_VIEW", "name": "View roles", "module": "ADMIN"},
    {"code": "ROLES_CREATE", "name": "Create roles", "module": "ADMIN"},
    {"code": "ROLES_UPDATE", "name": "Update roles", "module": "ADMIN"},
    {"code": "PERMISSIONS_VIEW", "name": "View permissions", "module": "ADMIN"},
    {"code": "PERMISSIONS_CREATE", "name": "Create permissions", "module": "ADMIN"},
    {"code": "PERMISSIONS_UPDATE", "name": "Update permissions", "module": "ADMIN"},
    # ── Module: catalog ─────────────────────────────────────────────────
    {"code": "MENU-CATALOG", "name": "Menu Catalog", "module": "CATALOG"},
    {"code": "VERTICALS_READ", "name": "Read verticals", "module": "CATALOG"},
    {"code": "VERTICALS_CREATE", "name": "Create verticals", "module": "CATALOG"},
    {"code": "VERTICALS_UPDATE", "name": "Update verticals", "module": "CATALOG"},
    {"code": "VERTICALS_DELETE", "name": "Delete verticals", "module": "CATALOG"},
    {"code": "SERVICES_READ", "name": "Read services", "module": "CATALOG"},
    {"code": "SERVICES_CREATE", "name": "Create services", "module": "CATALOG"},
    {"code": "SERVICES_UPDATE", "name": "Update services", "module": "CATALOG"},
    {"code": "SERVICES_DELETE", "name": "Delete services", "module": "CATALOG"},
    {"code": "PRODUCTS_READ", "name": "Read products", "module": "CATALOG"},
    {"code": "PRODUCTS_CREATE", "name": "Create products", "module": "CATALOG"},
    {"code": "PRODUCTS_UPDATE", "name": "Update products", "module": "CATALOG"},
    {"code": "PRODUCTS_DELETE", "name": "Delete products", "module": "CATALOG"},
    # ── Module: clinic ──────────────────────────────────────────────────
    {"code": "MENU-CLINIC", "name": "Menu Clinic", "module": "CLINIC"},
    {"code": "BRANCHES_READ", "name": "Read branches", "module": "CLINIC"},
    {"code": "BRANCHES_CREATE", "name": "Create branches", "module": "CLINIC"},
    {"code": "BRANCHES_UPDATE", "name": "Update branches", "module": "CLINIC"},
    {"code": "BRANCHES_DELETE", "name": "Delete branches", "module": "CLINIC"},
    {"code": "OFFICES_READ", "name": "Read offices", "module": "CLINIC"},
    {"code": "OFFICES_CREATE", "name": "Create offices", "module": "CLINIC"},
    {"code": "OFFICES_UPDATE", "name": "Update offices", "module": "CLINIC"},
    {"code": "OFFICES_DELETE", "name": "Delete offices", "module": "CLINIC"},
    {"code": "OFFICE_HOURS_READ", "name": "Read office operating hours", "module": "CLINIC"},
    {"code": "OFFICE_HOURS_WRITE", "name": "Write office operating hours", "module": "CLINIC"},
    {"code": "OFFICE_CLOSURES_READ", "name": "Read office closures", "module": "CLINIC"},
    {"code": "OFFICE_CLOSURES_WRITE", "name": "Write office closures", "module": "CLINIC"},
    # ── Module: staff ───────────────────────────────────────────────────
    {"code": "MENU-STAFF", "name": "Menu Staff", "module": "STAFF"},
    {"code": "DOCTORS_READ", "name": "Read doctors", "module": "STAFF"},
    {"code": "DOCTORS_CREATE", "name": "Create doctors", "module": "STAFF"},
    {"code": "DOCTORS_UPDATE", "name": "Update doctors", "module": "STAFF"},
    {"code": "DOCTORS_DELETE", "name": "Delete doctors", "module": "STAFF"},
    {"code": "DOCTOR_AVAILABILITY_READ", "name": "Read any doctor availability", "module": "STAFF"},
    {
        "code": "DOCTOR_AVAILABILITY_WRITE",
        "name": "Write any doctor availability",
        "module": "STAFF",
    },
    {"code": "MY_DOCTOR_PROFILE_READ", "name": "Read my doctor profile", "module": "STAFF"},
    {"code": "MY_DOCTOR_PROFILE_WRITE", "name": "Write my doctor profile", "module": "STAFF"},
    {"code": "MY_AVAILABILITY_READ", "name": "Read my availability", "module": "STAFF"},
    {"code": "MY_AVAILABILITY_WRITE", "name": "Write my availability", "module": "STAFF"},
    # ── Module: crm (15 permisos) ───────────────────────────────────────
    {"code": "MENU-CRM", "name": "Menu CRM", "module": "CRM"},
    {"code": "PERSONS_READ", "name": "Read persons", "module": "CRM"},
    {"code": "PERSONS_CREATE", "name": "Create persons", "module": "CRM"},
    {"code": "PERSONS_UPDATE", "name": "Update persons", "module": "CRM"},
    {"code": "PERSONS_DELETE", "name": "Delete persons", "module": "CRM"},
    {"code": "LEAD_STATUSES_READ", "name": "Read lead statuses", "module": "CRM"},
    {"code": "LEAD_STATUSES_WRITE", "name": "Write lead statuses", "module": "CRM"},
    {"code": "CUSTOMER_STATUSES_READ", "name": "Read customer statuses", "module": "CRM"},
    {"code": "CUSTOMER_STATUSES_WRITE", "name": "Write customer statuses", "module": "CRM"},
    {"code": "LEAD_ASSIGNMENTS_READ", "name": "Read lead assignments", "module": "CRM"},
    {"code": "LEAD_ASSIGNMENTS_WRITE", "name": "Write lead assignments", "module": "CRM"},
    {"code": "LEAD_ACTIVITIES_READ", "name": "Read lead activities", "module": "CRM"},
    {"code": "LEAD_ACTIVITIES_WRITE", "name": "Write lead activities", "module": "CRM"},
    {"code": "LEAD_STATUS_HISTORY_READ", "name": "Read lead status history", "module": "CRM"},
    {"code": "MY_LEADS_READ", "name": "Read my assigned leads", "module": "CRM"},
    # ── Module: conversations (12 permisos) ─────────────────────────────
    {"code": "MENU-CONVERSATIONS", "name": "Menu Conversations", "module": "CONVERSATIONS"},
    {"code": "CHANNEL_ACCOUNTS_READ", "name": "Read channel accounts", "module": "CONVERSATIONS"},
    {
        "code": "CHANNEL_ACCOUNTS_CREATE",
        "name": "Create channel accounts",
        "module": "CONVERSATIONS",
    },
    {
        "code": "CHANNEL_ACCOUNTS_UPDATE",
        "name": "Update channel accounts",
        "module": "CONVERSATIONS",
    },
    {
        "code": "CHANNEL_ACCOUNTS_DELETE",
        "name": "Delete channel accounts",
        "module": "CONVERSATIONS",
    },
    {"code": "CONVERSATIONS_READ", "name": "Read conversations", "module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_TAKE", "name": "Take conversation", "module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_RELEASE", "name": "Release conversation", "module": "CONVERSATIONS"},
    {"code": "CONVERSATIONS_CLOSE", "name": "Close conversation", "module": "CONVERSATIONS"},
    {"code": "MESSAGES_READ", "name": "Read messages", "module": "CONVERSATIONS"},
    {"code": "MESSAGES_SEND", "name": "Send messages", "module": "CONVERSATIONS"},
    {"code": "MY_CONVERSATIONS_READ", "name": "Read my conversations", "module": "CONVERSATIONS"},
    # ── Module: bots (14 permisos) ──────────────────────────────────────
    {"code": "MENU-BOTS", "name": "Menu Bots", "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_READ", "name": "Read bot configurations", "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_CREATE", "name": "Create bot configurations", "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_UPDATE", "name": "Update bot configurations", "module": "BOTS"},
    {"code": "BOT_CONFIGURATIONS_DELETE", "name": "Delete bot configurations", "module": "BOTS"},
    {
        "code": "BOT_CONFIGURATION_VERSIONS_READ",
        "name": "Read bot configuration versions",
        "module": "BOTS",
    },
    {
        "code": "BOT_CONFIGURATION_VERSIONS_WRITE",
        "name": "Write bot configuration versions",
        "module": "BOTS",
    },
    {"code": "BOT_TOOLS_READ", "name": "Read bot tools", "module": "BOTS"},
    {"code": "BOT_TOOLS_WRITE", "name": "Write bot tools", "module": "BOTS"},
    {"code": "BOT_STATE_READ", "name": "Read bot state", "module": "BOTS"},
    {"code": "BOT_STATE_WRITE", "name": "Write bot state", "module": "BOTS"},
    {"code": "BOT_EVENTS_READ", "name": "Read bot events", "module": "BOTS"},
    {"code": "BOT_TOOL_CALLS_READ", "name": "Read bot tool calls", "module": "BOTS"},
    {"code": "BOT_ENGINE_INVOKE", "name": "Invoke bot engine", "module": "BOTS"},
    # ── Module: scheduling (13 permisos) ────────────────────────────────
    {"code": "MENU-SCHEDULING", "name": "Menu Scheduling", "module": "SCHEDULING"},
    {
        "code": "APPOINTMENT_STATUSES_READ",
        "name": "Read appointment statuses",
        "module": "SCHEDULING",
    },
    {
        "code": "APPOINTMENT_STATUSES_WRITE",
        "name": "Write appointment statuses",
        "module": "SCHEDULING",
    },
    {"code": "APPOINTMENTS_READ", "name": "Read appointments", "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_CREATE", "name": "Create appointments", "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_UPDATE", "name": "Update appointments", "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_DELETE", "name": "Delete appointments", "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_TRANSITION", "name": "Transition appointment", "module": "SCHEDULING"},
    {"code": "APPOINTMENTS_CANCEL", "name": "Cancel appointments", "module": "SCHEDULING"},
    {
        "code": "APPOINTMENTS_CANCEL_OVERRIDE",
        "name": "Override cancel limit",
        "module": "SCHEDULING",
    },
    {"code": "APPOINTMENTS_RESCHEDULE", "name": "Reschedule appointments", "module": "SCHEDULING"},
    {"code": "AVAILABILITY_READ", "name": "Read availability", "module": "SCHEDULING"},
    {"code": "MY_APPOINTMENTS_READ", "name": "Read my appointments", "module": "SCHEDULING"},
    # ── Module: marketing (12 permisos) ─────────────────────────────────
    {"code": "MENU-MARKETING", "name": "Menu Marketing", "module": "MARKETING"},
    {"code": "CAMPAIGNS_READ", "name": "Read campaigns", "module": "MARKETING"},
    {"code": "CAMPAIGNS_CREATE", "name": "Create campaigns", "module": "MARKETING"},
    {"code": "CAMPAIGNS_UPDATE", "name": "Update campaigns", "module": "MARKETING"},
    {"code": "CAMPAIGNS_DELETE", "name": "Delete campaigns", "module": "MARKETING"},
    {"code": "PROMOTIONS_READ", "name": "Read promotions", "module": "MARKETING"},
    {"code": "PROMOTIONS_CREATE", "name": "Create promotions", "module": "MARKETING"},
    {"code": "PROMOTIONS_UPDATE", "name": "Update promotions", "module": "MARKETING"},
    {"code": "PROMOTIONS_DELETE", "name": "Delete promotions", "module": "MARKETING"},
    {
        "code": "PROMOTION_VALIDATE",
        "name": "Validate promotion eligibility/price",
        "module": "MARKETING",
    },
    {"code": "PROMOTION_APPLY", "name": "Apply promotion (create usage)", "module": "MARKETING"},
    {"code": "PROMOTION_USAGES_READ", "name": "Read promotion usages", "module": "MARKETING"},
]


# Subsets de permisos por rol no-admin. Se declaran en su **forma final**
# (incluyen códigos de módulos aún no implementados, p.ej. scheduling/crm):
# ``_seed_role`` filtra `[p for p in all_permissions if p.code in codes]`, así que
# los códigos que todavía no existen se omiten silenciosamente hoy y se suman solos
# cuando el módulo que los define se implemente. A prueba de orden de implementación.
DOCTOR_PERMISSION_CODES: set[str] = {
    # Home / catálogo (consulta)
    "MENU-HOME",
    "MENU-CATALOG",
    "VERTICALS_READ",
    "SERVICES_READ",
    "PRODUCTS_READ",
    # Clínica (estructura, solo lectura)
    "BRANCHES_READ",
    "OFFICES_READ",
    "OFFICE_HOURS_READ",
    "OFFICE_CLOSURES_READ",
    # Staff (su propio perfil + agenda)
    "MENU-STAFF",
    "DOCTORS_READ",
    "MY_DOCTOR_PROFILE_READ",
    "MY_DOCTOR_PROFILE_WRITE",
    "MY_AVAILABILITY_READ",
    "MY_AVAILABILITY_WRITE",
    # CRM (lee paciente al atender) — módulo futuro
    "PERSONS_READ",
    # Scheduling (su agenda + atenciones) — módulo futuro
    "MENU-SCHEDULING",
    "APPOINTMENT_STATUSES_READ",
    "APPOINTMENTS_READ",
    "APPOINTMENTS_TRANSITION",
    "AVAILABILITY_READ",
    "MY_APPOINTMENTS_READ",
}

ASESOR_PERMISSION_CODES: set[str] = {
    # Home / catálogo (consulta)
    "MENU-HOME",
    "MENU-CATALOG",
    "VERTICALS_READ",
    "SERVICES_READ",
    "PRODUCTS_READ",
    # Clínica (consulta para responder al lead)
    "MENU-CLINIC",
    "BRANCHES_READ",
    "OFFICES_READ",
    # Staff (sabe qué doctores hay y su agenda para agendar)
    "DOCTORS_READ",
    "DOCTOR_AVAILABILITY_READ",
    # CRM (corazón de su trabajo) — módulo futuro
    "MENU-CRM",
    "PERSONS_READ",
    "PERSONS_CREATE",
    "PERSONS_UPDATE",
    "LEAD_STATUSES_READ",
    "CUSTOMER_STATUSES_READ",
    "LEAD_ASSIGNMENTS_READ",
    "LEAD_ASSIGNMENTS_WRITE",
    "LEAD_ACTIVITIES_READ",
    "LEAD_ACTIVITIES_WRITE",
    "LEAD_STATUS_HISTORY_READ",
    "MY_LEADS_READ",
    # Conversations (toma chat del bot, envía mensajes) — módulo futuro
    "MENU-CONVERSATIONS",
    "CONVERSATIONS_READ",
    "CONVERSATIONS_TAKE",
    "CONVERSATIONS_RELEASE",
    "CONVERSATIONS_CLOSE",
    "MESSAGES_READ",
    "MESSAGES_SEND",
    "MY_CONVERSATIONS_READ",
    # Bots (debug de la conversación que tomó) — módulo futuro
    "BOT_CONFIGURATIONS_READ",
    "BOT_STATE_READ",
    "BOT_EVENTS_READ",
    "BOT_TOOL_CALLS_READ",
    # Scheduling (agenda citas para sus leads) — módulo futuro
    "MENU-SCHEDULING",
    "APPOINTMENT_STATUSES_READ",
    "APPOINTMENTS_READ",
    "APPOINTMENTS_CREATE",
    "APPOINTMENTS_UPDATE",
    "APPOINTMENTS_TRANSITION",
    "APPOINTMENTS_CANCEL",
    "APPOINTMENTS_RESCHEDULE",
    "AVAILABILITY_READ",
    # Marketing (consulta promos para ofrecer al lead) — módulo futuro
    "MENU-MARKETING",
    "CAMPAIGNS_READ",
    "PROMOTIONS_READ",
    "PROMOTION_VALIDATE",
    "PROMOTION_APPLY",
    "PROMOTION_USAGES_READ",
}

# SYSTEM: rol del usuario técnico no autenticable. NO lleva permisos — solo existe
# para etiquetar como SYSTEM al actor de operaciones automáticas. El backend nunca
# resuelve `CurrentAuth` a este usuario (su `active=False` lo bloquea en el login).
SYSTEM_PERMISSION_CODES: set[str] = set()


# ── Catálogos de estado seed (crm F2, ADR-008) ─────────────────────────────
# Idempotentes por `code`: el seed inserta los faltantes y NO pisa los existentes
# (la clínica los puede renombrar/editar después). El `code` es UNIQUE no-parcial,
# así que se busca por código sobre TODAS las filas (incl. soft-deleted) para no
# chocar con la constraint.
#
# LeadStatus (7): (code, name, color, is_initial, is_final, is_won, display_order)
LEAD_STATUS_SEED: list[tuple[str, str, str, bool, bool, bool, int]] = [
    ("NUEVO", "Nuevo", "#9CA3AF", True, False, False, 10),
    ("INTENTANDO_CONTACTAR", "Intentando contactar", "#F59E0B", False, False, False, 20),
    ("CONTACTADO", "Contactado", "#3B82F6", False, False, False, 30),
    ("INTERESADO", "Interesado", "#06B6D4", False, False, False, 40),
    ("EVALUANDO", "Evaluando", "#8B5CF6", False, False, False, 50),
    ("CITA_AGENDADA", "Cita agendada", "#22C55E", False, True, True, 60),
    ("NO_INTERESADO", "No interesado", "#EF4444", False, True, False, 70),
]

# CustomerStatus (5): (code, name, color, is_initial, is_final, display_order)
CUSTOMER_STATUS_SEED: list[tuple[str, str, str, bool, bool, int]] = [
    ("ACTIVO", "Activo", "#22C55E", True, False, 10),
    ("EN_TRATAMIENTO", "En tratamiento", "#06B6D4", False, False, 20),
    ("COMPLETADO", "Completado", "#8B5CF6", False, False, 30),
    ("INACTIVO", "Inactivo", "#9CA3AF", False, False, 40),
    ("PERDIDO", "Perdido", "#EF4444", False, True, 50),
]

# Matriz base de transiciones (from_code, to_code). Editable por admin sin deploy.
# Lead: CITA_AGENDADA y NO_INTERESADO son terminales (sin aristas de salida).
LEAD_TRANSITIONS: list[tuple[str, str]] = [
    ("NUEVO", "INTENTANDO_CONTACTAR"),
    ("NUEVO", "NO_INTERESADO"),
    ("INTENTANDO_CONTACTAR", "CONTACTADO"),
    ("INTENTANDO_CONTACTAR", "NO_INTERESADO"),
    ("CONTACTADO", "INTERESADO"),
    ("CONTACTADO", "INTENTANDO_CONTACTAR"),
    ("CONTACTADO", "NO_INTERESADO"),
    ("INTERESADO", "EVALUANDO"),
    ("INTERESADO", "NO_INTERESADO"),
    ("EVALUANDO", "CITA_AGENDADA"),
    ("EVALUANDO", "INTERESADO"),
    ("EVALUANDO", "NO_INTERESADO"),
]

# Customer (permisiva): no-finales entre sí + hacia finales; PERDIDO terminal.
CUSTOMER_TRANSITIONS: list[tuple[str, str]] = [
    ("ACTIVO", "EN_TRATAMIENTO"),
    ("ACTIVO", "COMPLETADO"),
    ("EN_TRATAMIENTO", "ACTIVO"),
    ("EN_TRATAMIENTO", "COMPLETADO"),
    ("COMPLETADO", "ACTIVO"),
    ("COMPLETADO", "EN_TRATAMIENTO"),
    ("ACTIVO", "INACTIVO"),
    ("EN_TRATAMIENTO", "INACTIVO"),
    ("COMPLETADO", "INACTIVO"),
    ("ACTIVO", "PERDIDO"),
    ("EN_TRATAMIENTO", "PERDIDO"),
    ("COMPLETADO", "PERDIDO"),
    ("INACTIVO", "PERDIDO"),
    ("INACTIVO", "ACTIVO"),  # reactivar
]

# ── Catálogo de estados de cita seed (scheduling F1, ADR-008) ──────────────
# Idéntico patrón que crm: idempotente por `code` (MAYÚSCULAS, inmutables — los
# shortcuts del service de F3 resuelven por estos codes). is_initial único = SCHEDULED;
# is_final = {ATTENDED, NO_SHOW, CANCELLED, RESCHEDULED}; is_active_attention = IN_PROGRESS.
#
# AppointmentStatus (8): (code, name, color, is_initial, is_final, is_active_attention, display_order)
APPOINTMENT_STATUS_SEED: list[tuple[str, str, str, bool, bool, bool, int]] = [
    ("SCHEDULED", "Agendada", "#3B82F6", True, False, False, 10),
    ("CONFIRMED", "Confirmada", "#06B6D4", False, False, False, 20),
    ("CHECKED_IN", "En recepción", "#F59E0B", False, False, False, 30),
    ("IN_PROGRESS", "En atención", "#8B5CF6", False, False, True, 40),
    ("ATTENDED", "Atendida", "#22C55E", False, True, False, 50),
    ("NO_SHOW", "No asistió", "#EF4444", False, True, False, 60),
    ("CANCELLED", "Cancelada", "#6B7280", False, True, False, 70),
    ("RESCHEDULED", "Reagendada", "#9CA3AF", False, True, False, 80),
]

# Matriz base de transiciones de cita (from_code, to_code). Editable por admin sin
# deploy. Los finales (ATTENDED/NO_SHOW/CANCELLED/RESCHEDULED) no tienen salida.
# Reschedule permitido desde {SCHEDULED, CONFIRMED}.
APPOINTMENT_TRANSITIONS: list[tuple[str, str]] = [
    ("SCHEDULED", "CONFIRMED"),
    ("SCHEDULED", "CHECKED_IN"),
    ("SCHEDULED", "NO_SHOW"),
    ("SCHEDULED", "CANCELLED"),
    ("SCHEDULED", "RESCHEDULED"),
    ("CONFIRMED", "CHECKED_IN"),
    ("CONFIRMED", "NO_SHOW"),
    ("CONFIRMED", "CANCELLED"),
    ("CONFIRMED", "RESCHEDULED"),
    ("CHECKED_IN", "IN_PROGRESS"),
    ("CHECKED_IN", "CANCELLED"),
    ("IN_PROGRESS", "ATTENDED"),
    ("IN_PROGRESS", "CANCELLED"),
]

# ── Catálogo de tools del bot — scheduling (F5) ────────────────────────────
# Las 3 tools que cierran el loop lead→bot→cita→cliente. El `code` DEBE coincidir con el
# @register_tool de `bots/services/engine/tools/scheduling.py` (si no, is_registered=false y
# el engine devuelve TOOL_NOT_REGISTERED). El admin las ASIGNA a un bot vía el M:N
# `bot_configuration_tool`. Idempotente por code. parameters_schema = JSON Schema (lo que ve
# el LLM para decidir cuándo/cómo invocarlas). requires_confirmation=true en las que mutan.
# (code, name, description, parameters_schema, target_service, requires_confirmation)
BOT_TOOL_SEED: list[tuple[str, str, str, dict[str, Any], str, bool]] = [
    (
        "check_availability",
        "Consultar disponibilidad",
        "Lista los horarios libres de un doctor para un producto/servicio en un rango de "
        "fechas. Úsala para ofrecerle opciones de horario al paciente antes de reservar.",
        {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string", "description": "ID del doctor"},
                "product_id": {"type": "string", "description": "ID del producto/servicio"},
                "from_date": {
                    "type": "string",
                    "description": "Fecha inicial del rango (YYYY-MM-DD)",
                },
                "to_date": {
                    "type": "string",
                    "description": "Fecha final del rango, inclusive (YYYY-MM-DD)",
                },
                "office_id": {"type": "string", "description": "Opcional: acota a un consultorio"},
                "branch_id": {"type": "string", "description": "Opcional: acota a una sede"},
            },
            "required": ["doctor_id", "product_id", "from_date", "to_date"],
        },
        "scheduling.availability.compute_available_slots",
        False,
    ),
    (
        "book_appointment",
        "Reservar cita",
        "Reserva una cita para el contacto de la conversación en el horario elegido (un slot "
        "devuelto por check_availability). Devuelve la cita creada o el motivo si el horario "
        "ya no está disponible.",
        {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "string", "description": "ID del doctor"},
                "office_id": {
                    "type": "string",
                    "description": "ID del consultorio (el office_id del slot elegido)",
                },
                "product_id": {"type": "string", "description": "ID del producto/servicio"},
                "scheduled_for": {
                    "type": "string",
                    "description": "Inicio de la cita en ISO 8601 (el starts_at del slot elegido)",
                },
                "notes": {"type": "string", "description": "Opcional: notas internas de la cita"},
            },
            "required": ["doctor_id", "office_id", "product_id", "scheduled_for"],
        },
        "scheduling.appointment.create_appointment",
        True,
    ),
    (
        "cancel_appointment",
        "Cancelar cita",
        "Cancela una cita existente. Puede rechazarse si falta muy poco para la cita (política "
        "de cancelación de la clínica); en ese caso pídele al paciente que llame a la clínica.",
        {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "string", "description": "ID de la cita a cancelar"},
                "cancellation_reason": {
                    "type": "string",
                    "description": "Opcional: motivo de la cancelación",
                },
            },
            "required": ["appointment_id"],
        },
        "scheduling.transition.cancel",
        True,
    ),
]


async def _seed_permissions(db: AsyncSession, actor_id: str) -> list[Permission]:
    existing = (await db.execute(select(Permission))).scalars().all()
    by_code = {p.code: p for p in existing}
    out: list[Permission] = []
    now = datetime.now(UTC)
    for spec in SEED_PERMISSIONS:
        if spec["code"] in by_code:
            out.append(by_code[spec["code"]])
            continue
        perm = Permission(
            id=str(uuid.uuid4()),
            code=spec["code"],
            name=spec["name"],
            description=spec["name"],
            module=spec["module"],
            active=True,
            created_by=actor_id,
            created_on=now,
            updated_by=actor_id,
            updated_on=now,
        )
        db.add(perm)
        out.append(perm)
        logger.info("seed.permission.created code=%s", spec["code"])
    return out


async def _seed_role(
    db: AsyncSession,
    actor_id: str,
    role_name: str,
    role_description: str,
    permission_codes: set[str],
    all_permissions: list[Permission],
) -> Role:
    """Seed idempotente de un rol con un subconjunto de permisos.

    ``permission_codes`` puede declarar códigos de módulos aún no implementados:
    se filtran contra ``all_permissions`` (lo que existe hoy), de modo que los
    códigos inexistentes se omiten silenciosamente. Reemplaza al antiguo
    ``_seed_admin_role`` único del template.
    """
    perms = [p for p in all_permissions if p.code in permission_codes]
    existing = (await db.execute(select(Role).where(Role.name == role_name))).scalars().first()
    if existing is not None:
        existing.permissions = perms
        existing.description = role_description
        return existing
    now = datetime.now(UTC)
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
    logger.info("seed.role.created name=%s perms=%d", role_name, len(perms))
    return role


async def _seed_admin_user(db: AsyncSession, role: Role, actor_id: str) -> User:
    existing = (
        (await db.execute(select(User).where(User.email == settings.SEED_ADMIN_EMAIL)))
        .scalars()
        .first()
    )
    if existing is not None:
        existing.roles = [role]
        return existing
    now = datetime.now(UTC)
    user = User(
        id=actor_id,
        email=settings.SEED_ADMIN_EMAIL,
        password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
        first_name="Admin",
        last_name="User",
        active=True,
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        roles=[role],
    )
    db.add(user)
    logger.info("seed.user.created email=%s", settings.SEED_ADMIN_EMAIL)
    return user


async def _seed_system_user(db: AsyncSession, role: Role, actor_id: str) -> User:
    """Usuario técnico para las audit columns de operaciones automáticas (crm/bots).

    `active=False` → no puede autenticarse; el backend nunca resuelve `CurrentAuth`
    a él. Su id es estable (lo usan los services como `created_by`/`actor_id`).
    """
    system_user_id = "00000000-0000-0000-0000-000000000002"
    existing = (await db.execute(select(User).where(User.id == system_user_id))).scalars().first()
    if existing is not None:
        existing.roles = [role]
        return existing
    now = datetime.now(UTC)
    user = User(
        id=system_user_id,
        email="system@medisage.internal",
        password_hash=hash_password(uuid.uuid4().hex),  # no adivinable, no usable
        first_name="System",
        last_name="Internal",
        active=False,  # no puede iniciar sesión
        created_by=actor_id,
        created_on=now,
        updated_by=actor_id,
        updated_on=now,
        roles=[role],
    )
    db.add(user)
    logger.info("seed.user.created email=system@medisage.internal active=false")
    return user


async def _seed_lead_statuses(db: AsyncSession, actor_id: str) -> None:
    """Inserta los LeadStatus faltantes (idempotente por code). Busca sobre TODAS
    las filas — el code es UNIQUE no-parcial: un code soft-deleted sigue reservado."""
    existing_codes = {s.code for s in (await db.execute(select(LeadStatus))).scalars().all()}
    now = datetime.now(UTC)
    for code, name, color, is_initial, is_final, is_won, display_order in LEAD_STATUS_SEED:
        if code in existing_codes:
            continue
        db.add(
            LeadStatus(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                description=None,
                color=color,
                is_initial=is_initial,
                is_final=is_final,
                is_won=is_won,
                display_order=display_order,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.lead_status.created code=%s", code)


async def _seed_customer_statuses(db: AsyncSession, actor_id: str) -> None:
    """Inserta los CustomerStatus faltantes (idempotente por code, incl. soft-deleted)."""
    existing_codes = {s.code for s in (await db.execute(select(CustomerStatus))).scalars().all()}
    now = datetime.now(UTC)
    for code, name, color, is_initial, is_final, display_order in CUSTOMER_STATUS_SEED:
        if code in existing_codes:
            continue
        db.add(
            CustomerStatus(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                description=None,
                color=color,
                is_initial=is_initial,
                is_final=is_final,
                display_order=display_order,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.customer_status.created code=%s", code)


async def _seed_lead_transition_matrix(db: AsyncSession, actor_id: str) -> None:
    """Inserta las aristas base de la matriz de lead que falten (idempotente).
    Resuelve los codes a ids sobre estados VIVOS (no resucita aristas a estados
    borrados); omite una arista si alguno de sus extremos no existe."""
    id_by_code = {
        s.code: s.id
        for s in (await db.execute(select(LeadStatus).where(LeadStatus.deleted_at.is_(None))))
        .scalars()
        .all()
    }
    existing_edges = {
        (t.from_lead_status_id, t.to_lead_status_id)
        for t in (await db.execute(select(LeadStatusTransition))).scalars().all()
    }
    now = datetime.now(UTC)
    for from_code, to_code in LEAD_TRANSITIONS:
        from_id = id_by_code.get(from_code)
        to_id = id_by_code.get(to_code)
        if from_id is None or to_id is None or (from_id, to_id) in existing_edges:
            continue
        db.add(
            LeadStatusTransition(
                id=str(uuid.uuid4()),
                from_lead_status_id=from_id,
                to_lead_status_id=to_id,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.lead_transition.created %s->%s", from_code, to_code)


async def _seed_customer_transition_matrix(db: AsyncSession, actor_id: str) -> None:
    """Inserta las aristas base de la matriz de cliente que falten (idempotente)."""
    id_by_code = {
        s.code: s.id
        for s in (
            await db.execute(select(CustomerStatus).where(CustomerStatus.deleted_at.is_(None)))
        )
        .scalars()
        .all()
    }
    existing_edges = {
        (t.from_customer_status_id, t.to_customer_status_id)
        for t in (await db.execute(select(CustomerStatusTransition))).scalars().all()
    }
    now = datetime.now(UTC)
    for from_code, to_code in CUSTOMER_TRANSITIONS:
        from_id = id_by_code.get(from_code)
        to_id = id_by_code.get(to_code)
        if from_id is None or to_id is None or (from_id, to_id) in existing_edges:
            continue
        db.add(
            CustomerStatusTransition(
                id=str(uuid.uuid4()),
                from_customer_status_id=from_id,
                to_customer_status_id=to_id,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.customer_transition.created %s->%s", from_code, to_code)


async def _seed_appointment_statuses(db: AsyncSession, actor_id: str) -> None:
    """Inserta los AppointmentStatus faltantes (idempotente por code, incl.
    soft-deleted: el code es UNIQUE no-parcial)."""
    existing_codes = {s.code for s in (await db.execute(select(AppointmentStatus))).scalars().all()}
    now = datetime.now(UTC)
    for (
        code,
        name,
        color,
        is_initial,
        is_final,
        is_active_attention,
        display_order,
    ) in APPOINTMENT_STATUS_SEED:
        if code in existing_codes:
            continue
        db.add(
            AppointmentStatus(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                description=None,
                color=color,
                is_initial=is_initial,
                is_final=is_final,
                is_active_attention=is_active_attention,
                display_order=display_order,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.appointment_status.created code=%s", code)


async def _seed_appointment_transition_matrix(db: AsyncSession, actor_id: str) -> None:
    """Inserta las aristas base de la matriz de cita que falten (idempotente).
    Resuelve los codes a ids sobre estados VIVOS; omite una arista si alguno de sus
    extremos no existe."""
    id_by_code = {
        s.code: s.id
        for s in (
            await db.execute(
                select(AppointmentStatus).where(AppointmentStatus.deleted_at.is_(None))
            )
        )
        .scalars()
        .all()
    }
    existing_edges = {
        (t.from_status_id, t.to_status_id)
        for t in (await db.execute(select(AppointmentStatusTransition))).scalars().all()
    }
    now = datetime.now(UTC)
    for from_code, to_code in APPOINTMENT_TRANSITIONS:
        from_id = id_by_code.get(from_code)
        to_id = id_by_code.get(to_code)
        if from_id is None or to_id is None or (from_id, to_id) in existing_edges:
            continue
        db.add(
            AppointmentStatusTransition(
                id=str(uuid.uuid4()),
                from_status_id=from_id,
                to_status_id=to_id,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.appointment_transition.created %s->%s", from_code, to_code)


async def _seed_bot_tools(db: AsyncSession, actor_id: str) -> None:
    """Inserta las filas BotTool faltantes del catálogo (idempotente por code). El admin las
    ASIGNA a un bot vía el M:N; `is_registered` se deriva en runtime (code ∈ TOOL_REGISTRY) —
    estas 3 quedan registradas por `bots/services/engine/tools/scheduling.py`.

    Idempotencia sobre filas VIVAS: el UNIQUE de `bot_tool.code` es PARCIAL (solo deleted_at
    IS NULL), a diferencia de appointment_status (UNIQUE no-parcial). Si un code quedó
    soft-deleted (p.ej. un test previo), se re-crea una fila viva — el UNIQUE parcial lo
    permite y la herramienta vuelve a estar disponible/asignable."""
    existing_codes = {
        t.code
        for t in (await db.execute(select(BotTool).where(BotTool.deleted_at.is_(None))))
        .scalars()
        .all()
    }
    now = datetime.now(UTC)
    for (
        code,
        name,
        description,
        parameters_schema,
        target_service,
        requires_confirmation,
    ) in BOT_TOOL_SEED:
        if code in existing_codes:
            continue
        db.add(
            BotTool(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                description=description,
                parameters_schema=parameters_schema,
                target_service=target_service,
                requires_confirmation=requires_confirmation,
                active=True,
                created_by=actor_id,
                created_on=now,
                updated_by=actor_id,
                updated_on=now,
            )
        )
        logger.info("seed.bot_tool.created code=%s", code)


async def seed() -> None:
    """Run the full seed inside one transaction."""
    actor_id = "00000000-0000-0000-0000-000000000001"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            perms = await _seed_permissions(db, actor_id)
            await db.flush()

            admin_role = await _seed_role(
                db,
                actor_id,
                "ADMIN",
                "Full administrative access",
                {p.code for p in perms},
                perms,
            )
            # DOCTOR/ASESOR se siembran con su subset disponible hoy (el helper
            # filtra los códigos de módulos aún no implementados). SYSTEM se
            # introduce con crm: rol sin permisos + usuario técnico no autenticable.
            await _seed_role(
                db,
                actor_id,
                "DOCTOR",
                "Médico — agenda propia + atenciones",
                DOCTOR_PERMISSION_CODES,
                perms,
            )
            await _seed_role(
                db,
                actor_id,
                "ASESOR",
                "Asesor comercial — leads + conversaciones + citas",
                ASESOR_PERMISSION_CODES,
                perms,
            )
            system_role = await _seed_role(
                db,
                actor_id,
                "SYSTEM",
                "Usuario técnico no autenticable (operaciones automáticas)",
                SYSTEM_PERMISSION_CODES,
                perms,
            )
            await db.flush()

            await _seed_admin_user(db, admin_role, actor_id)
            await _seed_system_user(db, system_role, actor_id)

            # crm F2: catálogos de estado + matriz base (idempotente). Primero los
            # estados; flush para materializar sus ids antes de resolver las aristas.
            await _seed_lead_statuses(db, actor_id)
            await _seed_customer_statuses(db, actor_id)
            await db.flush()
            await _seed_lead_transition_matrix(db, actor_id)
            await _seed_customer_transition_matrix(db, actor_id)

            # scheduling F1: catálogo de estados de cita + matriz base (idempotente).
            # Primero los estados; flush para materializar sus ids antes de las aristas.
            await _seed_appointment_statuses(db, actor_id)
            await db.flush()
            await _seed_appointment_transition_matrix(db, actor_id)

            # bots/scheduling F5: catálogo de tools del bot (idempotente por code). El admin
            # las asigna a un bot vía el M:N; el engine resuelve por code en TOOL_REGISTRY.
            await _seed_bot_tools(db, actor_id)


if __name__ == "__main__":
    configure_logging(settings.LOG_LEVEL)
    asyncio.run(seed())
