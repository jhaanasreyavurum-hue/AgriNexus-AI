"""Phase-3 smoke check: knowledge engines + opportunities + finance-aware NBA.

    python scripts/knowledge_demo.py [--offline] [--farm TS_WARANGAL_COTTON_DEMO]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.kb import load_knowledge_base  # noqa: E402
from core.models import list_demo_farms, load_farm_context  # noqa: E402
from core.reasoning import generate_farm_advice, run_full_assessment  # noqa: E402


def show(a):
    k = a.knowledge
    f = k.facts
    print("=" * 110)
    print(f"{a.ctx.farm_name}")
    print("=" * 110)
    print(f"FACTS  {f.state}/{f.district} · {f.acres:.1f} ac ({f.category}) · income ₹{f.income:,} · crop {f.crop_master} {sorted(f.crop_groups)}")
    print(f"       attrs={f.profile_attrs}  risks={sorted(f.active_risk_types)}  docs_held={len(f.documents_held)}")
    print(f"       {k.coverage_note}")
    print(f"       eligibility rules fired: {len(k.fired_eligibility_rules)} · ai rules fired: {len(k.fired_ai_rules)}")
    if k.fired_ai_rules:
        r = k.fired_ai_rules[0]
        print(f"       e.g. AI rule {r['rule_id']} ({r['cond_state']}/{r['cond_crop']}/{r['cond_land_band']}/{r['cond_income_band']}, conf {r['confidence']}): {r['reason'][:150]}…")

    print("\n🌱 CROP ADVISOR (target season: %s)" % (a.ctx.crop.season))
    for i, m in enumerate(k.crops[:6], 1):
        cur = " ← current" if m.payload["is_current_crop"] else ""
        print(f"  {i}. {m.title:26s} {m.score:3.0f}%  {m.label:14s}{cur}")
        print(f"       ✓ " + " | ".join(x.name for x in m.explanation.positive[:4]) + ("   ✗ " + " | ".join(x.name for x in m.explanation.limiting[:2]) if m.explanation.limiting else ""))

    print("\n🎯 SCHEMES YOU MAY BE ELIGIBLE FOR")
    for i, m in enumerate(k.schemes[:6], 1):
        p = m.payload
        print(f"  {i}. {m.title[:60]:60s} {m.score:3.0f}%  {m.label}")
        print(f"       ✓ " + " · ".join(x.name for x in m.explanation.positive[:5]))
        if m.explanation.limiting:
            print(f"       – " + " · ".join(x.detail[:70] for x in m.explanation.limiting[:2]))
        print(f"       benefit: max ₹{p['maximum_subsidy']:,.0f} ({p['subsidy_percentage']:g}%) · docs ready {p['document_readiness_pct']:.0f}% · missing: {', '.join(m.documents_missing[:3]) or '—'} · {p['official_portal']}"
              + (f" · KB-corrected: {p['kb_overrides']}" if p['kb_overrides'] else ""))

    print("\n💳 LOAN ADVISOR")
    la = k.loans
    print(f"  Estimated eligibility ₹{la.estimated_eligibility_inr:,.0f} — {la.eligibility_rating} ({la.rating_score:.0f}/100)   purpose={la.purpose}")
    for x in la.explanation.positive[:3]: print(f"       ✓ {x.detail[:100]}")
    for x in la.explanation.limiting[:2]: print(f"       – {x.detail[:100]}")
    for i, m in enumerate(la.products[:5], 1):
        p = m.payload
        print(f"  {i}. {m.title[:55]:55s} {m.score:3.0f}%  {p['interest_rate']:18s} ₹{p['amount_min']:,}–₹{p['amount_max']:,}  collateral={'Y' if p['collateral_required'] else 'N'}  docs {p['document_readiness_pct']:.0f}%")
    print(f"  Branches: {la.branch_coverage_note}")
    for b in la.branches[:3]:
        print(f"       · {b['bank_name']} — {b['branch_name']} ({b['ifsc']}) {'★' if b['offers_matched_product'] else ''}")

    print("\n🛡 INSURANCE (informational)")
    if k.insurance_gap_note:
        print(f"  ⚠ {k.insurance_gap_note}")
    for i, m in enumerate(k.insurance[:5], 1):
        p = m.payload
        print(f"  {i}. {m.title[:62]:62s} {m.score:3.0f}%  {p['coverage_type'][:28]:28s} risk='{p['covered_risk']}' farmer premium≈{p['farmer_premium_pct']}%  hits={p['risk_hits']}")

    print("\n💰 SUBSIDIES")
    for i, m in enumerate(k.subsidies[:5], 1):
        p = m.payload
        print(f"  {i}. {m.title[:45]:45s} {m.score:3.0f}%  {p['subcategory'][:32]:32s} ₹{p['maximum_amount']:>9,.0f}  needs={p['need_hits']}")

    print("\n✨ OPPORTUNITIES")
    for o in k.opportunities:
        print(f"  {o.title[:70]:70s} {o.score:3.0f}  {o.value_hint or ''}")
        print(f"       {o.reason[:120]}")

    print("\n>>> ACTION LIST (NEXT BEST ACTION first)")
    for r in a.actions:
        print(f"  {r.priority}. [{r.category:10s} {r.horizon:18s} {r.method.value:22s}] {r.action[:105]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--farm", default=None)
    ap.add_argument("--ask", default=None)
    args = ap.parse_args()
    kb = load_knowledge_base()
    for f in list_demo_farms():
        if args.farm and f["farm_id"] != args.farm:
            continue
        ctx = load_farm_context(f["path"])
        if not args.offline and ctx.location.latitude:
            from core.integrations.weather import get_provider
            w = get_provider().fetch(ctx.location.latitude, ctx.location.longitude)
            w.annual_rainfall_normal_mm = ctx.weather.annual_rainfall_normal_mm
            ctx.weather = w
        a = run_full_assessment(ctx, kb)
        show(a)
        for q in ([args.ask] if args.ask else ["What government schemes may apply to me?", "What loan options may suit me?", "What opportunities are available to me?"]):
            adv = generate_farm_advice(ctx, kb, q, assessment=a)
            print(f"\nCOPILOT Q: {q}  (intent={adv.intent}; methods={adv.method_labels}; refs={adv.kb_references[:4]})")
            print("   " + adv.answer.replace("\n", "\n   "))
        print()


if __name__ == "__main__":
    main()
