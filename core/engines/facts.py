"""FarmerFacts — the normalised view of the twin that all matchers consume.

Computed once per assessment so every engine uses identical land / income /
category / document / crop-group facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from core.models.farm_context import FarmContext


@dataclass
class FarmerFacts:
    state: str
    district: str
    acres: float
    hectares: float
    land_bands: List[str]
    income: Optional[float]
    income_bands: List[str]
    age: Optional[int]
    category: str                         # Marginal/Small/Medium/Large Farmer
    profile_attrs: List[str]              # canonical: any, landowner, tenant, women, fpo_member ...
    farmer_terms: Set[str]                # every KB farmer spelling the profile satisfies
    crop_master: Optional[str]            # crop_master.crop_name
    crop_groups: Set[str]                 # KB group labels incl. crop name itself
    crop_category: Optional[str]          # market_category from crop_master
    is_horticulture: bool
    documents_held: Set[str]              # canonical names (explicit + implied by profile)
    has_aadhaar: bool
    has_bank_account: bool
    has_soil_card: bool
    has_kcc: bool
    has_insurance: bool
    livestock: bool
    is_fpo: bool
    is_owner: bool
    is_tenant_or_sharecropper: bool
    is_woman: bool
    irrigation_available: bool
    irrigation_source: Optional[str]
    irrigation_method: Optional[str]
    loan_purpose: Optional[str]
    collateral: bool
    objective: str
    active_risk_types: Set[str] = field(default_factory=set)
    soil_limitations: List[str] = field(default_factory=list)
    low_oc: bool = False
    harvest_near: bool = False
    kb_coverage: str = "limited"

    def satisfies_farmer_term(self, kb_term: Optional[str]) -> Optional[bool]:
        """True/False if the term is known, None if the KB term is unrecognised."""
        if kb_term is None or str(kb_term).strip() in ("", "nan"):
            return True
        t = str(kb_term).strip()
        if t in self.farmer_terms:
            return True
        # unknown spelling → None (soft), known-but-unsatisfied → False
        from core.kb.vocab import load_vocab
        known = {x for lst in load_vocab().farmer_kb_terms.values() for x in lst}
        return False if t in known else None


def build_facts(ctx: FarmContext, kb, assessment=None) -> FarmerFacts:
    v = kb.vocab
    f = ctx.farmer
    acres, ha = ctx.area_acres, ctx.area_hectares
    attrs = f.category_attrs(ha, v)
    row = kb.crop_row(ctx.crop.current_crop) if ctx.crop.current_crop else None
    master = row.crop_name if row is not None else None
    groups = set(v.crop_groups_for(master)) if master else set()
    cat = row.market_category if row is not None else None
    is_hort = "Horticulture Crops" in groups or cat in ("Fruit", "Vegetable", "Spice", "Plantation")
    if is_hort:
        attrs.append("horticulture")

    docs = set(v.canonical_documents(f.documents_held))
    imp = v.doc_implied_by_profile
    if f.has_aadhaar:
        docs |= set(imp.get("has_aadhaar", []))
    if f.has_bank_account:
        docs |= set(imp.get("has_bank_account", []))
    if f.has_soil_health_card:
        docs |= set(imp.get("has_soil_health_card", []))
    if f.land_ownership == "owner" and f.has_land_records:
        docs |= set(imp.get("has_land_records_owner", []))
    if f.is_fpo_member:
        docs |= set(imp.get("is_fpo_member", []))

    risk_types, soil_lims, low_oc, harvest_near = set(), [], False, False
    if assessment is not None:
        risk_types = {r.risk_type for r in assessment.risks}
        soil_lims = list(assessment.soil.limitations)
        low_oc = any(p.key == "organic_carbon_pct" and p.rating == "low" for p in assessment.soil.params)
        st = assessment.stage
        harvest_near = bool(st.available and st.progress_pct is not None and st.progress_pct >= 75)

    return FarmerFacts(
        state=ctx.location.state, district=ctx.location.district, acres=acres, hectares=ha,
        land_bands=v.land_band_labels(acres), income=f.annual_income_inr,
        income_bands=v.income_band_labels(f.annual_income_inr), age=f.age,
        category=v.farmer_category_from_land(ha), profile_attrs=attrs,
        farmer_terms=set(v.farmer_terms_satisfied(attrs)), crop_master=master, crop_groups=groups,
        crop_category=cat, is_horticulture=is_hort, documents_held=docs,
        has_aadhaar=f.has_aadhaar, has_bank_account=f.has_bank_account, has_soil_card=f.has_soil_health_card,
        has_kcc=f.has_kcc, has_insurance=f.has_crop_insurance, livestock=f.livestock, is_fpo=f.is_fpo_member,
        is_owner=(f.land_ownership == "owner"), is_tenant_or_sharecropper=(f.land_ownership in ("tenant", "sharecropper")),
        is_woman=((f.gender or "").lower() == "female"),
        irrigation_available=ctx.irrigation.available, irrigation_source=ctx.irrigation.source,
        irrigation_method=ctx.irrigation.method, loan_purpose=ctx.finance.loan_purpose,
        collateral=ctx.finance.collateral_available, objective=f.primary_objective or "profit",
        active_risk_types=risk_types, soil_limitations=soil_lims, low_oc=low_oc, harvest_near=harvest_near,
        kb_coverage=kb.coverage_level(ctx.location.state),
    )
