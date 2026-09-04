"""Crop Insurance matcher (§13) — informational matches from ``crop_insurance_products``.

Scoring: crop coverage (hard), district applicability (hard when a district
list is given), farmer-type fit, **risk relevance** (covered_risk vs risks the
Risk Center detected on this farm), premium burden, government subsidy, KB
priority, and eligibility / ai-rule boosts. Livestock covers are included
only if the farmer keeps livestock.

Everything here is *informational* — premium % and sums insured are KB values,
not live quotes. The UI must say so.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from core.engines.documents import resolve_documents
from core.engines.facts import FarmerFacts
from core.engines.scheme_matcher import _ai_rule_names_match, _isnull, fire_ai_rules, fire_eligibility_rules
from core.models.results import Explanation, Factor, MatchResult, Method, score_label

FARMER_TERM_FIT = {
    "All Farmers (Loanee and Non-Loanee)": lambda f: True,
    "Non-Loanee Farmers (Voluntary Enrolment)": lambda f: not f.has_kcc,
    "Loanee Farmers (Compulsory Coverage via KCC/Crop Loan)": lambda f: f.has_kcc,
    "Landowning Farmers with Revenue Records": lambda f: f.is_owner and "Land Ownership / Pattadar Passbook" in f.documents_held,
    "Sharecroppers and Tenant Farmers with Valid Certificate": lambda f: f.is_tenant_or_sharecropper,
    "Horticulture Growers with Plantation Records": lambda f: f.is_horticulture,
    "Farmers with Registered Livestock and Health Certificate": lambda f: f.livestock,
}


def _risk_relevance(covered_risk: str, active: set, kw_map: dict) -> tuple[float, List[str]]:
    hits = []
    cr = covered_risk.lower()
    for risk_type in active:
        for kw in kw_map.get(risk_type, []):
            if kw.lower() in cr:
                hits.append(risk_type)
                break
    return (1.0 if hits else 0.0), sorted(set(hits))


def match_insurance(kb, facts: FarmerFacts, soil_canonical: Optional[str] = None, top_n: int = 8,
                    sum_insured_hint: Optional[float] = None) -> List[MatchResult]:
    v = kb.vocab
    uni = kb.interpretation.get("universal_region_terms", [])
    ins = kb.insurance[~kb.insurance["excluded"]]
    elig = fire_eligibility_rules(kb, facts, soil_canonical)
    ai = fire_ai_rules(kb, facts)
    rule_ins = set(elig["recommended_insurance"])
    ai_ins = [x for _, r in ai.iterrows() for x in r.insurance_list]
    out: List[MatchResult] = []
    for _, p in ins.iterrows():
        ex = Explanation(summary="", method=Method.KNOWLEDGE_BASE, kb_references=[p.insurance_id],
                         sources=["Knowledge base · crop_insurance_products"],
                         data_considered=["crop", "district", "farmer type", "detected farm risks", "premium %", "govt subsidy"])
        score, hard = 0.0, False
        # crop / livestock
        if p.is_livestock:
            if not facts.livestock:
                continue
            score += 20; ex.add(Factor("Livestock cover", "positive", f"Covers {p.covered_crop.replace('Not Crop Specific - ', '')}; farmer keeps livestock.", weight=20))
        elif v.crop_matches(p.covered_crop, facts.crop_master):
            score += 25; ex.add(Factor("Crop covered", "positive", f"Product covers {p.covered_crop}.", weight=25))
        else:
            hard = True; ex.add(Factor("Crop not covered", "risk", f"Product covers {p.covered_crop}; farm grows {facts.crop_master or 'unspecified'}."))
        # district
        dl = list(p.districts_list)
        if any(d in uni for d in dl) or str(p.district_applicable) in uni:
            score += 10; ex.add(Factor("Region", "positive", f"Applicable: {p.district_applicable}.", weight=10))
        elif any(d.strip().lower() == facts.district.lower() for d in dl):
            score += 15; ex.add(Factor("District notified", "positive", f"{facts.district} is in the notified list.", weight=15))
        else:
            # Telangana-specific lists; if farm is in another state treat as not applicable
            hard = True; ex.add(Factor("District not notified", "risk", f"Notified districts: {p.district_applicable}."))
        # farmer type
        fit = FARMER_TERM_FIT.get(str(p.eligible_farmer))
        if fit is None:
            score += 4; ex.add(Factor("Farmer type", "neutral", f"KB term '{p.eligible_farmer}' not verifiable.", weight=4))
        elif fit(facts):
            score += 12; ex.add(Factor("Farmer type eligible", "positive", f"Profile fits '{p.eligible_farmer}'.", weight=12))
        else:
            score += 0; ex.add(Factor("Farmer type", "limiting", f"Product is for '{p.eligible_farmer}'.", weight=0))
        # risk relevance
        # crop-risk keywords (pest, disease, drought…) only apply to crop covers — a livestock
        # "Death due to Disease" policy is not evidence for a crop-stress risk.
        rel, hits = (0.0, []) if p.is_livestock else _risk_relevance(str(p.covered_risk), facts.active_risk_types, v.risk_to_cover_keywords)
        if rel:
            score += 24; ex.add(Factor("Covers an active farm risk", "positive", f"'{p.covered_risk}' matches detected risk(s): {', '.join(h.replace('_', ' ') for h in hits)}.", weight=24, source="Risk Center"))
        else:
            score += 4; ex.add(Factor("Risk covered", "neutral", f"Covers '{p.covered_risk}' (not currently active on the farm).", weight=4))
        # premium & subsidy
        prem = float(p.premium_percentage)
        sub = 0.0 if _isnull(p.government_subsidy) else float(p.government_subsidy)
        net = prem * (1 - sub / 100)
        pts = float(np.clip(8 - net * 2, 0, 8))
        score += pts
        ex.add(Factor("Premium burden", "positive" if net <= 2 else "neutral", f"Premium {prem:g}% of sum insured; govt subsidy {sub:g}% → farmer share ≈ {net:.1f}%.", value=round(net, 2), weight=round(pts, 1)))
        if sub >= 50:
            score += 5; ex.add(Factor("Government subsidised", "positive", f"{sub:g}% premium subsidy.", weight=5))
        score += float(p.priority_score)
        if any(_ai_rule_names_match(x, p.insurance_name) or _ai_rule_names_match(x, p.coverage_type) for x in ai_ins):
            score += 6; ex.add(Factor("Profile-segment rule", "positive", "KB ai_recommendation_rules list this cover type for the farmer's segment.", weight=6, source="Knowledge base · ai_recommendation_rules"))
        if any(_ai_rule_names_match(x, p.coverage_type) or _ai_rule_names_match(x, p.insurance_name) for x in rule_ins):
            score += 6; ex.add(Factor("Eligibility rule", "positive", "KB eligibility rules recommend this cover type.", weight=6, source="Knowledge base · eligibility_rules"))
        if not facts.has_insurance:
            score += 4; ex.add(Factor("Currently uninsured", "positive", "Farmer has no crop insurance — any cover reduces exposure.", weight=4))
        score = 0.0 if hard else float(np.clip(score, 0, 100))
        checklist = resolve_documents(kb, facts, list(p.documents_list), contexts=(["livestock"] if bool(p.is_livestock) else []))
        lbl = "Not applicable" if hard else score_label(score, 70, 45)
        cov = None if _isnull(p.coverage_amount) else float(p.coverage_amount)
        prem_inr = None
        if cov is not None:
            prem_inr = round(cov * net / 100)
        ex.summary = (f"{lbl} ({score:.0f}%): {p.coverage_type} — {p.covered_risk}; farmer premium ≈ {net:.1f}%" if not hard else f"Not applicable — {ex.risks[0].detail}")
        out.append(MatchResult(
            p.insurance_id, p.insurance_name, "insurance", score, lbl, ex, hard_fail=hard,
            documents=[i.name for i in checklist.applicable], documents_missing=checklist.missing_blocking,
            payload={"provider": p.provider, "coverage_type": p.coverage_type, "covered_crop": p.covered_crop, "covered_risk": p.covered_risk,
                     "premium_pct": prem, "government_subsidy_pct": sub, "farmer_premium_pct": round(net, 2), "coverage_amount": cov,
                     "indicative_farmer_premium_inr": prem_inr, "claim_period": p.claim_period, "claim_process": p.claim_process,
                     "eligible_farmer": p.eligible_farmer, "district_applicable": p.district_applicable, "priority_score": float(p.priority_score),
                     "risk_hits": hits, "is_livestock": bool(p.is_livestock), "document_readiness_pct": checklist.readiness_pct,
                     "checklist": checklist, "informational_only": True},
        ))
    out.sort(key=lambda m: -m.score)
    return [m for m in out if not m.hard_fail][:top_n]


def crop_covers(matches: List[MatchResult]) -> List[MatchResult]:
    """Crop (non-livestock) covers only — used for 'crop is uninsured' reasoning."""
    return [m for m in matches if not m.payload.get("is_livestock")]


def insurance_gap_note(kb, facts: FarmerFacts, matches: List[MatchResult]) -> Optional[str]:
    """Honest statement when the KB has no district-notified crop cover for this farm."""
    if crop_covers(matches):
        return None
    crop = facts.crop_master or "this crop"
    n_crop = int(kb.vocab.crop_matches_series(kb.insurance["covered_crop"], facts.crop_master).sum()) if hasattr(kb.vocab, "crop_matches_series") else \
        int(sum(kb.vocab.crop_matches(c, facts.crop_master) for c in kb.insurance["covered_crop"]))
    if n_crop:
        return (f"The knowledge base lists {n_crop} {crop} cover(s), but none is notified for {facts.district} ({facts.state}). "
                f"PMFBY/RWBCIS notification is decided state-wise each season — check the official PMFBY portal or your bank/CSC for the current notified list.")
    return (f"The knowledge base has no crop-insurance product for {crop}. Check the PMFBY portal for the notified crops in {facts.district}, {facts.state}.")
