"""Crop Advisor (§9) — ranked crop suitability from crop_master + farm conditions.

Score (0–100) = weighted sum of factor scores, each explained:

  factor            weight   source
  soil suitability   0.28    crop_master.soil_type × farm soil (similarity matrix)
  rainfall           0.22    crop min/max annual rainfall vs district normal (+ irrigation buffer)
  water requirement  0.15    crop water need vs irrigation availability / reliability
  season             0.15    crop season(s) vs target season
  rotation           0.08    previous crop category (legume→cereal bonus, same-crop penalty)
  objective          0.07    market category vs farmer objective (config table)
  regional fit       0.05    district major crop / KB zone hints

Rule-based (the KB does not supply yield or price models — none are invented).
"""
from __future__ import annotations

from typing import List, Optional

from core.engines.facts import FarmerFacts
from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, MatchResult, Method, score_label

W = {"soil": 0.26, "rain": 0.20, "water": 0.16, "season": 0.14, "rotation": 0.08, "objective": 0.10, "region": 0.06}
WATER_NEED = {"Low": 1, "Medium": 2, "High": 3}


def _rain_score(rmin: float, rmax: float, normal: Optional[float], irrigated: bool, reliability: Optional[str]):
    if normal is None:
        return None, "District annual rainfall not available."
    if rmin <= normal <= rmax:
        return 100.0, f"Annual rainfall {normal:.0f} mm is within the crop's {rmin:.0f}–{rmax:.0f} mm range."
    if normal < rmin:
        gap = rmin - normal
        if irrigated:
            buff = {"assured": 0.9, "partial": 0.6}.get(reliability or "", 0.4)
            sc = max(20.0, 100.0 - gap / rmin * 100 * (1 - buff))
            return sc, f"Rainfall {normal:.0f} mm is {gap:.0f} mm below the crop minimum ({rmin:.0f}); irrigation ({reliability or 'available'}) partly compensates."
        sc = max(0.0, 100.0 - gap / rmin * 160)
        return sc, f"Rainfall {normal:.0f} mm is {gap:.0f} mm below the crop minimum ({rmin:.0f}) and the farm is rainfed."
    gap = normal - rmax
    sc = max(10.0, 100.0 - gap / rmax * 120)
    return sc, f"Rainfall {normal:.0f} mm exceeds the crop maximum ({rmax:.0f}) by {gap:.0f} mm — drainage / disease pressure."


def _water_score(need: str, irrigated: bool, reliability: Optional[str]):
    n = WATER_NEED.get(need, 2)
    if irrigated:
        rel = {"assured": 1.0, "partial": 0.75, "unreliable": 0.5}.get(reliability or "", 0.75)
        sc = 100.0 if n == 1 else (55 + 45 * rel if n == 2 else 20 + 70 * rel)
        return sc, f"{need} water requirement; irrigation available ({reliability or 'unspecified'} reliability)."
    sc = {1: 95.0, 2: 55.0, 3: 20.0}[n]
    return sc, f"{need} water requirement on a rainfed farm."


def _season_score(seasons: List[str], target: Optional[str]):
    if not target:
        return None, "Target season not specified."
    if target in seasons:
        return (100.0, f"Grown in {target} (primary season).") if seasons[0] == target else (85.0, f"Grown in {target} (alternate season).")
    if "Year-round (Perennial)" in seasons:
        return 55.0, "Perennial crop — can be planted around the target season but ties the plot up for years."
    return 15.0, f"Not a {target} crop (KB season: {', '.join(seasons)})."


def _rotation_score(prev_cat: Optional[str], prev_name: Optional[str], cat: str, name: str):
    if not prev_name:
        return None, "Previous crop not specified."
    if prev_name == name:
        return 25.0, f"Same crop as last season ({prev_name}) — pest/disease build-up and nutrient mining."
    if prev_cat == "Pulse" and cat in ("Cereal", "Cash Crop / Fibre", "Vegetable", "Oilseed"):
        return 100.0, f"Follows a legume ({prev_name}) — residual nitrogen benefit."
    if prev_cat == cat:
        return 55.0, f"Same category as previous crop ({prev_cat}) — limited rotation benefit."
    return 85.0, f"Good rotation after {prev_name} ({prev_cat})."


