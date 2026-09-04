"""Session glue for authentication: who is signed in, login/logout, page guards.

Authorization itself lives in ``core.auth`` and is enforced inside core
functions; these helpers only decide what the UI shows and stop rendering
early for the wrong role.
"""
from __future__ import annotations

from typing import Iterable, Optional

import streamlit as st

from core.auth import Permission, Role, User, ROLE_LABELS
from ui import state

ROLE_ICON = {Role.FARMER: "🌾", Role.BANK_MANAGER: "🏦", Role.GOVERNMENT_OFFICER: "🏛️", Role.ADMINISTRATOR: "🛠️"}
ROLE_TAGLINE = {Role.FARMER: "Personal farm & finance intelligence",
                Role.BANK_MANAGER: "Agricultural Credit Intelligence",
                Role.GOVERNMENT_OFFICER: "Financial Inclusion & Scheme Monitoring",
                Role.ADMINISTRATOR: "Platform administration"}


def current_user() -> Optional[User]:
    d = st.session_state.get("user")
    return User.from_dict(d) if d else None


def login(user: User) -> None:
    st.session_state["user"] = user.to_dict()
    state.clear_context()
    st.session_state.pop("scope_state", None)
    if user.role == Role.FARMER and user.farm_id:
        try:
            state.select_farm(user.farm_id)
        except StopIteration:
            pass


def logout() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def require(*roles: Role, perm: Optional[Permission] = None) -> User:
    """Page guard: stop rendering unless the signed-in user has one of ``roles`` (and ``perm`` if given)."""
    u = current_user()
    if u is None:
        st.error("Please sign in to continue.")
        st.stop()
    if roles and u.role not in roles:
        st.error(f"This module is for {', '.join(ROLE_LABELS[r] for r in roles)} accounts. You are signed in as {u.role_label}.")
        st.stop()
    if perm is not None and not u.can(perm):
        st.error(f"Your role ({u.role_label}) does not have the '{perm.value}' permission.")
        st.stop()
    return u
