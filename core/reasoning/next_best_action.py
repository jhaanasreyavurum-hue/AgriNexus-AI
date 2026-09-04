"""NEXT BEST ACTION (§3) — rule-based decision from the analytics results.

Priority order (agronomic urgency):
  1. Irrigation decision (always produced — irrigate / hold / monitor)
  2. Active weather hazard response (heavy rain, heat)
  3. Crop-stress investigation (NDVI not explained by water)
  4. Stage-linked agronomy (nutrients at critical stages, harvest prep)
  5. Soil amendment (season-level)
  6. Financial protection (insurance / credit) when uninsured & exposed
The first item in the returned list is THE Next Best Action.
"""
from __future__ import annotations

from typing import List

from core.analytics.crop_stage import StageAnalysis
from core.analytics.ndvi import NDVIAnalysis
from core.analytics.soil import SoilAnalysis
from core.analytics.water_balance import WaterAnalysis
from core.analytics.weather import WeatherAnalysis
from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method, Recommendation, Risk


def _merge(*exps: Explanation, summary: str, considered: List[str]) -> Explanation:
    out = Explanation(summary=summary, method=Method.RULE_BASED, data_considered=considered)
    for e in exps:
        if e is None:
            continue
        out.positive += e.positive
        out.limiting += e.limiting
        out.risks += e.risks
        out.missing += e.missing
        out.neutral += e.neutral
        out.sources += [s for s in e.sources if s not in out.sources]
        out.demo_data_used |= e.demo_data_used
    return out


