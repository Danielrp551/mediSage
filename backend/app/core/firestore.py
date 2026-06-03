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


# ── Writers del read-model (F2 — ADR-011) ────────────────────────────────────────
# El stream de mensajes vive en Firestore como read-model real-time. El relay del
# Transactional Outbox los invoca con el Admin SDK (`set(doc_id)` idempotente). El Admin
# SDK BYPASSA las Security Rules (esas gobiernan solo al cliente Web). Son SÍNCRONOS (la
# lib `firebase_admin` es bloqueante); el relay async los envuelve en `asyncio.to_thread`.
# El smoke (sqlite, sin GCP) NUNCA los llama: los mockea (monkeypatch a este módulo).


def write_message_doc(conversation_id: str, doc: dict[str, Any]) -> None:
    """conversations/{cid}/messages/{mid} ← set(doc). doc-id = doc['id'] (mid) →
    create-if-absent idempotente (reprocesar el outbox no duplica)."""
    db = get_db()
    (
        db.collection("conversations")
        .document(conversation_id)
        .collection("messages")
        .document(doc["id"])
        .set(doc)
    )


def upsert_conversation_doc(conversation_id: str, doc: dict[str, Any]) -> None:
    """conversations/{cid} ← set(doc, merge=True). Espejo liviano del Conversation de
    Postgres (status/assignee/allowed_reader_ids/preview/unread). Idempotente por overwrite."""
    get_db().collection("conversations").document(conversation_id).set(doc, merge=True)


def update_message_status(conversation_id: str | None, patch: dict[str, Any]) -> None:
    """Patch (merge) del doc de un mensaje (delivered/read/failed + external_status). Si
    `conversation_id` + `patch['id']` (mid) vienen → update directo; si NO (status callback
    sin cid) → collection group query por `external_id` para ubicar el doc. No-op si no se
    puede ubicar (status de un mensaje que no enviamos)."""
    db = get_db()
    mid = patch.get("id")
    if conversation_id is not None and mid is not None:
        (
            db.collection("conversations")
            .document(conversation_id)
            .collection("messages")
            .document(mid)
            .set(patch, merge=True)
        )
        return
    external_id = patch.get("external_id")
    if external_id is None:
        return
    from firebase_admin import firestore

    query = (
        db.collection_group("messages")
        .where(filter=firestore.FieldFilter("external_id", "==", external_id))
        .limit(1)
        .stream()
    )
    for snap in query:
        snap.reference.set(patch, merge=True)
        return


def list_message_docs(
    conversation_id: str, *, skip: int, limit: int
) -> tuple[list[dict[str, Any]], int]:
    """Fallback server-side (SSR / sin Firestore en el cliente): lee
    conversations/{cid}/messages orderBy created_at, pagina. Devuelve (docs, total). El
    path PRIMARIO de lectura es el cliente Firestore real-time (onSnapshot)."""
    db = get_db()
    base = db.collection("conversations").document(conversation_id).collection("messages")
    total = base.count().get()[0][0].value  # aggregation query
    docs = [
        snap.to_dict() for snap in base.order_by("created_at").offset(skip).limit(limit).stream()
    ]
    return docs, total
