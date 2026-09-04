"""💰 Financial Inclusion — four-pillar indicators by segment and district; credit-access lens."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import state, theme
from ui.analytics_components import bar_chart, basis_badge, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import esc, footer, md, plot
from ui.pages.government._common import guard, header


def _radar(seg: pd.DataFrame) -> None:
    fig = go.Figure()
    cats = ["Scheme", "Credit", "Insurance", "Subsidy"]
    for _, r in seg.iterrows():
        fig.add_trace(go.Scatterpolar(r=[r["scheme_reach_pct"], r["credit_reach_pct"], r["insurance_reach_pct"], r["subsidy_reach_pct"], r["scheme_reach_pct"]],
                                      theta=cats + [cats[0]], name=r["segment_label"], opacity=0.75))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], tickfont=dict(size=9))), height=430, margin=dict(l=30, r=30, t=44, b=10),
                      title=dict(text="Reach by pillar per segment (%)", font=dict(size=14, color=theme.INK)), legend=dict(font=dict(size=9)), paper_bgcolor="rgba(0,0,0,0)")
    plot(fig, key="incl_radar")


def render() -> None:
    user = guard()
    sc, tags, ii = header("💰 Financial Inclusion", user, with_segments=True)
    kb = state.get_kb()
    modelled_banner("inclusion", ii.notes, ii.stale)
    k = ii.kpis
    seg = ii.by_segment
    kpi_row([("Inclusion index", f"{k['inclusion_index']:.0f}/100", "household-weighted"), ("Scheme reach", f"{k['scheme_reach_pct']:.0f}%", "≥1 eligible scheme"),
             ("Credit reach", f"{k['credit_reach_pct']:.0f}%", "rating Good/Moderate"), ("Insurance cover", f"{k['insurance_reach_pct']:.0f}%", "crop cover notified"),
             ("Subsidy reach", f"{k['subsidy_reach_pct']:.0f}%", "≥1 subsidy matched")], basis_badge())

    c1, c2 = st.columns([1.1, 1])
    with c1:
        if len(seg):
            _radar(seg)
    with c2:
        bar_chart(seg, "segment_label", "inclusion_index", "Inclusion index by segment", key="incl_seg", height=430, color="segment_group")

    st.subheader("Where inclusion breaks down")
    if len(seg):
        weakest = seg.iloc[0]
        gaps = []
        for _, r in seg.iterrows():
            for col, name in (("credit_reach_pct", "credit"), ("insurance_reach_pct", "insurance"), ("subsidy_reach_pct", "subsidy"), ("scheme_reach_pct", "scheme")):
                if r[col] < 60:
                    gaps.append((r["segment_label"], name, r[col]))
        if gaps:
            md("".join(f'<div class="an-card tight"><b>{esc(s)}</b> — {esc(p)} reach only {v:.0f}%</div>' for s, p, v in sorted(gaps, key=lambda x: x[2])[:8]))
        else:
            md('<div class="an-note">All segments exceed 60% reach on every pillar in this scope (modelled).</div>')
        if (seg["segment_id"] == "TENANT").any():
            t = seg[seg["segment_id"] == "TENANT"].iloc[0]
            md(f'<div class="an-note">Tenant / sharecropper archetype: credit reach {t["credit_reach_pct"]:.0f}% — the KB loan rules require land records or a cultivator certificate, which is the single largest '
               f'structural exclusion in the model. Policy lever: cultivator-certificate drives and JLG lending.</div>')

    st.subheader("Segment table")
    ranking_table(seg, {"segment_label": ("Segment", "str"), "segment_group": ("Group", "str"), "tags": ("Tags", "str"), "households": ("Households", "int"), "inclusion_index": ("Index", "num"),
                        "scheme_reach_pct": ("Scheme %", "pct"), "credit_reach_pct": ("Credit %", "pct"), "insurance_reach_pct": ("Insurance %", "pct"), "subsidy_reach_pct": ("Subsidy %", "pct"),
                        "avg_schemes": ("Avg schemes", "num"), "avg_subsidies": ("Avg subsidies", "num"), "top_scheme": ("Top scheme", "str")})
    download_df(seg, "Download segment inclusion (CSV)", "inclusion_segments.csv", "dl_incl")

    st.subheader("Credit access infrastructure (KB)")
    br = kb.branches if not sc else kb.branches[kb.branches["state"] == sc]
    if len(br):
        g = br.groupby("district", as_index=False).agg(branches=("branch_name", "count"), loan_desks=("loan_available_bool", "sum"), insurance_desks=("insurance_available_bool", "sum"),
                                                        govt_linked=("government_linked", lambda s: int((s == "Yes").sum())))
        bar_chart(g.sort_values("loan_desks").head(15), "district", "loan_desks", "Fewest KB agri-loan desks — bottom 15 districts", key="incl_desks", height=400)
        st.caption("Branch directory is a KB reference (200 branches, Telangana). Districts with few agri-loan desks are candidates for banking-correspondent / camp-mode outreach.")
    else:
        st.caption("No KB branch directory for this scope (branches are listed for Telangana only).")
    footer()
