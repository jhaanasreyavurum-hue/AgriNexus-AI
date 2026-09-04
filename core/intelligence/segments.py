"""Farmer-segment archetypes used to model district-level eligibility.

Each segment is a *synthetic but explicit* farmer profile. Land-holding
classes follow the KB vocabulary (Marginal ≤1 ha, Small ≤2 ha, Medium ≤10 ha,
Large >10 ha). The default household shares are a **scenario assumption**
loosely aligned with the all-India operational-holding distribution
(Agriculture Census 2015-16: ~68 % marginal, ~18 % small, ~10 % semi-medium,
~4 % medium, <1 % large) — they are not KB data and can be changed by the user.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Segment:
    segment_id: str
    label: str
    group: str                       # holding | social | tenure | allied
    acres: float
    annual_income_inr: float
    gender: Optional[str] = None
    age: Optional[int] = None
    land_ownership: str = "owner"
    has_land_records: bool = True
    irrigated: bool = False
    irrigation_reliability: Optional[str] = None
    has_kcc: bool = False
    has_soil_health_card: bool = False
    is_fpo_member: bool = False
    livestock: bool = False
    collateral: bool = False
    documents_held: tuple = ("Aadhaar Card", "Passport Size Photograph", "Land Ownership / Pattadar Passbook", "Bank Statement (6 months)")
    default_share: float = 0.0       # share of farm households (scenario assumption)
    tags: tuple = ()                 # for filters: small_marginal, women, irrigated, rainfed, tenant, fpo, livestock, youth

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_TENANT_DOCS = ("Aadhaar Card", "Passport Size Photograph", "Bank Statement (6 months)")

SEGMENTS: List[Segment] = [
    Segment("MARG_RAINFED", "Marginal · rainfed", "holding", 1.5, 80_000, irrigated=False, default_share=0.34,
            tags=("small_marginal", "marginal", "rainfed")),
    Segment("MARG_IRRIG", "Marginal · irrigated", "holding", 2.0, 120_000, irrigated=True, irrigation_reliability="partial", has_kcc=True, default_share=0.22,
            tags=("small_marginal", "marginal", "irrigated", "kcc")),
    Segment("SMALL_RAINFED", "Small · rainfed", "holding", 3.5, 150_000, irrigated=False, default_share=0.09,
            tags=("small_marginal", "small", "rainfed")),
    Segment("SMALL_IRRIG", "Small · irrigated", "holding", 4.5, 220_000, irrigated=True, irrigation_reliability="assured", has_kcc=True, has_soil_health_card=True, default_share=0.09,
            tags=("small_marginal", "small", "irrigated", "kcc")),
    Segment("MEDIUM", "Medium · irrigated", "holding", 9.0, 450_000, irrigated=True, irrigation_reliability="assured", has_kcc=True, has_soil_health_card=True, collateral=True, default_share=0.06,
            tags=("medium", "irrigated", "kcc", "collateral")),
    Segment("LARGE", "Large · irrigated", "holding", 30.0, 1_200_000, irrigated=True, irrigation_reliability="assured", has_kcc=True, has_soil_health_card=True, collateral=True, default_share=0.01,
            tags=("large", "irrigated", "kcc", "collateral")),
    Segment("WOMEN_MARG", "Women · marginal", "social", 1.5, 90_000, gender="female", irrigated=False, default_share=0.08,
            tags=("small_marginal", "marginal", "women", "rainfed")),
    Segment("YOUTH_SMALL", "Young farmer (≤30) · small", "social", 3.0, 140_000, age=27, irrigated=True, irrigation_reliability="partial", default_share=0.04,
            tags=("small_marginal", "small", "youth", "irrigated")),
    Segment("TENANT", "Tenant / sharecropper", "tenure", 3.0, 110_000, land_ownership="tenant", has_land_records=False, irrigated=False,
            documents_held=_TENANT_DOCS, default_share=0.04, tags=("small_marginal", "tenant", "rainfed")),
    Segment("FPO_SMALL", "FPO member · small", "social", 4.0, 200_000, irrigated=True, irrigation_reliability="partial", is_fpo_member=True, has_kcc=True, default_share=0.02,
            tags=("small_marginal", "small", "fpo", "irrigated", "kcc")),
    Segment("LIVESTOCK_MARG", "Marginal + livestock (allied)", "allied", 1.2, 100_000, irrigated=False, livestock=True, default_share=0.01,
            tags=("small_marginal", "marginal", "livestock", "rainfed")),
]
SEGMENT_BY_ID: Dict[str, Segment] = {s.segment_id: s for s in SEGMENTS}
assert abs(sum(s.default_share for s in SEGMENTS) - 1.0) < 1e-6


def segment_context(seg: Segment, state: str, district: str, crop: Optional[str], season: Optional[str] = None,
                    loan_purpose: str = "crop_loan", lat: Optional[float] = None, lon: Optional[float] = None,
                    zone: Optional[str] = None) -> Dict[str, Any]:
    """Sparse FarmContext dict for ``FarmContext.from_dict`` (no soil / NDVI / weather → engines report them as not assessed)."""
    return {
        "farm_id": f"SEG_{seg.segment_id}_{district}".replace(" ", "_")[:64],
        "farm_name": f"{seg.label} — {district}",
        "farmer": {"farmer_id": f"SEG-{seg.segment_id}", "name": seg.label, "age": seg.age, "gender": seg.gender,
                   "land_ownership": seg.land_ownership, "has_land_records": seg.has_land_records, "is_fpo_member": seg.is_fpo_member,
                   "has_aadhaar": True, "has_bank_account": True, "has_soil_health_card": seg.has_soil_health_card, "has_kcc": seg.has_kcc,
                   "has_crop_insurance": False, "annual_income_inr": seg.annual_income_inr, "existing_loans_inr": 0.0,
                   "documents_held": list(seg.documents_held), "livestock": seg.livestock, "primary_objective": "profit"},
        "location": {"state": state, "district": district, "latitude": lat, "longitude": lon, "agro_climatic_zone": zone},
        "geometry": {"area_value": seg.acres, "area_unit": "acres"},
        "crop": {"current_crop": crop, "season": season},
        "irrigation": {"available": seg.irrigated, "reliability": seg.irrigation_reliability if seg.irrigated else None,
                       "source": "borewell" if seg.irrigated else "rainfed"},
        "finance": {"loan_purpose": loan_purpose, "collateral_available": seg.collateral},
        "is_demo": False,
    }
