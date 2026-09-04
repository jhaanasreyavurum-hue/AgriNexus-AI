"""🗺️ District Performance — map + ranking of districts by modelled inclusion index and pillars."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import state, theme
from ui.analytics_components import bar_chart, basis_badge, district_map, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import badge, esc, footer, md, plot
from ui.pages.government._common import guard, header


def _pillar_chart(d: pd.DataFrame, n: int) -> None:
    v = d.head(n)
    fig = go.Figure()
    for col, name, color in (("p_scheme", "Scheme depth", theme.GREEN), ("p_credit", "Credit", theme.BLUE), ("p_insurance", "Insurance", theme.AMBER), ("p_subsidy", "Subsidy", "#7B61FF")):
        fig.add_trace(go.Bar(name=name, x=v["district"], y=25 * v[col], marker_color=color))
    fig.update_layout(barmode="stack", title=dict(text="Inclusion index composition (four pillars × 25)", font=dict(size=14, color=theme.INK)), height=400,
                      margin=dict(l=10, r=10, t=44, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h"), yaxis=dict(range=[0, 100]))
    plot(fig, key="dist_pillars")


def render() -> None:
    user = guard()
    sc, tags, ii = header("🗺️ District Performance", user, with_segments=True)
    kb = state.get_kb()
    modelled_banner("inclusion", ii.notes, ii.stale)
    d = ii.by_district
    if d.empty:
        st.info("No districts in scope.")
        footer()
        return
    kpi_row([("Districts", str(len(d)), sc or "All KB districts"), ("Best", d.iloc[0]["district"], f"index {d.iloc[0]['inclusion_index']:.0f}"),
             ("Weakest", d.iloc[-1]["district"], f"index {d.iloc[-1]['inclusion_index']:.0f}"),
             ("Spread", f"{d['inclusion_index'].max() - d['inclusion_index'].min():.0f} pts", "max − min"),
             ("Lower-third districts", str(int((d["relative_band"] == "Lower third").sum())), "relative ranking in scope")], basis_badge())
    if sc and d["inclusion_index"].std() < 3:
        md('<div class="an-note">Within one state the KB applies the same schemes and rules everywhere, so the index varies mainly through the district major crop (insurance notification, crop-linked schemes). '
           'Use the relative band for prioritisation and upload observed adoption (Scheme Adoption) to bring real district variation in.</div>')

    c1, c2 = st.columns([1.5, 1])
    with c1:
        district_map(kb, d, "inclusion_index", "district", "relative_band", title="Inclusion index by district", tooltip_cols=["crop", "performance", "relative_band"], height=470)
    with c2:
        bar_chart(d.sort_values("inclusion_index").head(15), "district", "inclusion_index", "Lowest inclusion index — bottom 15", key="dist_low", height=470, color="relative_band",
                  color_map={"Upper third": "#1B7F4C", "Middle third": "#C97A00", "Lower third": "#B3261E"})
    _pillar_chart(d.sort_values("inclusion_index"), min(20, len(d)))

    st.subheader("Ranking")
    ranking_table(d, {"rank": ("Rank", "int"), "district": ("District", "str"), "state": ("State", "str"), "crop": ("Major crop", "str"), "inclusion_index": ("Index", "num"), "performance": ("Band (abs.)", "str"),
                      "relative_band": ("Band (relative)", "str"), "scheme_reach_pct": ("Scheme %", "pct"), "credit_reach_pct": ("Credit %", "pct"), "insurance_reach_pct": ("Insurance %", "pct"),
                      "subsidy_reach_pct": ("Subsidy %", "pct"), "avg_schemes": ("Avg schemes", "num"), "branches": ("KB branches", "int"), "coverage": ("KB coverage", "str")}, height=480)
    download_df(d, "Download district performance (CSV)", "district_performance.csv", "dl_dist")

    st.subheader("District drill-down")
    pick = st.selectbox("District", list(d["district"]), key="dist_pick")
    r = d[d["district"] == pick].iloc[0]
    m = state.get_matrix().districts(sc)
    m = m[m["district"] == pick]
    md(f'<div class="an-card"><div class="title">{esc(pick)}, {esc(r["state"])} {badge(r["relative_band"], {"Upper third": "green", "Middle third": "amber", "Lower third": "red"}[r["relative_band"]])}</div>'
       f'<div class="sub">Inclusion index {r["inclusion_index"]:.0f} · scheme depth {25 * r["p_scheme"]:.0f}/25 · credit {25 * r["p_credit"]:.0f}/25 · insurance {25 * r["p_insurance"]:.0f}/25 · subsidy {25 * r["p_subsidy"]:.0f}/25 · '
       f'major crop {esc(r["crop"] or "—")} · {int(r["branches"])} KB branches</div></div>')
    if len(m):
        ranking_table(m[["segment_label", "n_schemes_eligible", "top_scheme", "loan_rating", "crop_cover_available", "n_subsidies", "top_subsidy"]],
                      {"segment_label": ("Segment", "str"), "n_schemes_eligible": ("Schemes ≥50", "int"), "top_scheme": ("Top scheme", "str"), "loan_rating": ("Credit rating", "str"),
                       "crop_cover_available": ("Crop cover", "str"), "n_subsidies": ("Subsidies", "int"), "top_subsidy": ("Top subsidy", "str")})
    footer()
