"""
Import every module here so SQLAlchemy can resolve cross-module
relationships before `Base.metadata.create_all` or Alembic autogenerate.
"""

from app.modules.admin import models as admin_models  # noqa: F401
from app.modules.catalog import models as catalog_models  # noqa: F401

__all__ = ["admin_models", "catalog_models"]
