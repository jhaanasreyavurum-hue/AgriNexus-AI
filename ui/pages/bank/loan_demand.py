"""💳 Loan Demand — modelled demand by district, crop, product and bank."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import state
from ui.analytics_components import bar_chart, basis_badge, donut, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import footer, inr, md
from ui.pages.bank._common import guard, header


def render() -> None:
    user = guard()
    sc, tags, crop, ci = header("💳 Loan Demand", user, with_segments=True, with_crop=True)
    modelled_banner("credit", ci.notes, ci.stale)
    k = ci.kpis
    kpi_row([("Potential loan demand", inr(k["demand_inr"]), f"{k['districts']} district(s) · modelled"),
             ("Per 10,000 households", inr(k["demand_per_10k_inr"]), "normalised demand density"),
             ("Potentially eligible", f"{k['eligible_households']:,.0f}", f"{k['eligible_pct']:.0f}% of modelled households"),
             ("Average ticket", inr(k["avg_ticket_inr"]), "demand ÷ eligible households"),
             ("Top product type", k["top_loan_type"] or "—", k["top_product"] or "")], basis_badge())

    tabs = st.tabs(["By district", "By product", "By bank", "Demand table"])
    with tabs[0]:
        c1, c2 = st.columns([1.3, 1])
        with c1:
            bar_chart(ci.by_district.head(15), "district", "demand_inr", "Modelled loan demand — top districts (₹)", key="ld_dist", height=460, color="potential",
                      color_map={"High": "#1B7F4C", "Medium": "#C97A00", "Low": "#B3261E"})
        with c2:
            bar_chart(ci.by_district.head(15), "district", "eligible_pct", "Potentially eligible households (%)", key="ld_elig", height=460, text_fmt="%{text:.0f}%")
        if len(ci.by_district) and ci.by_district["demand_inr"].nunique() <= 2 and sc:
            md('<div class="an-note">Districts within one state share the same KB eligibility rules and product set, so modelled demand per household is identical across them; '
               'differences arise from the district major crop (insurance cover, crop-specific products) and branch access. Upload observed household counts in the scenario to weight districts.</div>')
    with tabs[1]:
        c1, c2 = st.columns([1.3, 1])
        with c1:
            bar_chart(ci.by_product.head(15), "product", "eligible_households", "Product demand — modelled eligible households", key="ld_prod", height=480)
        with c2:
            donut(ci.by_product.groupby("loan_type", as_index=False)["eligible_households"].sum(), "loan_type", "eligible_households", "Loan-type mix", key="ld_type", height=480)
        ranking_table(ci.by_product.head(25), {"product": ("Product", "str"), "bank": ("Bank", "str"), "loan_type": ("Type", "str"),
                                                "eligible_households": ("Eligible households", "int"), "avg_score": ("Avg match score", "num"), "districts": ("Districts", "int")})
    with tabs[2]:
        st.caption("KB branch presence (agri-loan desks) vs modelled households for which the bank's products score as eligible. A bank with high modelled demand but few desks is under-distributed.")
        bar_chart(ci.by_bank, "bank_name", "modelled_eligible_households", "Bank reach — modelled eligible households", key="ld_bank", height=380)
        ranking_table(ci.by_bank, {"bank_name": ("Bank", "str"), "branches": ("KB branches", "int"), "loan_desks": ("Agri-loan desks", "int"), "districts": ("Districts served", "int"),
                                   "products": ("Products matched", "int"), "modelled_eligible_households": ("Modelled eligible households", "int")})
        if user.bank_name:
            mine = ci.by_bank[ci.by_bank["bank_name"].str.contains(user.bank_name.split()[0], case=False, na=False)]
            if len(mine):
                r = mine.iloc[0]
                md(f'<div class="an-note">🏦 <b>{r["bank_name"]}</b> (your bank): {int(r["branches"])} KB branches, {int(r["loan_desks"])} agri-loan desks in {int(r["districts"])} districts; '
                   f'{int(r["modelled_eligible_households"]):,} modelled eligible households across {int(r["products"])} matched products.</div>')
    with tabs[3]:
        ranking_table(ci.by_district, {"district": ("District", "str"), "state": ("State", "str"), "crop": ("Major crop", "str"), "households": ("Households (scenario)", "int"),
                                       "eligible_households": ("Eligible", "int"), "eligible_pct": ("Eligible %", "pct"), "demand_inr": ("Modelled demand", "inr"),
                                       "avg_loan_est_inr": ("Avg ticket", "inr"), "loan_desks": ("KB loan desks", "int"), "potential": ("Potential", "str")}, height=520)
        download_df(ci.by_district, "Download district demand (CSV)", "modelled_loan_demand_by_district.csv", "dl_ld")
    footer()
