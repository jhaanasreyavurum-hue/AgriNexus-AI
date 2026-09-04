"""🏠 Scheme Dashboard — Financial Inclusion & Scheme Monitoring overview (MODELLED)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import state
from ui.analytics_components import bar_chart, basis_badge, district_map, kpi_row, modelled_banner, ranking_table
from ui.components import esc, footer, md
from ui.pages.government._common import guard, header


def render() -> None:
    user = guard()
    sc, _, ii = header("🏠 Scheme Dashboard — Financial Inclusion & Scheme Monitoring", user)
    kb = state.get_kb()
    modelled_banner("inclusion", ii.notes, ii.stale)
    k = ii.kpis
    scope_txt = sc or "All KB districts"

    md(f'<div class="an-hero" style="background:linear-gradient(120deg,#5E3A00,#9C6B12)"><div class="eyebrow">Inclusion summary · {esc(scope_txt)} · {esc(ii.basis)}</div>'
       f'<div class="action">Modelled inclusion index {k["inclusion_index"]:.0f}/100 across {k["districts"]} district(s) — '
       f'{k["low_districts"]} district(s) flagged for intervention.</div>'
       f'<div class="why">Scheme reach {k["scheme_reach_pct"]:.0f}% · credit reach {k["credit_reach_pct"]:.0f}% · insurance cover {k["insurance_reach_pct"]:.0f}% · subsidy reach {k["subsidy_reach_pct"]:.0f}% of scenario households. '
       f'Widest-reach scheme: {esc(k["top_scheme"] or "—")}. Weakest segment: {esc(k["weakest_segment"] or "—")}.</div>'
       f'<div class="meta"><span>{k["schemes_active"]} schemes with modelled reach</span><span>avg {k["avg_schemes_per_household"]:.1f} eligible schemes / household</span></div></div>')

    kpi_row([("Scheme reach", f"{k['scheme_reach_pct']:.0f}%", "households eligible for ≥1 scheme"),
             ("Credit reach", f"{k['credit_reach_pct']:.0f}%", "eligibility rated Good/Moderate"),
             ("Insurance cover", f"{k['insurance_reach_pct']:.0f}%", "crop cover notified for district crop"),
             ("Subsidy reach", f"{k['subsidy_reach_pct']:.0f}%", "≥1 subsidy matched"),
             ("Intervention districts", str(k["low_districts"]), "lowest inclusion index in scope")], basis_badge())

    c1, c2 = st.columns([1.35, 1])
    with c1:
        if len(ii.by_district):
            district_map(kb, ii.by_district, "inclusion_index", "district", "relative_band", title="Inclusion index by district (colour = relative rank in scope)",
                         tooltip_cols=["crop", "performance", "relative_band"], height=400)
    with c2:
        bar_chart(ii.by_scheme.head(10), "scheme", "reach_pct", "Scheme reach (% of households, modelled)", key="gov_home_schemes", height=400, text_fmt="%{text:.0f}%")

    c3, c4 = st.columns(2)
    with c3:
        pillars = pd.DataFrame({"pillar": ["Scheme", "Credit", "Insurance", "Subsidy"],
                                "reach_pct": [k["scheme_reach_pct"], k["credit_reach_pct"], k["insurance_reach_pct"], k["subsidy_reach_pct"]]})
        bar_chart(pillars, "pillar", "reach_pct", "Four inclusion pillars (reach %)", orientation="v", key="gov_home_pillars", height=320, text_fmt="%{text:.0f}%")
    with c4:
        bar_chart(ii.by_segment, "segment_label", "inclusion_index", "Inclusion index by farmer segment", key="gov_home_seg", height=320)

    st.subheader("Districts needing intervention")
    ranking_table(ii.low_adoption.head(10), {"district": ("District", "str"), "state": ("State", "str"), "crop": ("Major crop", "str"), "inclusion_index": ("Inclusion index", "num"),
                                              "scheme_reach_pct": ("Scheme %", "pct"), "credit_reach_pct": ("Credit %", "pct"), "insurance_reach_pct": ("Insurance %", "pct"),
                                              "subsidy_reach_pct": ("Subsidy %", "pct"), "weakest_pillar": ("Weakest pillar", "str"), "intervention": ("Suggested intervention", "str")})
    st.caption("Interventions are rule-based suggestions keyed to the weakest modelled pillar — for field verification, not directives.")
    footer()
