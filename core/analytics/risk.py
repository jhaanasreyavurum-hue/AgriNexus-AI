"""Farm Risk Center (§15) — rule-based detection of seven risk classes.

Each risk carries severity, score, reason, action and an Explanation, plus
keywords that the insurance matcher uses to link risks to KB covers.
"""
from __future__ import annotations

from typing import List, Optional

from core.analytics.crop_stage import StageAnalysis
from core.analytics.ndvi import NDVIAnalysis
from core.analytics.soil import SoilAnalysis
from core.analytics.water_balance import WaterAnalysis
from core.analytics.weather import WeatherAnalysis
from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method, Risk, Severity


def _sev(score: float) -> Severity:
    if score >= 80:
        return Severity.CRITICAL
    if score >= 60:
        return Severity.HIGH
    if score >= 35:
        return Severity.MODERATE
    return Severity.LOW


def detect_risks(ctx: FarmContext, ndvi: NDVIAnalysis, soil: SoilAnalysis, water: WaterAnalysis,
                 weather: WeatherAnalysis, stage: StageAnalysis, kb=None) -> List[Risk]:
    risks: List[Risk] = []
    kw = kb.vocab.risk_to_cover_keywords if kb is not None else {}
    rainfed = not ctx.irrigation.available

    # ---- water stress ----------------------------------------------------------
    if water.available and water.status in ("deficit", "approaching_deficit"):
        score = 75 if water.status == "deficit" else 45
        if stage.critical_water_window:
            score += 15
        if ndvi.stress_signal:
            score += 10
        if rainfed:
            score += 5
        ex = Explanation(summary=water.explanation.summary, method=Method.RULE_BASED, sources=water.explanation.sources,
                         data_considered=water.explanation.data_considered, demo_data_used=water.explanation.demo_data_used)
        ex.risks = list(water.explanation.risks) + list(water.explanation.limiting)
        if stage.critical_water_window:
            ex.add(Factor("Growth stage", "risk", f"{stage.current_stage} is water-critical — yield penalty for deficit is high."))
        mm = water.net_mm_recommended or 25
        if rainfed:
            action = "Rainfed: apply mulch, avoid top-dressing N until rain; check weather-index insurance cover."
        elif water.status == "deficit":
            action = f"Irrigate within 24 hours (≈{mm:.0f} mm net) — crop is past allowable depletion."
        else:
            action = f"Plan irrigation within 24–48 hours (≈{mm:.0f} mm net); re-check forecast tomorrow."
        risks.append(Risk("water_stress", "Water Stress Risk", _sev(min(100, score)), float(min(100, score)),
                          water.explanation.summary, action, ex, kw.get("water_stress", [])))

    # ---- drought (multi-week dryness) ---------------------------------------------
    if weather.available and weather.dry_spell and (weather.rain_last_7d_mm or 0) < 10:
        score = 50 + (15 if rainfed else 0) + (10 if ndvi.stress_signal else 0) + (10 if (weather.rain_next_7d_mm or 0) < 5 else 0)
        ex = Explanation(summary="Two consecutive dry weeks (past + forecast) with high evaporative demand.", method=Method.WEATHER,
                         sources=[weather.provider_label], data_considered=["7-day rain history", "7-day forecast", "ET0"])
        ex.add(Factor("Past 7 days", "risk", f"{weather.rain_last_7d_mm or 0:.0f} mm rain.", value=weather.rain_last_7d_mm))
        ex.add(Factor("Next 7 days", "risk", f"{weather.rain_next_7d_mm or 0:.0f} mm forecast vs ET0 {weather.et0_next_7d_mm or 0:.0f} mm.", value=weather.rain_next_7d_mm))
        risks.append(Risk("drought", "Drought / Dry-Spell Risk", _sev(score), float(score), ex.summary,
                          "Prioritise irrigation to critical stages; if rainfed, consider contingency (mulching, life-saving irrigation, insurance claim readiness).",
                          ex, kw.get("drought", [])))

    # ---- excess rainfall / waterlogging -----------------------------------------------
    if weather.available and weather.heavy_rain_expected:
        r = max(weather.rain_next_24h_mm or 0, (weather.rain_next_7d_mm or 0) / 3)
        score = 40 + min(40, r) + (15 if soil.soil_canonical in ("black", "clay") else 0)
        ex = Explanation(summary=f"Forecast rainfall {weather.rain_next_24h_mm or 0:.0f} mm / 24 h, {weather.rain_next_7d_mm or 0:.0f} mm / 7 d.",
                         method=Method.WEATHER, sources=[weather.provider_label], data_considered=["rain forecast", "soil drainage class"])
        ex.add(Factor("Forecast rain", "risk", ex.summary))
        if soil.soil_canonical in ("black", "clay"):
            ex.add(Factor("Soil drainage", "risk", f"{soil.soil_type} drains poorly — waterlogging likely."))
        risks.append(Risk("excess_rainfall", "Excess Rainfall Risk", _sev(score), float(min(100, score)), ex.summary,
                          "Avoid irrigation; clear drainage channels; postpone fertiliser and spraying; monitor for waterlogging and fungal disease.",
                          ex, kw.get("excess_rainfall", [])))

    # ---- heat stress -----------------------------------------------------------------
    if weather.available and weather.heat_stress:
        score = 45 + (20 if stage.available and stage.current_stage and "Flower" in stage.current_stage else 0) + (10 if water.status == "deficit" else 0)
        ex = Explanation(summary=f"Max temperature {weather.temp_max_c:.0f} °C.", method=Method.WEATHER, sources=[weather.provider_label],
                         data_considered=["max temperature", "growth stage"])
        ex.add(Factor("Temperature", "risk", ex.summary, value=weather.temp_max_c))
        if stage.available and stage.current_stage and "Flower" in stage.current_stage:
            ex.add(Factor("Stage", "risk", "Heat during flowering reduces pollination / fruit set."))
        risks.append(Risk("heat_stress", "Heat Stress Risk", _sev(score), float(score), ex.summary,
                          "Irrigate early morning/evening to cool the canopy; avoid midday operations; ensure adequate K nutrition.",
                          ex, kw.get("heat_stress", [])))

    # ---- crop stress (vegetation) --------------------------------------------------------
    if ndvi.available and ndvi.stress_signal:
        score = 40 + min(30, abs(ndvi.change_pct or 0) * 2)
        explained_by_water = water.status in ("deficit", "approaching_deficit")
        ex = Explanation(summary=ndvi.explanation.summary, method=Method.REMOTE_SENSING, sources=ndvi.explanation.sources,
                         demo_data_used=ndvi.is_demo, data_considered=ndvi.explanation.data_considered)
        ex.risks = list(ndvi.explanation.risks)
        cause = "consistent with water deficit" if explained_by_water else "not explained by water balance — check pests, disease or nutrient deficiency"
        ex.add(Factor("Likely cause", "risk", f"NDVI decline is {cause}."))
        risks.append(Risk("crop_stress", "Crop Stress Signal (NDVI)", _sev(score), float(score),
                          f"NDVI {ndvi.change_pct:+.1f}% since last pass; {cause}.",
                          ("Address water deficit first, then re-check NDVI after 7–10 days." if explained_by_water
                           else "Field-scout within 48 h for pests/disease; check leaf colour for N/K deficiency."),
                          ex, kw.get("crop_stress", [])))

    # ---- soil limitations --------------------------------------------------------------------
    if soil.available and soil.limitations:
        score = min(55, 20 + 10 * len(soil.limitations))   # chronic constraint — capped at moderate
        ex = Explanation(summary=soil.explanation.summary, method=Method.RULE_BASED, sources=soil.explanation.sources,
                         demo_data_used=soil.is_demo, data_considered=soil.explanation.data_considered)
        ex.limiting = list(soil.explanation.limiting)
        risks.append(Risk("soil_limitation", "Soil Limitation", _sev(score), float(min(100, score)),
                          "; ".join(soil.limitations[:2]), soil.limitations[0], ex, []))

    # ---- financial exposure --------------------------------------------------------------------
    f, farmer = ctx.finance, ctx.farmer
    fin_factors: List[Factor] = []
    score = 0
    if not farmer.has_crop_insurance:
        score += 30
        fin_factors.append(Factor("Insurance", "risk", "Crop is not insured — weather losses fall entirely on the farmer."))
    if f.input_cost_estimate_inr and farmer.annual_income_inr and f.input_cost_estimate_inr > 0.5 * farmer.annual_income_inr:
        score += 20
        fin_factors.append(Factor("Input exposure", "risk", f"Input cost ₹{f.input_cost_estimate_inr:,.0f} is >50% of annual income."))
    if farmer.existing_loans_inr and farmer.annual_income_inr and farmer.existing_loans_inr > 0.4 * farmer.annual_income_inr:
        score += 15
        fin_factors.append(Factor("Debt", "risk", f"Existing loans ₹{farmer.existing_loans_inr:,.0f} vs income ₹{farmer.annual_income_inr:,.0f}."))
    if any(r.risk_type in ("drought", "water_stress", "excess_rainfall") and r.severity.rank >= 3 for r in risks) and not farmer.has_crop_insurance:
        score += 15
        fin_factors.append(Factor("Uninsured active hazard", "risk", "A high-severity weather risk is active while the crop is uninsured."))
    if score >= 30:
        ex = Explanation(summary="Financial exposure from uninsured production risk.", method=Method.RULE_BASED,
                         sources=[f.provenance.label()], demo_data_used=f.provenance.is_demo,
                         data_considered=["insurance status", "input cost vs income", "existing loans"])
        ex.risks = fin_factors
        risks.append(Risk("financial", "Financial Exposure", _sev(score), float(min(100, score)), ex.summary,
                          "Review crop-insurance options (see Finance & Schemes) and KCC for lower-cost working capital.", ex, []))

    return sorted(risks, key=lambda r: (-r.severity.rank, -r.score))
