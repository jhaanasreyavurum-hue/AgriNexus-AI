"""Opportunity Engine (§14) — turns knowledge-engine matches + farm analytics
into a ranked list of concrete opportunities (money, protection, diversification).
"""
from __future__ import annotations

from typing import List, Optional

from core.engines.facts import FarmerFacts
from core.engines.loan_advisor import LoanAdvice
from core.models.results import Explanation, Factor, MatchResult, Method, Opportunity


def _fmt_inr(v: Optional[float]) -> Optional[str]:
    if v is None:
        return None
    if v >= 1e5:
        return f"₹{v/1e5:.1f} lakh"
    return f"₹{v:,.0f}"


def detect_opportunities(facts: FarmerFacts, schemes: List[MatchResult], subsidies: List[MatchResult], loans: LoanAdvice,
                         insurance: List[MatchResult], crops: List[MatchResult], assessment=None, top_n: int = 8) -> List[Opportunity]:
    opps: List[Opportunity] = []

    # ---- subsidies ---------------------------------------------------------
    for m in [x for x in subsidies if x.score >= 55][:3]:
        p = m.payload
        ex = Explanation(summary=m.explanation.summary, method=Method.KNOWLEDGE_BASE, kb_references=m.explanation.kb_references,
                         sources=m.explanation.sources, positive=m.explanation.positive[:3])
        opps.append(Opportunity("subsidy", f"💰 {m.title}", _fmt_inr(p.get("maximum_amount")),
                                (m.explanation.positive[0].detail if m.explanation.positive else m.explanation.summary),
                                f"Apply under {p['scheme_name']}: {str(p['application_process'])[:120]}…", m.item_id, m.score, ex))

    # ---- schemes -----------------------------------------------------------
    for m in [x for x in schemes if x.score >= 60 and not x.hard_fail][:3]:
        p = m.payload
        ex = Explanation(summary=m.explanation.summary, method=Method.KNOWLEDGE_BASE, kb_references=m.explanation.kb_references,
                         sources=m.explanation.sources, positive=m.explanation.positive[:3])
        val = _fmt_inr(p.get("maximum_subsidy"))
        opps.append(Opportunity("scheme", f"🎯 {m.title}", val, m.explanation.summary,
                                f"Apply via {p.get('application_mode')} — {p.get('official_portal')}; documents ready {p.get('document_readiness_pct', 0):.0f}%.",
                                m.item_id, m.score * 0.95, ex))

    # ---- insurance ---------------------------------------------------------
    crop_ins = [m for m in insurance if not m.payload.get("is_livestock")]
    if not facts.has_insurance and crop_ins:
        m = crop_ins[0]
        p = m.payload
        ex = Explanation(summary=m.explanation.summary, method=Method.KNOWLEDGE_BASE, kb_references=m.explanation.kb_references,
                         sources=m.explanation.sources, positive=m.explanation.positive[:3])
        active = ", ".join(r.replace("_", " ") for r in p.get("risk_hits", [])) or "seasonal weather risk"
        val = f"cover {_fmt_inr(p['coverage_amount'])} for ≈{p['farmer_premium_pct']}% premium" if p.get("coverage_amount") else None
        opps.append(Opportunity("insurance", f"🛡 Insurance opportunity: {p['coverage_type']}", val,
                                f"Crop is uninsured while {active} is present; {m.title} covers '{p['covered_risk']}'.",
                                f"Enrol with {p['provider']} (informational — confirm premium with insurer/bank).", m.item_id, m.score, ex))

    # ---- credit ------------------------------------------------------------
    if loans.products:
        m = loans.products[0]
        p = m.payload
        ex = Explanation(summary=loans.explanation.summary, method=Method.RULE_BASED, kb_references=[m.item_id],
                         sources=loans.explanation.sources, positive=loans.explanation.positive[:3])
        reason = (f"Indicative eligibility {_fmt_inr(loans.estimated_eligibility_inr)} ({loans.eligibility_rating}); best-fit product "
                  f"{p['loan_type']} at {p['interest_rate']}" + (" — you already hold a KCC; consider enhancement." if facts.has_kcc else "."))
        opps.append(Opportunity("loan", f"💳 Credit opportunity: {p['loan_type']}", _fmt_inr(loans.estimated_eligibility_inr), reason,
                                f"Approach {p['bank_short']} with: {', '.join(m.documents[:4])}.", m.item_id, m.score * 0.9, ex))

    # ---- crop diversification -----------------------------------------------
    alts = [c for c in crops if not c.payload.get("is_current_crop") and c.score >= 70]
    cur = next((c for c in crops if c.payload.get("is_current_crop")), None)

    def _advantage(a):
        # an alternative is an *opportunity* only if it fixes something the current crop scores poorly on
        if cur is None:
            return "no current crop on record"
        fa, fc = a.payload.get("factor_scores", {}), cur.payload.get("factor_scores", {})
        gains = [k for k in ("water", "rain", "soil", "rotation") if (fa.get(k) or 0) - (fc.get(k) or 0) >= 20]
        if a.score > cur.score:
            return "higher overall suitability"
        if gains:
            return "better " + "/".join(gains) + " fit"
        return None

    best = next(((a, _advantage(a)) for a in alts if _advantage(a)), None)
    if best:
        a, why = best
        ex = Explanation(summary=a.explanation.summary, method=Method.RULE_BASED, kb_references=a.explanation.kb_references,
                         sources=a.explanation.sources, positive=a.explanation.positive[:4])
        cmp = f" vs current {cur.title} {cur.score:.0f}%" if cur else ""
        opps.append(Opportunity("crop_diversification", f"🌱 Crop option: {a.title}", f"suitability {a.score:.0f}%{cmp}",
                                f"{why.capitalize()}. " + a.explanation.summary, f"Evaluate {a.title} for {a.payload.get('seasons_all', [a.payload.get('season')])[0]}; KB-linked schemes: {', '.join(a.payload.get('recommended_schemes', [])[:2])}.",
                                a.item_id, a.score * (0.85 if cur is None or a.score > cur.score else 0.7), ex))

    # ---- soil-card / market quick wins ----------------------------------------
    if not facts.has_soil_card:
        shc = next((m for m in schemes if "Soil Health Card" in m.title), None)
        if shc:
            ex = Explanation(summary="No Soil Health Card on record; several KB schemes require it.", method=Method.RULE_BASED, kb_references=[shc.item_id])
            opps.append(Opportunity("scheme", "🧪 Get a Soil Health Card", "free", "Unlocks soil-card-linked schemes and gives measured N-P-K/pH for fertiliser planning.",
                                    f"Apply under {shc.title} ({shc.payload.get('official_portal')}).", shc.item_id, 62.0, ex))
    if facts.harvest_near:
        enam = next((m for m in schemes if "e-NAM" in m.title), None)
        if enam:
            ex = Explanation(summary="Crop nearing harvest — market registration improves price discovery.", method=Method.RULE_BASED, kb_references=[enam.item_id])
            opps.append(Opportunity("market", "🏷 Register on e-NAM before harvest", None, ex.summary, f"Register via {enam.payload.get('official_portal')}.", enam.item_id, 58.0, ex))

    opps.sort(key=lambda o: -o.score)
    return opps[:top_n]
