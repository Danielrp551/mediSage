"""
Agrega los sub-routers de crm bajo un solo prefix. `main.py` incluye este
`router` una sola vez (igual que clinic/staff.routers). El orden importa solo
dentro de cada sub-router (/active y /search antes de /{id}); el orden del
agregador es informativo.

F1 expone `person` (/persons/*) y `contact_identifier` (/persons/{id}/
identifiers/* anidado). F2 agrega lead_status/customer_status (/lead-statuses/*,
/customer-statuses/* + matriz). Las fases siguientes agregan
lead_lifecycle/assignment/activity (F3), customer_lifecycle (F4).
"""

from fastapi import APIRouter

from app.modules.crm.routers.contact_identifier import router as identifier_router
from app.modules.crm.routers.customer_status import router as customer_status_router
from app.modules.crm.routers.lead_status import router as lead_status_router
from app.modules.crm.routers.person import router as person_router

router = APIRouter(prefix="/crm")
router.include_router(person_router)  # /persons/*
router.include_router(identifier_router)  # /persons/{id}/identifiers/* (nested)
router.include_router(lead_status_router)  # /lead-statuses/* (+ matriz)
router.include_router(customer_status_router)  # /customer-statuses/* (+ matriz)
# F3: router.include_router(lead_lifecycle_router)    # /persons/{id}/lead-status[...]
# F4: router.include_router(customer_lifecycle_router)# /persons/{id}/customer-status[...]
# F3: router.include_router(assignment_router)        # /persons/{id}/assignment[...] + /me/leads
# F3: router.include_router(activity_router)          # /persons/{id}/activities/*

__all__ = ["router"]
