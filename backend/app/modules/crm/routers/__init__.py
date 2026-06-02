"""
Agrega los sub-routers de crm bajo un solo prefix. `main.py` incluye este
`router` una sola vez (igual que clinic/staff.routers). El orden importa solo
dentro de cada sub-router (/active y /search antes de /{id}); el orden del
agregador es informativo.

F1: person (/persons/*) + contact_identifier (/persons/{id}/identifiers/*).
F2: lead_status/customer_status (/lead-statuses/*, /customer-statuses/* + matriz).
F3: lead_lifecycle (/persons/{id}/lead-status[...]), assignment
(/persons/{id}/assignment[...] + /advisors/active + /me/leads/list), activity
(/persons/{id}/activities/list — solo lectura; el composer es F5).
F4 agregará customer_lifecycle (/persons/{id}/customer-status[...] + promote).
"""

from fastapi import APIRouter

from app.modules.crm.routers.activity import router as activity_router
from app.modules.crm.routers.assignment import advisors_router, me_router
from app.modules.crm.routers.assignment import router as assignment_router
from app.modules.crm.routers.contact_identifier import router as identifier_router
from app.modules.crm.routers.customer_status import router as customer_status_router
from app.modules.crm.routers.lead_lifecycle import router as lead_lifecycle_router
from app.modules.crm.routers.lead_status import router as lead_status_router
from app.modules.crm.routers.person import router as person_router

router = APIRouter(prefix="/crm")
router.include_router(person_router)  # /persons/*
router.include_router(identifier_router)  # /persons/{id}/identifiers/* (nested)
router.include_router(lead_status_router)  # /lead-statuses/* (+ matriz)
router.include_router(customer_status_router)  # /customer-statuses/* (+ matriz)
router.include_router(lead_lifecycle_router)  # /persons/{id}/lead-status[...]
router.include_router(assignment_router)  # /persons/{id}/assignment[...]
router.include_router(advisors_router)  # /advisors/active
router.include_router(me_router)  # /me/leads/list
router.include_router(activity_router)  # /persons/{id}/activities/list (lectura)
# F4: router.include_router(customer_lifecycle_router)# /persons/{id}/customer-status[...] + promote

__all__ = ["router"]
