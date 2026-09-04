"""Authentication + authorization for the four-role platform.

* ``Role`` — the four platform roles.
* ``User`` — a signed-in principal (plain dataclass, session-storable).
* ``authenticate()`` / ``register_farmer()`` — demo user directory backed by
  ``data/config/users.yaml`` + an in-memory registry (no database).
* ``require_role()`` / ``authorize()`` — enforcement helpers used **inside**
  core functions (loan-product management, admin registries, analytics), so a
  hidden button is never the only barrier.

No Streamlit here; the UI stores the ``User`` in ``st.session_state["user"]``.
"""
from .models import Role, User, Permission, ROLE_LABELS, ROLE_PERMISSIONS, PermissionDenied
from .service import authenticate, register_farmer, list_users, require_role, authorize, has_permission, user_directory

__all__ = ["Role", "User", "Permission", "ROLE_LABELS", "ROLE_PERMISSIONS", "PermissionDenied",
           "authenticate", "register_farmer", "list_users", "require_role", "authorize", "has_permission", "user_directory"]
