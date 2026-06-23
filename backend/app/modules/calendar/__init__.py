"""
Módulo `calendar` (#9) — integración de calendario externo agnóstica al proveedor.

Lee la ocupación de los calendarios externos de la clínica (Google Calendar API + Microsoft
Graph, vía adaptadores nativos — molde ADR-005) y la muestra como una capa INFORMATIVA
(overlay no-bloqueante) sobre la grilla de `scheduling`. Fase 1 = solo PULL, nivel clínica:
una (o pocas) conexión(es) OAuth de la clínica, con N calendarios mapeados a sedes (`Branch`).
NO toca `scheduling.compute_available_slots` ni los invariantes de booking → capa puramente
aditiva (un calendario externo caído nunca rompe la grilla ni una reserva). Los tokens OAuth
por conexión viven en Secret Manager (ADR-010). Diseño completo:
`docs/modules/calendar/{README,backend,ui,frontend}.md` + ADR-014.

⚠ F0 (Prep): este paquete es un SKELETON INERTE — los `__init__.py` solo documentan la
estructura. **NO está registrado** en `app/modules/__init__.py` ni en `app/main.py` (lo cablea
F1, como hicieron crm/conversations/bots/scheduling/marketing). Sin modelos/migración todavía →
no aporta tablas ni rutas (las rutas `/calendar/*` dan 404 en F0). Migración inicial
`0025_calendar_connection` (down_revision `0024_marketing_promotion_usage`).
"""
