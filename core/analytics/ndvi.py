"""NDVI analytics (§6) — remote-sensing result (or DEMO when the series is demo).

Computes current / previous / change / % change / trend slope over the last
N observations and an agronomic interpretation that is *stage-aware*: a
falling NDVI during senescence is normal; during vegetative or flowering it
is a stress signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method

# generic NDVI condition bands for field crops at canopy stage
NDVI_BANDS = [
    (0.0, 0.20, "Bare soil / very sparse", 15),
    (0.20, 0.35, "Sparse / early vegetation", 35),
    (0.35, 0.50, "Moderate vegetation", 55),
    (0.50, 0.65, "Good vegetation", 75),
    (0.65, 0.80, "Dense, healthy canopy", 90),
    (0.80, 1.01, "Very dense canopy", 95),
]

SENESCENCE_STAGES = {"Maturity / Harvest", "Boll Opening / Picking", "Ripening / Picking", "Harvest",
                     "Maturity / Ripening", "Post-harvest"}
EARLY_STAGES = {"Sowing", "Emergence", "Planting", "Nursery / Transplanting", "Sprouting", "Germination / Tillering"}


@dataclass
class NDVIAnalysis:
    available: bool
    current: Optional[float] = None
    previous: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    trend_slope_per_10d: Optional[float] = None    # linear slope over last 4 obs
    trend: Optional[str] = None                    # improving | stable | declining
    condition: Optional[str] = None
    score: Optional[float] = None                  # 0..100 vegetation-health sub-score
    peak: Optional[float] = None
    peak_date: Optional[str] = None
    series: List[dict] = field(default_factory=list)
    ndwi_current: Optional[float] = None
    ndwi_change: Optional[float] = None
    is_demo: bool = False
    stress_signal: bool = False
    explanation: Explanation = field(default_factory=lambda: Explanation(summary=""))


def _band(v: float):
    for lo, hi, label, score in NDVI_BANDS:
        if lo <= v < hi:
            return label, score
    return "Out of range", 0


def analyse_ndvi(ctx: FarmContext, current_stage: Optional[str] = None) -> NDVIAnalysis:
    rs = ctx.remote_sensing
    prov = rs.provenance
    is_demo = prov.is_demo
    ex = Explanation(summary="", method=Method.REMOTE_SENSING, sources=[prov.label()], demo_data_used=is_demo,
                     data_considered=["NDVI time series", "NDWI (if present)", "crop growth stage"])
    if not rs.ndvi_series:
        ex.summary = "No NDVI data available for this farm."
        ex.add(Factor("NDVI", "missing", "Upload an NDVI time series (CSV) or connect a satellite source to enable vegetation analytics."))
        return NDVIAnalysis(False, explanation=ex, is_demo=is_demo)

    obs = sorted(rs.ndvi_series, key=lambda o: o.date)
    vals = np.array([o.ndvi for o in obs], dtype=float)
    cur, prev = float(vals[-1]), (float(vals[-2]) if len(vals) > 1 else None)
    change = round(cur - prev, 3) if prev is not None else None
    change_pct = round(100.0 * change / prev, 1) if (prev not in (None, 0)) else None

    # trend over last 4 observations (slope per 10 days)
    slope = None
    if len(obs) >= 3:
        from datetime import date
        tail = obs[-4:]
        d0 = date.fromisoformat(tail[0].date)
        x = np.array([(date.fromisoformat(o.date) - d0).days for o in tail], dtype=float)
        y = np.array([o.ndvi for o in tail])
        if np.ptp(x) > 0:
            slope = float(np.polyfit(x, y, 1)[0] * 10)
    # latest inter-pass change dominates; slope only breaks ties for small changes
    pct = change_pct or 0.0
    if pct <= -5.0 or (change or 0) <= -0.04:
        trend = "declining"
    elif pct >= 5.0 or (change or 0) >= 0.04:
        trend = "improving"
    elif slope is not None and abs(slope) > 0.02:
        trend = "improving" if slope > 0 else "declining"
    else:
        trend = "stable"

    condition, score = _band(cur)
    peak_i = int(vals.argmax())
    ndwi_cur = obs[-1].ndwi
    ndwi_change = (round(obs[-1].ndwi - obs[-2].ndwi, 3)
                   if len(obs) > 1 and obs[-1].ndwi is not None and obs[-2].ndwi is not None else None)

    # ---- stage-aware interpretation ---------------------------------------
    stress = False
    in_senescence = current_stage in SENESCENCE_STAGES if current_stage else False
    in_early = current_stage in EARLY_STAGES if current_stage else False
    drop_from_peak = float(vals.max() - cur)

    if trend == "declining" and not in_senescence:
        stress = True
        score = max(0, score - 15)
        ex.add(Factor("NDVI trend", "risk",
                      f"NDVI fell {abs(change or 0):.2f} ({change_pct:+.1f}%) since the previous pass during {current_stage or 'active growth'} — "
                      "a canopy-stress signal (water, nutrient or pest/disease).", value=change_pct))
    elif trend == "declining" and in_senescence:
        ex.add(Factor("NDVI trend", "neutral",
                      f"NDVI is declining ({change_pct:+.1f}%) but the crop is in {current_stage}; canopy senescence is expected.", value=change_pct))
    elif trend == "improving":
        ex.add(Factor("NDVI trend", "positive", f"NDVI rising ({change_pct:+.1f}% since last pass) — canopy is developing well.", value=change_pct))
    else:
        ex.add(Factor("NDVI trend", "neutral", "NDVI is stable between the last two passes.", value=change_pct))

    if in_early and cur < 0.35:
        ex.add(Factor("NDVI level", "neutral", f"Low NDVI ({cur:.2f}) is normal at {current_stage}; canopy has not closed yet."))
        score = max(score, 60)  # don't penalise early crop for low NDVI
    elif cur >= 0.5:
        ex.add(Factor("NDVI level", "positive", f"Current NDVI {cur:.2f} → {condition.lower()}.", value=cur))
    else:
        ex.add(Factor("NDVI level", "limiting", f"Current NDVI {cur:.2f} → {condition.lower()} for this stage.", value=cur))

    if drop_from_peak > 0.08 and not in_senescence:
        ex.add(Factor("Drop from seasonal peak", "risk",
                      f"NDVI is {drop_from_peak:.2f} below the season peak of {vals.max():.2f} ({obs[peak_i].date}).", value=drop_from_peak))
        stress = True
    if ndwi_change is not None and ndwi_change < -0.05 and not in_senescence:
        ex.add(Factor("NDWI", "risk", f"NDWI fell {ndwi_change:+.2f} — canopy water content is decreasing.", value=ndwi_change))
        stress = True
    elif ndwi_change is not None and ndwi_change < -0.05 and in_senescence:
        ex.add(Factor("NDWI", "neutral", f"NDWI fell {ndwi_change:+.2f}; canopy drying is expected during {current_stage}.", value=ndwi_change))
    elif ndwi_cur is not None:
        ex.add(Factor("NDWI", "neutral", f"NDWI {ndwi_cur:+.2f}; canopy water content {'adequate' if ndwi_cur > 0.05 else 'low'}.", value=ndwi_cur))

    if is_demo:
        ex.add(Factor("Data source", "limiting", "This NDVI series is DEMO data, not a satellite measurement."))

    verdict = {"improving": "Vegetation condition is improving.",
               "stable": "Vegetation condition is stable.",
               "declining": ("Vegetation is senescing as expected for this stage." if in_senescence
                             else "Vegetation condition is deteriorating — investigate stress.")}[trend]
    ex.summary = f"Current NDVI {cur:.2f} (previous {prev:.2f}, {change_pct:+.1f}%). {verdict}" if prev is not None \
        else f"Current NDVI {cur:.2f}. {verdict}"

    return NDVIAnalysis(
        True, cur, prev, change, change_pct, round(slope, 4) if slope is not None else None, trend, condition,
        float(score), float(vals.max()), obs[peak_i].date,
        [{"date": o.date, "ndvi": o.ndvi, "ndwi": o.ndwi} for o in obs],
        ndwi_cur, ndwi_change, is_demo, stress, ex,
    )
