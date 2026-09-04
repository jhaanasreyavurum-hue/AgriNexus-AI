"""Farmer-facing financial summary derived from a full assessment.

Turns the knowledge-engine results into the four home-dashboard cards
(MY FARM · MY FINANCIAL PROFILE · MY ELIGIBILITY · MY RECOMMENDATIONS) and a
*financial* Next Best Action, all rule-based over engine outputs (no new KB
reads, no invented values — anything not assessed is reported as such).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from core.models.results import Explanation, Factor, Method, Recommendation

STRONG, POSSIBLE = 75.0, 50.0


@dataclass
class FinancialSummary:
    # eligibility counts
    loan_products_strong: int
    loan_products_possible: int
    scheme_strong: int
    scheme_possible: int
    insurance_matches: int
    crop_cover_available: bool
    subsidy_matches: int
    subsidy_potential_inr: float
    # profile
    estimated_credit_inr: Optional[float]
    credit_rating: str
    credit_rating_score: float
    income_inr: Optional[float]
    existing_loans_inr: float
    debt_to_income: Optional[float]
    farmer_category: str
    document_readiness_pct: Optional[float]      # mean readiness over top loan + top scheme
    documents_missing: List[str]
    # readiness index and NBA
    financial_readiness: float                   # 0..100
    readiness_label: str
    readiness_explanation: Explanation
    next_best_action: Recommendation
    profile_gaps: List[str] = field(default_factory=list)   # fields the farmer could add to sharpen results

    def cards(self) -> Dict[str, Dict[str, Any]]:
        return {
            "loan_eligibility": {"value": f"{self.loan_products_strong + self.loan_products_possible} products", "sub": f"{self.loan_products_strong} strong · est. ₹{(self.estimated_credit_inr or 0):,.0f} ({self.credit_rating})"},
            "scheme_matches": {"value": f"{self.scheme_strong + self.scheme_possible} schemes", "sub": f"{self.scheme_strong} strong matches"},
            "insurance_matches": {"value": f"{self.insurance_matches} covers", "sub": "crop cover notified" if self.crop_cover_available else "no district-notified crop cover in KB"},
            "potential_subsidies": {"value": f"{self.subsidy_matches} subsidies", "sub": f"largest cap ₹{self.subsidy_potential_inr:,.0f} (not additive)" if self.subsidy_potential_inr else "no amount caps listed"},
            "financial_readiness": {"value": f"{self.financial_readiness:.0f} / 100", "sub": self.readiness_label},
            "recommended_action": {"value": self.next_best_action.action, "sub": self.next_best_action.explanation.summary},
        }


def _readiness(kr, facts, top_docs_pct: Optional[float], ex: Explanation) -> float:
    """0-100 composite: documents 35 · credit rating 30 · protection 15 · profile completeness 20."""
    score = 0.0
    if top_docs_pct is not None:
        part = 35 * top_docs_pct / 100
        score += part
        ex.add(Factor("Documents", "positive" if top_docs_pct >= 70 else ("neutral" if top_docs_pct >= 40 else "limiting"), f"{top_docs_pct:.0f}% of key documents for your best loan/scheme are in hand.", value=round(top_docs_pct)))
    else:
        ex.add(Factor("Documents", "missing", "No product matched yet, so document readiness could not be assessed."))
    part = 30 * (kr.loans.rating_score or 0) / 100
    score += part
    ex.add(Factor("Credit standing", "positive" if kr.loans.eligibility_rating == "Good" else ("neutral" if kr.loans.eligibility_rating == "Moderate" else "limiting"),
                  f"Indicative credit eligibility rated {kr.loans.eligibility_rating} ({kr.loans.rating_score:.0f}/100).", value=round(kr.loans.rating_score or 0)))
    prot = 0
    if facts.has_insurance:
        prot += 10
    if facts.has_bank_account and facts.has_aadhaar:
        prot += 5
    score += prot
    ex.add(Factor("Protection & banking", "positive" if prot >= 15 else ("neutral" if prot >= 5 else "limiting"),
                  ("Crop insured" if facts.has_insurance else "Crop not insured") + (" · Aadhaar + bank account in place" if facts.has_bank_account and facts.has_aadhaar else " · Aadhaar/bank account missing"), value=prot))
    comp = 0
    for ok in (facts.income is not None, facts.crop_master is not None, facts.age is not None, bool(facts.documents_held), facts.loan_purpose is not None):
        comp += 4 if ok else 0
    score += comp
    ex.add(Factor("Profile completeness", "positive" if comp >= 16 else "neutral", f"{comp // 4} of 5 key profile inputs provided (income, crop, age, documents, credit need).", value=comp))
    return float(np.clip(score, 0, 100))


def summarise_finances(assessment) -> FinancialSummary:
    kr = assessment.knowledge
    facts = kr.facts
    ctx = assessment.ctx
    loans = [m for m in kr.loans.products if not m.hard_fail]
    l_strong = sum(1 for m in loans if m.score >= STRONG)
    l_poss = sum(1 for m in loans if POSSIBLE <= m.score < STRONG)
    schemes = [m for m in kr.schemes if not m.hard_fail]
    s_strong = sum(1 for m in schemes if m.score >= STRONG)
    s_poss = sum(1 for m in schemes if POSSIBLE <= m.score < STRONG)
    crop_ins = [m for m in kr.insurance if not m.payload.get("is_livestock")]
    subs = [m for m in kr.subsidies if m.score >= POSSIBLE]
    sub_amt = float(max([(m.payload.get("maximum_amount") or 0) for m in subs], default=0))   # largest single cap — caps are not additive

    docs_pcts = [m.payload.get("document_readiness_pct") for m in (loans[:1] + schemes[:1]) if m.payload.get("document_readiness_pct") is not None]
    top_docs = float(np.mean(docs_pcts)) if docs_pcts else None
    missing: List[str] = []
    for m in loans[:1] + schemes[:1]:
        for d in m.documents_missing:
            if d not in missing:
                missing.append(d)

    dti = (ctx.farmer.existing_loans_inr / facts.income) if (facts.income and ctx.farmer.existing_loans_inr) else (0.0 if facts.income else None)

    ex = Explanation(summary="", method=Method.RULE_BASED, sources=["Knowledge-engine results (loans, schemes, insurance, subsidies)", "Farmer profile"],
                     data_considered=["document readiness", "credit rating", "insurance status", "Aadhaar/bank account", "profile completeness"])
    readiness = _readiness(kr, facts, top_docs, ex)
    label = "Bank-ready" if readiness >= 75 else ("Nearly ready — close the gaps" if readiness >= 50 else "Preparation needed")
    ex.summary = f"Financial readiness {readiness:.0f}/100 — {label}."

    gaps = []
    if facts.income is None:
        gaps.append("annual income")
    if not facts.crop_master:
        gaps.append("current crop")
    if facts.loan_purpose is None:
        gaps.append("credit need / loan purpose")
    if not ctx.farmer.documents_held:
        gaps.append("documents held")
    if facts.age is None:
        gaps.append("age (some schemes have age limits)")

    # ---- financial next best action (ordered rules) ----------------------------
    nex = Explanation(summary="", method=Method.RULE_BASED, sources=ex.sources, data_considered=ex.data_considered)
    if facts.loan_purpose and loans and missing and (top_docs or 0) < 60:
        top = loans[0]
        action = f"Complete your documents before applying — {len(missing)} missing for {top.title}: {', '.join(missing[:3])}."
        nex.summary = f"You may be eligible for {l_strong + l_poss} loan product(s) (best: {top.title}, {top.score:.0f}% match) but documents are only {top_docs:.0f}% ready."
        cat, conf = "finance", 0.7
    elif facts.loan_purpose and loans:
        top = loans[0]
        action = f"You may be eligible for {l_strong + l_poss} loan product(s) — apply for {top.title} (indicative limit ₹{(kr.loans.estimated_eligibility_inr or 0):,.0f})."
        nex.summary = f"{top.payload.get('loan_type')} at {top.payload.get('interest_rate')} from {top.payload.get('bank_short')}; documents {top.payload.get('document_readiness_pct', 0):.0f}% ready."
        cat, conf = "finance", 0.65
    elif not facts.has_insurance and crop_ins:
        m = crop_ins[0]
        action = f"Insure your crop — {m.title} ({m.payload.get('provider')}) matches at {m.score:.0f}%."
        nex.summary = f"Crop is uninsured; farmer premium ≈{m.payload.get('farmer_premium_pct')}% under the notified cover."
        cat, conf = "insurance", 0.65
    elif schemes:
        m = schemes[0]
        action = f"Apply for {m.title} ({m.score:.0f}% match)."
        nex.summary = m.explanation.summary
        cat, conf = "scheme", 0.6
    else:
        action = "Complete your profile (income, crop, documents) so the engines can match products."
        nex.summary = "Not enough profile information for loan or scheme matching yet."
        cat, conf = "finance", 0.5
    if gaps:
        nex.add(Factor("Profile gaps", "limiting", "Add " + ", ".join(gaps[:3]) + " to sharpen matches."))
    for f in (ex.limiting + ex.positive)[:3]:
        nex.add(f)
    nba = Recommendation(action, 1, "this_season", cat, nex, conf, Method.RULE_BASED)

    return FinancialSummary(l_strong, l_poss, s_strong, s_poss, len(kr.insurance), bool(crop_ins), len(subs), sub_amt,
                            kr.loans.estimated_eligibility_inr, kr.loans.eligibility_rating, kr.loans.rating_score or 0.0,
                            facts.income, ctx.farmer.existing_loans_inr or 0.0, dti, facts.category, top_docs, missing,
                            readiness, label, ex, nba, gaps)