def generate_next_best_actions(ctx: FarmContext, ndvi: NDVIAnalysis, soil: SoilAnalysis, water: WaterAnalysis,
                               weather: WeatherAnalysis, stage: StageAnalysis, risks: List[Risk]) -> List[Recommendation]:
    recs: List[Recommendation] = []
    rainfed = not ctx.irrigation.available
    stage_txt = f" during {stage.current_stage}" if stage.available and stage.current_stage else ""
    considered = ["water balance", "24–48 h rain forecast", "NDVI/NDWI trend", "growth stage", "irrigation availability"]

    # ---------------------------------------------------------------- 1. irrigation
    adv = water.irrigation_advice
    r24 = weather.rain_next_24h_mm if weather.available else None
    if adv == "irrigate_now":
        if rainfed:
            action, why = ("Rainfed field in water deficit — apply mulch / life-saving measures; irrigation not available.",
                           f"Root-zone deficit exceeds readily-available water{stage_txt}, and no irrigation source is recorded.")
        else:
            mm = water.net_mm_recommended or 25
            action, why = (f"Irrigate within the next 24 hours (≈{mm:.0f} mm net).",
                           f"Root-zone deficit ({water.deficit_mm:.0f} mm) exceeds readily-available water ({water.raw_mm:.0f} mm){stage_txt}"
                           + (f"; only {r24:.0f} mm rain expected in 24 h." if r24 is not None else "."))
        conf = 0.85 if water.mode == "quantitative" else 0.6
    elif adv == "irrigate_24h":
        if rainfed:
            action, why = ("Rainfed: moisture approaching deficit — mulch, avoid nitrogen top-dressing, watch forecast.",
                           "Deficit is building and no irrigation source is available.")
        else:
            action, why = ("Plan irrigation within 24–48 hours; re-check forecast tomorrow morning.",
                           f"Deficit is {(water.stress_ratio or 0)*100:.0f}% of readily-available water{stage_txt}; allowable depletion will be reached within ~1–2 days."
                           + (f" Forecast rain ({r24:.0f} mm) is insufficient to close the gap." if r24 is not None else ""))
        conf = 0.75 if water.mode == "quantitative" else 0.55
    elif adv == "hold_rain":
        action, why = ("Do not irrigate today. Reassess after the rainfall.",
                       f"Rainfall is expected ({r24 if r24 is not None else '—'} mm / 24 h; {weather.rain_next_7d_mm if weather.available else '—'} mm / 7 d) and current moisture is adequate for the interval.")
        conf = 0.8
    elif adv == "hold_adequate":
        action, why = ("No irrigation needed today — soil moisture is adequate. Re-evaluate in 2–3 days.",
                       f"Deficit is only {(water.stress_ratio or 0)*100:.0f}% of readily-available water{stage_txt}.")
        conf = 0.8 if water.mode == "quantitative" else 0.55
    else:
        action, why = ("Monitor soil moisture — insufficient data for a quantitative irrigation decision.",
                       "ET0/rain history or growth stage unavailable; no stress signal detected.")
        conf = 0.4
    ex = _merge(water.explanation, summary=why, considered=considered)
    ex.method = Method.RULE_BASED
    recs.append(Recommendation(action, 1, "24h" if "24" in action or "today" in action.lower() else "this_week", "irrigation", ex, conf))

    # ---------------------------------------------------------------- 2. weather hazards
    for r in risks:
        if r.risk_type == "excess_rainfall" and r.severity.rank >= 2:
            recs.append(Recommendation(r.action, 2, "24h", "protection",
                                       _merge(r.explanation, summary=r.reason, considered=["rain forecast", "soil drainage"]), 0.75, Method.WEATHER))
        if r.risk_type == "heat_stress" and r.severity.rank >= 2:
            recs.append(Recommendation(r.action, 2, "24h", "protection",
                                       _merge(r.explanation, summary=r.reason, considered=["temperature", "growth stage"]), 0.7, Method.WEATHER))

    # ---------------------------------------------------------------- 3. crop stress
    for r in risks:
        if r.risk_type == "crop_stress":
            recs.append(Recommendation(r.action, 3, "48h", "monitoring",
                                       _merge(r.explanation, summary=r.reason, considered=["NDVI trend", "NDWI", "water status"]), 0.6, Method.REMOTE_SENSING))

    # ---------------------------------------------------------------- 4. stage agronomy
    if stage.available and stage.current_stage:
        s = stage.current_stage
        if any(k in s for k in ("Flower", "Square", "Tassel", "Panicle", "Heading")):
            ex = Explanation(summary=f"{s} is the peak nutrient- and water-demand window.", method=Method.RULE_BASED,
                             data_considered=["growth stage", "soil N/K"], sources=["Reference · FAO-56 / ICAR"])
            ex.add(Factor("Stage", "neutral", f"Crop at {s} ({stage.days_after_sowing} DAS)."))
            if soil.available:
                low = [p.label for p in soil.params if p.rating == "low" and p.key in ("nitrogen_kg_ha", "potassium_kg_ha")]
                if low:
                    ex.add(Factor("Soil test", "limiting", f"Low {' and '.join(low)} on the soil card — top-dress if not already done."))
            recs.append(Recommendation(f"Complete top-dressing (N/K) and scout for sucking pests — crop is at {s}.", 4, "this_week", "nutrient", ex, 0.6))
        elif any(k in s for k in ("Maturity", "Harvest", "Picking", "Ripening")):
            ex = Explanation(summary=f"Crop at {s}; expected harvest ≈ {stage.expected_harvest}.", method=Method.RULE_BASED,
                             data_considered=["growth stage", "expected harvest date"])
            recs.append(Recommendation("Stop irrigation 7–10 days before harvest; arrange labour, storage and market (e-NAM) — crop is maturing.", 4, "this_week", "crop_plan", ex, 0.65))

    # ---------------------------------------------------------------- 5. soil
    if soil.available and soil.limitations:
        ex = _merge(soil.explanation, summary=soil.limitations[0], considered=["Soil Health Card values"])
        recs.append(Recommendation(f"Soil: {soil.limitations[0]}", 5, "before_next_season", "nutrient", ex, 0.7))

    # ---------------------------------------------------------------- 6. finance
    for r in risks:
        if r.risk_type == "financial":
            recs.append(Recommendation(r.action, 6, "this_season", "insurance",
                                       _merge(r.explanation, summary=r.reason, considered=["insurance status", "income", "loans"]), 0.7))

    recs.sort(key=lambda r: r.priority)
    return recs


