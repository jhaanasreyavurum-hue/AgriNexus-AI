"""Match-result card renderers shared by the farmer modules and the legacy
Finance & Schemes page. Pure presentation of ``MatchResult`` objects."""
from __future__ import annotations

import streamlit as st

from ui.components import badge, doc_checklist, esc, explanation_block, inr, match_header, md, positives_and_limits


def scheme_card(m, rank: int, key: str) -> None:
    p = m.payload
    benefit = []
    if p.get("maximum_subsidy"):
        benefit.append(f"up to {inr(p['maximum_subsidy'])}")
    if p.get("subsidy_percentage"):
        benefit.append(f"{p['subsidy_percentage']:.0f}% support")
    if p.get("interest_subvention"):
        benefit.append(f"interest subvention {p['interest_subvention']}")
    if p.get("loan_support"):
        benefit.append("loan-linked")
    chips = [p.get("scheme_type"), p.get("government_level"), p.get("state"), f"docs {p.get('document_readiness_pct', 0):.0f}% ready"]
    with st.container(border=True):
        match_header(m, rank, p.get("objective") or p.get("description") or "", chips)
        if benefit:
            md(f'<div style="margin:.35rem 0"><b>Benefit:</b> {esc(" · ".join(benefit))}'
               + (f' &nbsp;·&nbsp; <b>Apply:</b> {esc(p.get("application_mode"))}' if p.get("application_mode") else "")
               + (f' &nbsp;·&nbsp; <b>Processing:</b> ~{p["processing_time_days"]} days' if p.get("processing_time_days") else "") + "</div>")
        positives_and_limits(m)
        if p.get("kb_overrides"):
            md(f'<div class="an-note" style="margin-top:.4rem">KB record corrected via kb_overrides.yaml: {esc(", ".join(p["kb_overrides"]))}.</div>')
        t1, t2, t3 = st.tabs(["📄 Documents", "🔍 Why this score", "ℹ️ Scheme details"])
        with t1:
            doc_checklist(m)
        with t2:
            explanation_block(m.explanation, limit=10)
        with t3:
            md(f'<div style="font-size:.88rem">{esc(p.get("description") or "")}</div>')
            rows = [("Ministry", p.get("ministry")), ("Beneficiary type", p.get("beneficiary_type")), ("KB eligible crop", p.get("eligible_crop")),
                    ("KB eligible farmer", p.get("eligible_farmer")), ("Land range (ac)", " – ".join(str(x) for x in p.get("land_range_acres", []) if x is not None) or None),
                    ("Income limit", inr(p["income_limit"]) if p.get("income_limit") else None),
                    ("Age range", " – ".join(str(x) for x in p.get("age_range", []) if x is not None) or None),
                    ("Official portal", p.get("official_portal")), ("Rules fired", ", ".join(p.get("fired_rules", [])) or None),
                    ("AI-rule ids", ", ".join(str(x) for x in p.get("ai_rules", [])) or None)]
            md("".join(f'<div style="font-size:.84rem"><b>{esc(k)}:</b> {esc(v)}</div>' for k, v in rows if v))


def loan_card(m, rank: int, key: str) -> None:
    p = m.payload
    chips = [p.get("loan_type"), f"{inr(p['amount_min'])} – {inr(p['amount_max'])}", f"{p.get('repayment_years')} yr tenure",
             "no collateral" if not p.get("collateral_required") else "collateral required", f"approval ~{p.get('approval_days')} d",
             f"docs {p.get('document_readiness_pct', 0):.0f}% ready"]
    with st.container(border=True):
        match_header(m, rank, f"{p.get('bank')} · {p.get('interest_rate')}" + (f" · processing fee {p.get('processing_fee')}" if p.get("processing_fee") else ""), chips)
        positives_and_limits(m)
        t1, t2, t3 = st.tabs(["📄 Documents", "🔍 Why this score", "ℹ️ Product details"])
        with t1:
            doc_checklist(m)
        with t2:
            explanation_block(m.explanation, limit=10)
        with t3:
            md(f'<div style="font-size:.88rem">{esc(p.get("eligibility_summary") or "")}</div>')
            rows = [("Government linked", "yes" if p.get("government_linked") else "no"), ("Max subsidy", inr(p["maximum_subsidy"]) if p.get("maximum_subsidy") else None),
                    ("Interest range", f"{p.get('min_interest')}% – {p.get('max_interest')}%"), ("KB loan score", p.get("loan_score"))]
            md("".join(f'<div style="font-size:.84rem"><b>{esc(k)}:</b> {esc(v)}</div>' for k, v in rows if v is not None))


def insurance_card(m, rank: int, key: str) -> None:
    p = m.payload
    chips = [p.get("coverage_type"), f"covers: {p.get('covered_crop')}", f"risk: {p.get('covered_risk')}",
             f"farmer premium ≈{p.get('farmer_premium_pct')}%", f"govt subsidy {p.get('government_subsidy_pct'):.0f}%" if p.get("government_subsidy_pct") is not None else None]
    with st.container(border=True):
        match_header(m, rank, f"{p.get('provider')} · notified: {p.get('district_applicable')}", chips)
        cols = st.columns(4)
        cols[0].metric("Sum insured (KB)", inr(p.get("coverage_amount")))
        cols[1].metric("Gross premium", f"{p.get('premium_pct')}%")
        cols[2].metric("Farmer share ≈", f"{p.get('farmer_premium_pct')}%")
        cols[3].metric("Indicative farmer premium", inr(p.get("indicative_farmer_premium_inr")))
        if p.get("risk_hits"):
            md(f'<div style="margin:.2rem 0">{badge("covers active risk: " + ", ".join(h.replace("_", " ") for h in p["risk_hits"]), "red")}</div>')
        positives_and_limits(m)
        t1, t2, t3 = st.tabs(["📄 Documents", "🔍 Why this score", "ℹ️ Claims"])
        with t1:
            doc_checklist(m)
        with t2:
            explanation_block(m.explanation, limit=10)
        with t3:
            md(f'<div style="font-size:.86rem"><b>Claim period:</b> {esc(p.get("claim_period"))}<br><b>Process:</b> {esc(p.get("claim_process"))}<br>'
               f'<b>Eligible farmer (KB):</b> {esc(p.get("eligible_farmer"))}</div>')


def subsidy_card(m, rank: int, key: str) -> None:
    p = m.payload
    chips = [p.get("subcategory"), p.get("scheme_name"), p.get("state"), f"docs {p.get('document_readiness_pct', 0):.0f}% ready"]
    with st.container(border=True):
        match_header(m, rank, p.get("eligibility") or "", chips)
        md(f'<div style="margin:.3rem 0"><b>Benefit:</b> up to {inr(p.get("maximum_amount"))}'
           + (f' ({p["percentage"]:.0f}% of cost)' if p.get("percentage") else "")
           + (f' &nbsp;·&nbsp; <b>Relevant because:</b> {esc(", ".join(h.replace("_", " ") for h in p["need_hits"]))}' if p.get("need_hits") else "") + "</div>")
        positives_and_limits(m)
        t1, t2, t3 = st.tabs(["📄 Documents", "🔍 Why this score", "ℹ️ How to apply"])
        with t1:
            doc_checklist(m)
        with t2:
            explanation_block(m.explanation, limit=10)
        with t3:
            md(f'<div style="font-size:.86rem">{esc(p.get("application_process") or "Not specified in KB.")}</div>')


