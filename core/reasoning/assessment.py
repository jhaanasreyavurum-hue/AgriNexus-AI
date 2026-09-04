"""Full farm assessment — the one call that runs the whole chain.

    FarmContext → stage → NDVI → soil → weather → water → risks → health → NBA
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.analytics.crop_stage import StageAnalysis, analyse_stage
from core.analytics.farm_health import FarmHealth, compute_farm_health
from core.analytics.ndvi import NDVIAnalysis, analyse_ndvi
from core.analytics.risk import detect_risks
from core.analytics.soil import SoilAnalysis, analyse_soil
from core.analytics.water_balance import WaterAnalysis, analyse_water
from core.analytics.weather import WeatherAnalysis, analyse_weather
from core.models.farm_context import FarmContext
from core.models.results import Recommendation, Risk
from core.reasoning.next_best_action import generate_next_best_actions

# indicative crop heat-stress thresholds (°C max) — reference values, not KB
CROP_TMAX = {"Cotton": 40, "Paddy (Rice)": 38, "Wheat": 32, "Maize": 36, "Soybean": 35, "Groundnut": 36,
             "Chickpea (Gram)": 32, "Pigeon Pea (Tur/Arhar)": 36, "Red Chilli": 36, "Sugarcane": 40, "Turmeric": 36, "Onion": 35}


@dataclass
class FarmAssessment:
    ctx: FarmContext
    stage: StageAnalysis
    ndvi: NDVIAnalysis
    soil: SoilAnalysis
    weather: WeatherAnalysis
    water: WaterAnalysis
    risks: List[Risk]
    health: FarmHealth
    actions: List[Recommendation]
    kb_coverage: str = "limited"
    crop_master_name: Optional[str] = None
    crop_row: Dict[str, Any] = field(default_factory=dict)
    knowledge: Any = None            # KnowledgeResults once run_full_assessment() is used

    @property
    def next_best_action(self) -> Recommendation:
        return self.actions[0]

    def headline(self) -> Dict[str, Any]:
        """Compact dict for the Home page / Copilot / reports."""
        return {
            "farm": self.ctx.farm_name, "is_demo": self.ctx.is_demo, "as_of": self.ctx.today().isoformat(),
            "health_score": self.health.score, "health_label": self.health.label, "confidence": self.health.confidence,
            "next_best_action": self.next_best_action.action, "nba_why": self.next_best_action.explanation.summary,
            "top_risk": self.risks[0].title if self.risks else None,
            "ndvi": self.ndvi.current, "ndvi_change_pct": self.ndvi.change_pct, "ndvi_trend": self.ndvi.trend,
            "water_status": self.water.status, "stage": self.stage.current_stage,
            "kb_coverage": self.kb_coverage,
            "top_opportunity": (self.knowledge.opportunities[0].title if self.knowledge and self.knowledge.opportunities else None),
        }


def assess_farm(ctx: FarmContext, kb) -> FarmAssessment:
    row = kb.crop_row(ctx.crop.current_crop) if ctx.crop.current_crop else None
    master = row.crop_name if row is not None else None

    stage = analyse_stage(ctx, kb)
    ndvi = analyse_ndvi(ctx, stage.current_stage)
    soil = analyse_soil(ctx, kb)
    weather = analyse_weather(ctx, CROP_TMAX.get(master or "", None))
    water = analyse_water(ctx, stage.current_kc, stage.current_stage, soil.soil_canonical, ndvi.stress_signal,
                          {"heavy_rain_expected": weather.heavy_rain_expected, "dry_spell": weather.dry_spell, "heat_stress": weather.heat_stress})
    risks = detect_risks(ctx, ndvi, soil, water, weather, stage, kb)
    health = compute_farm_health(ndvi, soil, water, weather, stage, risks)
    actions = generate_next_best_actions(ctx, ndvi, soil, water, weather, stage, risks)

    return FarmAssessment(ctx, stage, ndvi, soil, weather, water, risks, health, actions,
                          kb_coverage=kb.coverage_level(ctx.location.state), crop_master_name=master,
                          crop_row={k: (None if str(v) == "nan" else v) for k, v in row.to_dict().items()} if row is not None else {})


def run_full_assessment(ctx: FarmContext, kb, target_season: Optional[str] = None) -> FarmAssessment:
    """Analytics + knowledge engines + finance-aware Next Best Action list."""
    from core.engines.knowledge_results import run_knowledge_engines
    from core.reasoning.next_best_action import append_knowledge_actions

    a = assess_farm(ctx, kb)
    a.knowledge = run_knowledge_engines(ctx, kb, a, target_season=target_season)
    a.actions = append_knowledge_actions(a.actions, a.knowledge, a)
    return a
