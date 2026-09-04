"""Demo user directory + authorization checks.

The directory is ``data/config/users.yaml`` (salted SHA-256 password hashes)
plus a process-local registry for farmers who self-register in the UI. There
is no database: newly registered accounts live only for the server process and
are labelled as such in the UI. This is deliberately simple and honest — it is
not a production identity provider.
"""
from __future__ import annotations

import hashlib
import re
import threading
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml

from core import CONFIG_DIR
from .models import Permission, PermissionDenied, Role, User

_LOCK = threading.Lock()
_RUNTIME_USERS: Dict[str, Dict[str, Any]] = {}      # username -> record (self-registered, session-process only)
_USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")


def _load_directory(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or (CONFIG_DIR / "users.yaml")
    with open(p, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _to_user(rec: Dict[str, Any], is_demo: bool) -> User:
    return User(username=rec["username"], display_name=rec.get("display_name") or rec["username"], role=Role(rec["role"]),
                organisation=rec.get("organisation") or "", farm_id=rec.get("farm_id"), bank_name=rec.get("bank_name"),
                home_state=rec.get("home_state"), is_demo_account=is_demo)


def user_directory() -> List[Dict[str, Any]]:
    """All known accounts (without password hashes) — for the admin Users page."""
    d = _load_directory()
    out = []
    for rec in d.get("users", []):
        out.append({k: v for k, v in rec.items() if k != "password_sha256"} | {"origin": "users.yaml (demo directory)"})
    with _LOCK:
        for rec in _RUNTIME_USERS.values():
            out.append({k: v for k, v in rec.items() if k != "password_sha256"} | {"origin": "self-registered (this server session only)"})
    return out


def list_users(role: Optional[Role] = None) -> List[User]:
    d = _load_directory()
    users = [_to_user(r, True) for r in d.get("users", [])]
    with _LOCK:
        users += [_to_user(r, False) for r in _RUNTIME_USERS.values()]
    if role is not None:
        users = [u for u in users if u.role == role]
    return users


def authenticate(username: str, password: str) -> Optional[User]:
    """Return the User on success, None otherwise. Constant-shape on failure."""
    username = (username or "").strip().lower()
    if not username or password is None:
        return None
    d = _load_directory()
    salt = d.get("salt", "")
    for rec in d.get("users", []):
        if rec["username"].lower() == username and rec.get("password_sha256") == _hash(password, salt):
            return _to_user(rec, True)
    with _LOCK:
        rec = _RUNTIME_USERS.get(username)
    if rec and rec.get("password_sha256") == _hash(password, salt):
        return _to_user(rec, False)
    return None


def register_farmer(username: str, display_name: str, password: str, organisation: str = "") -> User:
    """Self-registration is restricted to the farmer role (other roles are provisioned by an administrator)."""
    username = (username or "").strip().lower()
    if not _USERNAME_RE.match(username):
        raise ValueError("Username must be 3–32 characters: lowercase letters, digits, '.', '_' or '-'.")
    if not display_name or not display_name.strip():
        raise ValueError("Please enter your name.")
    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")
    d = _load_directory()
    if any(r["username"].lower() == username for r in d.get("users", [])):
        raise ValueError("That username already exists.")
    with _LOCK:
        if username in _RUNTIME_USERS:
            raise ValueError("That username already exists.")
        rec = {"username": username, "display_name": display_name.strip(), "role": Role.FARMER.value,
               "organisation": organisation or "", "farm_id": None, "password_sha256": _hash(password, d.get("salt", ""))}
        _RUNTIME_USERS[username] = rec
    return _to_user(rec, False)


# ------------------------------------------------------------------ authorization
def has_permission(user: Optional[User], perm: Permission) -> bool:
    return user is not None and user.can(perm)


def authorize(user: Optional[User], perm: Permission, action: str = "") -> None:
    """Raise PermissionDenied unless ``user`` holds ``perm``. Call this inside core functions."""
    if user is None:
        raise PermissionDenied(f"Sign in required{(' to ' + action) if action else ''}.")
    if not user.can(perm):
        raise PermissionDenied(f"Role '{user.role_label}' is not authorised{(' to ' + action) if action else ''} (needs {perm.value}).")


def require_role(*roles: Role) -> Callable:
    """Decorator: first positional argument must be a User with one of ``roles``."""
    allowed = set(roles)

    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(user: Optional[User], *args, **kwargs):
            if user is None:
                raise PermissionDenied(f"Sign in required for {fn.__name__}.")
            if user.role not in allowed:
                raise PermissionDenied(f"Role '{user.role_label}' cannot call {fn.__name__} (allowed: {', '.join(r.value for r in allowed)}).")
            return fn(user, *args, **kwargs)
        return wrapper
    return deco
