"""Phase-3 tests: knowledge engines (facts, documents, crop advisor, scheme
matcher, loan advisor, insurance matcher, subsidy finder, opportunities,
knowledge-driven Next Best Action and advisor intents).

All tests are offline: the demo farms are assessed with an empty weather
snapshot so no network call is made.
"""
import pytest

from core.engines import (
    advise_loans, build_facts, detect_opportunities, find_subsidies, match_insurance, match_schemes,
    recommend_crops, resolve_documents, run_knowledge_engines,
)
from core.engines.scheme_matcher import fire_ai_rules, fire_eligibility_rules
from core.kb import load_knowledge_base
from core.models import DataSource, Provenance, WeatherSnapshot, list_demo_farms, load_farm_context
from core.models.results import Method
from core.reasoning import generate_farm_advice, run_full_assessment
from core.reasoning.assessment import assess_farm

WARANGAL = "TS_WARANGAL_COTTON_DEMO"
NASHIK = "MH_NASHIK_SOYBEAN_DEMO"


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


def _farm(farm_id=WARANGAL):
    p = next(f["path"] for f in list_demo_farms() if f["farm_id"] == farm_id)
    ctx = load_farm_context(p)
    ctx.weather = WeatherSnapshot(provenance=Provenance(source=DataSource.WEATHER_API, detail="offline-test"))
    return ctx


@pytest.fixture(scope="module")
def full(kb):
    """Full assessments for both demo farms (offline)."""
    return {fid: run_full_assessment(_farm(fid), kb) for fid in (WARANGAL, NASHIK)}


# ----------------------------------------------------------------------------- facts
def test_facts_warangal_small_farmer(kb):
    ctx = _farm(WARANGAL)
    f = build_facts(ctx, kb, assess_farm(ctx, kb))
    assert f.category == "Small Farmer"
    assert "2-5 Acres" in f.land_bands and "<5 Acres" in f.land_bands
    assert f.crop_master == "Cotton"
    assert "Small Farmer" in f.farmer_terms and "All Categories of Farmers" in f.farmer_terms
    assert "Aadhaar Card" in f.documents_held            # implied by has_aadhaar
    assert f.kb_coverage == "deep"
    assert not f.has_insurance


def test_facts_nashik_marginal_woman_livestock(kb):
    ctx = _farm(NASHIK)
    f = build_facts(ctx, kb, assess_farm(ctx, kb))
    assert f.category == "Marginal Farmer"
    assert f.is_woman and f.livestock
    assert not f.irrigation_available
    assert f.kb_coverage == "moderate"


# ------------------------------------------------------------------------- documents
def test_document_canonicalisation_and_readiness(kb):
    ctx = _farm(WARANGAL)
    f = build_facts(ctx, kb)
    cl = resolve_documents(kb, f, ["Bank Passbook", "Land Passbook / Pattadar Passbook", "Income Proof", "KCC Application Form"])
    names = {i.name for i in cl.items}
    assert "Bank Passbook / Cancelled Cheque" in names and "Land Ownership / Pattadar Passbook" in names
    assert "Income Certificate" in cl.missing_blocking
    assert "KCC Application Form" in cl.missing_obtainable   # form filled at application, never blocking
    # 3 scored docs (form excluded), 2 held -> 67 %
    assert cl.readiness_pct == pytest.approx(67, abs=1)


def test_conditional_documents_not_applicable_without_context(kb):
    f = build_facts(_farm(WARANGAL), kb)              # no livestock, owner, not FPO
    cl = resolve_documents(kb, f, ["Ear-Tag / Animal Identification Certificate", "Tenant Farmer / Sharecropper Certificate", "Aadhaar Card"])
    assert set(cl.not_applicable) == {"Ear-Tag / Animal Identification Certificate", "Tenant Farmer / Sharecropper Certificate"}
    assert cl.readiness_pct == 100.0
    # with an explicit livestock context the ear-tag becomes a real requirement
    cl2 = resolve_documents(kb, f, ["Ear-Tag / Animal Identification Certificate", "Aadhaar Card"], contexts=["livestock"])
    assert "Ear-Tag / Animal Identification Certificate" in cl2.missing_blocking


