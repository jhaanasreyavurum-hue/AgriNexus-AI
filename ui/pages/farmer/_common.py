"""Shared guard for farmer modules: requires a farm context (else points to My Farm)."""
from __future__ import annotations

import streamlit as st

from core.auth import Role
from ui import auth, state
from ui.components import demo_banner, md


def guard_with_farm(title: str):
    """Returns (user, ctx, assessment) or stops with guidance when no farm is set up."""
    user = auth.require(Role.FARMER)
    st.title(title)
    if not state.has_context():
        md('<div class="an-note">No farm profile yet. Go to <b>🏠 My Farm</b> to set up your profile (4 steps) or load a demo farm.</div>')
        if st.button("Go to My Farm", type="primary", key=f"goto_home_{title}"):
            st.switch_page("ui/pages/farmer/home.py") if False else st.rerun()
        st.stop()
    ctx = st.session_state["ctx"]
    demo_banner(ctx)
    a = state.get_assessment()
    if a.knowledge is None:
        st.error("Knowledge engines did not run.")
        st.stop()
    return user, ctx, a
