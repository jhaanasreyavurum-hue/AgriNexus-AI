"""Phase-4 UI smoke tests — every page renders for both demo farms and for a
sparse user-entered farm without raising, using Streamlit's headless AppTest.
Weather is forced offline so the tests need no network."""
import datetime
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["farm_home", "farm_intelligence", "crop_advisor", "finance_schemes", "copilot", "reports"]
FARMS = ["TS_WARANGAL_COTTON_DEMO", "MH_NASHIK_SOYBEAN_DEMO"]


def _script(page: str, farm: str = None, sparse: bool = False) -> str:
    setup = f'state.select_farm("{farm}")' if farm else ""
    if sparse:
        setup = ('from core.models import FarmContext\n'
                 'state.set_context(FarmContext.from_dict(dict(farm_id="U1", farm_name="Sparse farm", farmer=dict(farmer_id="f", name="n"), '
                 'location=dict(state="Bihar", district="Patna"), geometry=dict(area_value=2.0))))')
    return f"""
import sys; sys.path.insert(0, r"{ROOT}")
import streamlit as st
from ui import state
state.ensure_context()
{setup}
st.session_state["weather_mode"] = "offline"
import importlib; importlib.import_module("ui.pages.{page}").render()
"""


def _run(page, farm=None, sparse=False):
    at = AppTest.from_string(_script(page, farm, sparse), default_timeout=120).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    return at


@pytest.mark.parametrize("farm", FARMS)
@pytest.mark.parametrize("page", PAGES)
def test_page_renders_for_demo_farm(page, farm):
    at = _run(page, farm)
    assert at.title and at.title[0].value


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_for_sparse_user_farm(page):
    _run(page, sparse=True)


def test_farm_home_shows_nba_and_labels():
    at = _run("farm_home", FARMS[0])
    html = "\n".join(m.value for m in at.markdown)
    assert "Next best action" in html
    assert "DEMO DATA" in html                     # demo farm clearly labelled
    assert "Rule-based" in html or "Knowledge base" in html


def test_finance_page_has_scheme_loan_insurance_cards():
    at = _run("finance_schemes", FARMS[0])
    html = "\n".join(m.value for m in at.markdown)
    assert "Kisan Credit Card" in html
    assert "Document readiness" in html
    assert "Informational only" in html            # insurance disclaimer


def test_copilot_handles_blank_and_real_questions():
    at = _run("copilot", FARMS[0])
    at.chat_input[0].set_value("   ").run()
    assert any("type a question" in w.value for w in at.warning)
    at.chat_input[0].set_value("Which schemes apply to me?").run()
    assert not at.exception
    hist = at.session_state["copilot_history"]
    assert hist and hist[-1]["adv"].intent == "schemes"


def test_farm_form_validation_and_save():
    script = f"""
import sys; sys.path.insert(0, r"{ROOT}")
from ui import state
from ui.farm_form import farm_editor
farm_editor(state.ensure_context())
"""
    at = AppTest.from_string(script, default_timeout=120).run()
    at.button[0].click().run()
    msgs = [e.value for e in at.error]
    assert "Farm name is required." in msgs and "Area must be greater than zero." in msgs
    at = AppTest.from_string(script, default_timeout=120).run()
    at.text_input[0].set_value("Unit Test Farm")
    at.text_input[1].set_value("Tester")
    {n.label: n for n in at.number_input}["Area *"].set_value(1.5)
    {d.label: d for d in at.date_input}["Sowing date"].set_value(datetime.date.today() + datetime.timedelta(days=2))
    at.button[0].click().run()
    assert any("future" in e.value for e in at.error)
    at = AppTest.from_string(script, default_timeout=120).run()
    at.text_input[0].set_value("Unit Test Farm")
    at.text_input[1].set_value("Tester")
    {n.label: n for n in at.number_input}["Area *"].set_value(1.5)
    at.button[0].click().run()
    assert not at.error and not at.exception
    ctx = at.session_state["ctx"]
    assert ctx.is_demo is False and ctx.farm_name == "Unit Test Farm" and ctx.soil.ph is None


def test_pdf_report_builds():
    from core.kb import load_knowledge_base
    from core.models import list_demo_farms, load_farm_context
    from core.reasoning import run_full_assessment
    from ui.report_pdf import build_pdf
    kb = load_knowledge_base()
    ctx = load_farm_context(next(f["path"] for f in list_demo_farms() if f["farm_id"] == FARMS[0]))
    b = build_pdf(run_full_assessment(ctx, kb), ["nba", "health", "schemes", "loans", "insurance"])
    assert b[:5] == b"%PDF-" and len(b) > 3000


def test_app_entry_point_shows_login_gate():
    os.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert "user" not in at.session_state
    assert at.text_input, "login form expected"
    assert any("Sign in" in b.label or "Log in" in b.label for b in at.button)


@pytest.mark.parametrize("username,title", [("ramulu", "My Farm"), ("bank.manager", "Bank Dashboard"), ("officer", "Scheme Dashboard"), ("admin", "Admin Dashboard")])
def test_app_entry_point_routes_each_role_to_its_dashboard(username, title):
    os.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    at.text_input[0].set_value(username)
    at.text_input[1].set_value("agrinexus")
    next(b for b in at.button if "Sign in" in b.label or "Log in" in b.label).click().run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert at.session_state["user"]["username"] == username
    assert any(title in t.value for t in at.title), [t.value for t in at.title]
