"""
Services del módulo `calendar` (F1+): conexión OAuth (start/callback con `state` firmado),
mapeo calendario→sede (replace atómico), lectura best-effort del overlay (`read_external_events`,
nunca 5xx), y los adaptadores nativos de proveedor en `services/providers/` (Google Calendar API
+ Microsoft Graph vía httpx; molde ADR-005). INERTE en F0 (llegan en F1/F2).
"""
