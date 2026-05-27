"""
Persistence for refresh-token families. See `models/token_family.py` for
the rotation contract.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin.models.token_family import TokenFamily
from app.shared.utils import generate_uuid, utc_now


async def create_family(
    db: AsyncSession,
    *,
    family_id: str,
    user_id: str,
    initial_jti: str,
) -> TokenFamily:
    family = TokenFamily(
        id=generate_uuid(),
        family_id=family_id,
        user_id=user_id,
        current_jti=initial_jti,
        created_at=utc_now(),
    )
    db.add(family)
    await db.flush()
    return family


async def get_family(db: AsyncSession, family_id: str) -> TokenFamily | None:
    q = select(TokenFamily).where(TokenFamily.family_id == family_id)
    return (await db.execute(q)).scalars().first()


async def get_family_for_update(db: AsyncSession, family_id: str) -> TokenFamily | None:
    """Same as `get_family` but with `SELECT ... FOR UPDATE` to serialise
    concurrent refreshes against the same family.

    Without this lock, two refresh requests carrying the same `jti` can
    both observe `current_jti == incoming_jti` and both rotate — neither
    triggers reuse detection. The lock forces the second request to wait
    until the first commits, by which time `current_jti` has changed and
    the second is correctly identified as reuse.

    SQLite ignores `FOR UPDATE` (no-op), so tests still pass.
    """
    q = select(TokenFamily).where(TokenFamily.family_id == family_id).with_for_update()
    return (await db.execute(q)).scalars().first()


async def rotate_jti(db: AsyncSession, family: TokenFamily, new_jti: str) -> None:
    """Mark this rotation step. Caller is responsible for verifying the
    incoming jti matched `family.current_jti` before calling."""
    family.current_jti = new_jti
    await db.flush()


async def revoke(db: AsyncSession, family: TokenFamily, *, reason: str) -> None:
    family.revoked_at = utc_now()
    family.reason = reason
    await db.flush()
