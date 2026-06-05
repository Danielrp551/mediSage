"""
Tools MVP que tocan crm. Corren como SYSTEM (sin CurrentAuth): las reglas las impone el service
de crm (matriz de transición, dedup de identifier, etc.). Reusan las firmas REALES verificadas:
- crm.person.find_by_identifier_or_create(db, channel_type, identifier, profile, *, campaign_id=None)
- crm.lead_activity.log(db, person_id, ActivityType, *, advisor_user_id, actor_id, content=None,
    payload=None, related_conversation_id=None, ...)
- crm.person_lead_status.transition(db, person_id, to_id, *, actor_id, reason=None)

⚠ Estas funciones se REGISTRAN en el TOOL_REGISTRY al importar (F2, para `is_registered`) pero el
motor que las INVOCA llega en F3 — sus cuerpos no se ejecutan en F2.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.crm.enums import ActivityType, ChannelType
from app.modules.crm.schemas.person import PersonCreate
from app.modules.crm.services import lead_activity as crm_lead_activity
from app.modules.crm.services import person as crm_person
from app.modules.crm.services import person_lead_status as crm_lead_status

SYSTEM_USER_ID = crm_person.SYSTEM_USER_ID


@register_tool("resolve_or_create_contact")
async def resolve_or_create_contact(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Resuelve/crea el contacto por (channel_type, identifier). Idempotente. Devuelve el
    person_id + full_name para que el bot continúe."""
    person = await crm_person.find_by_identifier_or_create(
        db,
        ChannelType(args.get("channel_type", ChannelType.whatsapp.value)),
        args["identifier"],
        profile=PersonCreate(
            first_name=(args.get("first_name") or "Contacto")[:80],
            last_name=(args.get("last_name") or "(WhatsApp)")[:80],
            identifiers=[],
        ),
    )
    return {
        "person_id": person.id,
        "full_name": f"{person.first_name} {person.last_name}".strip(),
    }


@register_tool("register_lead_note")
async def register_lead_note(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Registra una NOTA en el timeline del lead, atada a la conversación (audit trail). Reusa
    lead_activity.log con related_conversation_id (el bot escribe como SYSTEM)."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    activity = await crm_lead_activity.log(
        db,
        ctx.person_id,
        ActivityType.NOTE,
        advisor_user_id=None,
        actor_id=SYSTEM_USER_ID,
        content=args["content"][:4000],
        related_conversation_id=ctx.conversation_id,
        payload={"source": "bot", "bot_configuration_id": ctx.bot_configuration_id},
    )
    return {"ok": True, "activity_id": activity.id}


@register_tool("set_lead_status")
async def set_lead_status(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Transiciona el estado del lead (valida la matriz de crm → LEAD_TRANSITION_NOT_ALLOWED).
    requires_confirmation=true en el catálogo. Captura la excepción y la reporta como result de
    la tool (el LLM la ve y puede explicarle al usuario), en vez de romper el turno."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    try:
        await crm_lead_status.transition(
            db,
            ctx.person_id,
            args["to_lead_status_id"],
            actor_id=SYSTEM_USER_ID,
            reason=args.get("reason", "Transición por bot"),
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — matriz/estado final → reportar al LLM, no romper el turno
        return {"ok": False, "error": str(exc)[:255]}
