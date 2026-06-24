"""
Plano de LECTURA del panel. Cada función arma su response SUMANDO el rollup
(dashboard_metric_repository) sobre el rango+filtros del DashboardFilter + resolviendo los codes a
labels/colores con catalog.py (ADR-008). NUNCA escanea las fuentes (eso es refresh). Rollup vacío
→ conteos 0 (NO error, §8). Lanza BadRequestException(DASHBOARD_INVALID_DATE_RANGE) si el rango es
inválido (contrato §8; el code de dominio gana sobre el 422 de Pydantic — §22).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.modules.clinic.repositories.branch import branch_repository
from app.modules.dashboards.enums import DashboardMetric
from app.modules.dashboards.repositories.dashboard_metric import dashboard_metric_repository
from app.modules.dashboards.repositories.dashboard_refresh_state import refresh_state_repository
from app.modules.dashboards.schemas.distribution import DistributionBucket, DistributionSummary
from app.modules.dashboards.schemas.filter import DashboardFilter
from app.modules.dashboards.schemas.funnel import FunnelStage, FunnelSummary
from app.modules.dashboards.schemas.meta import BranchOption, DashboardMeta, StatusOption
from app.modules.dashboards.schemas.series import SeriesMeta, TimeSeries, TimeSeriesPoint
from app.modules.dashboards.schemas.summary import KpiSummary
from app.modules.dashboards.services import catalog
from app.modules.scheduling.enums import AppointmentSource
from app.shared.base_schemas import SingleResponse

_MAX_RANGE_DAYS = 366


def _guard_range(f: DashboardFilter) -> None:
    """Backstop del contrato §8: el code de dominio (400) gana sobre el 422 de Pydantic."""
    if f.date_to < f.date_from or (f.date_to - f.date_from).days > _MAX_RANGE_DAYS:
        raise BadRequestException(
            "Rango de fechas inválido (date_to anterior a date_from o más de 366 días).",
            code="DASHBOARD_INVALID_DATE_RANGE",
        )


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _appt_total(by_status: dict[str, int]) -> int:
    """Citas 'agendadas' = todas menos RESCHEDULED (cita hija → no doble-contar) y el segmento ''."""
    return sum(v for code, v in by_status.items() if code and code != catalog.RESCHEDULED_APPT_CODE)


async def get_funnel(db: AsyncSession, f: DashboardFilter) -> SingleResponse[FunnelSummary]:
    _guard_range(f)
    lead_map = await catalog.lead_status_map(db)
    won = catalog.won_lead_code(lead_map)

    conv = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.conversations, date_from=f.date_from, date_to=f.date_to
    )
    conv_bot = await dashboard_metric_repository.sum_scalar(
        db,
        metric=DashboardMetric.conversations,
        date_from=f.date_from,
        date_to=f.date_to,
        segment="bot",
    )
    leads = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.leads_created, date_from=f.date_from, date_to=f.date_to
    )
    lead_by_stage = await dashboard_metric_repository.sum_by_segment(
        db, metric=DashboardMetric.lead_stage, date_from=f.date_from, date_to=f.date_to
    )
    appt_by_status = await dashboard_metric_repository.sum_by_segment(
        db,
        metric=DashboardMetric.appointments,
        date_from=f.date_from,
        date_to=f.date_to,
        branch_id=f.branch_id,
    )
    customers = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.customers_new, date_from=f.date_from, date_to=f.date_to
    )

    conv_count = conv[0]
    leads_count = leads[0]
    customers_count = customers[0]
    engaged = sum(lead_by_stage.get(c, 0) for c in catalog.ENGAGED_LEAD_CODES)
    appt_total = _appt_total(appt_by_status)
    confirmed = sum(appt_by_status.get(c, 0) for c in catalog.CONFIRMED_OR_BEYOND_APPT_CODES)

    stages = [
        FunnelStage(
            key="conversations", label="Conversaciones", count=conv_count, rate_from_prev=None
        ),
        FunnelStage(
            key="leads",
            label="Leads",
            count=leads_count,
            rate_from_prev=_rate(leads_count, conv_count),
        ),
        FunnelStage(
            key="engaged",
            label="Contactados/Interesados",
            count=engaged,
            rate_from_prev=_rate(engaged, leads_count),
        ),
        FunnelStage(
            key="appointments",
            label="Citas agendadas",
            count=appt_total,
            rate_from_prev=_rate(appt_total, engaged),
        ),
        FunnelStage(
            key="confirmed",
            label="Citas confirmadas",
            count=confirmed,
            rate_from_prev=_rate(confirmed, appt_total),
        ),
        FunnelStage(
            key="customers",
            label="Clientes",
            count=customers_count,
            rate_from_prev=_rate(customers_count, confirmed),
        ),
    ]
    return SingleResponse(
        data=FunnelSummary(
            stages=stages,
            conversion_rate=_rate(lead_by_stage.get(won or "", 0), leads_count),
            total_leads=leads_count,
            total_appointments=appt_total,
            total_customers=customers_count,
            chatbot_share=_rate(conv_bot[0], conv_count),
        )
    )


async def get_leads_evolution(db: AsyncSession, f: DashboardFilter) -> SingleResponse[TimeSeries]:
    _guard_range(f)
    lead_map = await catalog.lead_status_map(db)
    data = await dashboard_metric_repository.sum_by_date_segment(
        db, metric=DashboardMetric.lead_stage, date_from=f.date_from, date_to=f.date_to
    )

    present = {seg for (_d, seg) in data if seg and seg in lead_map}
    series = [
        SeriesMeta(key=code, label=lead_map[code]["name"], color=lead_map[code]["color"])
        for code in sorted(present, key=lambda c: lead_map[c]["display_order"])
    ]

    points: list[TimeSeriesPoint] = []
    day = f.date_from
    while day <= f.date_to:
        values = {seg: cnt for (d, seg), cnt in data.items() if d == day and seg and cnt}
        points.append(TimeSeriesPoint(date=day.isoformat(), values=values))
        day += timedelta(days=1)

    return SingleResponse(data=TimeSeries(series=series, points=points))


async def get_appointments_distribution(
    db: AsyncSession, f: DashboardFilter
) -> SingleResponse[DistributionSummary]:
    _guard_range(f)
    appt_map = await catalog.appointment_status_map(db)
    by_status = await dashboard_metric_repository.sum_by_segment(
        db,
        metric=DashboardMetric.appointments,
        date_from=f.date_from,
        date_to=f.date_to,
        branch_id=f.branch_id,
    )
    codes = sorted(
        (c for c in by_status if c),
        key=lambda c: appt_map.get(c, {}).get("display_order", 9999),
    )
    buckets = [
        DistributionBucket(
            code=code,
            label=appt_map.get(code, {}).get("name", code),
            color=appt_map.get(code, {}).get("color"),
            count=by_status[code],
        )
        for code in codes
    ]
    total = sum(by_status[c] for c in by_status if c)
    return SingleResponse(data=DistributionSummary(buckets=buckets, total=total))


async def get_summary(db: AsyncSession, f: DashboardFilter) -> SingleResponse[KpiSummary]:
    _guard_range(f)
    lead_map = await catalog.lead_status_map(db)
    won = catalog.won_lead_code(lead_map)

    conv = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.conversations, date_from=f.date_from, date_to=f.date_to
    )
    conv_bot = await dashboard_metric_repository.sum_scalar(
        db,
        metric=DashboardMetric.conversations,
        date_from=f.date_from,
        date_to=f.date_to,
        segment="bot",
    )
    leads = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.leads_created, date_from=f.date_from, date_to=f.date_to
    )
    lead_by_stage = await dashboard_metric_repository.sum_by_segment(
        db, metric=DashboardMetric.lead_stage, date_from=f.date_from, date_to=f.date_to
    )
    appt_by_status = await dashboard_metric_repository.sum_by_segment(
        db,
        metric=DashboardMetric.appointments,
        date_from=f.date_from,
        date_to=f.date_to,
        branch_id=f.branch_id,
    )
    customers = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.customers_new, date_from=f.date_from, date_to=f.date_to
    )
    bot_turns = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.bot_turns, date_from=f.date_from, date_to=f.date_to
    )
    bot_cost = await dashboard_metric_repository.sum_scalar(
        db, metric=DashboardMetric.bot_cost, date_from=f.date_from, date_to=f.date_to
    )

    leads_count = leads[0]
    appt_total = _appt_total(appt_by_status)
    confirmed = sum(appt_by_status.get(c, 0) for c in catalog.CONFIRMED_OR_BEYOND_APPT_CODES)
    attended = appt_by_status.get(catalog.ATTENDED_APPT_CODE, 0)
    no_show = appt_by_status.get(catalog.NO_SHOW_APPT_CODE, 0)
    customers_count = customers[0]

    return SingleResponse(
        data=KpiSummary(
            conversion_rate=_rate(lead_by_stage.get(won or "", 0), leads_count),
            lead_to_appt_rate=_rate(appt_total, leads_count),
            confirmation_rate=_rate(confirmed, appt_total),
            show_rate=_rate(attended, attended + no_show),
            no_show_rate=_rate(no_show, attended + no_show),
            customer_rate=_rate(customers_count, attended),
            total_conversations=conv[0],
            conversations_bot=conv_bot[0],
            total_leads=leads_count,
            total_appointments=appt_total,
            total_confirmed=confirmed,
            total_attended=attended,
            total_customers=customers_count,
            bot_turns=bot_turns[0],
            bot_cost_usd=f"{bot_cost[1]:.2f}",
        )
    )


async def get_meta(db: AsyncSession) -> SingleResponse[DashboardMeta]:
    state = await refresh_state_repository.get(db)
    lead_map = await catalog.lead_status_map(db)
    appt_map = await catalog.appointment_status_map(db)
    branches = await branch_repository.list_active(db)

    lead_statuses = [
        StatusOption(code=c, name=m["name"], color=m["color"], display_order=m["display_order"])
        for c, m in sorted(lead_map.items(), key=lambda kv: kv[1]["display_order"])
    ]
    appointment_statuses = [
        StatusOption(code=c, name=m["name"], color=m["color"], display_order=m["display_order"])
        for c, m in sorted(appt_map.items(), key=lambda kv: kv[1]["display_order"])
    ]
    return SingleResponse(
        data=DashboardMeta(
            last_refreshed_at=(
                state.last_refreshed_at.isoformat() if state and state.last_refreshed_at else None
            ),
            lead_statuses=lead_statuses,
            appointment_statuses=appointment_statuses,
            branches=[BranchOption(id=b.id, name=b.name) for b in branches],
            sources=[s.value for s in AppointmentSource],
        )
    )
