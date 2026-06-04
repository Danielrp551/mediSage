"""
Routers del módulo `bots` (F1+). Aggregator bajo `/bots` (configurations CRUD + /active +
versions + activate-version + tools CRUD + M:N + state/events/tool-calls) + `/engine/dispatch-manual`
(RBAC `BOT_ENGINE_INVOKE`). El endpoint `POST /api/v1/bots/engine/dispatch` (target de Cloud
Tasks, auth OIDC/shared-secret, NO RBAC) es top-level. `/engine/external/*` DIFERIDO (F4).

⚠ F0: NADA montado. El aggregator NO se incluye en `app/main.py` hasta F1 (skeleton inerte).
"""
