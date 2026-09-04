"""📊 Government Report — downloadable Financial Inclusion & Scheme Monitoring Report (PDF + CSV)."""
from __future__ import annotations

from datetime import date

import streamlit as st

from ui.analytics_components import basis_badge, download_df, kpi_row, modelled_banner, ranking_table
from ui.analytics_pdf import build_inclusion_report
from ui.components import footer
from ui.pages.government._common import guard, header

SECTIONS = {"schemes": "Scheme reach", "districts": "District performance", "low": "Low-adoption / intervention areas", "segments": "Segments", "crops": "Crop-wise scheme association"}


def render() -> None:
    user = guard()
    sc, _, ii = header("📊 Government Report", user)
    modelled_banner("inclusion", ii.notes, ii.stale)
    k = ii.kpis
    kpi_row([("Scope", sc or "All KB districts", f"{k['districts']} districts"), ("Inclusion index", f"{k['inclusion_index']:.0f}/100", "modelled"),
             ("Scheme reach", f"{k['scheme_reach_pct']:.0f}%", ""), ("Insurance cover", f"{k['insurance_reach_pct']:.0f}%", ""), ("Flagged districts", str(k["low_districts"]), "")], basis_badge())
    st.subheader("Financial Inclusion & Scheme Monitoring Report (PDF)")
    chosen = st.multiselect("Sections", list(SECTIONS), default=list(SECTIONS), format_func=SECTIONS.get, key="gov_rep_sections")
    try:
        pdf = build_inclusion_report(ii, user, chosen)
        st.download_button("⬇️ Download PDF report", pdf, f"agrinexus_inclusion_{(sc or 'india').replace(' ', '_')}_{date.today().isoformat()}.pdf", "application/pdf", type="primary", key="dl_gov_pdf")
        st.caption(f"{len(pdf) / 1024:.0f} KB")
    except Exception as exc:
        st.error(f"PDF generation failed: {exc}")
    st.subheader("Data exports (CSV)")
    c = st.columns(5)
    with c[0]:
        download_df(ii.by_district, "Districts", "inclusion_districts.csv", "dl_g1")
    with c[1]:
        download_df(ii.by_scheme, "Schemes", "scheme_reach.csv", "dl_g2")
    with c[2]:
        download_df(ii.low_adoption, "Low adoption", "low_adoption.csv", "dl_g3")
    with c[3]:
        download_df(ii.by_segment, "Segments", "inclusion_segments.csv", "dl_g4")
    with c[4]:
        download_df(ii.by_crop_scheme, "Crop × scheme", "crop_scheme.csv", "dl_g5")
    st.subheader("Preview — district ranking")
    ranking_table(ii.by_district.head(10), {"rank": ("Rank", "int"), "district": ("District", "str"), "state": ("State", "str"), "inclusion_index": ("Index", "num"), "scheme_reach_pct": ("Scheme %", "pct"),
                                             "credit_reach_pct": ("Credit %", "pct"), "insurance_reach_pct": ("Insurance %", "pct"), "subsidy_reach_pct": ("Subsidy %", "pct"), "relative_band": ("Band", "str")})
    footer()