# ----------------------------------------------------------------------- crop advisor
def test_crop_advisor_ranks_current_crop_high_and_excludes_fodder(kb):
    ctx = _farm(WARANGAL)
    res = recommend_crops(ctx, kb, build_facts(ctx, kb), top_n=10)
    assert res and res[0].title == "Cotton" and res[0].payload["is_current_crop"]
    assert all(m.payload["market_category"] != "Fodder" for m in res)      # no livestock on this farm
    assert all(m.explanation.method == Method.RULE_BASED for m in res)
    # factor scores + KB reference present for WHY panel
    assert set(res[0].payload["factor_scores"]) >= {"soil", "rain", "water", "season"}
    assert res[0].explanation.kb_references == ["CROP036"]


def test_crop_advisor_respects_target_season(kb):
    ctx = _farm(WARANGAL)
    rabi = recommend_crops(ctx, kb, build_facts(ctx, kb), target_season="Rabi", top_n=5)
    assert rabi and all("Rabi" in m.payload["seasons_all"] or "Year-round (Perennial)" in m.payload["seasons_all"] for m in rabi)


def test_rainfed_farm_penalises_high_water_crops(kb):
    ctx = _farm(NASHIK)
    res = recommend_crops(ctx, kb, build_facts(ctx, kb), top_n=40)
    high = [m for m in res if m.payload["water_requirement"] == "High"]
    low = [m for m in res if m.payload["water_requirement"] == "Low"]
    assert low and (not high or max(m.payload["factor_scores"]["water"] for m in high) < min(m.payload["factor_scores"]["water"] for m in low))


# --------------------------------------------------------------------- scheme matcher
def test_scheme_matcher_state_filter_and_explanations(kb):
    ctx = _farm(NASHIK)
    res = match_schemes(kb, build_facts(ctx, kb), None, top_n=20)
    assert res
    assert all(m.payload["state"] in ("All India", "Maharashtra") for m in res)
    for m in res:
        assert m.explanation.method == Method.KNOWLEDGE_BASE
        assert m.explanation.kb_references and m.explanation.summary


def test_scheme_matcher_filters_allied_and_women_schemes_for_male_crop_farmer(kb):
    ctx = _farm(WARANGAL)
    res = match_schemes(kb, build_facts(ctx, kb), "black", top_n=8)
    titles = " | ".join(m.title.lower() for m in res)
    assert "fisher" not in titles and "matsya" not in titles
    assert "women" not in titles
    assert "poultry" not in titles and "gokul" not in titles


def test_pm_kisan_override_makes_it_a_strong_match(kb):
    ctx = _farm(WARANGAL)
    res = match_schemes(kb, build_facts(ctx, kb), "black", top_n=12)
    pmk = next(m for m in res if m.item_id == "SCHM001")
    assert pmk.score >= 70
    assert "insurance_required" in pmk.payload["kb_overrides"]
    assert not any("crop insurance" in f.detail for f in pmk.explanation.limiting)


def test_eligibility_and_ai_rules_fire(kb):
    ctx = _farm(WARANGAL)
    f = build_facts(ctx, kb)
    elig = fire_eligibility_rules(kb, f, "black")
    ai = fire_ai_rules(kb, f)
    assert len(elig) >= 1 and {"soil_match", "land_match", "effective_priority"} <= set(elig.columns)
    assert len(ai) >= 1 and ai.iloc[0].cond_state == "Telangana"


# ---------------------------------------------------------------------- loan advisor
def test_loan_advisor_indicative_eligibility_and_products(kb):
    ctx = _farm(WARANGAL)
    la = advise_loans(kb, build_facts(ctx, kb), 0.0, "black", top_n=5)
    assert la.estimated_eligibility_inr > 0
    assert la.eligibility_rating in ("Good", "Moderate", "Limited")
    assert la.products and la.products[0].payload["loan_type"] == "Kisan Credit Card (KCC)"   # purpose crop_loan
    assert la.branches and all(b["district"].lower() == "warangal rural" for b in la.branches)
    for m in la.products:
        assert "Ear-Tag / Animal Identification Certificate" not in m.documents   # conditional doc, no livestock


def test_loan_advisor_no_branches_outside_kb_coverage(kb):
    ctx = _farm(NASHIK)
    la = advise_loans(kb, build_facts(ctx, kb), 0.0, None, top_n=5)
    assert la.products
    assert la.branches == [] and "Maharashtra" in la.branch_coverage_note


