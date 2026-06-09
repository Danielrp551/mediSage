"""
Tools de marketing (F4) — cierran el loop lead→bot→cita→cliente CON DESCUENTO. El bot
ofrece las promos elegibles para el contacto del hilo y un producto; luego usa
`book_appointment` con `apply_promotion_id` para aplicarlas al agendar (la aplicación real
ocurre dentro de `scheduling.create_appointment`, atómica — ver tools/scheduling.py).

`list_eligible_promotions` es READ-ONLY (no inserta nada; consulta `eligible_for`). Corre
como SYSTEM (sin CurrentAuth). Anti-suplantación: el sujeto SIEMPRE es `ctx.person_id` (el
contacto del hilo), NUNCA un person_id que venga del LLM. Si el hilo aún no resolvió su
contacto, devuelve `no_person` (el LLM debe llamar antes a `resolve_or_create_contact`).

Patrón de error (igual que crm/scheduling): se capturan las excepciones de DOMINIO
(BadRequest/Conflict/NotFound — que marketing lanza ANTES de escribir, sesión limpia) y se
devuelven como `{"ok": False, "error": code}`. Lo INESPERADO propaga al savepoint del engine
(begin_nested por tool) — no se captura en ancho para no comerse un error de BD con la sesión
sucia (lección bots F3a).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.modules.bots.services.engine.tools import BotInvocationContext, register_tool
from app.modules.marketing.services import promotion_usage as mkt_usage

DomainException = (BadRequestException, ConflictException, NotFoundException)


def _domain_error(
    exc: BadRequestException | ConflictException | NotFoundException,
) -> dict[str, Any]:
    """Traduce una excepción de dominio al result que ve el LLM (code estable o detalle)."""
    return {"ok": False, "error": exc.code or exc.detail}


@register_tool("list_eligible_promotions")
async def list_eligible_promotions(
    args: dict[str, Any], ctx: BotInvocationContext, db: AsyncSession
) -> dict[str, Any]:
    """Lista las promos ELEGIBLES para el contacto del hilo (ctx.person_id) y un producto, con
    su descuento ya calculado (original/discount/final + currency). Read-only. El bot ofrece
    estas opciones y luego usa book_appointment con el `promotion_id` elegido como
    `apply_promotion_id`. Anti-IDOR: el sujeto es ctx.person_id, NO un id del LLM."""
    if ctx.person_id is None:
        return {"ok": False, "error": "no_person"}
    try:
        product_id = str(args["product_id"])
    except KeyError:
        return {"ok": False, "error": "missing_required_argument"}
    try:
        result = await mkt_usage.eligible_for(db, product_id=product_id, person_id=ctx.person_id)
    except DomainException as exc:
        return _domain_error(exc)
    # Solo las elegibles (is_eligible=true); el model_dump trae el snapshot de montos (Decimal
    # → string) para que el LLM le explique al usuario el descuento.
    return {
        "ok": True,
        "promotions": [e.model_dump(mode="json") for e in result.data if e.is_eligible],
    }
