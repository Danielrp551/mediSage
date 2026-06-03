"""
Sub-paquete de procesadores de webhook por canal (cohesión por proveedor). `whatsapp.py`
implementa la verificación de firma (HMAC-SHA256 del body raw con el app_secret) + el parse
del payload de WhatsApp Cloud API + la orquestación (resolver Person vía crm →
find_or_create_open → persist_inbound). Telegram/otros se agregan como módulos hermanos sin
tocar el router (URL futura `/webhooks/telegram/{channel_account_id}`).
"""