# ------------------------------------------------------------------ insurance matcher
def test_insurance_crop_and_district_hard_filters(kb):
    ctx = _farm(WARANGAL)
    res = match_insurance(kb, build_facts(ctx, kb, assess_farm(ctx, kb)), "black", top_n=8)
    assert res
    for m in res:
        assert m.payload["informational_only"] is True
        assert not m.payload["is_livestock"]
        assert kb.vocab.crop_matches(m.payload["covered_crop"], "Cotton")
    # a product covering an active risk must outrank one that does not, all else roughly equal
    hit = [m for m in res if m.payload["risk_hits"]]
    assert hit and hit[0].score >= max(m.score for m in res if not m.payload["risk_hits"]) - 1


def test_insurance_gap_note_when_no_crop_cover_notified(kb):
    kr = run_knowledge_engines(_farm(NASHIK), kb)
    assert all(m.payload["is_livestock"] for m in kr.insurance)     # only livestock covers fit Nashik
    assert kr.insurance_gap_note and "Nashik" in kr.insurance_gap_note
    assert all(m.payload["risk_hits"] == [] for m in kr.insurance)  # livestock covers never claim crop-risk hits


# ------------------------------------------------------------------- subsidy finder
def test_subsidy_finder_situational(kb):
    ctx = _farm(WARANGAL)
    a = assess_farm(ctx, kb)
    f = build_facts(ctx, kb, a)
    res = find_subsidies(kb, f, {}, top_n=10)
    assert res and all(m.payload["state"] in ("All India", "Telangana") for m in res)
    assert any("Micro Irrigation" in m.payload["subcategory"] for m in res)       # flood irrigation + water stress
    assert not any(m.payload["subcategory"] in ("Fisheries", "Livestock & Dairy Development", "Beekeeping") for m in res)


# ---------------------------------------------------------------------- opportunities
def test_opportunities_ranked_and_explained(full):
    for fid, a in full.items():
        opps = a.knowledge.opportunities
        assert opps
        assert all(o.explanation.summary for o in opps)
        scores = [o.score for o in opps]
        assert scores == sorted(scores, reverse=True)
    w = full[WARANGAL].knowledge.opportunities
    # top opportunity for the cotton farm should not be a crop switch away from a 98 % suitability crop
    assert w[0].opportunity_type != "crop_diversification"


# ------------------------------------------------------------- knowledge NBA + advisor
def test_knowledge_actions_appended_and_deduplicated(full):
    a = full[WARANGAL]
    cats = [r.category for r in a.actions]
    assert "scheme" in cats and "finance" in cats and "insurance" in cats
    assert cats.count("insurance") == 1                       # rule-based duplicate replaced by KB-specific action
    assert [r.priority for r in a.actions] == list(range(1, len(a.actions) + 1))
    ins = next(r for r in a.actions if r.category == "insurance")
    assert ins.method == Method.KNOWLEDGE_BASE and ins.explanation.kb_references


def test_nashik_insurance_action_is_honest_when_no_cover(full):
    a = full[NASHIK]
    ins = next(r for r in a.actions if r.category == "insurance")
    assert "notified" in ins.action.lower() and "livestock" not in ins.action.lower()


def test_summary_and_top_opportunity(full):
    s = full[WARANGAL].headline()
    assert "top_opportunity" in s and s["top_opportunity"]


@pytest.mark.parametrize("question,intent", [
    ("What government schemes may apply to me?", "schemes"),
    ("Which loan should I take?", "loans"),
    ("Which insurance covers my risks?", "insurance"),
    ("What opportunities are there?", "opportunities"),
    ("What documents do I need?", "documents"),
])
def test_advisor_intents_use_knowledge_engines(kb, full, question, intent):
    ctx = _farm(WARANGAL)
    adv = generate_farm_advice(ctx, kb, question, assessment=full[WARANGAL])
    assert adv.intent == intent
    assert adv.answer and "Phase 3" not in adv.answer
    assert Method.KNOWLEDGE_BASE.value in adv.method_labels
    if intent in ("schemes", "loans", "insurance"):
        assert adv.kb_references
