"""Finance & Loan Advisor (§12).

Two outputs:

1. **Estimated credit eligibility** — an *indicative* figure and rating derived
   from farm scale, KB loan-amount ranges for the relevant loan types, and
   profile factors (existing debt, income, collateral, land records). It is
   NOT a bank offer; the rating and every factor are exposed.

   scale of finance = crop-loan KB median amount per acre × acres (bounded by
   the KB min/max of matching products), adjusted by:
     – income coverage      (annual income vs requested amount)
     – existing debt burden (loans / income)
     – collateral & land records (unlocks collateral-required products)
     – KCC holder           (existing relationship)

2. **Matching loan products** from ``agri_loan_products`` (120 products, 10
   banks × 12 types), scored on purpose fit, collateral feasibility, crop fit,
   amount fit, cost (interest), government linkage, KB loan_score, and boosts
   from eligibility / ai rules. Documents come from the product row +
   ``required_documents``. Nearby branches from ``bank_branches`` (Telangana
   only in the KB — coverage is reported).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from core.engines.documents import resolve_documents
from core.engines.facts import FarmerFacts
from core.engines.scheme_matcher import _ai_rule_names_match, _isnull, fire_ai_rules, fire_eligibility_rules
from core.models.results import Explanation, Factor, MatchResult, Method, score_label


@dataclass
class LoanAdvice:
    estimated_eligibility_inr: Optional[float]
    eligibility_rating: str                 # Good | Moderate | Limited | Not assessed
    rating_score: float                     # 0..100
    explanation: Explanation
    products: List[MatchResult] = field(default_factory=list)
    branches: List[Dict] = field(default_factory=list)
    branch_coverage_note: str = ""
    purpose: Optional[str] = None
    relevant_loan_types: List[str] = field(default_factory=list)


def _bank_short(name: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", name).strip()


def _estimate_eligibility(kb, facts: FarmerFacts, types: List[str]) -> tuple[Optional[float], str, float, Explanation]:
    ex = Explanation(summary="", method=Method.RULE_BASED,
                     sources=["Knowledge base · agri_loan_products (amount ranges)", "Farmer profile"],
                     data_considered=["farm area", "KB loan amount ranges for relevant products", "annual income", "existing loans", "collateral", "land records", "KCC status"])
    loans = kb.loans[~kb.loans["excluded"]]
    pool = loans[loans["loan_type"].isin(types)]
    if pool.empty:
        pool = loans[loans["loan_type"].isin(["Kisan Credit Card (KCC)", "Crop Loan (Seasonal Agricultural Operations)"])]
    kb_min, kb_max = float(pool["loan_amount_min"].min()), float(pool["loan_amount_max"].max())
    kb_med_max = float(pool["loan_amount_max"].median())
    ex.add(Factor("KB product range", "neutral", f"{len(pool)} relevant products lend ₹{kb_min:,.0f} – ₹{kb_max:,.0f} (median cap ₹{kb_med_max:,.0f}).", source="Knowledge base"))

    # scale of finance: the KB doesn't give per-acre norms; use median cap of matching
    # products as the reference for a 5-acre holding and scale linearly, capped by KB max.
    ref_acres = 5.0
    base = kb_med_max * min(facts.acres, 25.0) / ref_acres
    base = float(np.clip(base, kb_min, kb_max))
    ex.add(Factor("Farm scale", "neutral", f"{facts.acres:.1f} ac → indicative scale of finance ≈ ₹{base:,.0f} (median KB cap scaled from a {ref_acres:.0f}-ac reference).", value=round(base)))

    score = 60.0
    mult = 1.0
    if facts.income is not None:
        cov = facts.income / max(base, 1)
        if cov >= 1.0:
            score += 15; ex.add(Factor("Income coverage", "positive", f"Annual income ₹{facts.income:,.0f} covers the indicative amount ({cov:.1f}×).", value=round(cov, 2)))
        elif cov >= 0.5:
            score += 5; ex.add(Factor("Income coverage", "neutral", f"Income covers {cov:.0%} of the indicative amount.", value=round(cov, 2)))
        else:
            score -= 10; mult *= 0.75
            ex.add(Factor("Income coverage", "limiting", f"Income ₹{facts.income:,.0f} is only {cov:.0%} of the indicative amount — lenders may reduce the limit.", value=round(cov, 2)))
    else:
        ex.add(Factor("Income", "missing", "Annual income not provided — coverage not assessed."))

    # debt burden
    from core.models.farm_context import FarmContext  # noqa: F401 (typing only)
    debt = getattr(facts, "_existing_loans", None)
    if debt is None:
        debt = 0.0
    if facts.income and debt:
        ratio = debt / facts.income
        if ratio > 0.6:
            score -= 20; mult *= 0.6
            ex.add(Factor("Existing debt", "risk", f"Existing loans ₹{debt:,.0f} = {ratio:.0%} of income — high burden.", value=round(ratio, 2)))
        elif ratio > 0.3:
            score -= 8; mult *= 0.85
            ex.add(Factor("Existing debt", "limiting", f"Existing loans ₹{debt:,.0f} = {ratio:.0%} of income.", value=round(ratio, 2)))
        else:
            score += 5; ex.add(Factor("Existing debt", "positive", f"Existing loans ₹{debt:,.0f} are modest ({ratio:.0%} of income).", value=round(ratio, 2)))
    elif not debt:
        score += 8; ex.add(Factor("Existing debt", "positive", "No existing loans recorded."))

    if facts.is_owner and "Land Ownership / Pattadar Passbook" in facts.documents_held:
        score += 10; ex.add(Factor("Land records", "positive", "Pattadar passbook / land records available — unlocks most crop and term loans."))
    elif facts.is_tenant_or_sharecropper:
        if "Tenant Farmer / Sharecropper Certificate" in facts.documents_held:
            score -= 2; ex.add(Factor("Tenure", "neutral", "Tenant/sharecropper with certificate — eligible for KCC/crop loan via JLG or tenant provisions; term loans limited."))
        else:
            score -= 15; mult *= 0.6
            ex.add(Factor("Tenure", "limiting", "Tenant/sharecropper without a cultivation certificate — obtain a Tenant Farmer Certificate first."))
    if facts.collateral:
        score += 7; ex.add(Factor("Collateral", "positive", "Collateral available — collateral-backed products (higher limits) are feasible."))
    else:
        ex.add(Factor("Collateral", "neutral", "No collateral — matches restricted to collateral-free products (KCC, small crop loans, gold loan)."))
    if facts.has_kcc:
        score += 5; ex.add(Factor("KCC holder", "positive", "Existing KCC — enhancement / renewal is the fastest route."))
    if facts.is_fpo:
        score += 3; ex.add(Factor("FPO member", "positive", "FPO membership opens FPO term loans and group lending."))

    est = float(np.clip(base * mult, kb_min, kb_max))
    est = round(est / 5000) * 5000
    score = float(np.clip(score, 0, 100))
    rating = "Good" if score >= 75 else ("Moderate" if score >= 55 else "Limited")
    ex.summary = (f"Indicative credit eligibility ≈ ₹{est:,.0f} ({rating}). This is a rule-based estimate from KB product ranges and profile factors — "
                  "not a bank sanction.")
    return est, rating, score, ex


def advise_loans(kb, facts: FarmerFacts, existing_loans_inr: float = 0.0, soil_canonical: Optional[str] = None,
                 top_n: int = 8) -> LoanAdvice:
    v = kb.vocab
    facts._existing_loans = existing_loans_inr  # type: ignore[attr-defined]
    purpose = facts.loan_purpose or "crop_loan"
    types = list(v.loan_purpose_to_types.get(purpose, v.loan_purpose_to_types["crop_loan"]))
    if facts.livestock and "Dairy & Livestock Development Loan" not in types:
        types.append("Dairy & Livestock Development Loan")
    if facts.is_horticulture and "Horticulture & Plantation Loan" not in types:
        types.append("Horticulture & Plantation Loan")
    if facts.is_fpo and "Farmer Producer Organisation (FPO) Term Loan" not in types:
        types.append("Farmer Producer Organisation (FPO) Term Loan")
    if {"water_stress", "drought"} & facts.active_risk_types:
        for t in ("Micro Irrigation / Drip & Sprinkler Loan", "Solar Pump / Renewable Energy Agri Loan"):
            if t not in types:
                types.append(t)

    est, rating, rscore, ex_el = _estimate_eligibility(kb, facts, types[:3])
    elig = fire_eligibility_rules(kb, facts, soil_canonical)
    ai = fire_ai_rules(kb, facts)
    rule_types = set(elig["recommended_loan"])
    ai_loans = [x for _, r in ai.iterrows() for x in r.loans_list]

    loans = kb.loans[~kb.loans["excluded"]]
    out: List[MatchResult] = []
    for _, l in loans.iterrows():
        ex = Explanation(summary="", method=Method.KNOWLEDGE_BASE, kb_references=[l.loan_id],
                         sources=["Knowledge base · agri_loan_products", "Knowledge base · required_documents"],
                         data_considered=["loan purpose", "collateral", "crop", "amount vs eligibility", "interest rate", "government linkage", "KB loan score"])
        score, hard = 0.0, False
        # purpose fit
        if l.loan_type == types[0]:
            score += 30; ex.add(Factor("Purpose fit", "positive", f"{l.loan_type} is the primary product for purpose '{purpose}'.", weight=30))
        elif l.loan_type in types:
            score += 20; ex.add(Factor("Purpose fit", "positive", f"{l.loan_type} is relevant to '{purpose}' / farm situation.", weight=20))
        else:
            score += 2; ex.add(Factor("Purpose", "limiting", f"{l.loan_type} does not match purpose '{purpose}'.", weight=2))
        # collateral
        if l.collateral_required_bool and not facts.collateral:
            hard = True; ex.add(Factor("Collateral required", "risk", "Product requires collateral; none available."))
        elif l.collateral_required_bool:
            score += 6; ex.add(Factor("Collateral", "positive", "Collateral-backed product; collateral available.", weight=6))
        else:
            score += 10; ex.add(Factor("Collateral-free", "positive", "No collateral required.", weight=10))
        # crop specificity
        if l.crop_specific_flag:
            if v.crop_matches(l.crop_specific, facts.crop_master):
                score += 10; ex.add(Factor("Crop-specific product", "positive", f"Designed for {l.crop_specific}.", weight=10))
            else:
                hard = True; ex.add(Factor("Crop mismatch", "risk", f"Product is specific to {l.crop_specific}; farm grows {facts.crop_master}."))
        # amount fit
        if est is not None:
            if l.loan_amount_min <= est <= l.loan_amount_max:
                score += 10; ex.add(Factor("Amount fit", "positive", f"Indicative need ₹{est:,.0f} within ₹{l.loan_amount_min:,.0f}–₹{l.loan_amount_max:,.0f}.", weight=10))
            elif est < l.loan_amount_min:
                score += 3; ex.add(Factor("Amount", "limiting", f"Minimum ticket ₹{l.loan_amount_min:,.0f} exceeds indicative need ₹{est:,.0f}.", weight=3))
            else:
                score += 6; ex.add(Factor("Amount", "neutral", f"Cap ₹{l.loan_amount_max:,.0f} is below indicative need ₹{est:,.0f}; partial financing.", weight=6))
        # cost
        rate = float(l.minimum_interest)
        cost_pts = float(np.clip(12 - rate, 0, 10))
        score += cost_pts
        ex.add(Factor("Interest rate", "positive" if rate <= 7 else "neutral", f"{l.interest_rate} · processing fee {l.processing_fee} · tenure {l.repayment_years} yr · approval ~{l.approval_days} d.", value=rate, weight=round(cost_pts, 1)))
        if l.government_linked_bool:
            score += 6; ex.add(Factor("Government-linked", "positive", "Government-linked product (interest subvention / subsidy may apply)." + (f" Max subsidy ₹{l.maximum_subsidy:,.0f}." if not _isnull(l.maximum_subsidy) and l.maximum_subsidy > 0 else ""), weight=6))
        if facts.has_kcc and l.loan_type == "Kisan Credit Card (KCC)":
            score += 4; ex.add(Factor("Existing KCC", "positive", "Renewal / enhancement route.", weight=4))
        score += float(l.loan_score)  # KB 0..10
        if l.loan_type in rule_types:
            score += 8; ex.add(Factor("Eligibility rule", "positive", "KB eligibility rules recommend this loan type for the farm profile.", weight=8, source="Knowledge base · eligibility_rules"))
        if any(_ai_rule_names_match(x, l.loan_type) or _ai_rule_names_match(x, l.loan_name) for x in ai_loans):
            score += 6; ex.add(Factor("Profile-segment rule", "positive", "KB ai_recommendation_rules list this product type for the farmer's segment.", weight=6, source="Knowledge base · ai_recommendation_rules"))
        score = 0.0 if hard else float(np.clip(score, 0, 100))
        doc_ctx = []
        if bool(l.collateral_required_bool):
            doc_ctx.append("collateral_loan")
        if l.loan_type in ("Agri Infrastructure & Cold Storage Loan", "Farmer Producer Organisation (FPO) Term Loan",
                           "Solar Pump / Renewable Energy Agri Loan", "Warehouse Receipt / Post-Harvest Loan"):
            doc_ctx.append("project_loan")
        if bool(l.livestock_supported_bool) and facts.livestock:
            doc_ctx.append("livestock")
        if l.loan_type == "Farmer Producer Organisation (FPO) Term Loan":
            doc_ctx.append("fpo_member")
        checklist = resolve_documents(kb, facts, list(l.documents_list), loan_type=l.loan_type, contexts=doc_ctx)
        lbl = "Not suitable" if hard else score_label(score, 70, 45)
        ex.summary = (f"{lbl} ({score:.0f}%): {l.loan_type} at {l.interest_rate}" if not hard else f"Not suitable — {ex.risks[0].detail}")
        ex.add(Factor("Bank eligibility note", "neutral", str(l.eligibility_summary), source="Knowledge base"))
        if checklist.missing_blocking:
            ex.add(Factor("Documents to arrange", "limiting", ", ".join(checklist.missing_blocking[:4])))
        out.append(MatchResult(
            l.loan_id, l.loan_name, "loan", score, lbl, ex, hard_fail=hard,
            documents=[i.name for i in checklist.applicable], documents_missing=checklist.missing_blocking,
            payload={"bank": l.bank_name, "bank_short": _bank_short(l.bank_name), "loan_type": l.loan_type, "interest_rate": l.interest_rate,
                     "min_interest": rate, "max_interest": float(l.maximum_interest), "amount_min": int(l.loan_amount_min), "amount_max": int(l.loan_amount_max),
                     "repayment_years": int(l.repayment_years), "processing_fee": l.processing_fee, "collateral_required": bool(l.collateral_required_bool),
                     "government_linked": bool(l.government_linked_bool), "maximum_subsidy": None if _isnull(l.maximum_subsidy) else float(l.maximum_subsidy),
                     "approval_days": int(l.approval_days), "eligibility_summary": l.eligibility_summary, "loan_score": float(l.loan_score),
                     "document_readiness_pct": checklist.readiness_pct, "checklist": checklist},
        ))
    out.sort(key=lambda m: -m.score)
    products = [m for m in out if not m.hard_fail][:top_n]

    # branches
    br = kb.branches
    mine = br[(br["state"].str.lower() == facts.state.lower()) & (br["district"].str.lower() == facts.district.lower()) & br["loan_available_bool"]]
    banks_in_products = {m.payload["bank_short"] for m in products}
    mine = mine.copy()
    mine["offers_matched_product"] = mine["bank_name"].isin(banks_in_products)
    mine = mine.sort_values(["offers_matched_product", "government_linked"], ascending=False)
    branches = mine[["bank_name", "branch_name", "district", "ifsc", "phone", "latitude", "longitude", "insurance_available", "working_days", "offers_matched_product"]].head(8).to_dict("records")
    if len(mine):
        note = f"{len(mine)} KB branches with agri-loan desks in {facts.district}."
    elif (br["state"].str.lower() == facts.state.lower()).any():
        note = f"No KB branch listed for {facts.district}; {int((br['state'].str.lower() == facts.state.lower()).sum())} branches listed elsewhere in {facts.state}."
    else:
        note = f"The knowledge base has no branch directory for {facts.state} (coverage: {facts.kb_coverage}). Product matches are still valid — visit any listed bank."

    return LoanAdvice(est, rating, rscore, ex_el, products, branches, note, purpose, types)
