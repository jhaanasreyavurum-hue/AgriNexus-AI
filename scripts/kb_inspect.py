"""Phase-1 smoke check: load KB, show overrides, load demo farms, resolve
their vocabulary, and (optionally) fetch live weather.

    python scripts/kb_inspect.py            # offline parts only
    python scripts/kb_inspect.py --weather  # also call Open-Meteo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.kb import load_knowledge_base  # noqa: E402
from core.models import list_demo_farms, load_farm_context  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weather", action="store_true")
    args = ap.parse_args()

    kb = load_knowledge_base()
    s = kb.summary()
    print("== KNOWLEDGE BASE ==")
    for t, n in s["tables"].items():
        print(f"  {t:18s} {n:5d} rows   checksum={s['checksums'][__import__('core.kb.loader', fromlist=['TABLES']).TABLES[t]]}")
    print(f"  overrides applied: {s['overrides_applied']}  (see data/config/kb_overrides.yaml)")
    for o in kb.override_log[:6]:
        print(f"    {o.override_id}: {o.table}.{o.column}  {o.original!r} -> {o.new!r}")
    print("    ...")

    print("\n== DEMO FARMS ==")
    for f in list_demo_farms():
        ctx = load_farm_context(f["path"])
        v = kb.vocab
        ha = ctx.area_hectares
        crop = kb.crop_row(ctx.crop.current_crop)
        geo = kb.district_row(ctx.location.state, ctx.location.district)
        print(f"\n  {ctx.farm_name}")
        print(f"    demo={ctx.is_demo}  as_of={ctx.as_of}  area={ctx.area_acres:.2f} ac / {ha:.2f} ha")
        print(f"    state coverage      : {kb.coverage_level(ctx.location.state)}")
        print(f"    district (KB)       : {geo.district_name}, {geo.agriculture_zone}, major crop {geo.major_crop}")
        print(f"    crop -> master      : {ctx.crop.current_crop!r} -> {crop.crop_name} [{crop.season}, {crop.soil_type}, "
              f"{crop.minimum_rainfall}-{crop.maximum_rainfall} mm, water {crop.water_requirement}]")
        print(f"    crop groups         : {v.crop_groups_for(ctx.crop.current_crop)}")
        print(f"    soil -> canonical   : {ctx.soil.soil_type!r} -> {v.canonical_soil(ctx.soil.soil_type)}"
              f"  (crop-soil similarity {v.soil_match_score(crop.soil_type, ctx.soil.soil_type)})")
        print(f"    land bands          : {v.land_band_labels(ctx.area_acres)}")
        print(f"    income bands        : {v.income_band_labels(ctx.farmer.annual_income_inr)}")
        print(f"    farmer category     : {v.farmer_category_from_land(ha)}")
        attrs = ctx.farmer.category_attrs(ha, v)
        print(f"    profile attrs       : {attrs}")
        print(f"    KB farmer terms met : {len(v.farmer_terms_satisfied(attrs))} spellings")
        print(f"    days after sowing   : {ctx.crop.days_after_sowing(ctx.today())}")
        print(f"    NDVI latest/prev    : {ctx.remote_sensing.latest.ndvi} / {ctx.remote_sensing.previous.ndvi}"
              f"  [{ctx.remote_sensing.provenance.label()}]")
        print(f"    missing blocks      : {ctx.missing_blocks()}")
        if args.weather and ctx.location.latitude:
            from core.integrations.weather import get_provider
            w = get_provider().fetch(ctx.location.latitude, ctx.location.longitude)
            print(f"    weather [{w.provenance.label()}]: tmax={w.temp_max_c} rain7d_past={w.rain_last_7d_mm} "
                  f"rain24h={w.rain_next_24h_mm} rain7d={w.rain_next_7d_mm} et0_7d={w.et0_next_7d_mm}")


if __name__ == "__main__":
    main()