def recommend_crops(ctx: FarmContext, kb, facts: FarmerFacts, target_season: Optional[str] = None,
                    top_n: int = 10, include_current: bool = True) -> List[MatchResult]:
    v = kb.vocab
    crops = kb.crops[~kb.crops["excluded"]]
    farm_soil = ctx.soil.soil_type
    normal = ctx.weather.annual_rainfall_normal_mm
    irrigated, rel = ctx.irrigation.available, ctx.irrigation.reliability
    season = target_season or ctx.crop.season
    prev_row = kb.crop_row(ctx.crop.previous_crop) if ctx.crop.previous_crop else None
    prev_cat, prev_name = (prev_row.market_category, prev_row.crop_name) if prev_row is not None else (None, None)
    geo = kb.district_row(ctx.location.state, ctx.location.district)
    major = geo.major_crop if geo is not None else None
    major_master = v.resolve_crop_name(major) if major else None
    bonus_tbl = v.objective_category_bonus.get(facts.objective, {})
    demo = ctx.soil.provenance.is_demo or ctx.weather.provenance.is_demo

    out: List[MatchResult] = []
    for _, c in crops.iterrows():
        if c.market_category == "Fodder" and not facts.livestock:
            continue
        ex = Explanation(summary="", method=Method.RULE_BASED, demo_data_used=demo,
                         sources=["Knowledge base · crop_master", ctx.soil.provenance.label(), ctx.weather.provenance.label()],
                         kb_references=[c.crop_id],
                         data_considered=["soil type", "district annual rainfall", "irrigation availability", "season", "previous crop", "farm objective", "district major crop"])
        parts = {}

        # soil
        sim = v.soil_match_score(c.soil_type, farm_soil)
        if sim is None:
            parts["soil"] = None
            ex.add(Factor("Soil", "missing", "Farm soil type not available."))
        else:
            parts["soil"] = sim * 100
            ex.add(Factor("Soil suitable" if sim >= 0.8 else ("Soil moderately suitable" if sim >= 0.5 else "Soil poorly suited"),
                          "positive" if sim >= 0.8 else ("neutral" if sim >= 0.5 else "limiting"),
                          f"Farm soil {farm_soil}; crop prefers {c.soil_type} (similarity {sim:.2f}).", value=sim, weight=W["soil"]))
        # rainfall
        sc, msg = _rain_score(float(c.minimum_rainfall), float(c.maximum_rainfall), normal, irrigated, rel)
        parts["rain"] = sc
        ex.add(Factor("Rainfall suitable" if (sc or 0) >= 75 else ("Rainfall marginal" if (sc or 0) >= 45 else "Rainfall unsuitable"),
                      "missing" if sc is None else ("positive" if sc >= 75 else ("neutral" if sc >= 45 else "limiting")), msg, value=sc, weight=W["rain"]))
        # water
        sc, msg = _water_score(c.water_requirement, irrigated, rel)
        parts["water"] = sc
        ex.add(Factor("Water requirement met" if sc >= 75 else ("Water requirement marginal" if sc >= 45 else "Water requirement not met"),
                      "positive" if sc >= 75 else ("neutral" if sc >= 45 else "limiting"), msg, value=sc, weight=W["water"]))
        # season
        sc, msg = _season_score(list(c.seasons_all), season)
        parts["season"] = sc
        ex.add(Factor("Season suitable" if (sc or 0) >= 70 else "Season mismatch",
                      "missing" if sc is None else ("positive" if sc >= 70 else "limiting"), msg, value=sc, weight=W["season"]))
        # rotation
        sc, msg = _rotation_score(prev_cat, prev_name, c.market_category, c.crop_name)
        parts["rotation"] = sc
        ex.add(Factor("Rotation", "missing" if sc is None else ("positive" if sc >= 80 else ("neutral" if sc >= 50 else "limiting")), msg, value=sc, weight=W["rotation"]))
        # objective
        b = bonus_tbl.get(c.market_category, 0)
        parts["objective"] = 40 + b * 10
        ex.add(Factor("Objective fit", "positive" if b >= 4 else "neutral",
                      f"{c.market_category} crop vs objective '{facts.objective}'.", value=b, weight=W["objective"]))
        # region
        if major_master and c.crop_name == major_master:
            parts["region"] = 100.0
            ex.add(Factor("Regional fit", "positive", f"{c.crop_name} is the KB-listed major crop of {geo.district_name}.", weight=W["region"], source="Knowledge base · state_district_master"))
        elif geo is not None and major_master:
            parts["region"] = 50.0
            ex.add(Factor("Regional fit", "neutral", f"Not the district's KB-listed major crop ({major_master}); check local market access.", weight=W["region"], source="Knowledge base · state_district_master"))
        else:
            parts["region"] = None

        avail = {k: s for k, s in parts.items() if s is not None}
        wsum = sum(W[k] for k in avail)
        score = round(sum(W[k] * s for k, s in avail.items()) / wsum, 0) if wsum else 0.0
        if c.crop_name == facts.crop_master:
            ex.add(Factor("Current crop", "neutral", "This is the crop currently in the field."))
        pos = [f.name for f in ex.positive]
        lim = [f.name for f in ex.limiting]
        ex.summary = f"Suitability {score:.0f}%: " + (", ".join(pos[:3]) if pos else "no strong positives") + (f"; limiting: {', '.join(lim[:2])}" if lim else "") + "."
        out.append(MatchResult(
            c.crop_id, c.crop_name, "crop", float(score), score_label(score, 75, 55), ex,
            payload={"season": c.season, "seasons_all": list(c.seasons_all), "soil_type": c.soil_type,
                     "rainfall_range_mm": [int(c.minimum_rainfall), int(c.maximum_rainfall)], "water_requirement": c.water_requirement,
                     "market_category": c.market_category, "insurance_available": bool(c.insurance_available_bool),
                     "recommended_schemes": list(c.recommended_schemes_list), "recommended_loans": list(c.recommended_loans_list),
                     "is_current_crop": c.crop_name == facts.crop_master, "factor_scores": parts,
                     "kb_overrides": [o.column for o in kb.overrides_for("crops", c.crop_id)]},
        ))
    out.sort(key=lambda m: -m.score)
    if not include_current:
        out = [m for m in out if not m.payload["is_current_crop"]]
    return out[:top_n]
