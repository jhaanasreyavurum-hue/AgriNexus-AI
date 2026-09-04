"""Simplified root-zone water balance (rule-based / modelled).

Method (FAO-56 style, deliberately simple and fully explained):

    ETc(day)   = Kc(stage) × ET0(day)
    deficit    = Σ ETc − Σ effective rain (since last irrigation or 7 days)
    RAW        = readily-available water = p × TAW × root depth (soil-class table)
    stress     = deficit / RAW           (1.0 → crop reached allowable depletion)

Forecast rain in the next 24 h / 48 h offsets the deficit before a decision is
made. Where ET0 or rain history is missing, the engine says so and falls back
to qualitative signals (weather flags + NDVI/NDWI stress) rather than
inventing numbers. Output is labelled *Modelled* in the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method

# Total available water (mm per m of soil) by canonical soil class — FAO-56 Table 19 indicative
TAW_MM_PER_M = {"sandy": 90, "red": 120, "laterite": 130, "loam": 160, "alluvial": 170,
                "clay": 180, "black": 190, "saline_alkaline": 140, None: 140}
ROOT_DEPTH_M_BY_STAGE = {"early": 0.3, "mid": 0.6, "late": 0.8}
P_DEPLETION = 0.5   # allowable depletion fraction (FAO-56 typical p≈0.5)


@dataclass
class WaterAnalysis:
    available: bool
    mode: str                                   # "quantitative" | "qualitative"
    deficit_mm: Optional[float] = None
    raw_mm: Optional[float] = None
    stress_ratio: Optional[float] = None        # deficit / RAW
    etc_7d_mm: Optional[float] = None
    rain_eff_7d_mm: Optional[float] = None
    forecast_rain_48h_mm: Optional[float] = None
    days_since_irrigation: Optional[int] = None
    status: str = "unknown"                     # adequate | approaching_deficit | deficit | surplus | unknown
    score: Optional[float] = None               # 0..100 water-status sub-score
    irrigation_advice: str = ""                 # irrigate_now | irrigate_24h | hold_rain | hold_adequate | monitor | unknown
    net_mm_recommended: Optional[float] = None
    explanation: Explanation = field(default_factory=lambda: Explanation(summary=""))


def _eff_rain(mm: float) -> float:
    """USDA-SCS style effective rainfall approximation for daily totals."""
    if mm <= 0:
        return 0.0
    if mm < 5:
        return 0.0            # small events evaporate
    return mm * 0.8 if mm <= 25 else 20 + (mm - 25) * 0.5


def analyse_water(ctx: FarmContext, kc: Optional[float], stage_name: Optional[str], soil_canonical: Optional[str],
                  ndvi_stress: bool = False, weather_flags: Optional[dict] = None) -> WaterAnalysis:
    w = ctx.weather
    flags = weather_flags or {}
    ex = Explanation(summary="", method=Method.RULE_BASED, sources=[w.provenance.label(), ctx.irrigation.provenance.label()],
                     data_considered=["ET0 & rainfall (past 7 d)", "rain forecast 24–48 h", "crop coefficient Kc (stage)",
                                      "soil water-holding class", "last irrigation date", "NDVI/NDWI stress", "irrigation source"])
    daily = w.forecast_daily or []
    today = ctx.today()
    past = [d for d in daily if not d.get("is_forecast")]
    future = [d for d in daily if d.get("is_forecast")]

    # ---- window since last irrigation (max 7 d) --------------------------------
    dsi = None
    if ctx.irrigation.last_irrigation_date:
        dsi = (today - date.fromisoformat(ctx.irrigation.last_irrigation_date)).days
    window = min(7, dsi) if dsi is not None else 7
    past_w = past[-window:] if window > 0 else []

    have_quant = bool(past_w) and kc is not None and all(d.get("et0_mm") is not None for d in past_w)
    rain48 = None
    if future:
        r = [d.get("rain_mm") for d in future[:2] if d.get("rain_mm") is not None]
        rain48 = round(sum(r), 1) if r else None
    elif w.rain_next_24h_mm is not None:
        rain48 = w.rain_next_24h_mm

    if have_quant:
        etc = sum(kc * float(d["et0_mm"]) for d in past_w)
        rain_eff = sum(_eff_rain(float(d.get("rain_mm") or 0)) for d in past_w)
        deficit = max(0.0, etc - rain_eff)
        # root depth by stage phase
        phase = "mid"
        if stage_name and any(k in stage_name for k in ("Sowing", "Emergence", "Nursery", "Planting", "Sprouting")):
            phase = "early"
        elif stage_name and any(k in stage_name for k in ("Maturity", "Harvest", "Picking", "Ripening")):
            phase = "late"
        taw = TAW_MM_PER_M.get(soil_canonical, 140)
        raw = P_DEPLETION * taw * ROOT_DEPTH_M_BY_STAGE[phase]
        # offset by forecast effective rain
        deficit_after_rain = max(0.0, deficit - _eff_rain(rain48 or 0))
        ratio = deficit / raw if raw else None

        ex.add(Factor("Crop water use (ETc)", "neutral", f"Kc {kc:.2f} × ET0 over {len(past_w)} d ≈ {etc:.0f} mm.", value=round(etc, 1)))
        ex.add(Factor("Effective rainfall", "positive" if rain_eff > 0 else "neutral", f"≈ {rain_eff:.0f} mm effective rain in the same window.", value=round(rain_eff, 1)))
        ex.add(Factor("Root-zone capacity (RAW)", "neutral", f"{taw} mm/m × {ROOT_DEPTH_M_BY_STAGE[phase]} m root depth × p={P_DEPLETION} ≈ {raw:.0f} mm readily available.", value=round(raw, 1), source="Reference · FAO-56 indicative"))
        if dsi is not None:
            ex.add(Factor("Last irrigation", "neutral", f"{dsi} days ago ({ctx.irrigation.last_irrigation_date}).", value=dsi))
        else:
            ex.add(Factor("Last irrigation", "missing", "Last irrigation date unknown — balance computed over 7 days."))
        if rain48:
            ex.add(Factor("Forecast rain 48 h", "positive", f"{rain48:.0f} mm expected → ≈{_eff_rain(rain48):.0f} mm effective.", value=rain48))

        if ratio is None:
            status, score, advice, net = "unknown", None, "unknown", None
        elif rain_eff > etc + 15 or (flags.get("heavy_rain_expected") and ratio < 0.6):
            status, score, advice, net = "surplus", 70.0, "hold_rain", None
            ex.add(Factor("Water status", "neutral", "Profile is wet / heavy rain imminent — irrigation would risk waterlogging.", value=round(ratio, 2)))
        elif deficit_after_rain < 0.5 * raw:
            if ratio >= 0.8 and (rain48 or 0) >= 10:
                status, score, advice, net = "approaching_deficit", 65.0, "hold_rain", None
                ex.add(Factor("Water status", "positive", f"Deficit {deficit:.0f} mm is {ratio*100:.0f}% of RAW but forecast rain should cover it.", value=round(ratio, 2)))
            else:
                status, score, advice, net = "adequate", 90.0 - 30 * ratio, "hold_adequate", None
                ex.add(Factor("Water status", "positive", f"Deficit {deficit:.0f} mm = {ratio*100:.0f}% of readily-available water — within comfort zone.", value=round(ratio, 2)))
        elif deficit_after_rain < raw:
            status, advice, net = "approaching_deficit", "irrigate_24h", round(deficit, 0)
            score = max(40.0, 70.0 - 30.0 * (ratio - 0.5) / 0.5)   # 0.5→70 … 1.0→40
            ex.add(Factor("Water status", "limiting", f"Deficit {deficit:.0f} mm = {ratio*100:.0f}% of RAW — allowable depletion will be reached within ~1–2 days.", value=round(ratio, 2)))
        else:
            status, score, advice, net = "deficit", 30.0, "irrigate_now", round(deficit, 0)
            ex.add(Factor("Water status", "risk", f"Deficit {deficit:.0f} mm exceeds readily-available water ({raw:.0f} mm) — crop is in water stress.", value=round(ratio, 2)))
        if ndvi_stress and status in ("adequate", "approaching_deficit"):
            score = (score or 60) - 10
            ex.add(Factor("NDVI/NDWI corroboration", "risk", "Vegetation indices also show a stress signal — supports earlier irrigation.", source="Remote sensing"))
        mode = "quantitative"
        ex.method = Method.RULE_BASED
        result = WaterAnalysis(True, mode, round(deficit, 1), round(raw, 1), round(ratio, 2) if ratio is not None else None,
                               round(etc, 1), round(rain_eff, 1), rain48, dsi, status, round(score, 0) if score is not None else None,
                               advice, net, ex)
    else:
        # ---- qualitative fallback ------------------------------------------------
        missing = []
        if not past_w:
            missing.append("rainfall/ET0 history")
        if kc is None:
            missing.append("crop stage (Kc)")
        for m in missing:
            ex.add(Factor(m, "missing", f"{m} not available — quantitative water balance not possible."))
        dry = flags.get("dry_spell", False)
        heavy = flags.get("heavy_rain_expected", False)
        rainfed = not ctx.irrigation.available
        if heavy:
            status, score, advice = "surplus", 70.0, "hold_rain"
            ex.add(Factor("Forecast", "neutral", "Significant rain expected — do not irrigate.", source="Weather"))
        elif dry and ndvi_stress:
            status, score, advice = "deficit", 35.0, "irrigate_now"
            ex.add(Factor("Signals", "risk", "Dry spell + declining NDVI/NDWI indicate water stress.", source="Weather + remote sensing"))
        elif dry or ndvi_stress:
            status, score, advice = "approaching_deficit", 55.0, "irrigate_24h" if not rainfed else "monitor"
            ex.add(Factor("Signals", "limiting", "One stress indicator present (dry outlook or NDVI decline)."))
        else:
            status, score, advice = "adequate", 75.0, "monitor"
            ex.add(Factor("Signals", "neutral", "No dry-spell or vegetation-stress signal detected."))
        result = WaterAnalysis(True, "qualitative", None, None, None, None, None, rain48, dsi, status, score, advice, None, ex)

    if not ctx.irrigation.available and result.irrigation_advice in ("irrigate_now", "irrigate_24h"):
        ex.add(Factor("Irrigation source", "limiting", "Farm is rainfed — irrigation not possible; consider protective measures (mulch, anti-transpirant, insurance)."))
    label = {"adequate": "Soil moisture adequate", "approaching_deficit": "Moisture approaching deficit", "deficit": "Crop water deficit",
             "surplus": "Water surplus / wet profile", "unknown": "Water status unknown"}[result.status]
    if result.mode == "quantitative":
        ex.summary = f"{label}: deficit ≈ {result.deficit_mm:.0f} mm vs {result.raw_mm:.0f} mm readily available ({(result.stress_ratio or 0)*100:.0f}% depleted)."
    else:
        ex.summary = f"{label} (qualitative assessment — quantitative water balance not possible with available data)."
    return result
