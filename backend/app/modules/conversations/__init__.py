"""Módulo `conversations`: el dueño del pipe de mensajería multicanal. Recibe
mensajes inbound desde los webhooks de los proveedores (WhatsApp Cloud API en el
MVP), los persiste, identifica al `Person` que escribe vía
`crm.find_by_identifier_or_create`, deja la conversación en la bandeja del asesor
(auto-asignada al dueño del lead, con fallback a bandeja compartida) y permite
responder outbound real contra la Graph API de Meta.

Es el módulo #5 del proyecto (catalog → clinic → staff → crm COMPLETOS en prod →
conversations). Skeleton creado en F0 (Prep); el contenido real entra por fases
(ver `docs/modules/conversations/`):
- F1: `ChannelAccount` + `secret_resolver` (`app/core/secrets.py`).
- F2: `Conversation` + `Message` + `MessageAttachment` +
  `ConversationAssignmentLog` + webhook inbound (pipe de recepción).
- F3: handoff (tomar/liberar/cerrar/reabrir) + outbound real (Meta Graph API).
- F4 (diferida): processing de adjuntos/media.

`ChannelType` se REUSA de `crm.enums` (single source of truth; NO se duplica). Las
columnas que apuntan a módulos futuros (`bot_configuration_id`,
`default_campaign_id`) son `varchar(36)` SIN FK hasta que ese módulo exista
(ADR-009). Este paquete NO se registra en `app/modules/__init__.py` ni en
`app/main.py` hasta F1 (los webhooks top-level se cablean en F2).
"""
