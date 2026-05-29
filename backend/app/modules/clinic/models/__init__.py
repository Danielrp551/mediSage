"""
Importing models here ensures SQLAlchemy registers them on `Base.metadata`
before Alembic reads the schema.
"""

from app.modules.clinic.models.branch import Branch

__all__ = ["Branch"]