def append_knowledge_actions(actions: List[Recommendation], kr, assessment) -> List[Recommendation]:
    """Add finance / scheme / insurance actions derived from the knowledge engines.

    These never outrank agronomic urgency (priority 1–4) unless an insurance
    enrolment window coincides with an active high-severity weather risk, in
    which case the insurance action is promoted to priority 2.
    """
    if kr is None:
        return actions
    out = list(actions)
    facts = kr.facts
    high_weather = any(r.risk_type in ("drought", "water_stress", "excess_rainfall", "heat_stress") and r.severity.rank >= 3 for r in assessment.risks)

    # insurance
    crop_ins = [m for m in kr.insurance if not m.payload.get("is_livestock")]
    if not facts.has_insurance and crop_ins:
        m = crop_ins[0]
        p = m.payload
        ex = Explanation(summary=f"Crop is uninsured; {m.title} covers '{p['covered_risk']}' at ≈{p['farmer_premium_pct']}% farmer premium.",
                         method=Method.KNOWLEDGE_BASE, kb_references=[m.item_id], sources=m.explanation.sources,
                         positive=m.explanation.positive[:3], limiting=m.explanation.limiting[:2],
                         data_considered=["insurance status", "detected risks", "KB insurance products"])
        # replace the generic rule-based insurance action with the KB-specific one
        out = [r for r in out if not (r.category == "insurance" and r.method == Method.RULE_BASED)]
        out.append(Recommendation(f"Enrol in crop insurance — best fit: {m.title} ({p['provider']}).",
                                  2 if high_weather else 6, "this_season", "insurance", ex, 0.7, Method.KNOWLEDGE_BASE))
    elif not facts.has_insurance and getattr(kr, "insurance_gap_note", None):
        out = [r for r in out if not (r.category == "insurance" and r.method == Method.RULE_BASED)]
        ex = Explanation(summary=kr.insurance_gap_note, method=Method.KNOWLEDGE_BASE, sources=["Knowledge base · crop_insurance_products"],
                         data_considered=["insurance status", "KB insurance products", "district"])
        out.append(Recommendation("Crop is uninsured — ask your bank/CSC which PMFBY/RWBCIS covers are notified for your district this season.",
                                  2 if high_weather else 6, "this_season", "insurance", ex, 0.6, Method.KNOWLEDGE_BASE))
    # top scheme with high readiness
    ready = [m for m in kr.schemes if not m.hard_fail and m.score >= 60]
    if ready:
        m = max(ready, key=lambda x: x.score + 0.2 * x.payload.get("document_readiness_pct", 0))
        p = m.payload
        ex = Explanation(summary=m.explanation.summary, method=Method.KNOWLEDGE_BASE, kb_references=m.explanation.kb_references,
                         sources=m.explanation.sources, positive=m.explanation.positive[:4], limiting=m.explanation.limiting[:2],
                         data_considered=m.explanation.data_considered)
        miss = f" Arrange: {', '.join(m.documents_missing[:3])}." if m.documents_missing else " All key documents in hand."
        out.append(Recommendation(f"Apply for {m.title} ({m.score:.0f}% match, documents {p.get('document_readiness_pct', 0):.0f}% ready).{miss}",
                                  7, "this_season", "scheme", ex, 0.65, Method.KNOWLEDGE_BASE))
    # top situational subsidy
    if kr.subsidies and kr.subsidies[0].score >= 60 and kr.subsidies[0].payload.get("need_hits"):
        m = kr.subsidies[0]
        ex = Explanation(summary=m.explanation.summary, method=Method.KNOWLEDGE_BASE, kb_references=m.explanation.kb_references,
                         sources=m.explanation.sources, positive=m.explanation.positive[:3], data_considered=m.explanation.data_considered)
        out.append(Recommendation(f"Explore subsidy: {m.title} under {m.payload['scheme_name']} (up to ₹{(m.payload.get('maximum_amount') or 0):,.0f}).",
                                  8, "this_season", "finance", ex, 0.6, Method.KNOWLEDGE_BASE))
    # credit when input cost is high and no KCC
    if not facts.has_kcc and kr.loans.products and kr.loans.eligibility_rating in ("Good", "Moderate"):
        m = kr.loans.products[0]
        ex = Explanation(summary=kr.loans.explanation.summary, method=Method.RULE_BASED, kb_references=[m.item_id],
                         sources=kr.loans.explanation.sources, positive=kr.loans.explanation.positive[:3], limiting=kr.loans.explanation.limiting[:2])
        out.append(Recommendation(f"Consider {m.payload['loan_type']} from {m.payload['bank_short']} ({m.payload['interest_rate']}) — indicative eligibility ₹{kr.loans.estimated_eligibility_inr:,.0f}.",
                                  9, "this_season", "finance", ex, 0.55))
    out.sort(key=lambda r: r.priority)
    for i, r in enumerate(out, 1):          # re-number so the list reads 1..n
        r.priority = i
    return out
