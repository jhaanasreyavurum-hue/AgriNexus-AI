"""Shared plumbing for government-officer pages."""
from __future__ import annotations

import json
from typing import List, Optional

import pandas as pd
import streamlit as st

from core.auth import Permission, Role, User
from core.intelligence import inclusion_intelligence, Scenario
from ui import auth, state
from ui.analytics_components import not_available, scope_selector, segment_filter


def guard() -> User:
    return auth.require(Role.GOVERNMENT_OFFICER, Role.ADMINISTRATOR, perm=Permission.SCHEME_ANALYTICS)


def scenario() -> Scenario:
    sc = st.session_state.get("scenario")
    return sc if isinstance(sc, Scenario) else Scenario()


def observed() -> Optional[pd.DataFrame]:
    d = st.session_state.get("observed_adoption")
    return d if isinstance(d, pd.DataFrame) and len(d) else None


@st.cache_data(show_spinner="Aggregating modelled inclusion intelligence…", max_entries=32)
def _ii_cached(_user_dict: dict, state_: Optional[str], tags: tuple, scen_key: str, obs_key: str, _matrix_key: str):
    user = User.from_dict(_user_dict)
    return inclusion_intelligence(user, state.get_kb(), state.get_matrix(), state_, scenario(), observed(), list(tags) or None)


def intelligence(user: User, state_: Optional[str], tags: Optional[List[str]] = None):
    m = state.get_matrix()
    if not m.available:
        return None
    obs = observed()
    obs_key = obs.to_json() if obs is not None else ""
    return _ii_cached(user.to_dict(), state_, tuple(tags or []), json.dumps(scenario().to_dict(), sort_keys=True), obs_key, m.meta.get("fingerprint", ""))


def header(title: str, user: User, with_segments: bool = False):
    st.title(title)
    kb = state.get_kb()
    c1, c2 = st.columns([1.2, 2])
    with c1:
        sc = scope_selector(user, kb)
    tags: List[str] = []
    with c2:
        if with_segments:
            tags = segment_filter("gov_seg_filter")
    ii = intelligence(user, sc, tags)
    if ii is None:
        not_available(title)
        st.stop()
    return sc, tags, ii
