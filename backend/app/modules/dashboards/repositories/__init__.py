"""
Repositorios del módulo `dashboards`. INERTE en F0.

F1 agrega:
- `dashboard_metric`: plano de LECTURA (SUM/COALESCE + group_by sobre `dashboard_daily_metric` por
  rango + filtros; molde `marketing/repositories/promotion_usage.py:usage_summary`).
- `source_aggregation`: plano de CÓMPUTO del refresco (agrega las tablas FUENTE por día; bucketing
  por día con `func.date(col)` — compila en Postgres y sqlite; ver design.md §6).
- `dashboard_refresh_state`: lectura/escritura del singleton de frescura.
No extienden `get_paginated` (no es un listado paginado); son queries de agregación dedicadas.
"""
