"""Routers de `staff`.

En F1 este `__init__.py` se vuelve el aggregator (`router = APIRouter(prefix="/staff")`
que incluye los sub-routers `doctor`/`doctor_availability`/`me`) y se registra una
sola vez en `app/main.py`, igual que `clinic.routers`. Hoy el módulo no expone rutas.
"""
