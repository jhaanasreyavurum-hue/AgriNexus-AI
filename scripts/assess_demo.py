"""Phase-2 smoke check: run the full chain on every demo farm.

    python scripts/assess_demo.py             # live Open-Meteo weather
    python scripts/assess_demo.py --offline   # no weather call (tests qualitative fallback)
    python scripts/assess_demo.py --ask "Should I irrigate today?"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.kb import load_knowledge_base  # noqa: E402
from core.models import list_demo_farms, load_farm_context  # noqa: E402
from core.reasoning import generate_farm_advice, run_full_assessment  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--ask", default=None)
    args = ap.parse_args()
    kb = load_knowledge_base()

    for f in list_demo_farms():
        ctx = load_farm_context(f["path"])
        if not args.offline and ctx.location.latitude:
            from core.integrations.weather import get_provider
            ctx.weather = get_provider().fetch(ctx.location.latitude, ctx.location.longitude)
            # keep the demo annual normal (weather provider doesn't know it)
        a = run_full_assessment(ctx, kb)
        print("=" * 100)
        print(f"{ctx.farm_name}   [{'DEMO' if ctx.is_demo else 'REAL'}]  KB coverage: {a.kb_coverage}")
        print("=" * 100)
        print(f"FARM HEALTH  {a.health.score:.0f}/100  {a.health.label}   (confidence {a.health.confidence}, assessed weight {a.health.assessed_weight})")
        for b in a.health.breakdown:
            sc = f"{b.score:5.0f}" if b.score is not None else "  n/a"
            print(f"   {b.name:20s} {sc}  w={b.weight:.2f}  {b.label:14s} | {b.explanation.summary[:95]}")
        print(f"\nSTAGE   {a.stage.explanation.summary}")
        print(f"NDVI    {a.ndvi.explanation.summary}")
        print(f"WEATHER [{a.weather.provider_label}] {a.weather.explanation.summary}")
        for s in a.weather.signals:
            print(f"         · {s.title}: {s.value} → {s.action}")
        print(f"WATER   ({a.water.mode}) {a.water.explanation.summary}  advice={a.water.irrigation_advice}")
        print(f"SOIL    {a.soil.explanation.summary}")
        print(f"\nRISKS ({len(a.risks)})")
        for r in a.risks:
            print(f"   [{r.severity.value.upper():8s} {r.score:3.0f}] {r.title}: {r.reason[:90]}")
            print(f"              → {r.action[:110]}")
        print("\n>>> NEXT BEST ACTION")
        nba = a.next_best_action
        print(f"    {nba.action}")
        print(f"    WHY: {nba.explanation.summary}")
        print(f"    method={nba.method.value}  confidence={nba.confidence}  sources={nba.explanation.sources}")
        for fct in nba.explanation.risks[:3]:
            print(f"      ⚠ {fct.detail[:110]}")
        for fct in nba.explanation.positive[:3]:
            print(f"      ✓ {fct.detail[:110]}")
        print("    Other actions:")
        for r in a.actions[1:]:
            print(f"      {r.priority}. [{r.category}/{r.horizon}] {r.action[:110]}")
        if args.ask:
            adv = generate_farm_advice(ctx, kb, args.ask, assessment=a)
            print(f"\nCOPILOT  Q: {args.ask}   (intent={adv.intent}, methods={adv.method_labels})")
            print("   " + adv.answer.replace("\n", "\n   "))
        print()


if __name__ == "__main__":
    main()
