"""Weather intelligence (§8) — converts forecast numbers into agricultural meaning.

Inputs come from ``FarmContext.weather`` (populated by a WeatherProvider).
Output: condition score, list of interpreted signals with potential actions,
and flags reused by the water-balance and risk engines.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method


@dataclass
class WeatherSignal:
    key: str
    title: str
    value: str
    meaning: str
    action: str
    severity: str        # info | watch | warning | alert


@dataclass
class WeatherAnalysis:
    available: bool
    score: Optional[float]                     # 0..100 weather-condition sub-score
    signals: List[WeatherSignal] = field(default_factory=list)
    rain_next_24h_mm: Optional[float] = None
    rain_next_7d_mm: Optional[float] = None
    rain_last_7d_mm: Optional[float] = None
    et0_next_7d_mm: Optional[float] = None
    temp_max_c: Optional[float] = None
    heat_stress: bool = False
    heavy_rain_expected: bool = False
    dry_spell: bool = False
    provider_label: str = ""
    explanation: Explanation = field(default_factory=lambda: Explanation(summary=""))


def analyse_weather(ctx: FarmContext, crop_temp_max: Optional[float] = None) -> WeatherAnalysis:
    w = ctx.weather
    ex = Explanation(summary="", method=Method.WEATHER, sources=[w.provenance.label()],
                     data_considered=["7-day rainfall history", "24h / 7-day rainfall forecast", "max temperature", "reference ET0", "humidity"])
    if w.temp_max_c is None and not w.forecast_daily:
        ex.summary = "Weather data unavailable (provider offline or no coordinates)."
        ex.add(Factor("Weather", "missing", w.provenance.detail or "No weather snapshot."))
        return WeatherAnalysis(False, None, explanation=ex, provider_label=w.provenance.label())

    signals: List[WeatherSignal] = []
    score = 80.0
    heat = heavy = dry = False
    r24, r7, rp7, et7, tmax = w.rain_next_24h_mm, w.rain_next_7d_mm, w.rain_last_7d_mm, w.et0_next_7d_mm, w.temp_max_c

    # ---- rainfall next 24h ----------------------------------------------------
    if r24 is not None:
        if r24 >= 50:
            heavy = True; score -= 25
            signals.append(WeatherSignal("rain24", "Heavy rain expected", f"{r24:.0f} mm / 24 h",
                                         "Very heavy rainfall — waterlogging and nutrient leaching likely; field operations disrupted.",
                                         "Do not irrigate. Open drainage channels; postpone fertiliser/spray.", "alert"))
        elif r24 >= 20:
            heavy = True; score -= 10
            signals.append(WeatherSignal("rain24", "Significant rain expected", f"{r24:.0f} mm / 24 h",
                                         "Irrigation demand is likely to decrease; risk of temporary waterlogging on heavy soils.",
                                         "Skip irrigation; reassess after the rain.", "warning"))
        elif r24 >= 5:
            signals.append(WeatherSignal("rain24", "Light–moderate rain expected", f"{r24:.0f} mm / 24 h",
                                         "Partial recharge of topsoil moisture.", "Reassess irrigation after rainfall.", "watch"))
        else:
            signals.append(WeatherSignal("rain24", "No meaningful rain in 24 h", f"{r24:.0f} mm",
                                         "No rainfall relief expected tomorrow.", "Base irrigation decision on soil-moisture balance.", "info"))
    # ---- 7-day outlook ---------------------------------------------------------
    if r7 is not None and et7 is not None:
        balance = r7 - et7
        if r7 < 10 and et7 > 25:
            dry = True; score -= 15
            signals.append(WeatherSignal("dry7", "Dry week ahead", f"rain {r7:.0f} mm vs ET0 {et7:.0f} mm",
                                         f"Atmospheric demand exceeds rainfall by ~{abs(balance):.0f} mm — crop water deficit will build.",
                                         "Plan irrigation for the week; mulch to reduce evaporation.", "warning"))
        elif balance < -15:
            signals.append(WeatherSignal("bal7", "Net water deficit this week", f"{balance:+.0f} mm",
                                         "Rainfall will not cover evapotranspiration.", "Schedule supplementary irrigation.", "watch"))
        elif balance > 30:
            heavy = heavy or r7 >= 60
            if r7 >= 60:
                score -= 10
            signals.append(WeatherSignal("bal7", "Wet week ahead", f"rain {r7:.0f} mm vs ET0 {et7:.0f} mm",
                                         "Rain exceeds crop demand — no irrigation needed; disease pressure rises with prolonged wetness.",
                                         "Hold irrigation; scout for fungal disease.", "watch"))
        else:
            signals.append(WeatherSignal("bal7", "Balanced week", f"rain {r7:.0f} mm vs ET0 {et7:.0f} mm",
                                         "Rainfall roughly matches evapotranspiration.", "Monitor; irrigate only if soil dries.", "info"))
    elif r7 is not None:
        if r7 < 5:
            dry = True; score -= 12
            signals.append(WeatherSignal("dry7", "Dry week ahead", f"{r7:.0f} mm", "Little rain in the 7-day outlook.", "Plan irrigation.", "warning"))
    # ---- recent rain ------------------------------------------------------------
    if rp7 is not None:
        if rp7 < 5:
            dry = dry or (r7 is not None and r7 < 15)
            signals.append(WeatherSignal("past7", "Dry past week", f"{rp7:.0f} mm in 7 days",
                                         "Soil moisture has been drawing down.", "Check soil moisture / crop wilting signs.", "watch"))
        elif rp7 > 100:
            signals.append(WeatherSignal("past7", "Very wet past week", f"{rp7:.0f} mm in 7 days",
                                         "Profile is likely saturated.", "Avoid irrigation; check for waterlogging.", "watch"))
    # ---- temperature -------------------------------------------------------------
    if tmax is not None:
        threshold = crop_temp_max or 38.0
        if tmax >= threshold + 2:
            heat = True; score -= 20
            signals.append(WeatherSignal("heat", "Heat stress conditions", f"{tmax:.0f} °C max",
                                         f"Above ~{threshold:.0f} °C flowering and grain set are impaired; transpiration demand is high.",
                                         "Irrigate in the evening / early morning; avoid midday spraying.", "alert"))
        elif tmax >= threshold - 2:
            heat = True; score -= 8
            signals.append(WeatherSignal("heat", "High temperature", f"{tmax:.0f} °C max",
                                         "Approaching crop heat-stress threshold; water demand elevated.", "Ensure moisture is adequate.", "warning"))
    if w.humidity_pct is not None and w.humidity_pct >= 85 and (rp7 or 0) > 20:
        signals.append(WeatherSignal("humid", "Prolonged high humidity", f"{w.humidity_pct:.0f}% RH",
                                     "Favourable for fungal/bacterial disease.", "Scout for leaf spots / blight; ensure canopy airflow.", "watch"))

    score = max(0.0, min(100.0, score))
    for s in signals:
        eff = {"alert": "risk", "warning": "risk", "watch": "limiting", "info": "neutral"}[s.severity]
        ex.add(Factor(s.title, eff, f"{s.value} — {s.meaning}", value=s.value))
    top = signals[0] if signals else None
    ex.summary = (f"{top.title}: {top.value}. {top.meaning}" if top else "No notable weather signal.")
    return WeatherAnalysis(True, score, signals, r24, r7, rp7, et7, tmax, heat, heavy, dry, w.provenance.label(), ex)
