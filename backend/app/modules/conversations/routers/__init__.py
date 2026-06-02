"""Routers del módulo `conversations` (skeleton F0, inerte).

En F1 este `__init__.py` se convierte en el aggregator (`APIRouter(prefix=
"/conversations")`) que incluye los sub-routers (`channel_account`,
`conversation`, `me`) y lo monta `main.py` una sola vez. El router de webhooks es
TOP-LEVEL (sin JWT) y vive en `app/routers/webhooks.py` — NO acá. El módulo se
registra en `app/modules/__init__.py` + `main.py` recién en F1. F0 no declara
routers todavía.
"""
