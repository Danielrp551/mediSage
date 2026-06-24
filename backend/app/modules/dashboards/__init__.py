"""
Módulo `dashboards` (#10, OE3) — panel de conversión en tiempo real + reportes. READ-ONLY:
agrega data que YA existe en prod (crm/scheduling/conversations/bots/marketing) a una capa de
agregación materializada (rollup diario). Ver docs/modules/dashboards/{README,backend,ui,frontend}.md,
ADR-015 y design.md.

ESTADO: F0 (Prep) — paquete INERTE. NO está registrado en `app/modules/__init__.py` ni montado en
`app/main.py`, por lo que sus rutas dan 404. No tiene migración en F0 (solo se siembran los 3
permisos en `app/core/seed.py` y se declaran las Settings en `app/core/config.py`).

F1 agrega: los modelos del rollup (`dashboard_daily_metric` + `dashboard_refresh_state`), los
repositorios/servicios de agregación, los endpoints de lectura (funnel/leads-evolution/
appointments-distribution/summary/meta) + el endpoint de refresco (shared-secret, target del
Cloud Scheduler), registra el módulo y agrega la migración `0026_dashboard_metric` + índices
aditivos. F2 = panel frontend (Fluent Charts). F3 = reportes PDF/Excel server-side.
"""
