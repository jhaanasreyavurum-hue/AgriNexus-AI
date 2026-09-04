"""Typed result objects returned by every engine.

The UI never receives a bare number. It receives a result with a score, a
label, the factors that drove it, the method used (rule / ML / remote
sensing / weather / KB lookup / LLM) and the data sources considered. This is
what makes every recommendation explainable and honestly labelled.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class Method(str, Enum):
    RULE_BASED = "Rule-based"
    ML_MODEL = "Machine-learning prediction"
    REMOTE_SENSING = "Remote-sensing result"
    WEATHER = "Weather result"
    KNOWLEDGE_BASE = "Knowledge-base lookup"
    LLM = "LLM-generated explanation"
    REFERENCE = "Reference table"


class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"low": 1, "moderate": 2, "high": 3, "critical": 4}[self.value]


@dataclass
class Factor:
    """One reason for/against a result."""
    name: str
    effect: str                     # "positive" | "limiting" | "risk" | "neutral" | "missing"
    detail: str
    value: Optional[Any] = None
    weight: Optional[float] = None  # contribution to score if applicable
    source: Optional[str] = None    # provenance label


@dataclass
class Explanation:
    summary: str
    data_considered: List[str] = field(default_factory=list)
    positive: List[Factor] = field(default_factory=list)
    limiting: List[Factor] = field(default_factory=list)
    risks: List[Factor] = field(default_factory=list)
    missing: List[Factor] = field(default_factory=list)
    neutral: List[Factor] = field(default_factory=list)
    method: Method = Method.RULE_BASED
    sources: List[str] = field(default_factory=list)   # provenance labels
    kb_references: List[str] = field(default_factory=list)  # e.g. "SCHM001", "RULE0042"
    demo_data_used: bool = False

    def add(self, f: Factor) -> None:
        {"positive": self.positive, "limiting": self.limiting, "risk": self.risks,
         "missing": self.missing, "neutral": self.neutral}.get(f.effect, self.neutral).append(f)


@dataclass
class ScoreBreakdown:
    name: str
    score: Optional[float]          # 0..100, None when data missing
    weight: float
    label: str
    explanation: Explanation
    available: bool = True


@dataclass
class Recommendation:
    """A concrete action with priority, horizon and explanation."""
    action: str
    priority: int                   # 1 = do first
    horizon: str                    # "today" | "24h" | "this_week" | "this_season" | "before_next_season"
    category: str                   # irrigation | nutrient | protection | finance | scheme | insurance | crop_plan | monitoring
    explanation: Explanation
    confidence: Optional[float] = None
    method: Method = Method.RULE_BASED


@dataclass
class Risk:
    risk_type: str                  # drought | water_stress | excess_rainfall | heat_stress | crop_stress | soil_limitation | financial
    title: str
    severity: Severity
    score: float                    # 0..100
    reason: str
    action: str
    explanation: Explanation
    related_insurance_keywords: List[str] = field(default_factory=list)


@dataclass
class Opportunity:
    opportunity_type: str           # subsidy | scheme | loan | insurance | crop_diversification | market
    title: str
    value_hint: Optional[str]       # e.g. "Up to ₹75,000"
    reason: str
    action: str
    kb_reference: Optional[str]
    score: float                    # 0..100 relevance
    explanation: Explanation


@dataclass
class MatchResult:
    """A KB item (scheme / loan / insurance / subsidy / crop) matched to the farm."""
    item_id: str
    title: str
    item_type: str
    score: float                    # 0..100
    label: str                      # "Strong match" / "Possible match" / "Unlikely"
    explanation: Explanation
    payload: Dict[str, Any] = field(default_factory=dict)   # KB row (selected columns)
    documents: List[str] = field(default_factory=list)
    documents_missing: List[str] = field(default_factory=list)
    hard_fail: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_label(score: float, strong: float = 75, possible: float = 50) -> str:
    if score >= strong:
        return "Strong match"
    if score >= possible:
        return "Possible match"
    return "Unlikely match"
