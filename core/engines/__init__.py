"""Knowledge engines — match the Farm Digital Twin against the knowledge base.

All engines are pure functions of (FarmContext, KnowledgeBase[, FarmAssessment])
and return lists of :class:`MatchResult` / :class:`Opportunity` with full
explanations and KB references. Method label: *Knowledge-base lookup* combined
with *Rule-based* scoring. No Streamlit imports.
"""
from core.engines.facts import FarmerFacts, build_facts
from core.engines.documents import resolve_documents, DocumentChecklist
from core.engines.crop_advisor import recommend_crops
from core.engines.scheme_matcher import match_schemes
from core.engines.loan_advisor import advise_loans, LoanAdvice
from core.engines.insurance_matcher import match_insurance
from core.engines.subsidy_finder import find_subsidies
from core.engines.opportunity import detect_opportunities
from core.engines.knowledge_results import KnowledgeResults, run_knowledge_engines

__all__ = [
    "FarmerFacts", "build_facts", "resolve_documents", "DocumentChecklist", "recommend_crops",
    "match_schemes", "advise_loans", "LoanAdvice", "match_insurance", "find_subsidies",
    "detect_opportunities", "KnowledgeResults", "run_knowledge_engines",
]
