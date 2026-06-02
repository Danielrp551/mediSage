"""Schemas Pydantic v2 del módulo `conversations` (skeleton F0, inerte).

Variantes por entidad (`Create`, `Update`, `Item`, `Detail`, `Option`) + los
request bodies de las acciones de handoff (`take`/`release`) y de envío de
mensajes. `ChannelAccountDetail` NUNCA expone el valor del secreto (solo
`secret_name` y flags `has_secret`/`has_verify_token`). Se introducen por fases
(F1: channel_account; F2: conversation + message). F0 no declara schemas todavía.
"""
