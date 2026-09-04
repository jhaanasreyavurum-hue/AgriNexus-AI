"""Orchestrator: run every knowledge engine once and bundle the results."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.engines.crop_advisor import recommend_crops
from core.engines.facts import FarmerFacts, build_facts
from core.engines.insurance_matcher import crop_covers, insurance_gap_note, match_insurance
from core.engines.loan_advisor import LoanAdvice, advise_loans
from core.engines.opportunity import detect_opportunities
from core.engines.scheme_matcher import fire_ai_rules, fire_eligibility_rules, match_schemes
from core.engines.subsidy_finder import find_subsidies
from core.models.farm_context import FarmContext
from core.models.results import MatchResult, Opportunity


@dataclass
class KnowledgeResults:
    facts: FarmerFacts
    crops: List[MatchResult]
    schemes: List[MatchResult]
    subsidies: List[MatchResult]
    loans: LoanAdvice
    insurance: List[MatchResult]
    opportunities: List[Opportunity]
    fired_eligibility_rules: List[Dict[str, Any]] = field(default_factory=list)
    fired_ai_rules: List[Dict[str, Any]] = field(default_factory=list)
    coverage_note: str = ""
    insurance_gap_note: Optional[str] = None      # set when no crop cover is notified for the district

    def as_advisor_dict(self) -> Dict[str, Any]:
        return {"crops": self.crops, "schemes": self.schemes, "loans": self.loans.products,
                "insurance": self.insurance, "subsidies": self.subsidies, "opportunities": self.opportunities,
                "loan_advice": self.loans, "insurance_gap_note": self.insurance_gap_note}


def run_knowledge_engines(ctx: FarmContext, kb, assessment=None, target_season: Optional[str] = None) -> KnowledgeResults:
    facts = build_facts(ctx, kb, assessment)
    soil_canon = assessment.soil.soil_canonical if assessment is not None else kb.vocab.canonical_soil(ctx.soil.soil_type)

    crops = recommend_crops(ctx, kb, facts, target_season=target_season, top_n=10)
    schemes = match_schemes(kb, facts, soil_canon, top_n=12)
    scheme_scores = {m.title: m.score for m in schemes}
    subsidies = find_subsidies(kb, facts, scheme_scores, top_n=10)
    loans = advise_loans(kb, facts, ctx.farmer.existing_loans_inr or 0.0, soil_canon, top_n=8)
    insurance = match_insurance(kb, facts, soil_canon, top_n=8)
    opportunities = detect_opportunities(facts, schemes, subsidies, loans, insurance, crops, assessment)

    elig = fire_eligibility_rules(kb, facts, soil_canon)
    ai = fire_ai_rules(kb, facts)
    cov = facts.kb_coverage
    note = {"deep": f"Knowledge base has deep coverage for {facts.state} (state schemes, subsidies, branches, district-level insurance).",
            "moderate": f"Knowledge base has moderate coverage for {facts.state}: national schemes and eligibility rules apply; no state-specific schemes or bank branches are listed.",
            "limited": f"Knowledge base coverage for {facts.state} is limited to national schemes and generic rules; state-specific programmes are not in the KB."}[cov]
    return KnowledgeResults(
        facts, crops, schemes, subsidies, loans, insurance, opportunities,
        elig[["rule_id", "rule_name", "crop", "state", "soil_type", "farmer_category", "recommended_scheme", "recommended_loan", "recommended_insurance", "priority"]].head(10).to_dict("records"),
        ai[["rule_id", "cond_state", "cond_crop", "cond_land_band", "cond_income_band", "priority", "confidence", "reason"]].head(5).to_dict("records"),
        note,
        insurance_gap_note=insurance_gap_note(kb, facts, insurance),
    )
