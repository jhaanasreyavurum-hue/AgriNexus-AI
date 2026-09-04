"""🛡️ Insurance — informational crop / livestock cover matches with risk linkage."""
from __future__ import annotations

import streamlit as st

from ui.components import badge, esc, footer, inr, kpi, md, risk_card
from ui.match_cards import insurance_card
from ui.pages.farmer._common import guard_with_farm


def render() -> None:
    user, ctx, a = guard_with_farm("🛡️ Insurance")
    kr = a.knowledge
    f = kr.facts
    crop_ins = [m for m in kr.insurance if not m.payload.get("is_livestock")]
    live_ins = [m for m in kr.insurance if m.payload.get("is_livestock")]

    md('<div class="an-warn">Informational only — premiums and sums insured are knowledge-base figures, not live quotes. '
       'PMFBY / RWBCIS notification changes each season; confirm with your bank, CSC or insurer.</div>')
    c = st.columns(4)
    with c[0]:
        kpi("Current status", "insured" if f.has_insurance else "not insured", "as declared in your profile")
    with c[1]:
        kpi("Crop covers matched", str(len(crop_ins)), "notified for your district" if crop_ins else "none notified in KB", badge("KNOWLEDGE BASE", "green"))
    with c[2]:
        kpi("Livestock covers", str(len(live_ins)), "allied activity" if f.livestock else "no livestock declared")
    with c[3]:
        best = crop_ins[0] if crop_ins else None
        kpi("Best-fit farmer premium", f"≈{best.payload.get('farmer_premium_pct')}%" if best else "—", inr(best.payload.get("indicative_farmer_premium_inr")) + " indicative" if best and best.payload.get("indicative_farmer_premium_inr") else "")

    if kr.insurance_gap_note:
        md(f'<div class="an-note">⚠️ {esc(kr.insurance_gap_note)}</div>')
    active = [r for r in a.risks if r.risk_type in ("drought", "water_stress", "excess_rainfall", "heat_stress", "crop_stress")]
    if active:
        st.subheader("Risks the cover should address")
        cols = st.columns(min(3, len(active)))
        for i, r in enumerate(active[:3]):
            with cols[i]:
                risk_card(r)

    st.subheader("Matched covers")
    if not kr.insurance:
        st.info("No insurance product in the KB applies to this crop and district.")
    for i, m in enumerate(kr.insurance[:6], 1):
        insurance_card(m, i, f"ins{i}")
    footer()
