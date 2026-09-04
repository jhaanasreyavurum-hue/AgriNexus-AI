"""Farm Health index (§2) — rule-based weighted composite.

    Farm Health = Σ (available sub-score × weight) / Σ (weights of available sub-scores)

Six components: Vegetation · Soil · Water · Weather · Crop condition · Risk.
Components without data are excluded from the denominator and listed as
"not assessed" — the score is never padded with invented values. Confidence
reflects how much of the total weight was actually assessed and whether demo
data was involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.analytics.crop_stage import StageAnalysis
from core.analytics.ndvi import NDVIAnalysis
from core.analytics.soil import SoilAnalysis
from core.analytics.water_balance import WaterAnalysis
from core.analytics.weather import WeatherAnalysis
from core.models.results import Explanation, Factor, Method, Risk, ScoreBreakdown

WEIGHTS = {"Vegetation Health": 0.25, "Soil Health": 0.15, "Water Status": 0.20,
           "Weather Condition": 0.15, "Crop Condition": 0.10, "Risk": 0.15}


@dataclass
class FarmHealth:
    score: Optional[float]
    label: str
    breakdown: List[ScoreBreakdown]
    confidence: float                 # 0..1
    assessed_weight: float
    demo_data_used: bool
    explanation: Explanation = field(default_factory=lambda: Explanation(summary=""))


def _label(score: Optional[float]) -> str:
    if score is None:
        return "Not assessed"
    if score >= 80:
        return "Healthy"
    if score >= 65:
        return "Fair"
    if score >= 50:
        return "Stressed"
    return "Critical"


def _crop_condition(ndvi: NDVIAnalysis, stage: StageAnalysis, water: WaterAnalysis) -> ScoreBreakdown:
    """Crop condition = NDVI relative to what the stage expects + water status at critical stages."""
    ex = Explanation(summary="", method=Method.RULE_BASED, data_considered=["growth stage", "NDVI vs stage expectation", "water status"])
    if not stage.available and not ndvi.available:
        ex.summary = "Crop condition not assessed — no stage or NDVI data."
        return ScoreBreakdown("Crop Condition", None, WEIGHTS["Crop Condition"], "Not assessed", ex, False)
    score = 75.0
    if stage.available:
        ex.add(Factor("Stage", "neutral", f"{stage.current_stage} ({stage.days_after_sowing} DAS, {stage.progress_pct:.0f}% of cycle)."))
        if stage.critical_water_window and water.status in ("deficit", "approaching_deficit"):
            score -= 20 if water.status == "deficit" else 10
            ex.add(Factor("Critical-stage water", "risk", f"Water {water.status.replace('_', ' ')} during {stage.current_stage}."))
        elif stage.critical_water_window:
            ex.add(Factor("Critical-stage water", "positive", f"Water status {water.status} during sensitive stage {stage.current_stage}."))
    if ndvi.available:
        if ndvi.stress_signal:
            score -= 10
            ex.add(Factor("Vegetation signal", "risk", "NDVI/NDWI stress signal present."))
        elif ndvi.trend == "improving":
            score += 10
            ex.add(Factor("Vegetation signal", "positive", "Canopy developing (NDVI rising)."))
    score = max(0.0, min(100.0, score))
    ex.summary = f"Crop condition {score:.0f}/100."
    ex.demo_data_used = ndvi.is_demo
    return ScoreBreakdown("Crop Condition", score, WEIGHTS["Crop Condition"], _label(score), ex, True)


def _risk_component(risks: List[Risk]) -> ScoreBreakdown:
    ex = Explanation(summary="", method=Method.RULE_BASED, data_considered=["detected risks and severities"])
    if not risks:
        ex.summary = "No active risk detected."
        return ScoreBreakdown("Risk", 95.0, WEIGHTS["Risk"], "Low risk", ex, True)
    penalty = {"low": 5, "moderate": 10, "high": 20, "critical": 35}
    ordered = sorted(risks, key=lambda r: -r.severity.rank)
    # most severe risk counts fully; additional risks add 30 % of their penalty
    score = 100.0 - penalty[ordered[0].severity.value] - 0.3 * sum(penalty[r.severity.value] for r in ordered[1:])
    for r in ordered:
        ex.add(Factor(r.title, "risk", r.reason, value=r.severity.value))
    score = max(0.0, score)
    ex.summary = f"{len(risks)} active risk(s); highest severity {max(r.severity.rank for r in risks)}/4."
    return ScoreBreakdown("Risk", score, WEIGHTS["Risk"], _label(score), ex, True)


def compute_farm_health(ndvi: NDVIAnalysis, soil: SoilAnalysis, water: WaterAnalysis, weather: WeatherAnalysis,
                        stage: StageAnalysis, risks: List[Risk]) -> FarmHealth:
    parts: List[ScoreBreakdown] = [
        ScoreBreakdown("Vegetation Health", ndvi.score, WEIGHTS["Vegetation Health"], _label(ndvi.score), ndvi.explanation, ndvi.available),
        ScoreBreakdown("Soil Health", soil.score, WEIGHTS["Soil Health"], _label(soil.score), soil.explanation, soil.available and soil.score is not None),
        ScoreBreakdown("Water Status", water.score, WEIGHTS["Water Status"], _label(water.score), water.explanation, water.available and water.score is not None),
        ScoreBreakdown("Weather Condition", weather.score, WEIGHTS["Weather Condition"], _label(weather.score), weather.explanation, weather.available),
        _crop_condition(ndvi, stage, water),
        _risk_component(risks),
    ]
    assessed = [p for p in parts if p.available and p.score is not None]
    wsum = sum(p.weight for p in assessed)
    score = round(sum(p.score * p.weight for p in assessed) / wsum, 0) if wsum else None
    demo = any(p.explanation.demo_data_used for p in parts)
    confidence = round(wsum * (0.8 if demo else 1.0), 2)

    ex = Explanation(summary="", method=Method.RULE_BASED, demo_data_used=demo,
                     data_considered=[p.name for p in assessed])
    for p in sorted(assessed, key=lambda p: p.score):
        eff = "limiting" if p.score < 60 else ("positive" if p.score >= 75 else "neutral")
        ex.add(Factor(p.name, eff, f"{p.name} {p.score:.0f}/100 ({p.label}) × weight {p.weight:.2f}.", value=p.score, weight=p.weight))
    for p in parts:
        if p not in assessed:
            ex.add(Factor(p.name, "missing", f"{p.name} not assessed — excluded from the score."))
    drivers = sorted(assessed, key=lambda p: p.score)
    lowest = drivers[0].name if drivers else "—"
    highest = drivers[-1].name if drivers else "—"
    ex.summary = (f"Farm health {score:.0f}/100 ({_label(score)}). Strongest: {highest}; weakest: {lowest}. "
                  f"{len(assessed)}/{len(parts)} components assessed" + (" — includes DEMO data." if demo else "."))
    if score is None:
        ex.summary = "Farm health not assessable — no component data."
    return FarmHealth(score, _label(score), parts, confidence, round(wsum, 2), demo, ex)
