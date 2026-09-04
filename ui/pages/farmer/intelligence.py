"""🌱 Crop / Farm Intelligence — farm digital twin (GIS, NDVI, soil, weather, water, risks),
crop advisor and the advanced farm editor. Wraps the Phase-4 farm modules under the farmer role."""
from __future__ import annotations

import streamlit as st

from ui import state
from ui.farm_form import farm_editor
from ui.pages import crop_advisor, farm_home, farm_intelligence
from ui.pages.farmer._common import guard_with_farm


def render() -> None:
    user, ctx, a = guard_with_farm("🌱 Crop / Farm Intelligence")
    tabs = st.tabs(["🩺 Farm health & action plan", "🗺️ Farm intelligence (twin)", "🌾 Crop advisor", "✏️ Edit farm (advanced)"])
    with tabs[0]:
        farm_home.render_body(ctx, a)
    with tabs[1]:
        farm_intelligence.render_body(ctx, a)
    with tabs[2]:
        crop_advisor.render_body(ctx, a)
    with tabs[3]:
        st.caption("Advanced inputs: soil test values, NDVI CSV upload, sowing dates, documents. Saving replaces the current farm profile with what you enter.")
        farm_editor(ctx)
