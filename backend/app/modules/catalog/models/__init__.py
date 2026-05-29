"""
Importing models here ensures SQLAlchemy registers them on `Base.metadata`
before Alembic reads the schema.
"""

from app.modules.catalog.models.product import Product
from app.modules.catalog.models.service import Service
from app.modules.catalog.models.vertical import Vertical

__all__ = ["Product", "Service", "Vertical"]
