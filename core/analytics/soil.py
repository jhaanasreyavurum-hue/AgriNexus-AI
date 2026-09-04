"""Soil intelligence (§7) — rule-based interpretation of available soil data.

Thresholds follow the Indian Soil Health Card rating classes (low / medium /
high for OC, N, P, K) and standard pH / EC classes. Only fields that are
present are scored; the score is normalised over available fields and the
explanation lists what was missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method

# (low_max, medium_max) per Soil Health Card norms
SHC = {
    "organic_carbon_pct": (0.50, 0.75),
    "nitrogen_kg_ha": (280, 560),
    "phosphorus_kg_ha": (10, 25),
    "potassium_kg_ha": (108, 280),
}


@dataclass
class SoilParam:
    key: str
    label: str
    value: Optional[float]
    unit: str
    rating: Optional[str]      # low | medium | high | acidic | neutral | alkaline | ...
    score: Optional[float]     # 0..100
    implication: str
    available: bool


@dataclass
class SoilAnalysis:
    available: bool
    score: Optional[float]
    soil_type: Optional[str]
    soil_canonical: Optional[str]
    params: List[SoilParam] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    crop_soil_fit: Optional[float] = None     # 0..1 vs current crop's preferred soil
    is_demo: bool = False
    explanation: Explanation = field(default_factory=lambda: Explanation(summary=""))


def _rate_shc(key: str, v: float):
    lo, mid = SHC[key]
    if v < lo:
        return "low", 35.0
    if v <= mid:
        return "medium", 70.0
    return "high", 95.0


def analyse_soil(ctx: FarmContext, kb=None) -> SoilAnalysis:
    s = ctx.soil
    v = kb.vocab if kb is not None else None
    canon = v.canonical_soil(s.soil_type) if v else None
    ex = Explanation(summary="", method=Method.RULE_BASED, sources=[s.provenance.label()],
                     demo_data_used=s.provenance.is_demo,
                     data_considered=["soil type", "pH", "organic carbon", "N-P-K", "EC (salinity)", "current crop soil preference"])
    params: List[SoilParam] = []
    limitations: List[str] = []

    # --- organic carbon / NPK (SHC classes) --------------------------------
    labels = {"organic_carbon_pct": ("Organic carbon", "%"), "nitrogen_kg_ha": ("Available N", "kg/ha"),
              "phosphorus_kg_ha": ("Available P", "kg/ha"), "potassium_kg_ha": ("Available K", "kg/ha")}
    implications = {
        "organic_carbon_pct": {"low": "Low organic carbon limits water-holding capacity, nutrient supply and microbial activity — add FYM/compost, green manure or crop residue.",
                               "medium": "Moderate organic carbon; maintain with residue retention and organic inputs.",
                               "high": "Good organic carbon supports structure and nutrient cycling."},
        "nitrogen_kg_ha": {"low": "Low available N — split nitrogen applications by stage; consider legume rotation.",
                           "medium": "Medium N; follow crop-specific recommended dose.",
                           "high": "High available N; avoid excess N to limit lodging and pest pressure."},
        "phosphorus_kg_ha": {"low": "Low P limits root development and early vigour — basal P application recommended.",
                             "medium": "Medium P; maintain with basal dose.", "high": "High P; reduce P dose this season."},
        "potassium_kg_ha": {"low": "Low K reduces drought tolerance and quality — apply muriate of potash.",
                            "medium": "Medium K; maintenance dose.", "high": "High K; K application can be reduced."},
    }
    for key, (lab, unit) in labels.items():
        val = getattr(s, key)
        if val is None:
            params.append(SoilParam(key, lab, None, unit, None, None, "Not available.", False))
            ex.add(Factor(lab, "missing", f"{lab} not available."))
            continue
        rating, score = _rate_shc(key, float(val))
        imp = implications[key][rating]
        params.append(SoilParam(key, lab, float(val), unit, rating, score, imp, True))
        eff = "limiting" if rating == "low" else "positive"
        ex.add(Factor(lab, eff, f"{lab} {val} {unit} → {rating}. {imp}", value=val))
        if rating == "low":
            limitations.append(imp)

    # --- pH ------------------------------------------------------------------
    if s.ph is not None:
        p = float(s.ph)
        if p < 5.5:
            rating, score, imp = "strongly acidic", 35.0, "Strongly acidic soil fixes P and can cause Al toxicity — liming advised."
        elif p < 6.5:
            rating, score, imp = "slightly acidic", 75.0, "Slightly acidic; suits most crops, monitor P availability."
        elif p <= 7.5:
            rating, score, imp = "neutral", 100.0, "Near-neutral pH — optimal nutrient availability."
        elif p <= 8.5:
            rating, score, imp = "moderately alkaline", 65.0, "Moderately alkaline; micronutrients (Zn, Fe) may be less available — consider zinc sulphate and organic matter."
        else:
            rating, score, imp = "strongly alkaline", 30.0, "Strongly alkaline/sodic — gypsum amendment and drainage improvement advised."
        params.append(SoilParam("ph", "pH", p, "", rating, score, imp, True))
        ex.add(Factor("pH", "positive" if score >= 75 else "limiting", f"pH {p} → {rating}. {imp}", value=p))
        if score < 70:
            limitations.append(imp)
    else:
        params.append(SoilParam("ph", "pH", None, "", None, None, "Not available.", False))
        ex.add(Factor("pH", "missing", "Soil pH not available."))

    # --- EC / salinity -------------------------------------------------------
    if s.ec_ds_m is not None:
        e = float(s.ec_ds_m)
        if e < 1.0:
            rating, score, imp = "normal", 100.0, "No salinity constraint."
        elif e < 2.0:
            rating, score, imp = "slightly saline", 70.0, "Slight salinity — sensitive crops may be affected; ensure leaching."
        elif e < 4.0:
            rating, score, imp = "moderately saline", 45.0, "Moderate salinity reduces yield of most crops; leaching and salt-tolerant varieties."
        else:
            rating, score, imp = "highly saline", 20.0, "High salinity — reclamation required."
        params.append(SoilParam("ec_ds_m", "EC (salinity)", e, "dS/m", rating, score, imp, True))
        ex.add(Factor("Salinity (EC)", "positive" if score >= 70 else "limiting", f"EC {e} dS/m → {rating}. {imp}", value=e))
        if score < 70:
            limitations.append(imp)
    else:
        params.append(SoilParam("ec_ds_m", "EC (salinity)", None, "dS/m", None, None, "Not available.", False))

    # --- soil type vs crop -----------------------------------------------------
    fit = None
    if kb is not None and ctx.crop.current_crop and s.soil_type:
        row = kb.crop_row(ctx.crop.current_crop)
        if row is not None:
            fit = v.soil_match_score(row.soil_type, s.soil_type)
            if fit is not None:
                if fit >= 0.8:
                    ex.add(Factor("Soil–crop fit", "positive", f"{s.soil_type} is well suited to {row.crop_name} (KB preferred: {row.soil_type}).", value=fit, source="Knowledge base · crop_master"))
                elif fit >= 0.5:
                    ex.add(Factor("Soil–crop fit", "neutral", f"{s.soil_type} is moderately suited to {row.crop_name} (KB preferred: {row.soil_type}).", value=fit, source="Knowledge base · crop_master"))
                else:
                    ex.add(Factor("Soil–crop fit", "limiting", f"{s.soil_type} is a weak match for {row.crop_name} (KB preferred: {row.soil_type}).", value=fit, source="Knowledge base · crop_master"))
                    limitations.append(f"Soil type is a weak match for {row.crop_name}.")
    if canon == "black":
        ex.add(Factor("Soil type", "neutral", "Black (regur) soil: high water-holding but poor drainage — waterlogging risk after heavy rain; cracks when dry."))
    elif canon in ("sandy", "red", "laterite"):
        ex.add(Factor("Soil type", "neutral", f"{v.soil_label(canon)}: low water-holding — irrigate little and often; nutrient leaching risk."))

    avail = [p for p in params if p.available]
    if not avail and not s.soil_type:
        ex.summary = "No soil data available."
        ex.add(Factor("Soil data", "missing", "Add Soil Health Card values or soil type to enable soil intelligence."))
        return SoilAnalysis(False, None, s.soil_type, canon, params, [], None, s.provenance.is_demo, ex)

    score = round(sum(p.score for p in avail) / len(avail), 0) if avail else None
    if score is not None and fit is not None:
        score = round(0.8 * score + 20 * fit, 0)
    if s.provenance.is_demo:
        ex.add(Factor("Data source", "limiting", "Soil values are DEMO data (illustrative), not laboratory measurements."))
    if score is None:
        ex.summary = f"Soil type {s.soil_type}; no measured parameters available to score."
    else:
        verdict = "good" if score >= 75 else ("moderate" if score >= 55 else "constrained")
        n_missing = len(params) - len(avail)
        ex.summary = (f"Soil health {score:.0f}/100 ({verdict}) from {len(avail)} measured parameter(s)"
                      + (f"; {n_missing} not available" if n_missing else "") + ". "
                      + (limitations[0] if limitations else "No major limitation detected."))
    return SoilAnalysis(True, score, s.soil_type, canon, params, limitations, fit, s.provenance.is_demo, ex)
