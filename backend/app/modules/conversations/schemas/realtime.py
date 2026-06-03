"""
Schema de la respuesta del endpoint de real-time token (ADR-011).

`token` = Firebase Custom Token (JWT firmado por el backend vía Admin SDK; lo
intercambia el browser por un ID token de 1 h con `signInWithCustomToken`). NO es un
secreto persistente: es de vida corta y gateado por el RBAC del template (el endpoint
exige `CONVERSATIONS_READ` o `MY_CONVERSATIONS_READ`). `firebase_config` = config PÚBLICA
del proyecto Firebase (apiKey/projectId/etc. — config, NO secretos) por conveniencia; el
front normalmente la trae de sus `NEXT_PUBLIC_FIREBASE_*` → opcional (None).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class RealtimeTokenResponse(BaseModel):
    token: str
    firebase_config: dict[str, Any] | None = None
