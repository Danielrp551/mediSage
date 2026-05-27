"""
Import every module here so SQLAlchemy can resolve cross-module
relationships before `Base.metadata.create_all` or Alembic autogenerate.
"""

from app.modules.admin import models  # noqa: F401

__all__ = ["models"]
