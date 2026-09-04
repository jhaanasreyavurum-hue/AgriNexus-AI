"""Four-role platform tests: authorization in core functions, registry overlay (session-only product /
scheme changes), analytics copilot, role pages render headlessly, and PDF analytics reports build."""
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.auth import Permission, PermissionDenied, Role, authenticate  # noqa: E402
from core.intelligence import Scenario, credit_intelligence, inclusion_intelligence, load_segment_matrix  # noqa: E402
from core.kb import load_knowledge_base  # noqa: E402
from core.store.registry import Registry  # noqa: E402


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def matrix():
    m = load_segment_matrix()
    if not m.available:
        pytest.skip("segment matrix not built")
    return m


def _u(name):
    u = authenticate(name, "agrinexus")
    assert u is not None
    return u


# ------------------------------------------------------------------ auth & authorization
def test_demo_accounts_map_to_four_roles():
    assert _u("ramulu").role == Role.FARMER
    assert _u("bank.manager").role == Role.BANK_MANAGER
    assert _u("officer").role == Role.GOVERNMENT_OFFICER
    assert _u("admin").role == Role.ADMINISTRATOR
    assert authenticate("ramulu", "wrong") is None


def test_core_analytics_enforce_permissions(kb, matrix):
    farmer = _u("ramulu")
    with pytest.raises(PermissionDenied):
        credit_intelligence(farmer, kb, matrix, "Telangana")
    with pytest.raises(PermissionDenied):
        inclusion_intelligence(farmer, kb, matrix, "Telangana")
    from core.admin import platform_counts
    with pytest.raises(PermissionDenied):
        platform_counts(_u("officer"), kb, Registry(kb))


# ------------------------------------------------------------------ registry overlay
def test_registry_rejects_unauthorised_writes(kb):
    reg = Registry(kb)
    with pytest.raises(PermissionDenied):
        reg.add(_u("officer"), "loans", {"loan_name": "x", "bank_name": "SBI", "loan_type": "KCC"})
    with pytest.raises(PermissionDenied):
        reg.add(_u("bank.manager"), "schemes", {"scheme_name": "x", "scheme_type": "y", "government_level": "Central"})
    with pytest.raises(PermissionDenied):
        reg.add(_u("ramulu"), "banks", {"bank_name": "x"})
    assert reg.change_log() == []


def test_registry_validates_and_never_mutates_kb(kb):
    reg = Registry(kb)
    bm = _u("bank.manager")
    with pytest.raises(ValueError):
        reg.add(bm, "loans", {"loan_name": "Bad", "bank_name": "SBI", "loan_type": "KCC", "loan_amount_min": 500000, "loan_amount_max": 1000})
    n_before = len(kb.loans)
    rec = reg.add(bm, "loans", {"loan_name": "Test KCC Plus", "bank_name": "State Bank of India (SBI)", "loan_type": "Kisan Credit Card (KCC)", "minimum_interest": 7.0,
                                 "maximum_interest": 9.0, "loan_amount_min": 10000, "loan_amount_max": 300000, "repayment_years": 1, "crop_specific": "Cotton",
                                 "required_documents": "Aadhaar Card; Land Ownership / Pattadar Passbook", "government_linked": "Yes"})
    assert rec.key.startswith("LOAN") and rec.persisted is False
    assert len(kb.loans) == n_before                      # original KB untouched
    view = reg.view("loans")
    assert (view["loan_id"] == rec.key).any() and view["status"].eq("active").all()
    reg.deactivate(bm, "loans", rec.key)
    assert (reg.view("loans").set_index("loan_id").loc[rec.key, "status"]) == "inactive"


def test_effective_kb_feeds_farmer_matching(kb):
    from core.models import list_demo_farms, load_farm_context
    from core.reasoning import run_full_assessment
    reg = Registry(kb)
    admin = _u("admin")
    reg.add(admin, "loans", {"loan_name": "Session Cotton Kisan Plus", "bank_name": "State Bank of India (SBI)", "loan_type": "Kisan Credit Card (KCC)", "minimum_interest": 4.0,
                             "maximum_interest": 7.0, "loan_amount_min": 10000, "loan_amount_max": 300000, "repayment_years": 1, "crop_specific": "Cotton",
                             "required_documents": "Aadhaar Card; Land Ownership / Pattadar Passbook; Passport Size Photograph", "government_linked": "Yes", "collateral_required": "No"})
    reg.add(admin, "schemes", {"scheme_name": "Session Cotton Input Support", "scheme_type": "Direct Benefit Transfer", "government_level": "State", "state": "Telangana",
                               "eligible_crop": "Cotton", "eligible_farmer": "All Farmers", "maximum_subsidy": 5000, "application_mode": "Online", "active_status": "Active",
                               "documents_required": "Aadhaar Card; Pattadar Passbook"})
    ekb = reg.effective_kb()
    assert len(ekb.loans) == len(kb.loans) + 1 and len(ekb.schemes) == len(kb.schemes) + 1
    assert len(kb.loans) == 120 and len(kb.schemes) == 80
    ctx = load_farm_context(next(f["path"] for f in list_demo_farms() if f["farm_id"] == "TS_WARANGAL_COTTON_DEMO"))
    a = run_full_assessment(ctx, ekb)
    assert any(p.title == "Session Cotton Kisan Plus" for p in a.knowledge.loans.products)
    assert any(m.title == "Session Cotton Input Support" for m in a.knowledge.schemes)


