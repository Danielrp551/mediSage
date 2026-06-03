"""
Routers TOP-LEVEL (sin JWT) que no pertenecen al RBAC del template — hoy: los webhooks de
proveedores de mensajería (Meta/WhatsApp). Se montan bajo `settings.API_V1_PREFIX` en
`main.py`. La autenticación es la firma del proveedor (HMAC) / el verify token, NO el JWT.
"""
