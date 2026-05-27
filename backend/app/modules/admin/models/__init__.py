"""
Importing this package registers every model with SQLAlchemy. The order
ensures association tables exist before the entities that reference them.
"""

from app.modules.admin.models.associations import (  # noqa: F401
    role_permission,
    user_permission,
    user_role,
)
from app.modules.admin.models.permission import Permission  # noqa: F401
from app.modules.admin.models.role import Role  # noqa: F401
from app.modules.admin.models.token_family import TokenFamily  # noqa: F401
from app.modules.admin.models.user import User  # noqa: F401

__all__ = ["Permission", "Role", "TokenFamily", "User"]
