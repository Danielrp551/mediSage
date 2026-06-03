"""Módulo `conversations`: el dueño del pipe de mensajería multicanal. Recibe
mensajes inbound desde los webhooks de los proveedores (WhatsApp Cloud API en el
MVP), los persiste, identifica al `Person` que escribe vía
`crm.find_by_identifier_or_create`, deja la conversación en la bandeja del asesor
(auto-asignada al dueño del lead, con fallback a bandeja compartida) y permite
responder outbound real contra la Graph API de Meta.

Es el módulo #5 del proyecto (catalog → clinic → staff → crm COMPLETOS en prod →
conversations). El contenido entra por fases (ver `docs/modules/conversations/`):
- F1: `ChannelAccount` + `secret_resolver` (`app/core/secrets.py`) + Firebase Admin
  bootstrap (`app/core/firestore.py`) — registrado en `app/modules/__init__.py` y
  `app/main.py`.
- F2: `Conversation` + `MessageOutbox` + `ConversationAssignmentLog` + webhook
  inbound. El stream de mensajes vive en Firestore como read-model (CQRS/ADR-011),
  NO en Postgres — no hay tablas `Message`/`MessageAttachment`.
- F3: handoff (tomar/liberar/cerrar/reabrir) + outbound real (Meta Graph API).
- F4 (diferida): processing de adjuntos/media (binarios a GCS).

`ChannelType` se REUSA de `crm.enums` (single source of truth; NO se duplica). Las
columnas que apuntan a módulos futuros (`bot_configuration_id`,
`default_campaign_id`) son `varchar(36)` SIN FK hasta que ese módulo exista
(ADR-009). Los webhooks top-level (sin JWT) se cablean en F2
(`app/routers/webhooks.py`)."""
