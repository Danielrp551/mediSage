"""
Routers del módulo `dashboards` (aggregator, prefix `/dashboards`). INERTE en F0 — NO montado en
`app/main.py` (las rutas dan 404 hasta F1).

F1 agrega los endpoints de lectura (todos `DASHBOARD_VIEW`): POST `/funnel`, `/leads-evolution`,
`/appointments-distribution`, `/summary`; GET `/meta`. Más POST `/internal/refresh` (auth
SHARED-SECRET, NO JWT/RBAC; `hmac.compare_digest`, molde ADR-012 — target del Cloud Scheduler).
F3 agrega POST `/report` (`REPORTS_EXPORT`, binario PDF/Excel). Rutas estáticas antes que params.
"""
