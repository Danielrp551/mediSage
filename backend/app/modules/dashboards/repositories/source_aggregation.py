"""
PLANO DE CÓMPUTO del refresh (frío, por cron): agrega las TABLAS FUENTE (read-only) → tuplas
(metric_date, [branch_id], [segment], count, [value]) que el service inserta en el rollup. Es el
ÚNICO punto que escanea las tablas de negocio. Una query por DashboardMetric, con las fórmulas
EXACTAS de design.md §7 / backend.md §3 (atributos verificados contra el código real 2026-06-24).

Filtran `deleted_at IS NULL` SOLO donde la fuente tiene SoftDeleteMixin (conversation, appointment,
person_customer_status); NO en las append-only (lead_status_history, bot_event — sin SoftDelete).

⚠ El bucketing por día usa `func.date(col)` = `CAST(col AS DATE)` en Postgres y `date(col)` en
sqlite → corre idéntico en ambos (el smoke usa create_all en sqlite). El service (refresh.py)
normaliza el row[0] a un objeto `date` (en sqlite `func.date` devuelve str 'YYYY-MM-DD').
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bots.enums import BotEventType
from app.modules.bots.models.bot_event import BotEvent
from app.modules.conversations.enums import AssigneeType
from app.modules.conversations.models.conversation import Conversation
from app.modules.crm.models.lead_status import LeadStatus
from app.modules.crm.models.lead_status_history import LeadStatusHistory
from app.modules.crm.models.person_customer_status import PersonCustomerStatus
from app.modules.scheduling.models.appointment import Appointment
from app.modules.scheduling.models.appointment_status import AppointmentStatus


class SourceAggregationRepository:
    """NO extiende BaseRepository: no es una entidad propia, es un agregador de fuentes ajenas."""

    # ── conversations: COUNT(DISTINCT person_id) por opened_at::date; segment NULL ──
    async def conversations_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        q = (
            select(
                func.date(Conversation.opened_at),
                func.count(func.distinct(Conversation.person_id)),
            )
            .where(
                Conversation.opened_at >= since,
                Conversation.opened_at < until,
                Conversation.deleted_at.is_(None),
                Conversation.person_id.is_not(None),
            )
            .group_by(func.date(Conversation.opened_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── conversations 'bot': assignee_type='bot' OR EXISTS(bot_event de esa conversación) ──
    async def conversations_bot_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        bot_conv = select(BotEvent.id).where(BotEvent.conversation_id == Conversation.id).exists()
        q = (
            select(
                func.date(Conversation.opened_at),
                func.count(func.distinct(Conversation.person_id)),
            )
            .where(
                Conversation.opened_at >= since,
                Conversation.opened_at < until,
                Conversation.deleted_at.is_(None),
                Conversation.person_id.is_not(None),
                or_(Conversation.assignee_type == AssigneeType.bot, bot_conv),
            )
            .group_by(func.date(Conversation.opened_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── leads_created: COUNT(DISTINCT person_id) WHERE from_lead_status_id IS NULL ──
    async def leads_created_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """from_lead_status_id IS NULL = la fila de NACIMIENTO del lead. lead_status_history NO
        tiene SoftDelete (append-only) → sin filtro deleted_at. branch_id NULL (lead no tiene sede)."""
        q = (
            select(
                func.date(LeadStatusHistory.changed_at),
                func.count(func.distinct(LeadStatusHistory.person_id)),
            )
            .where(
                LeadStatusHistory.changed_at >= since,
                LeadStatusHistory.changed_at < until,
                LeadStatusHistory.from_lead_status_id.is_(None),
            )
            .group_by(func.date(LeadStatusHistory.changed_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── lead_stage: COUNT(DISTINCT person_id) por to_lead_status_id (segment=lead_status_code) ──
    async def lead_stage_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, str, int]]:
        """(día, lead_status_code, count). JOIN a lead_status para persistir el CODE (no el uuid —
        ADR-008: estable a renombrados). Alimenta la línea + las etapas del embudo de lead."""
        q = (
            select(
                func.date(LeadStatusHistory.changed_at),
                LeadStatus.code,
                func.count(func.distinct(LeadStatusHistory.person_id)),
            )
            .join(LeadStatus, LeadStatus.id == LeadStatusHistory.to_lead_status_id)
            .where(
                LeadStatusHistory.changed_at >= since,
                LeadStatusHistory.changed_at < until,
            )
            .group_by(func.date(LeadStatusHistory.changed_at), LeadStatus.code)
        )
        return [(row[0], row[1], row[2]) for row in (await db.execute(q)).all()]

    # ── appointments: COUNT por status_code (segment) + scheduled_for::date + branch_id ──
    async def appointments_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, str | None, str, int]]:
        """(día, branch_id, appointment_status_code, count). JOIN a appointment_status → CODE.
        Alimenta el donut + las etapas 4/5. branch_id es REAL (denorm). deleted_at IS NULL
        (appointment soft-deletea SOLO errores de captura; las citas cerradas siguen vivas)."""
        q = (
            select(
                func.date(Appointment.scheduled_for),
                Appointment.branch_id,
                AppointmentStatus.code,
                func.count(),
            )
            .join(AppointmentStatus, AppointmentStatus.id == Appointment.status_id)
            .where(
                Appointment.scheduled_for >= since,
                Appointment.scheduled_for < until,
                Appointment.deleted_at.is_(None),
            )
            .group_by(
                func.date(Appointment.scheduled_for),
                Appointment.branch_id,
                AppointmentStatus.code,
            )
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await db.execute(q)).all()]

    # ── appointments_source: COUNT por source (segment) + día + branch_id ──
    async def appointments_source_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, str | None, str, int]]:
        """(día, branch_id, source, count). source = AppointmentSource value ('bot'/'advisor'/…).
        Atribución al chatbot (sub-conteo de citas + chatbot por origen)."""
        q = (
            select(
                func.date(Appointment.scheduled_for),
                Appointment.branch_id,
                Appointment.source,
                func.count(),
            )
            .where(
                Appointment.scheduled_for >= since,
                Appointment.scheduled_for < until,
                Appointment.deleted_at.is_(None),
            )
            .group_by(
                func.date(Appointment.scheduled_for),
                Appointment.branch_id,
                Appointment.source,
            )
        )
        return [(row[0], row[1], row[2], row[3]) for row in (await db.execute(q)).all()]

    # ── customers_new: COUNT(DISTINCT person_id) por became_customer_at::date ──
    async def customers_new_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """became_customer_at lo fija solo attend()→ATTENDED (atómico). deleted_at IS NULL.
        branch_id NULL (cliente no tiene sede directa)."""
        q = (
            select(
                func.date(PersonCustomerStatus.became_customer_at),
                func.count(func.distinct(PersonCustomerStatus.person_id)),
            )
            .where(
                PersonCustomerStatus.became_customer_at >= since,
                PersonCustomerStatus.became_customer_at < until,
                PersonCustomerStatus.deleted_at.is_(None),
            )
            .group_by(func.date(PersonCustomerStatus.became_customer_at))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── bot_turns: COUNT WHERE event_type='turn_completed' por created_on::date ──
    async def bot_turns_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int]]:
        """SOLO event_type='turn_completed' (un turno emite varios eventos — NO COUNT(*) de toda la
        tabla, inflaría 2-3x). bot_event NO tiene SoftDelete (append-only)."""
        q = (
            select(func.date(BotEvent.created_on), func.count())
            .where(
                BotEvent.created_on >= since,
                BotEvent.created_on < until,
                BotEvent.event_type == BotEventType.turn_completed,
            )
            .group_by(func.date(BotEvent.created_on))
        )
        return [(row[0], row[1]) for row in (await db.execute(q)).all()]

    # ── bot_cost: count=SUM(tokens_in+tokens_out); value=SUM(cost_estimated_usd) ──
    async def bot_cost_by_day(
        self, db: AsyncSession, *, since: datetime, until: datetime
    ) -> list[tuple[date, int, Decimal]]:
        """(día, total_tokens, total_cost_usd). COALESCE en TODO (tokens/cost nullables). El SUM del
        costo es a PLENA precisión (cost_estimated_usd es Numeric(10,6); el rollup `value` es
        Numeric(14,6)) — NO se castea por fila a centavos (eso truncaría cada costo LLM sub-centavo
        a 0.00 antes de sumar → el total saldría siempre ~0; review F1). Sin filtro de event_type
        (todos los eventos con tokens/costo aportan)."""
        q = (
            select(
                func.date(BotEvent.created_on),
                func.coalesce(
                    func.sum(
                        func.coalesce(BotEvent.tokens_in, 0) + func.coalesce(BotEvent.tokens_out, 0)
                    ),
                    0,
                ),
                func.coalesce(func.sum(func.coalesce(BotEvent.cost_estimated_usd, 0)), 0),
            )
            .where(
                BotEvent.created_on >= since,
                BotEvent.created_on < until,
            )
            .group_by(func.date(BotEvent.created_on))
        )
        return [(row[0], row[1], row[2]) for row in (await db.execute(q)).all()]


source_aggregation_repository = SourceAggregationRepository()
