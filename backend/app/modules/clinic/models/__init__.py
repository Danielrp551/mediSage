"""
Importing models here ensures SQLAlchemy registers them on `Base.metadata`
before Alembic reads the schema. Import associations first so the M:N table
exists before Office references it.
"""

from app.modules.clinic.models.associations import office_vertical
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.modules.clinic.models.office_closure import OfficeClosure
from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours

__all__ = [
    "Branch",
    "Office",
    "OfficeClosure",
    "OfficeOperatingHours",
    "office_vertical",
]
