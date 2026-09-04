"""🗺️ High-Potential Areas — map + ranking of districts by modelled credit potential."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import state
from ui.analytics_components import bar_chart, basis_badge, district_map, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import badge, esc, footer, inr, md
from ui.pages.bank._common import guard, header


def render() -> None:
    user = guard()
    sc, tags, crop, ci = header("🗺️ High-Potential Areas", user, with_segments=True, with_crop=True)
    kb = state.get_kb()
    modelled_banner("credit", ci.notes, ci.stale)
    d = ci.by_district
    if d.empty:
        st.info("No districts in scope.")
        footer()
        return
    counts = d["potential"].value_counts()
    kpi_row([("High potential", str(int(counts.get("High", 0))), "score ≥ 67"), ("Medium potential", str(int(counts.get("Medium", 0))), "score 40–66"),
             ("Low potential", str(int(counts.get("Low", 0))), "score < 40"), ("Untapped (no KB loan desk)", str(int((d["credit_opportunity"].str.startswith("No KB")).sum())), "demand exists, no desk listed"),
             ("Thin branch presence", str(int((d["credit_opportunity"] == "Thin branch presence").sum())), "≤3 agri-loan desks")], basis_badge())
    st.caption("Potential score (0-100) = 30 × demand density + 25 × product fit + 15 × crop cover notified + 30 × under-served bonus (few KB agri-loan desks). All inputs are KB-derived; the under-served bonus rewards districts where demand is modelled but branch access is thin.")

    level = st.radio("Show", ["All", "High", "Medium", "Low"], horizontal=True, key="area_level")
    view = d if level == "All" else d[d["potential"] == level]
    c1, c2 = st.columns([1.5, 1])
    with c1:
        district_map(kb, view, "potential_score", "district", "potential", title="District credit potential", tooltip_cols=["crop", "potential", "credit_opportunity"], height=470)
    with c2:
        bar_chart(view.head(15), "district", "potential_score", "Potential score — top districts", key="area_bar", height=470, color="potential",
                  color_map={"High": "#1B7F4C", "Medium": "#C97A00", "Low": "#B3261E"})

    st.subheader("Ranking")
    ranking_table(view, {"district": ("District", "str"), "state": ("State", "str"), "crop": ("Major crop", "str"), "potential_score": ("Score", "num"), "potential": ("Potential", "str"),
                         "demand_per_10k_inr": ("Demand / 10k HH", "inr"), "eligible_pct": ("Eligible %", "pct"), "fit_score": ("Product fit", "num"), "crop_cover": ("Crop cover", "str"),
                         "loan_desks": ("KB loan desks", "int"), "branches": ("KB branches", "int"), "credit_opportunity": ("Opportunity", "str")}, height=480)
    download_df(view, "Download ranking (CSV)", "high_potential_areas.csv", "dl_areas")

    st.subheader("District drill-down")
    pick = st.selectbox("District", list(d["district"]), key="area_pick")
    r = d[d["district"] == pick].iloc[0]
    m = state.get_matrix().districts(sc)
    m = m[m["district"] == pick]
    md(f'<div class="an-card"><div class="title">{esc(pick)}, {esc(r["state"])} {badge(r["potential"] + " potential", {"High": "green", "Medium": "amber", "Low": "red"}[r["potential"]])}</div>'
       f'<div class="sub">Major crop {esc(r["crop"] or "—")} · KB coverage {esc(r["coverage"])} · {int(r["branches"])} KB branches ({int(r["loan_desks"])} agri-loan desks) · '
       f'crop cover {"notified" if r["crop_cover"] else "not notified"} · modelled demand {inr(r["demand_inr"])} · eligible {r["eligible_pct"]:.0f}%</div></div>')
    if len(m):
        show = m[["segment_label", "loan_est_inr", "loan_rating", "n_loan_products_eligible", "top_loan_product", "top_loan_score", "n_schemes_eligible", "crop_cover_available"]].copy()
        ranking_table(show, {"segment_label": ("Segment", "str"), "loan_est_inr": ("Indicative ticket", "inr"), "loan_rating": ("Rating", "str"), "n_loan_products_eligible": ("Products ≥50", "int"),
                             "top_loan_product": ("Top product", "str"), "top_loan_score": ("Top score", "num"), "n_schemes_eligible": ("Schemes", "int"), "crop_cover_available": ("Crop cover", "str")})
    br = kb.branches[(kb.branches["district"].str.lower() == pick.lower())]
    if len(br):
        st.caption("KB branches in this district")
        ranking_table(br[["bank_name", "branch_name", "ifsc", "loan_available", "insurance_available", "government_linked"]],
                      {"bank_name": ("Bank", "str"), "branch_name": ("Branch", "str"), "ifsc": ("IFSC", "str"), "loan_available": ("Agri loans", "str"), "insurance_available": ("Insurance", "str"), "government_linked": ("Govt-linked", "str")})
    footer()
