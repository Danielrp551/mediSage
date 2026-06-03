"""
Real-time token service (ADR-011). Mintea el Firebase Custom Token con developer_claims
que ESPEJAN el RBAC del template (los leen las Security Rules):
- `scope='conversations'` — namespacing del token (las rules lo exigen).
- `can_read_all` = el actor tiene `CONVERSATIONS_READ` (bandeja global / supervisor) → lee
  cualquier hilo. Si solo tiene `MY_CONVERSATIONS_READ` → False → solo sus hilos
  (`uid ∈ allowed_reader_ids`). Es EXACTAMENTE el mismo gate que `POST /list` (global) vs
  `POST /me/conversations/list` (propios), trasladado a las Security Rules vía el claim.
- `is_advisor` = bandera de conveniencia para la UI.

El `uid` del token = `actor.id` = el id que el backend pone en `assignee_user_id` /
`allowed_reader_ids`. El RBAC es la fuente de verdad: el router exige CONVERSATIONS_READ o
MY_CONVERSATIONS_READ ANTES de mintear. `firebase_config` = None → el front usa sus
`NEXT_PUBLIC_FIREBASE_*` (el backend no tiene el apiKey/appId, son config pública del front).
"""

from __future__ import annotations

import asyncio

from app.core.dependencies import AuthContext
from app.modules.conversations.schemas.realtime import RealtimeTokenResponse
from app.shared.base_schemas import SingleResponse


async def mint_token(*, actor: AuthContext) -> SingleResponse[RealtimeTokenResponse]:
    from app.core import firestore

    can_read_all = "CONVERSATIONS_READ" in actor.permissions
    claims = {
        "scope": "conversations",
        "can_read_all": can_read_all,
        "is_advisor": "MY_CONVERSATIONS_READ" in actor.permissions,
    }
    token = await asyncio.to_thread(firestore.mint_custom_token, actor.id, claims)
    return SingleResponse(data=RealtimeTokenResponse(token=token, firebase_config=None))
