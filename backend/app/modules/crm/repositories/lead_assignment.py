"""
Repositorio de la asignación de owner (LeadAssignment). `get_active_for_person`
resuelve el owner vivo. `pick_round_robin_advisor` elige el asesor con MENOS
asignaciones vivas (filas LeadAssignment con `deleted_at IS NULL`; desempate:
asignación más antigua primero) con `SELECT … FOR UPDATE` sobre el candidato para
serializar dos auto-asignaciones concurrentes. `advisor_map` es el batch lookup
(person_id → advisor_user_id) que alimenta PersonItem.assigned_advisor.

⚠ Nota (ADR-008/spec): el cierre de un lead (`transition` a `is_final`) soft-deletea
el PersonLeadStatus pero NO el LeadAssignment → la asignación queda viva y sigue
contando como "carga" del asesor. Es el comportamiento de la spec (cuenta filas
LeadAssignment vivas). Si se quiere que la carga refleje solo leads ABIERTOS, F4/F5
debe decidir explícitamente (cerrar también la asignación, o exigir un EXISTS de
PersonLeadStatus vivo en `active_lead_count`).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models.associations import user_role
from app.modules.admin.models.role import Role
from app.modules.admin.models.user import User
from app.modules.crm.models.lead_assignment import LeadAssignment
from app.shared.base_repository import BaseRepository


class LeadAssignmentRepository(BaseRepository[LeadAssignment]):
    ALLOWED_FIELDS: set[str] = set()

    def __init__(self) -> None:
        super().__init__(LeadAssignment)

    async def get_active_for_person(
        self, db: AsyncSession, person_id: str
    ) -> LeadAssignment | None:
        result = await db.execute(
            select(LeadAssignment).where(
                LeadAssignment.person_id == person_id,
                LeadAssignment.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def advisor_map(self, db: AsyncSession, person_ids: list[str]) -> dict[str, str]:
        """person_id → advisor_user_id del owner vivo (batch, sin N+1). El service
        resuelve los advisor_user_id a UserAuditInfo vía get_audit_info_map."""
        if not person_ids:
            return {}
        result = await db.execute(
            select(LeadAssignment.person_id, LeadAssignment.advisor_user_id).where(
                LeadAssignment.person_id.in_(person_ids),
                LeadAssignment.deleted_at.is_(None),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def pick_round_robin_advisor(self, db: AsyncSession) -> str | None:
        """Elige el ASESOR con menos asignaciones vivas (LeadAssignment con
        deleted_at IS NULL; empate → asignación más antigua). Ver la nota del módulo:
        un lead cerrado deja su LeadAssignment vivo y sigue contando. FOR UPDATE sobre
        la fila del candidato serializa dos auto-asignaciones concurrentes (ADR-003).
        Devuelve el user_id o None."""
        active_lead_count = (
            select(func.count(LeadAssignment.id))
            .where(
                LeadAssignment.advisor_user_id == User.id,
                LeadAssignment.deleted_at.is_(None),
            )
            .scalar_subquery()
            .label("lead_count")
        )
        last_assigned = (
            select(func.max(LeadAssignment.assigned_at))
            .where(LeadAssignment.advisor_user_id == User.id)
            .scalar_subquery()
            .label("last_assigned")
        )
        stmt = (
            select(User.id)
            .join(user_role, user_role.c.user_id == User.id)
            .join(Role, Role.id == user_role.c.role_id)
            .where(
                Role.name == "ASESOR",
                User.active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(active_lead_count.asc(), last_assigned.asc().nulls_first())
            .limit(1)
            .with_for_update()
        )
        result = await db.execute(stmt)
        return result.scalars().first()


lead_assignment_repository = LeadAssignmentRepository()
