"""
Importar los modelos acá los registra en Base.metadata antes de que Alembic lea el
esquema y antes de resolver los relationship() por string. Orden: connection antes
que source (source FK→connection).
"""

from app.modules.calendar.models.calendar_connection import CalendarConnection
from app.modules.calendar.models.calendar_source import CalendarSource

__all__ = ["CalendarConnection", "CalendarSource"]
