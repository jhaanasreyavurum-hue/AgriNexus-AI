"""📊 Analytics Report — downloadable Agricultural Credit Intelligence Report (PDF + CSV)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from ui.analytics_components import basis_badge, download_df, kpi_row, modelled_banner, ranking_table
from ui.analytics_pdf import build_credit_report
from ui.components import footer, inr, md
from ui.pages.bank._common import guard, header

SECTIONS = {"districts": "High-potential districts", "segments": "Farmer segments", "crops": "Crop credit trends", "products": "Product demand", "banks": "Bank presence vs reach"}


def render() -> None:
    user = guard()
    sc, _, _, ci = header("📊 Analytics Report", user)
    modelled_banner("credit", ci.notes, ci.stale)
    k = ci.kpis
    kpi_row([("Scope", sc or "All KB districts", f"{k['districts']} districts"), ("Potential demand", inr(k["demand_inr"]), "modelled"),
             ("Eligible households", f"{k['eligible_households']:,.0f}", f"{k['eligible_pct']:.0f}%"), ("High-potential districts", str(k["high_potential_districts"]), ""),
             ("Top product", k["top_product"] or "—", k["top_loan_type"] or "")], basis_badge())
    st.subheader("Agricultural Credit Intelligence Report (PDF)")
    st.caption("Every figure is a modelled indicator already shown in the dashboard; the report prints the basis, scenario and method on page 1 and in the footer of every page.")
    chosen = st.multiselect("Sections", list(SECTIONS), default=list(SECTIONS), format_func=SECTIONS.get, key="bank_rep_sections")
    try:
        pdf = build_credit_report(ci, user, chosen)
        st.download_button("⬇️ Download PDF report", pdf, f"agrinexus_credit_intelligence_{(sc or 'india').replace(' ', '_')}_{date.today().isoformat()}.pdf", "application/pdf", type="primary", key="dl_bank_pdf")
        st.caption(f"{len(pdf) / 1024:.0f} KB")
    except Exception as exc:
        st.error(f"PDF generation failed: {exc}")
    st.subheader("Data exports (CSV)")
    c = st.columns(5)
    with c[0]:
        download_df(ci.by_district, "Districts", "credit_districts.csv", "dl_r1")
    with c[1]:
        download_df(ci.by_segment, "Segments", "credit_segments.csv", "dl_r2")
    with c[2]:
        download_df(ci.by_crop, "Crops", "credit_crops.csv", "dl_r3")
    with c[3]:
        download_df(ci.by_product, "Products", "credit_products.csv", "dl_r4")
    with c[4]:
        download_df(ci.by_bank, "Banks", "credit_banks.csv", "dl_r5")
    st.subheader("Preview — top districts")
    ranking_table(ci.by_district.head(10), {"district": ("District", "str"), "state": ("State", "str"), "crop": ("Crop", "str"), "demand_inr": ("Demand", "inr"), "eligible_pct": ("Eligible %", "pct"),
                                             "potential_score": ("Score", "num"), "potential": ("Potential", "str"), "credit_opportunity": ("Opportunity", "str")})
    footer()
