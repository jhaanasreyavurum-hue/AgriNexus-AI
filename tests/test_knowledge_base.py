"""KB integrity + vocabulary tests. Run: pytest -q"""
import itertools
import json

import pytest

from core.kb import load_knowledge_base, load_vocab
from core.models import load_farm_context, list_demo_farms, DataSource

EXPECTED_ROWS = {
    "crops": 120, "geo": 68, "schemes": 80, "eligibility_rules": 300, "ai_rules": 500,
    "loans": 120, "subsidies": 100, "insurance": 60, "documents": 150, "branches": 200,
}


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def vocab():
    return load_vocab()


# ------------------------------------------------------------------ loading
def test_all_tables_load_with_expected_rows(kb):
    for name, n in EXPECTED_ROWS.items():
        assert len(kb.table(name)) == n, name


def test_original_kb_files_unmodified(kb):
    assert all(v == "ok" for v in kb.checksum_status.values()), kb.checksum_status


def test_primary_keys_unique(kb):
    from core.kb.loader import PRIMARY_KEYS
    for t, pk in PRIMARY_KEYS.items():
        if t == "geo":
            continue  # district_id repeats (KB quirk) — see test below
        assert kb.table(t)[pk].is_unique, t


def test_geo_state_district_pairs_unique(kb):
    g = kb.geo
    assert not g.duplicated(["state_name", "district_name"]).any()


# --------------------------------------------------------- referential joins
def test_eligibility_rules_reference_real_schemes_and_loans(kb):
    schemes = set(kb.schemes.scheme_name)
    loans = set(kb.loans.loan_type)
    assert set(kb.eligibility_rules.recommended_scheme) <= schemes
    assert set(kb.eligibility_rules.recommended_loan) <= loans


def test_documents_reference_real_schemes_and_loans(kb):
    schemes = set(kb.schemes.scheme_name)
    loans = set(kb.loans.loan_type)
    d = kb.documents
    assert set(d.scheme_name.dropna()) <= schemes
    assert set(d.loan_name.dropna()) <= loans


def test_subsidies_and_crop_master_reference_real_schemes(kb):
    schemes = set(kb.schemes.scheme_name)
    assert set(kb.subsidies.scheme_name) <= schemes
    cm = set(itertools.chain(*kb.crops.recommended_schemes_list))
    assert cm <= schemes


def test_ai_rules_condition_json_parses(kb):
    for c in kb.ai_rules.condition_json:
        json.loads(c)
    assert kb.ai_rules.cond_state.notna().all()


# --------------------------------------------------------------- overrides
def test_overrides_applied_and_logged(kb):
    assert len(kb.override_log) > 0
    pmk = kb.schemes[kb.schemes.scheme_id == "SCHM001"].iloc[0]
    assert pmk.scheme_type == "Direct Benefit Transfer"
    assert pmk.eligible_crop == "All Crops"
    recs = kb.overrides_for("schemes", "SCHM001")
    assert any(r.column == "scheme_type" and r.original == "Mechanization Subsidy" for r in recs)


def test_crop_overrides_fix_obvious_agronomy(kb):
    cotton = kb.crop_row("Cotton")
    assert cotton.season == "Kharif"
    bajra = kb.crop_row("Bajra")
    assert bajra.season == "Kharif" and bajra.water_requirement == "Low"


# ------------------------------------------------------------------- vocab
def test_all_kb_soils_canonicalise(kb, vocab):
    for s in set(kb.crops.soil_type) | set(kb.eligibility_rules.soil_type):
        assert vocab.canonical_soil(s) is not None, s


def test_every_crop_master_crop_in_group_map(kb, vocab):
    missing = [c for c in kb.crops.crop_name if c not in vocab.crop_groups]
    assert not missing, missing


def test_every_kb_crop_group_label_is_reachable(kb, vocab):
    """Every crop group used in schemes/rules/insurance must be produced by some crop."""
    used = (set(kb.schemes.eligible_crop) | set(kb.eligibility_rules.crop)
            | set(kb.insurance.covered_crop) | set(kb.ai_rules.cond_crop))
    used = {u for u in used if not u.startswith("Not Crop Specific") and u != "All Crops"}
    reachable = set(itertools.chain(*vocab.crop_groups.values())) | set(vocab.crop_groups)
    reachable |= {c.split(" (")[0] for c in vocab.crop_groups}
    assert used <= reachable, used - reachable


@pytest.mark.parametrize("alias,expected", [
    ("paddy", "Paddy (Rice)"), ("Rice", "Paddy (Rice)"), ("cotton", "Cotton"),
    ("Red Gram (Tur Dal)", "Pigeon Pea (Tur/Arhar)"), ("chilli", "Red Chilli"), ("Bajra", "Pearl Millet (Bajra)"),
])
def test_crop_alias_resolution(vocab, alias, expected):
    assert vocab.resolve_crop_name(alias) == expected


def test_crop_matches_groups(vocab):
    assert vocab.crop_matches("Pulses", "Pigeon Pea (Tur/Arhar)")
    assert vocab.crop_matches("Red Gram (Tur Dal)", "Tur")
    assert vocab.crop_matches("All Crops", None)
    assert not vocab.crop_matches("Not Crop Specific - Fisheries", "Cotton")
    assert not vocab.crop_matches("Wheat", "Cotton")


def test_land_and_income_bands(vocab):
    assert set(vocab.land_band_labels(3.5)) == {"2-5 Acres", "<5 Acres"}
    assert vocab.land_band_labels(12) == [">10 Acres"]
    assert set(vocab.income_band_labels(180000)) == {"<200000", "<300000"}
    assert vocab.income_band_labels(600000) == [">500000"]


def test_farmer_category(vocab):
    assert vocab.farmer_category_from_land(0.8) == "Marginal Farmer"
    assert vocab.farmer_category_from_land(1.5) == "Small Farmer"
    assert vocab.farmer_category_from_land(12) == "Large Farmer"


# ------------------------------------------------------------ demo farms
def test_demo_farms_load_and_are_labelled(kb):
    farms = list_demo_farms()
    assert len(farms) >= 2
    for f in farms:
        ctx = load_farm_context(f["path"])
        assert ctx.is_demo is True
        assert ctx.soil.provenance.source == DataSource.DEMO
        assert ctx.remote_sensing.provenance.source == DataSource.DEMO
        assert kb.district_row(ctx.location.state, ctx.location.district) is not None
        assert kb.crop_row(ctx.crop.current_crop) is not None
        assert ctx.area_hectares > 0
