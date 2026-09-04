"""🌾 Crop Trends — which crops carry credit demand, cover and product support (KB-derived)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from ui import state, theme
from ui.analytics_components import bar_chart, basis_badge, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import esc, footer, inr, md, plot
from ui.pages.bank._common import guard, header


def render() -> None:
    user = guard()
    sc, _, _, ci = header("🌾 Crop Trends", user)
    kb = state.get_kb()
    modelled_banner("credit", ci.notes, ci.stale)
    ct = ci.by_crop
    if ct.empty:
        st.info("No crop data in scope.")
        footer()
        return
    src = "state crop grid (12 major crops × all segments, one representative district)" if sc and len(state.get_matrix().crop_grid(sc)) else "district major crops in scope"
    st.caption(f"Source: {src}. Attractiveness = 40 product fit + 20 insurance cover + 20 subsidy depth + 20 crop-specific product availability (all KB-derived).")
    top = ct.iloc[0]
    kpi_row([("Crops analysed", str(len(ct)), src.split(" (")[0]),
             ("Most credit-attractive", top["crop"], f"score {top['credit_attractiveness']:.0f}/100"),
             ("Crop cover notified", f"{int((ct['crop_cover_pct'] >= 50).sum())} of {len(ct)}", "crop insurance product for the district"),
             ("Crop-specific products", f"{int(ct['crop_specific_products'].sum())}", "KB loan products tied to these crops"),
             ("Avg subsidies / profile", f"{ct['avg_subsidies'].mean():.1f}", "matched subsidies per archetype")], basis_badge())

    c1, c2 = st.columns([1.2, 1])
    with c1:
        bar_chart(ct, "crop", "credit_attractiveness", "Crop credit attractiveness (0-100)", key="ct_attr", height=420, text_fmt="%{text:.0f}")
    with c2:
        d = ct.copy()
        fig = px.scatter(d, x="avg_subsidies", y="fit_score", size="crop_specific_products", color="crop_cover_pct", text="crop", size_max=34,
                         color_continuous_scale=["#B3261E", "#C97A00", "#1B7F4C"], labels={"avg_subsidies": "Avg subsidies matched", "fit_score": "Best product fit (0-100)", "crop_cover_pct": "Cover %"})
        fig.update_traces(textposition="top center", textfont_size=10)
        fig.update_layout(title=dict(text="Fit vs subsidy support (bubble = crop-specific products)", font=dict(size=14, color=theme.INK)), height=420,
                          margin=dict(l=10, r=10, t=44, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        plot(fig, key="ct_scatter")

    st.subheader("Crop ranking")
    ranking_table(ct, {"crop": ("Crop", "str"), "market_category": ("Category", "str"), "credit_attractiveness": ("Attractiveness", "num"), "fit_score": ("Product fit", "num"),
                       "avg_loan_est_inr": ("Avg indicative ticket", "inr"), "crop_cover_pct": ("Cover %", "pct"), "avg_subsidies": ("Subsidies / profile", "num"),
                       "crop_specific_products": ("Crop-specific products", "int"), "kb_recommended_loans": ("KB recommended loans", "str"), "top_product": ("Top product", "str")})
    download_df(ct, "Download crop trends (CSV)", "crop_credit_trends.csv", "dl_ct")

    st.subheader("Where each crop is the major crop (KB district master)")
    geo = kb.geo if not sc else kb.geo[kb.geo.state_name == sc]
    cm = geo.groupby("major_crop", as_index=False).agg(districts=("district_name", "count"), names=("district_name", lambda s: ", ".join(sorted(s)[:8]) + ("…" if len(s) > 8 else "")))
    cm = cm[~cm["major_crop"].str.startswith("Not Applicable")].sort_values("districts", ascending=False)
    ranking_table(cm, {"major_crop": ("Major crop", "str"), "districts": ("Districts", "int"), "names": ("Districts (first 8)", "str")})
    st.caption("District → major-crop mapping is a KB reference table (one crop per district), not cropped-area statistics.")
    footer()
