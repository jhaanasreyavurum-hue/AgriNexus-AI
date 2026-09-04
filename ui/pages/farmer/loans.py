"""💰 Loans — personalised loan advisor, EMI calculator, product comparison, branches."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.finance import amortisation_schedule, compare_products, emi
from ui import theme
from ui.components import badge, esc, explanation_block, footer, inr, kpi, md, plot, table
from ui.match_cards import loan_card
from ui.pages.farmer._common import guard_with_farm


def _emi_section(products) -> None:
    st.subheader("EMI calculator")
    st.caption("Deterministic reducing-balance arithmetic — not a bank quote. Pre-filled from your best-matched product; change any value.")
    top = products[0] if products else None
    default_amt = int(min(max((top.payload.get("amount_min") or 50_000), 100_000), top.payload.get("amount_max") or 500_000)) if top else 200_000
    default_rate = float(top.payload.get("min_interest") or 7.0) if top else 7.0
    default_months = int((top.payload.get("repayment_years") or 1) * 12) if top else 12
    c1, c2, c3 = st.columns(3)
    amount = c1.number_input("Loan amount ₹", 1_000, 100_000_000, value=default_amt, step=10_000, key="emi_amt")
    rate = c2.number_input("Annual interest rate %", 0.0, 40.0, value=default_rate, step=0.25, key="emi_rate")
    months = c3.number_input("Tenure (months)", 1, 360, value=default_months, step=6, key="emi_months")
    try:
        r = emi(amount, rate, int(months))
    except ValueError as exc:
        st.error(str(exc))
        return
    k = st.columns(4)
    with k[0]:
        kpi("Monthly EMI", inr(r.emi), f"{int(months)} months")
    with k[1]:
        kpi("Total interest", inr(r.total_interest), f"{100 * r.total_interest / amount:.1f}% of principal")
    with k[2]:
        kpi("Total repayment", inr(r.total_repayment), "principal + interest")
    with k[3]:
        kpi("Effective rate", f"{rate:.2f}% p.a.", "reducing balance", badge("RULE-BASED", "grey"))
    with st.expander("Amortisation schedule & chart"):
        sched = amortisation_schedule(amount, rate, int(months))
        fig = go.Figure()
        fig.add_trace(go.Bar(x=sched["month"], y=sched["principal"], name="Principal", marker_color=theme.GREEN))
        fig.add_trace(go.Bar(x=sched["month"], y=sched["interest"], name="Interest", marker_color=theme.AMBER))
        fig.update_layout(barmode="stack", height=280, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h"), xaxis_title="Month", yaxis_title="₹")
        plot(fig, key="amort_chart")
        table(sched.rename(columns={"month": "Month", "emi": "EMI", "interest": "Interest", "principal": "Principal", "balance": "Balance"}), height=260)
        st.download_button("Download schedule (CSV)", sched.to_csv(index=False).encode(), "emi_schedule.csv", "text/csv", key="dl_sched")

    if products:
        st.subheader("Compare matched products at this amount")
        st.caption("Each product at its KB minimum published rate and default tenure (or the tenure above if 'same tenure' is ticked). Products whose amount range excludes this principal are flagged.")
        same = st.checkbox("Use the same tenure for all products", value=False, key="cmp_same_tenure")
        rows = [{"title": m.title, "bank_short": m.payload.get("bank_short"), "min_interest": m.payload.get("min_interest"), "repayment_years": m.payload.get("repayment_years"),
                 "amount_min": m.payload.get("amount_min"), "amount_max": m.payload.get("amount_max"), "score": round(m.score)} for m in products[:8]]
        cmp = compare_products(rows, amount, int(months) if same else None)
        show = cmp.rename(columns={"product": "Product", "bank": "Bank", "rate_pct": "Rate %", "tenure_months": "Tenure (mo)", "emi": "EMI ₹", "total_interest": "Total interest ₹",
                                   "total_repayment": "Total repayment ₹", "amount_within_product_range": "Amount in range", "match_score": "Match %"})
        for c in ("EMI ₹", "Total interest ₹", "Total repayment ₹"):
            show[c] = show[c].map(lambda v: f"{v:,.0f}")
        show["Amount in range"] = show["Amount in range"].map({True: "✓", False: "✗ outside range"})
        table(show)


def render() -> None:
    user, ctx, a = guard_with_farm("💰 Loans")
    kr = a.knowledge
    la = kr.loans
    f = kr.facts

    c = st.columns(5)
    with c[0]:
        kpi("Indicative eligibility", inr(la.estimated_eligibility_inr), "from KB product caps · not a sanction", badge("RULE-BASED", "grey"))
    with c[1]:
        kpi("Eligibility rating", la.eligibility_rating, f"{la.rating_score:.0f}/100")
    with c[2]:
        kpi("Credit need", (la.purpose or "not specified").replace("_", " "), ", ".join(la.relevant_loan_types[:2]))
    with c[3]:
        kpi("Products matched", str(len(la.products)), f"{sum(1 for m in la.products if m.score >= 75)} strong", badge("KNOWLEDGE BASE", "green"))
    with c[4]:
        kpi("Branches in district", str(len(la.branches)), la.branch_coverage_note[:70])
    with st.expander("How the indicative eligibility was derived — factors, method, sources"):
        explanation_block(la.explanation, limit=10)
    if f.is_tenant_or_sharecropper and "Tenant Farmer / Sharecropper Certificate" not in f.documents_held:
        md('<div class="an-warn">You are a tenant / sharecropper without a cultivation certificate on record. Most banks need a Tenant Farmer / Cultivator certificate (or a JLG route) before a crop loan — get it from the Revenue / Agriculture office first.</div>')

    tabs = st.tabs([f"Recommended loans ({len(la.products)})", "EMI calculator & comparison", f"Bank branches ({len(la.branches)})"])
    with tabs[0]:
        st.caption("Ranked by fit to your purpose, collateral, crop, amount vs eligibility, interest and government linkage. Each card shows match score, amount range, interest, tenure, collateral, documents and the reason.")
        if not la.products:
            st.info("No loan product in the KB matches the stated purpose and profile. Set a credit need in your profile (My Farm → new profile) to enable matching.")
        for i, m in enumerate(la.products[:8], 1):
            loan_card(m, i, f"loan{i}")
    with tabs[1]:
        _emi_section(la.products)
    with tabs[2]:
        if la.branches:
            df = pd.DataFrame(la.branches)
            df["offers_matched_product"] = df["offers_matched_product"].map({True: "★ yes", False: ""})
            table(df[["bank_name", "branch_name", "ifsc", "phone", "working_days", "insurance_available", "offers_matched_product"]]
                  .rename(columns={"bank_name": "Bank", "branch_name": "Branch", "ifsc": "IFSC", "phone": "Phone", "working_days": "Days",
                                   "insurance_available": "Insurance desk", "offers_matched_product": "Offers a matched product"}))
            pts = df.dropna(subset=["latitude", "longitude"])
            if len(pts):
                st.map(pts.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]], size=40, zoom=9)
            st.caption("Take your document checklist and the My Report PDF when you visit the branch.")
        else:
            md(f'<div class="an-warn">{esc(la.branch_coverage_note)}</div>')
    footer()