# ------------------------------------------------------------------ modelled intelligence + copilot
def test_credit_and_inclusion_intelligence_are_labelled_modelled(kb, matrix):
    ci = credit_intelligence(_u("bank.manager"), kb, matrix, "Telangana", Scenario())
    ii = inclusion_intelligence(_u("officer"), kb, matrix, "Telangana", Scenario())
    assert "MODELLED" in ci.basis and "MODELLED" in ii.basis
    assert ci.kpis["districts"] == 33 and len(ci.by_district) == 33
    assert {"potential_score", "credit_opportunity", "demand_per_10k_inr"} <= set(ci.by_district.columns)
    assert {"inclusion_index", "relative_band", "rank", "weakest_pillar"} <= set(ii.low_adoption.columns)
    assert 0 <= ii.kpis["inclusion_index"] <= 100


def test_observed_adoption_upload_yields_gap(kb, matrix):
    obs = pd.DataFrame({"district": ["Hyderabad", "Adilabad"], "observed_adoption_pct": [22.0, 61.0]})
    ii = inclusion_intelligence(_u("officer"), kb, matrix, "Telangana", Scenario(), obs)
    d = ii.by_district.set_index("district")
    assert d.loc["Hyderabad", "observed_adoption_pct"] == 22.0
    assert d.loc["Hyderabad", "adoption_gap_pct"] == pytest.approx(d.loc["Hyderabad", "scheme_reach_pct"] - 22.0)
    assert pd.isna(d.loc["Warangal Rural", "observed_adoption_pct"])


def test_analytics_copilot_answers_from_tables_only(kb, matrix):
    from core.reasoning.analytics_advisor import bank_advice, gov_advice
    ci = credit_intelligence(_u("bank.manager"), kb, matrix, "Telangana", Scenario())
    ii = inclusion_intelligence(_u("officer"), kb, matrix, "Telangana", Scenario())
    a = bank_advice(ci, "Tell me about Warangal Rural")
    assert a.intent == "district_detail" and "Warangal Rural" in a.answer and "Modelled (KB-derived)" in a.method_labels
    assert bank_advice(ci, "How real are these numbers?").intent == "basis"
    assert bank_advice(ci, "Which segments are under-served?").intent == "segments"
    g = gov_advice(ii, "Which districts have low adoption?")
    assert g.intent == "low" and "Intervention shortlist" in g.answer
    assert gov_advice(ii, "Tell me about Hyderabad").intent == "district_detail"
    assert "not observed" in gov_advice(ii, "Is this real data?").answer.lower() or "modelled" in gov_advice(ii, "Is this real data?").answer.lower()


def test_analytics_pdf_reports_build(kb, matrix):
    from ui.analytics_pdf import build_credit_report, build_inclusion_report
    from ui.pages.bank import report as br
    from ui.pages.government import report as gr
    bm, off = _u("bank.manager"), _u("officer")
    ci = credit_intelligence(bm, kb, matrix, "Telangana", Scenario())
    ii = inclusion_intelligence(off, kb, matrix, "Telangana", Scenario())
    b1 = build_credit_report(ci, bm, list(br.SECTIONS))
    b2 = build_inclusion_report(ii, off, list(gr.SECTIONS))
    assert b1[:5] == b"%PDF-" and len(b1) > 5000
    assert b2[:5] == b"%PDF-" and len(b2) > 5000


# ------------------------------------------------------------------ role pages render headlessly
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROLE_PAGES = {
    "bank.manager": ["bank.home", "bank.loan_demand", "bank.crop_trends", "bank.segments", "bank.areas", "bank.products", "bank.report", "bank.copilot"],
    "officer": ["government.home", "government.adoption", "government.districts", "government.inclusion", "government.low_adoption", "government.report", "government.copilot"],
    "admin": ["admin.home", "admin.users", "admin.banks", "admin.loan_schemes", "admin.gov_schemes", "admin.knowledge_base", "admin.monitoring"],
}


def _page_script(mod: str, user: str) -> str:
    return f"""
import sys, streamlit as st, importlib
sys.path.insert(0, r"{ROOT}")
from ui import state, auth
from core.auth import authenticate
if "user" not in st.session_state:
    auth.login(authenticate("{user}", "agrinexus"))
    st.session_state["weather_mode"] = "offline"
importlib.import_module("ui.pages.{mod}").render()
"""


@pytest.mark.parametrize("user,mod", [(u, m) for u, mods in ROLE_PAGES.items() for m in mods])
def test_role_page_renders(user, mod, matrix):
    os.chdir(ROOT)
    at = AppTest.from_string(_page_script(mod, user), default_timeout=180).run()
    assert not at.exception, [str(e.value) for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.title and at.title[0].value


@pytest.mark.parametrize("user,mod", [("officer", "bank.products"), ("bank.manager", "government.adoption"), ("ramulu", "admin.users"), ("bank.manager", "admin.monitoring")])
def test_role_page_denies_other_roles(user, mod):
    os.chdir(ROOT)
    at = AppTest.from_string(_page_script(mod, user), default_timeout=180).run()
    assert not at.exception
    assert at.error and "signed in as" in at.error[0].value
    assert not at.title


def test_bank_products_add_flow_is_session_only(matrix):
    os.chdir(ROOT)
    at = AppTest.from_string(_page_script("bank.products", "bank.manager"), default_timeout=180).run()
    next(t for t in at.text_input if t.label == "Product name *").set_value("AppTest Product")
    next(b for b in at.button if b.label == "Add product").click().run()
    assert not at.exception
    assert any("not persisted" in s.value for s in at.success)
    html = "\n".join(m.value for m in at.markdown)
    assert "No persistent database" in html
