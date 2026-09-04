"""Subsidy Finder — ``agricultural_subsidies`` matched to farm needs.

Relevance is driven by the farm's situation (risks, soil, irrigation, tenure,
crop, objective, stage) through the ``subsidy_relevance`` table in
vocab_mappings.yaml, plus region/crop applicability, the parent scheme's own
match score (if computed), and the KB priority_score.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from core.engines.documents import resolve_documents
from core.engines.facts import FarmerFacts
from core.engines.scheme_matcher import _isnull
from core.models.results import Explanation, Factor, MatchResult, Method, score_label


def farm_needs(facts: FarmerFacts) -> Dict[str, str]:
    """Situation tags → human reason. Drives subsidy relevance."""
    n: Dict[str, str] = {"always": "general input support"}
    if "water_stress" in facts.active_risk_types:
        n["water_stress"] = "water stress detected on the farm"
    if "drought" in facts.active_risk_types:
        n["drought"] = "drought / dry-spell risk active"
    if facts.irrigation_method == "flood":
        n["flood_irrigation"] = "flood irrigation in use — micro-irrigation would cut water use"
    if not facts.irrigation_available:
        n["rainfed"] = "farm is rainfed"
    if facts.irrigation_available:
        n["irrigation_available"] = "irrigation source present"
    if facts.irrigation_source == "borewell":
        n["borewell"] = "borewell-based pumping (solar pump candidate)"
    if facts.soil_limitations:
        n["soil_limitation"] = "soil limitation flagged: " + facts.soil_limitations[0][:60]
    if facts.low_oc:
        n["low_oc"] = "low soil organic carbon"
    if not facts.has_soil_card:
        n["no_soil_card"] = "no Soil Health Card on record"
    if facts.category in ("Marginal Farmer", "Small Farmer"):
        n["small_marginal"] = f"{facts.category.lower()} holding ({facts.acres:.1f} ac)"
    else:
        n["medium_large"] = f"{facts.category.lower()} holding ({facts.acres:.1f} ac)"
    if facts.is_fpo:
        n["fpo_member"] = "FPO member"
    if facts.is_horticulture:
        n["horticulture_crop"] = f"{facts.crop_master} is a horticulture crop"
    if facts.livestock:
        n["livestock"] = "farmer keeps livestock"
    if facts.harvest_near:
        n["harvest_near"] = "crop is nearing harvest"
    if facts.objective == "sustainability":
        n["sustainability"] = "objective: sustainability"
    if facts.objective in ("profit", "low_risk"):
        n["diversification"] = "diversification supports the stated objective"
    return n


def find_subsidies(kb, facts: FarmerFacts, scheme_scores: Optional[Dict[str, float]] = None, top_n: int = 10) -> List[MatchResult]:
    v = kb.vocab
    uni_region = kb.interpretation.get("universal_region_terms", ["All India"])
    uni_crop = tuple(kb.interpretation.get("universal_crop_terms", ["All Crops"]))
    needs = farm_needs(facts)
    subs = kb.subsidies[~kb.subsidies["excluded"]]
    scheme_scores = scheme_scores or {}
    out: List[MatchResult] = []
    for _, s in subs.iterrows():
        ex = Explanation(summary="", method=Method.KNOWLEDGE_BASE, kb_references=[s.subsidy_id],
                         sources=["Knowledge base · agricultural_subsidies"],
                         data_considered=["state", "crop", "farm situation (risks, soil, irrigation, tenure)", "parent scheme match", "KB priority"])
        score, hard = 0.0, False
        # region
        if str(s.state) in uni_region:
            score += 12; ex.add(Factor("Region", "positive", "Available across India.", weight=12))
        elif str(s.state).lower() == facts.state.lower():
            score += 18; ex.add(Factor("Relevant state", "positive", f"{s.state} state subsidy.", weight=18))
        else:
            hard = True; ex.add(Factor("Region", "risk", f"Specific to {s.state}."))
        # crop / allied
        crop_val = str(s.crop)
        if s.is_livestock_or_allied:
            kind = crop_val.replace("Not Crop Specific - ", "")
            if kind in ("Fisheries", "Apiculture") or "Fish" in kind:
                if not facts.livestock:
                    hard = True; ex.add(Factor("Allied activity", "risk", f"{kind} subsidy — not indicated by profile."))
                else:
                    score += 6; ex.add(Factor("Allied activity", "neutral", f"{kind} subsidy; farmer has allied livestock.", weight=6))
            elif facts.livestock:
                score += 15; ex.add(Factor("Livestock", "positive", f"{kind} subsidy; farmer keeps livestock.", weight=15))
            else:
                hard = True; ex.add(Factor("Livestock", "risk", f"{kind} subsidy — farmer has no livestock."))
        elif v.crop_matches(crop_val, facts.crop_master, uni_crop):
            score += 15 if crop_val not in uni_crop else 10
            ex.add(Factor("Crop eligible", "positive", f"Applies to {crop_val}.", weight=15))
        else:
            score += 2; ex.add(Factor("Crop focus differs", "limiting", f"Subsidy targets {crop_val}; farm grows {facts.crop_master}.", weight=2))
        # situational relevance
        rel = v.subsidy_relevance.get(str(s.subcategory), {}).get("needs", [])
        hits = [n for n in rel if n in needs and n != "always"]
        if hits:
            pts = min(30.0, 12.0 * len(hits))
            score += pts
            ex.add(Factor("Matches farm need", "positive", f"{s.subcategory}: " + "; ".join(needs[h] for h in hits[:3]) + ".", weight=pts, source="Farm analytics"))
        elif "always" in rel:
            score += 8; ex.add(Factor("General relevance", "neutral", f"{s.subcategory} — generally applicable.", weight=8))
        else:
            score += 2; ex.add(Factor("Relevance", "limiting", f"{s.subcategory} is not indicated by the current farm situation.", weight=2))
        # tenure / category hints in eligibility text
        et = str(s.eligibility).lower()
        if "tenant" in et and facts.is_tenant_or_sharecropper:
            score += 8; ex.add(Factor("Tenant provision", "positive", "Eligibility text explicitly includes tenant farmers/sharecroppers.", weight=8))
        if "small and marginal" in et and facts.category in ("Marginal Farmer", "Small Farmer"):
            score += 8; ex.add(Factor("Small/marginal priority", "positive", "Eligibility text prioritises small & marginal farmers.", weight=8))
        if "women" in et and facts.is_woman:
            score += 8; ex.add(Factor("Women-farmer priority", "positive", "Eligibility text prioritises women farmers.", weight=8))
        if ("fpo" in et or "producer organisation" in et) and facts.is_fpo:
            score += 6; ex.add(Factor("FPO provision", "positive", "Eligibility text includes FPOs.", weight=6))
        # parent scheme
        ps = scheme_scores.get(str(s.scheme_name))
        if ps is not None:
            pts = ps * 0.15
            score += pts
            ex.add(Factor("Parent scheme match", "positive" if ps >= 60 else "neutral", f"Parent scheme {s.scheme_name} scored {ps:.0f}% for this farm.", weight=round(pts, 1), source="Scheme Finder"))
        score += float(s.priority_score)
        score = 0.0 if hard else float(np.clip(score, 0, 100))
        doc_ctx = ["livestock"] if bool(s.is_livestock_or_allied) else []
        if "fpo" in str(s.subcategory).lower():
            doc_ctx.append("fpo_member")
        checklist = resolve_documents(kb, facts, list(s.documents_list), scheme_name=s.scheme_name, contexts=doc_ctx)
        lbl = "Not applicable" if hard else score_label(score, 65, 45)
        amt = None if _isnull(s.maximum_amount) else float(s.maximum_amount)
        pct = None if _isnull(s.percentage) else float(s.percentage)
        ex.summary = (f"{lbl} ({score:.0f}%): {s.subsidy_name} — up to ₹{amt:,.0f}" + (f" ({pct:g}%)" if pct else "") if not hard else f"Not applicable — {ex.risks[0].detail}")
        out.append(MatchResult(
            s.subsidy_id, s.subsidy_name, "subsidy", score, lbl, ex, hard_fail=hard,
            documents=[i.name for i in checklist.applicable], documents_missing=checklist.missing_blocking,
            payload={"scheme_name": s.scheme_name, "crop": s.crop, "state": s.state, "subcategory": s.subcategory, "maximum_amount": amt,
                     "percentage": pct, "eligibility": s.eligibility, "application_process": s.application_process,
                     "priority_score": float(s.priority_score), "need_hits": hits, "document_readiness_pct": checklist.readiness_pct, "checklist": checklist},
        ))
    out.sort(key=lambda m: -m.score)
    return [m for m in out if not m.hard_fail][:top_n]
