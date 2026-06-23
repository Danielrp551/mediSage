"""
Import every module here so SQLAlchemy can resolve cross-module
relationships before `Base.metadata.create_all` or Alembic autogenerate.
"""

from app.modules.admin import models as admin_models  # noqa: F401
from app.modules.bots import models as bots_models  # noqa: F401
from app.modules.calendar import models as calendar_models  # noqa: F401
from app.modules.catalog import models as catalog_models  # noqa: F401
from app.modules.clinic import models as clinic_models  # noqa: F401
from app.modules.conversations import models as conversations_models  # noqa: F401
from app.modules.crm import models as crm_models  # noqa: F401
from app.modules.marketing import models as marketing_models  # noqa: F401
from app.modules.scheduling import models as scheduling_models  # noqa: F401

__all__ = [
    "admin_models",
    "bots_models",
    "calendar_models",
    "catalog_models",
    "clinic_models",
    "conversations_models",
    "crm_models",
    "marketing_models",
    "scheduling_models",
]
