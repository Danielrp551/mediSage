"""Lecturas del panel (DASHBOARD_VIEW). 4 POST (llevan DashboardFilter en el body) + 1 GET /meta.
Ninguna pagina; todas devuelven SingleResponse[X] (leen el rollup, NO las fuentes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import DBSession, RequirePermission
from app.modules.dashboards.schemas.distribution import DistributionSummary
from app.modules.dashboards.schemas.filter import DashboardFilter
from app.modules.dashboards.schemas.funnel import FunnelSummary
from app.modules.dashboards.schemas.meta import DashboardMeta
from app.modules.dashboards.schemas.series import TimeSeries
from app.modules.dashboards.schemas.summary import KpiSummary
from app.modules.dashboards.services import metrics as metrics_service
from app.shared.base_schemas import SingleResponse

router = APIRouter(tags=["dashboards"])
_VIEW = Depends(RequirePermission("DASHBOARD_VIEW"))


@router.post("/funnel", response_model=SingleResponse[FunnelSummary], dependencies=[_VIEW])
async def funnel(payload: DashboardFilter, db: DBSession) -> SingleResponse[FunnelSummary]:
    return await metrics_service.get_funnel(db, payload)


@router.post("/leads-evolution", response_model=SingleResponse[TimeSeries], dependencies=[_VIEW])
async def leads_evolution(payload: DashboardFilter, db: DBSession) -> SingleResponse[TimeSeries]:
    return await metrics_service.get_leads_evolution(db, payload)


@router.post(
    "/appointments-distribution",
    response_model=SingleResponse[DistributionSummary],
    dependencies=[_VIEW],
)
async def appointments_distribution(
    payload: DashboardFilter, db: DBSession
) -> SingleResponse[DistributionSummary]:
    return await metrics_service.get_appointments_distribution(db, payload)


@router.post("/summary", response_model=SingleResponse[KpiSummary], dependencies=[_VIEW])
async def summary(payload: DashboardFilter, db: DBSession) -> SingleResponse[KpiSummary]:
    return await metrics_service.get_summary(db, payload)


@router.get("/meta", response_model=SingleResponse[DashboardMeta], dependencies=[_VIEW])
async def meta(db: DBSession) -> SingleResponse[DashboardMeta]:
    return await metrics_service.get_meta(db)
