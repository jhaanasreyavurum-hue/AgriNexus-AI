"""Crop growth-stage analysis (Crop Timeline, §16) — rule-based.

Uses sowing date + reference stage lengths from ``data/config/crop_stages.yaml``
(FAO-56 / ICAR, labelled *reference*). Produces the stage list with status,
current stage, Kc and whether the crop is in a water-critical window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional

import yaml

from core import CONFIG_DIR
from core.models.farm_context import FarmContext
from core.models.results import Explanation, Factor, Method


@dataclass
class StageRow:
    name: str
    start_day: int
    end_day: int
    kc: float
    critical_water: bool
    status: str            # done | current | upcoming
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    ndvi_mean: Optional[float] = None


@dataclass
class StageAnalysis:
    available: bool
    crop: Optional[str]
    days_after_sowing: Optional[int]
    current_stage: Optional[str]
    current_kc: Optional[float]
    critical_water_window: bool
    progress_pct: Optional[float]
    total_days: Optional[int]
    expected_harvest: Optional[str]
    stages: List[StageRow] = field(default_factory=list)
    explanation: Explanation = field(default_factory=lambda: Explanation(summary=""))
    reference_used: str = "default"


@lru_cache(maxsize=1)
def _load_stage_cfg() -> dict:
    with open(CONFIG_DIR / "crop_stages.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def stage_table_for(crop_master_name: Optional[str]) -> tuple[List[dict], int, str]:
    cfg = _load_stage_cfg()
    crops = cfg.get("crops", {})
    if crop_master_name and crop_master_name in crops:
        c = crops[crop_master_name]
        return c["stages"], int(c.get("total_days", c["stages"][-1]["ends_day"])), crop_master_name
    d = cfg["default"]
    return d["stages"], int(d["stages"][-1]["ends_day"]), "default"


def analyse_stage(ctx: FarmContext, kb=None) -> StageAnalysis:
    from datetime import date, timedelta

    crop_name = ctx.crop.current_crop
    master = None
    if kb is not None and crop_name:
        row = kb.crop_row(crop_name)
        master = row.crop_name if row is not None else crop_name
    else:
        master = crop_name

    das = ctx.crop.days_after_sowing(ctx.today())
    ex = Explanation(summary="", method=Method.RULE_BASED,
                     sources=[ctx.crop.provenance.label(), "Reference table · FAO-56 / ICAR stage lengths"],
                     demo_data_used=ctx.crop.provenance.is_demo)
    if das is None or not crop_name:
        ex.summary = "Crop timeline unavailable — sowing date or crop not provided."
        ex.add(Factor("Sowing date", "missing", "Enter the sowing date to enable the crop timeline."))
        return StageAnalysis(False, crop_name, das, None, None, False, None, None, None, explanation=ex)

    stages_cfg, total, ref = stage_table_for(master)
    sow = date.fromisoformat(ctx.crop.sowing_date)
    rows: List[StageRow] = []
    prev = 0
    current: Optional[StageRow] = None
    for s in stages_cfg:
        start, end = prev, int(s["ends_day"])
        status = "done" if das >= end else ("current" if das >= start else "upcoming")
        r = StageRow(s["name"], start, end, float(s["kc"]), bool(s.get("critical_water", False)), status,
                     (sow + timedelta(days=start)).isoformat(), (sow + timedelta(days=end)).isoformat())
        if status == "current":
            current = r
        rows.append(r)
        prev = end
    # mean NDVI per stage from series if present
    if ctx.remote_sensing.ndvi_series:
        for r in rows:
            vals = [o.ndvi for o in ctx.remote_sensing.ndvi_series if r.start_date <= o.date < r.end_date]
            r.ndvi_mean = round(sum(vals) / len(vals), 3) if vals else None

    if current is None:
        # past maturity
        current_name, kc, crit = ("Post-harvest", None, False) if das > total else (rows[0].name, rows[0].kc, rows[0].critical_water)
    else:
        current_name, kc, crit = current.name, current.kc, current.critical_water

    progress = round(min(100.0, 100.0 * das / total), 1)
    harvest = (sow + timedelta(days=total)).isoformat()
    ex.summary = (f"{master} is {das} days after sowing — stage: {current_name} "
                  f"({progress:.0f}% of a ~{total}-day cycle; expected harvest ≈ {harvest}).")
    ex.data_considered = ["sowing date", "crop", "reference stage lengths (FAO-56 / ICAR)"]
    if crit:
        ex.add(Factor("Water-critical stage", "risk",
                      f"{current_name} is a moisture-sensitive stage (Kc≈{kc}); water deficit now has a high yield penalty.", value=kc))
    else:
        ex.add(Factor("Stage water sensitivity", "positive",
                      f"{current_name} is not a peak water-demand stage (Kc≈{kc}).", value=kc))
    if ref == "default":
        ex.add(Factor("Stage reference", "limiting",
                      f"No crop-specific stage table for {master}; generic 120-day annual crop reference used."))
    return StageAnalysis(True, master, das, current_name, kc, crit, progress, total, harvest, rows, ex, ref)
