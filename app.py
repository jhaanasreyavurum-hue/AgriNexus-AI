"""AgriNexus AI — Agricultural Financial Intelligence Platform (entry point).

    streamlit run app.py

Four roles (farmer · bank_manager · government_officer · administrator) share
one shell: sign-in → role-aware navigation → role modules. All reasoning lives
in ``core`` (engines, intelligence, auth, store); ``ui`` only renders.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.auth import Role  # noqa: E402
from ui import auth, state  # noqa: E402
from ui.components import badge, esc, md  # noqa: E402
from ui.theme import inject_css  # noqa: E402

st.set_page_config(page_title="AgriNexus AI", page_icon="🌾", layout="wide", initial_sidebar_state="expanded",
                   menu_items={"About": "AgriNexus AI — AI-powered Agricultural Financial Intelligence Platform: farmer, bank, government and admin intelligence on one explainable knowledge base."})
inject_css()


# ----------------------------------------------------------------------------- navigation spec
# (module under ui/pages/, title, icon)  — the first page of each role is its home dashboard
NAV = {
    Role.FARMER: {
        "Dashboard": [("farmer.home", "My Farm", "🏠")],
        "Modules": [("farmer.loans", "Loans", "💰"), ("farmer.schemes", "Government Schemes", "🎯"), ("farmer.insurance", "Insurance", "🛡️"),
                    ("farmer.intelligence", "Crop / Farm Intelligence", "🌱"), ("farmer.copilot", "AI Copilot", "🤖")],
        "Reports": [("farmer.report", "My Report", "📄")],
    },
    Role.BANK_MANAGER: {
        "Dashboard": [("bank.home", "Bank Dashboard", "🏠")],
        "Modules": [("bank.loan_demand", "Loan Demand", "💳"), ("bank.crop_trends", "Crop Trends", "🌾"), ("bank.segments", "Farmer Segments", "👥"),
                    ("bank.areas", "High-Potential Areas", "🗺️"), ("bank.products", "Loan Products", "💼"), ("bank.copilot", "AI Copilot", "🤖")],
        "Reports": [("bank.report", "Analytics Report", "📊")],
    },
    Role.GOVERNMENT_OFFICER: {
        "Dashboard": [("government.home", "Scheme Dashboard", "🏠")],
        "Modules": [("government.adoption", "Scheme Adoption", "🎯"), ("government.districts", "District Performance", "🗺️"),
                    ("government.inclusion", "Financial Inclusion", "💰"), ("government.low_adoption", "Low-Adoption Areas", "⚠️"), ("government.copilot", "AI Copilot", "🤖")],
        "Reports": [("government.report", "Government Report", "📊")],
    },
    Role.ADMINISTRATOR: {
        "Dashboard": [("admin.home", "Admin Dashboard", "🏠")],
        "Modules": [("admin.users", "Users", "👥"), ("admin.banks", "Banks", "🏦"), ("admin.loan_schemes", "Loan Schemes", "💳"),
                    ("admin.gov_schemes", "Government Schemes", "🎯"), ("admin.knowledge_base", "Knowledge Base", "🧠"), ("admin.monitoring", "System Monitoring", "⚙️")],
        "Reports": [],
    },
}


def _page(module: str, title: str, icon: str, default: bool = False) -> st.Page:
    def _run():
        mod = importlib.import_module(f"ui.pages.{module}")
        mod.render()
    return st.Page(_run, title=title, icon=icon, url_path=module.replace(".", "-"), default=default)


def _brand(user) -> None:
    md('<div class="an-brand"><div class="logo">🌾</div><div><div class="name">AgriNexus AI</div>'
       '<div class="tag">Agricultural Financial Intelligence</div></div></div>')
    md(f'<div class="an-card tight" style="margin-bottom:.6rem"><div style="font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:#6B7A72;font-weight:600">Signed in</div>'
       f'<div style="font-weight:700">{esc(user.display_name)}</div>'
       f'<div style="font-size:.8rem;color:#6B7A72">{esc(user.organisation) if user.organisation else "&nbsp;"}</div>'
       f'<div style="margin-top:.3rem">{badge(auth.ROLE_ICON[user.role] + " " + user.role_label, "green")}{badge("DEMO ACCOUNT", "demo") if user.is_demo_account else badge("session account", "grey")}</div></div>')


def _sidebar_footer(user) -> None:
    st.divider()
    if user.role == Role.FARMER and state.has_context():
        ctx = st.session_state["ctx"]
        md(f'<div style="font-size:.8rem;line-height:1.5"><b>{esc(ctx.farm_name)}</b><br>{esc(ctx.location.district)}, {esc(ctx.location.state)}<br>'
           f'{ctx.area_acres:.2f} ac · {esc(ctx.crop.current_crop or "no crop set")}{"<br>" + badge("DEMO DATA", "demo") if ctx.is_demo else ""}</div>')
        mode = st.radio("Weather", list(state.WEATHER_MODES), format_func=state.WEATHER_MODES.get,
                        index=list(state.WEATHER_MODES).index(st.session_state.get("weather_mode", "live")), key="weather_radio")
        if mode != st.session_state.get("weather_mode"):
            st.session_state["weather_mode"] = mode
            st.rerun()
        if st.session_state.get("weather_error"):
            st.caption(f"⚠️ Live weather unavailable ({st.session_state['weather_error'][:60]}…).")
    if st.button("Log out", key="logout_btn", icon="🚪"):
        auth.logout()
        st.rerun()
    st.caption("KB: 10 tables · original CSVs untouched · corrections via kb_overrides.yaml")


user = auth.current_user()
if user is None:
    from ui import login
    login.render()
    st.stop()

sections = NAV[user.role]
pages = {}
first = True
for section, items in sections.items():
    if not items:
        continue
    pages[section] = [_page(m, t, i, default=first and idx == 0) for idx, (m, t, i) in enumerate(items)]
    first = False

nav = st.navigation(pages, position="sidebar")
with st.sidebar:
    _brand(user)
    _sidebar_footer(user)
nav.run()
