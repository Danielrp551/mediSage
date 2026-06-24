"""
Aggregator del módulo `dashboards` (prefix `/dashboards`, montado bajo `/api/v1/` en main.py).
F1: `metrics` (lecturas DASHBOARD_VIEW: funnel/leads-evolution/appointments-distribution/summary
+ GET meta) + `refresh` (interno, shared-secret, target del Cloud Scheduler). F3: `report`
(REPORTS_EXPORT, binario PDF/Excel).
"""

from fastapi import APIRouter

from app.modules.dashboards.routers.metrics import router as metrics_router
from app.modules.dashboards.routers.refresh import router as refresh_router
from app.modules.dashboards.routers.report import router as report_router

router = APIRouter(prefix="/dashboards")
router.include_router(metrics_router)
router.include_router(refresh_router)
router.include_router(report_router)

__all__ = ["router"]
