"""
Exportación de reportes (REPORTS_EXPORT). `POST /report` lleva `ReportRequest` en el body y
devuelve un binario PDF/Excel para descargar.

Devuelve `fastapi.Response` CRUDO (NO `SingleResponse[...]` ni `response_model`): el binario es
transporte, no payload de dominio — única excepción a "el router no construye respuestas a mano",
junto al webhook de WhatsApp. El service valida el formato (REPORT_FORMAT_NOT_SUPPORTED) y el rango
(DASHBOARD_INVALID_DATE_RANGE); el handler global de excepciones traduce ambos al envelope de error.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.core.dependencies import DBSession, RequirePermission
from app.modules.dashboards.schemas.report import ReportRequest
from app.modules.dashboards.services import report as report_service

router = APIRouter(tags=["dashboards"])
_EXPORT = Depends(RequirePermission("REPORTS_EXPORT"))


@router.post("/report", dependencies=[_EXPORT])
async def report(payload: ReportRequest, db: DBSession) -> Response:
    content, media_type, filename = await report_service.generate_report(db, payload)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
