"""
Firebase Admin SDK bootstrap (ADR-011) — el lado SERVIDOR del read-model Firestore.

- Init LAZY vía ADC (Application Default Credentials): en Cloud Run = la SA del
  servicio (medisage-sa[-qa]); local/dev = ADC de gcloud o key file. NUNCA un key
  file en Secret Manager (ADC es más robusto). La SA necesita `roles/datastore.user`
  (Firestore RW) + `roles/iam.serviceAccountTokenCreator` sobre sí misma (firmar
  custom tokens vía signBlob).
- `get_db()`: cliente Firestore de la database NOMBRADA del entorno (medisage-qa /
  medisage), elegida por `Settings.FIRESTORE_DATABASE` o, si vacía, por `ENV_NAME`
  (`_DB_BY_ENV`) — espeja el patrón de Cloud SQL.
- `mint_custom_token(uid, claims)`: `create_custom_token(uid, developer_claims=claims)`.
- Los writers del read-model (`write_message_doc` / `upsert_conversation_doc` /
  `update_message_status` / `list_message_docs`) son STUBS documentados en F1 — se
  completan en F2 (cuando existen las colecciones). NADA se llama en el boot.

`firebase_admin` se importa LAZY (dentro de las funciones, no al import del módulo)
→ el boot local / smoke sin GCP NO rompe. El smoke (sqlite) NUNCA llama Firestore:
el path de test mockea estas funciones o usa el emulador. Las escrituras del Admin
SDK BYPASSAN las Security Rules (esas gobiernan solo al cliente Web).
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings

_app: Any = None  # firebase_admin.App lazy
_db: Any = None  # firestore client lazy

# Database nombrada por entorno (espeja Cloud SQL). dev → la (default) o el emulador.
_DB_BY_ENV = {"prod": "medisage", "qa": "medisage-qa"}


def _resolve_database_id() -> str | None:
    """`Settings.FIRESTORE_DATABASE` explícito gana; si vacío, se elige por ENV_NAME.
    None → la database `(default)`."""
    settings = get_settings()
    if settings.FIRESTORE_DATABASE:
        return settings.FIRESTORE_DATABASE
    return _DB_BY_ENV.get(settings.ENV_NAME)


def _get_app() -> Any:
    """Inicializa el Firebase Admin App vía ADC en la primera llamada (no al import).
    Import diferido de `firebase_admin`: solo se carga en Cloud Run / con ADC presente."""
    global _app
    if _app is None:
        import firebase_admin
        from firebase_admin import credentials

        # ADC: en Cloud Run resuelve la SA del servicio; local usa gcloud ADC / key file.
        _app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            {"projectId": get_settings().GCP_PROJECT_ID},
        )
    return _app


def get_db() -> Any:
    """Cliente Firestore de la database nombrada del entorno."""
    global _db
    if _db is None:
        from firebase_admin import firestore

        database_id = _resolve_database_id()  # None → (default) DB
        _db = firestore.client(app=_get_app(), database_id=database_id)
    return _db


def mint_custom_token(uid: str, claims: dict[str, Any]) -> str:
    """Firebase Custom Token (JWT firmado vía signBlob por la SA). Lo intercambia el
    browser por un ID token (1 h) con `signInWithCustomToken`. `claims` van como
    `developer_claims` y quedan en `request.auth.token` (los leen las Security Rules)."""
    from firebase_admin import auth

    token = auth.create_custom_token(uid, developer_claims=claims, app=_get_app())
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)


def revoke_tokens(uid: str) -> None:
    """Logout / cambio de permisos → invalida los refresh tokens Firebase del uid."""
    from firebase_admin import auth

    auth.revoke_refresh_tokens(uid, app=_get_app())


# ── Writers del read-model (STUBS F1 — se completan en F2, ADR-011) ──────────────
# El stream de mensajes vive en Firestore como read-model real-time. En F2 el relay
# del Transactional Outbox los invoca con el Admin SDK (`set(doc_id)` idempotente).
# En F1 quedan documentados e inertes: NADA los llama todavía.


def write_message_doc(conversation_id: str, doc: dict[str, Any]) -> None:
    """F2: conversations/{cid}/messages/{mid} ← set(doc). doc-id = doc['id'] (mid) →
    create-if-absent idempotente (reprocesar el outbox no duplica)."""
    raise NotImplementedError("write_message_doc se implementa en F2 (ADR-011)")


def upsert_conversation_doc(conversation_id: str, doc: dict[str, Any]) -> None:
    """F2: conversations/{cid} ← set(doc, merge=True). Espejo liviano del Conversation
    de Postgres (status/assignee/allowed_reader_ids/preview/unread)."""
    raise NotImplementedError("upsert_conversation_doc se implementa en F2 (ADR-011)")


def update_message_status(conversation_id: str | None, patch: dict[str, Any]) -> None:
    """F2: patch del doc de un mensaje (delivered/read/failed + external_status)."""
    raise NotImplementedError("update_message_status se implementa en F2 (ADR-011)")


def list_message_docs(
    conversation_id: str, *, skip: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """F2: fallback server-side (SSR / sin Firestore en el cliente): lee
    conversations/{cid}/messages orderBy created_at, pagina. Devuelve (docs, total)."""
    raise NotImplementedError("list_message_docs se implementa en F2 (ADR-011)")
