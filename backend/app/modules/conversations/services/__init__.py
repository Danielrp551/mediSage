"""Services del módulo `conversations` (skeleton F0, inerte).

Módulos de funciones (no clases); lanzan excepciones de dominio (nunca
`HTTPException`); `actor_id` explícito desde el router. Incluyen el CRUD de
`ChannelAccount` + `get_credentials` (delega a `app.core.secrets` / fallback env),
la orquestación de `Conversation` (`find_or_create_open`, take/release/close/
reopen/mark_read), el envío/recepción de `Message` y el sub-paquete
`webhook_processor/` (cohesión por canal: `whatsapp.py`). Se introducen por fases
(F1: channel_account; F2: conversation + webhook_processor inbound; F3: outbound +
handoff). F0 no declara services todavía.
"""
