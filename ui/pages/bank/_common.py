"""Shared plumbing for bank-manager pages: guard, scope, cached intelligence."""
from __future__ import annotations

from typing import List, Optional

import streamlit as st

from core.auth import Permission, Role, User
from core.intelligence import credit_intelligence, Scenario
from ui import auth, state
from ui.analytics_components import not_available, scope_selector, segment_filter


def guard() -> User:
    return auth.require(Role.BANK_MANAGER, Role.ADMINISTRATOR, perm=Permission.CREDIT_ANALYTICS)


def scenario() -> Scenario:
    sc = st.session_state.get("scenario")
    return sc if isinstance(sc, Scenario) else Scenario()


@st.cache_data(show_spinner="Aggregating modelled credit intelligence…", max_entries=32)
def _ci_cached(_user_dict: dict, state_: Optional[str], crop: Optional[str], tags: tuple, scen_key: str, _matrix_key: str):
    user = User.from_dict(_user_dict)
    return credit_intelligence(user, state.get_kb(), state.get_matrix(), state_, scenario(), crop, list(tags) or None)


def intelligence(user: User, state_: Optional[str], crop: Optional[str] = None, tags: Optional[List[str]] = None):
    m = state.get_matrix()
    if not m.available:
        return None
    import json
    scen = scenario()
    return _ci_cached(user.to_dict(), state_, crop, tuple(tags or []), json.dumps(scen.to_dict(), sort_keys=True), m.meta.get("fingerprint", ""))


def header(title: str, user: User, with_segments: bool = False, with_crop: bool = False):
    """Title + scope controls. Returns (state, tags, crop, ci) or stops with a not-available notice."""
    st.title(title)
    kb = state.get_kb()
    c1, c2, c3 = st.columns([1.2, 1.6, 1.2])
    with c1:
        sc = scope_selector(user, kb)
    tags: List[str] = []
    crop = None
    with c2:
        if with_segments:
            tags = segment_filter("bank_seg_filter")
    with c3:
        if with_crop:
            crops = sorted(state.get_matrix().districts(sc)["crop"].dropna().unique()) if state.get_matrix().available else []
            pick = st.selectbox("Major crop", ["All crops"] + crops, key="bank_crop_filter")
            crop = None if pick == "All crops" else pick
    ci = intelligence(user, sc, crop, tags)
    if ci is None:
        not_available(title)
        st.stop()
    return sc, tags, crop, ci
