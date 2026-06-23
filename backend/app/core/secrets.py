"""
Resolución de secretos por-cuenta vía GCP Secret Manager SDK en RUNTIME (ADR-010).
El template inyecta secretos FIJOS por entorno vía `--set-secrets` de Cloud Run
(SECRET_KEY, DB creds → env vars que lee `Settings`). Las credenciales por
`ChannelAccount` necesitan resolución DINÁMICA para operar N números de WhatsApp
sin redeploy → este resolver.

- `resolve(secret_name) -> dict[str, str]`: parsea el payload del secreto como JSON
  ({access_token, app_secret, phone_number_id?}), con cache TTL en memoria (~10 min)
  para no golpear Secret Manager por webhook.
- El cliente del SDK se inicializa LAZY (no al import) → la app bootea sin GCP
  (local/test). El smoke (sqlite, ENV_NAME=dev) NUNCA llama Secret Manager: el
  fallback a env de `channel_account.get_credentials` lo evita.
- La SA de Cloud Run ya tiene `roles/secretmanager.secretAccessor`.

Reusable por cualquier módulo futuro con secretos por-tenant/cuenta (ej. bots #6).
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import BadRequestException

_CACHE: dict[str, tuple[dict[str, str], float]] = {}  # secret_name -> (creds, expires_at)
_TTL_SECONDS = 600
_client: Any = None  # lazy SecretManagerServiceAsyncClient


def _get_client() -> Any:
    """Construye el cliente async del SDK en la primera llamada (no al import).
    Import diferido: el paquete `google-cloud-secret-manager` solo se necesita en
    Cloud Run; el boot local / smoke no lo carga."""
    global _client
    if _client is None:
        from google.cloud import secretmanager

        _client = secretmanager.SecretManagerServiceAsyncClient()
    return _client


async def resolve(secret_name: str) -> dict[str, str]:
    """`secret_name` puede ser el nombre corto (`medisage-whatsapp-estetica-qa`) o el
    resource name completo (`projects/.../secrets/.../versions/latest`). Cachea por
    TTL (~10 min). Error (NotFound / PermissionDenied / JSON inválido) →
    CHANNEL_CREDENTIALS_MISSING."""
    now = time.monotonic()
    cached = _CACHE.get(secret_name)
    if cached is not None and cached[1] > now:
        return cached[0]
    settings = get_settings()
    resource = (
        secret_name
        if secret_name.startswith("projects/")
        else f"projects/{settings.GCP_PROJECT_ID}/secrets/{secret_name}/versions/latest"
    )
    try:
        client = _get_client()
        response = await client.access_secret_version(name=resource)
        creds: dict[str, str] = json.loads(response.payload.data.decode("utf-8"))
    except Exception as exc:  # NotFound / PermissionDenied / JSON inválido / SDK ausente
        raise BadRequestException(
            "No se pudo resolver el secreto del canal", code="CHANNEL_CREDENTIALS_MISSING"
        ) from exc
    _CACHE[secret_name] = (creds, now + _TTL_SECONDS)
    return creds


async def put(name: str, payload: dict[str, Any]) -> None:
    """Crea el secreto (si no existe) + agrega una versión con `payload` (JSON). Idempotente
    en la creación (`AlreadyExists` se ignora). Invalida la cache del secreto para que el
    próximo `resolve()` lea la versión nueva (rotación inmediata).

    Lo usa `calendar` para guardar/rotar los tokens OAuth por conexión (ADR-010 extendido a
    escritura). La SA de Cloud Run ya tiene `secretmanager.secretAccessor`; ESTO requiere
    además `secretmanager.admin` (o secretVersionAdder + create). Error → CALENDAR_CREDENTIALS_
    MISSING (espeja CHANNEL_CREDENTIALS_MISSING de `resolve`). Reusa el cliente lazy `_get_client`."""
    settings = get_settings()
    project = f"projects/{settings.GCP_PROJECT_ID}"
    parent = f"{project}/secrets/{name}"
    data = json.dumps(payload).encode("utf-8")
    try:
        client = _get_client()
        from google.api_core.exceptions import AlreadyExists

        try:
            await client.create_secret(
                parent=project,
                secret_id=name,
                secret={"replication": {"automatic": {}}},
            )
        except AlreadyExists:
            pass  # el secreto ya existe → seguimos a add_version (idempotente)
        await client.add_secret_version(parent=parent, payload={"data": data})
    except Exception as exc:  # PermissionDenied / SDK ausente / cuota / etc.
        raise BadRequestException(
            "No se pudo escribir el secreto del calendario",
            code="CALENDAR_CREDENTIALS_MISSING",
        ) from exc
    _CACHE.pop(name, None)  # invalida la cache (el próximo resolve lee la versión nueva)


def clear_cache() -> None:
    """Invalida la cache (rotación inmediata de credenciales / tests)."""
    _CACHE.clear()
