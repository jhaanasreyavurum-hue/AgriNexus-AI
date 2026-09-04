"""👥 Farmer Segments — eligibility, demand and product fit by farmer archetype (KB eligibility logic)."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from core.intelligence import SEGMENTS
from ui import state
from ui.analytics_components import bar_chart, basis_badge, donut, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import badge, esc, footer, inr, md, table
from ui.pages.bank._common import guard, header


def _segment_detail(seg_id: str, sc, matrix) -> None:
    d = matrix.districts(sc)
    d = d[d["segment_id"] == seg_id]
    if d.empty:
        st.caption("No rows.")
        return
    # product frequency for this segment (top products across districts)
    rows = []
    for _, r in d.iterrows():
        try:
            for p in json.loads(r["loan_products_json"]):
                rows.append(p)
        except Exception:
            pass
    if rows:
        p = pd.DataFrame(rows)
        g = p.groupby(["title", "bank", "type"], as_index=False).agg(avg_score=("score", "mean"), districts=("title", "count"), amount_max=("amount_max", "max"), rate=("rate", "min"))
        g = g.sort_values("avg_score", ascending=False).head(8)
        ranking_table(g, {"title": ("Product", "str"), "bank": ("Bank", "str"), "type": ("Type", "str"), "avg_score": ("Avg match", "num"), "amount_max": ("Max amount", "inr"), "rate": ("Min rate %", "num")})
    s = [x for x in SEGMENTS if x.segment_id == seg_id][0]
    md(f'<div class="an-card tight"><div class="title">Archetype assumptions</div><div class="sub">{s.acres:g} acres · income ₹{s.annual_income_inr:,.0f}/yr · '
       f'{"irrigated (" + (s.irrigation_reliability or "") + ")" if s.irrigated else "rainfed"} · {s.land_ownership} · {"KCC holder" if s.has_kcc else "no KCC"} · '
       f'{"collateral" if s.collateral else "no collateral"} · documents: {esc(", ".join(s.documents_held))} · default household share {s.default_share:.0%}</div></div>')


def render() -> None:
    user = guard()
    sc, _, crop, ci = header("👥 Farmer Segments", user, with_crop=True)
    modelled_banner("credit", ci.notes, ci.stale)
    seg = ci.by_segment
    if seg.empty:
        st.info("No data in scope.")
        footer()
        return
    best = seg.iloc[0]
    worst = seg.sort_values("eligible_pct").iloc[0]
    kpi_row([("Segments modelled", str(len(seg)), "explicit archetypes (holding · social · tenure · allied)"),
             ("Largest modelled demand", best["segment_label"], inr(best["demand_inr"])),
             ("Least eligible", worst["segment_label"], f"{worst['eligible_pct']:.0f}% eligible · {worst['rating']}"),
             ("Small & marginal share of demand", f"{100 * seg[seg['tags'].str.contains('small_marginal')]['demand_inr'].sum() / max(seg['demand_inr'].sum(), 1):.0f}%", "priority-sector relevance"),
             ("Women archetype eligible", f"{seg[seg['segment_id'] == 'WOMEN_MARG']['eligible_pct'].iat[0]:.0f}%" if (seg["segment_id"] == "WOMEN_MARG").any() else "—", "women · marginal")], basis_badge())

    c1, c2 = st.columns([1.3, 1])
    with c1:
        bar_chart(seg, "segment_label", "demand_inr", "Modelled loan demand by segment (₹)", key="seg_demand", height=420, color="segment_group")
    with c2:
        donut(seg, "segment_label", "households", "Household share (scenario assumption)", key="seg_share", height=420)
    c3, c4 = st.columns(2)
    with c3:
        bar_chart(seg, "segment_label", "avg_loan_est_inr", "Average indicative ticket by segment (₹)", key="seg_ticket", height=380)
    with c4:
        bar_chart(seg, "segment_label", "eligible_pct", "Potentially eligible (%)", key="seg_elig", height=380, text_fmt="%{text:.0f}%")

    st.subheader("Segment table")
    ranking_table(seg, {"segment_label": ("Segment", "str"), "segment_group": ("Group", "str"), "tags": ("Tags", "str"), "households": ("Households", "int"), "eligible_pct": ("Eligible %", "pct"),
                        "rating": ("Typical rating", "str"), "avg_loan_est_inr": ("Avg ticket", "inr"), "demand_inr": ("Modelled demand", "inr"), "avg_products": ("Products ≥50", "num"),
                        "top_loan_type": ("Top loan type", "str"), "doc_readiness": ("Docs ready %", "pct")})
    download_df(seg, "Download segment table (CSV)", "farmer_segments.csv", "dl_seg")

    st.subheader("Segment drill-down")
    pick = st.selectbox("Segment", list(seg["segment_id"]), format_func=lambda i: seg.set_index("segment_id").loc[i, "segment_label"], key="seg_pick")
    _segment_detail(pick, sc, state.get_matrix())
    st.caption("Product ranking = the real Loan Advisor run for this archetype in every district of the scope; scores are KB match scores, not approval rates.")
    footer()
