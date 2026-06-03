"""Services del módulo `conversations`.

Módulos de funciones (no clases); lanzan excepciones de dominio (nunca
`HTTPException`); `actor_id` explícito desde el router. Incluyen el CRUD de
`ChannelAccount` + `get_credentials` (delega a `app.core.secrets` / fallback env,
ADR-010), la orquestación de `Conversation` (`find_or_create_open`, take/release/
close/reopen/mark_read), la persistencia/relay de mensajes vía el Transactional
Outbox + Firestore (CQRS/ADR-011) y el sub-paquete `webhook_processor/` (cohesión
por canal: `whatsapp.py`). Se introducen por fases (F1: channel_account; F2:
conversation + outbox + webhook_processor inbound; F3: outbound + handoff).
"""
