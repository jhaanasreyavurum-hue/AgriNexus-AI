"""🏠 My Farm — farmer home: profile cards, eligibility cards, NEXT BEST ACTION."""
from __future__ import annotations

import streamlit as st

from core.auth import Role
from core.reasoning.financial_summary import summarise_finances
from ui import auth, onboarding, state
from ui.components import (badge, bar, demo_banner, esc, explanation_block, footer, inr, kpi, md, plot, gauge, score_color, why_expander)


def _farm_switcher(user) -> None:
    farms = state.demo_farms()
    with st.expander("Switch farm / start a new farm profile", expanded=False):
        c1, c2 = st.columns([2, 1])
        with c1:
            ids = [f["farm_id"] for f in farms]
            labels = {f["farm_id"]: f["farm_name"] for f in farms}
            pick = st.selectbox("Load a demo farm", ids, format_func=lambda i: labels[i], key="farm_pick")
            if st.button("Load demo farm", key="load_demo"):
                state.select_farm(pick)
                st.rerun()
        with c2:
            st.caption("Or create your own profile (4 steps).")
            if st.button("Start new farm profile", key="new_profile"):
                state.clear_context()
                st.session_state["onboard"] = {"step": 0, "data": {}}
                st.rerun()


def _no_farm(user, kb) -> None:
    md(f'<div class="an-hero" style="background:linear-gradient(120deg,#1B5E3B,#2E7D52)"><div class="eyebrow">Welcome, {esc(user.display_name)}</div>'
       '<div class="action">Let’s set up your farm so AgriNexus can find the loans, schemes, insurance and subsidies you may be eligible for.</div>'
       '<div class="why">Farmer profile → Farm details → Financial details → Analyze My Farm. Takes about two minutes.</div></div>')
    c1, c2 = st.columns([2.2, 1])
    with c1:
        onboarding.render(user, kb)
    with c2:
        md('<div class="an-card tight"><div class="title">Just exploring?</div><div class="sub">Load a demo farm (clearly labelled DEMO DATA) to see the full experience.</div></div>')
        for f in state.demo_farms():
            if st.button(f"Load {f['farm_name']}", key=f"demo_{f['farm_id']}"):
                state.select_farm(f["farm_id"])
                st.session_state.pop("onboard", None)
                st.rerun()


def render() -> None:
    user = auth.require(Role.FARMER)
    kb = state.get_kb()
    st.title("🏠 My Farm")
    if not state.has_context():
        _no_farm(user, kb)
        footer()
        return

    ctx = st.session_state["ctx"]
    demo_banner(ctx)
    if st.session_state.pop("just_analyzed", False):
        st.success("Farm profile saved — here is your analysis. Values you entered are labelled *User entered*; blanks are reported as not assessed.")
    _farm_switcher(user)

    a = state.get_assessment()
    kr = a.knowledge
    fs = summarise_finances(a)

    # ------------------------------------------------------------ NEXT BEST ACTION (financial)
    nba = fs.next_best_action
    md(f'<div class="an-hero"><div class="eyebrow">Next best action · {esc(nba.category)} · rule-based over knowledge-base results</div>'
       f'<div class="action">{esc(nba.action)}</div><div class="why">{esc(nba.explanation.summary)}</div>'
       f'<div class="meta"><span>Financial readiness {fs.financial_readiness:.0f}/100</span><span>{esc(fs.readiness_label)}</span>'
       f'<span>confidence {nba.confidence:.0%}</span>{"<span>DEMO DATA</span>" if ctx.is_demo else ""}</div></div>')
    with st.expander("Why this action? — factors, method & sources"):
        explanation_block(nba.explanation)
    if a.actions and a.next_best_action.category in ("irrigation", "protection", "nutrient", "monitoring"):
        md(f'<div class="an-note">🌱 <b>Agronomic priority right now:</b> {esc(a.next_best_action.action)} <span style="color:#6B7A72">— see Crop / Farm Intelligence.</span></div>')

    # ------------------------------------------------------------ four card groups
    f = kr.facts
    st.subheader("My farm")
    c = st.columns(5)
    with c[0]:
        kpi("Location", ctx.location.district, f"{ctx.location.state} · KB coverage {a.kb_coverage}")
    with c[1]:
        kpi("Land holding", f"{ctx.area_acres:.2f} ac", f"{ctx.area_hectares:.2f} ha · {f.category}")
    with c[2]:
        kpi("Crop · season", ctx.crop.current_crop or "not set", f"{ctx.crop.season or '—'} · {a.stage.current_stage or 'stage n/a'}")
    with c[3]:
        kpi("Irrigation", "yes" if ctx.irrigation.available else "rainfed", f"{ctx.irrigation.source or '—'} · {ctx.irrigation.reliability or ''}".strip(" ·"))
    with c[4]:
        kpi("Farm health", f"{a.health.score:.0f}" if a.health.score is not None else "n/a", f"{a.health.label} · confidence {a.health.confidence:.0%}")

    st.subheader("My financial profile")
    c = st.columns(5)
    with c[0]:
        kpi("Annual income", inr(fs.income_inr) if fs.income_inr else "not provided", "used for income limits")
    with c[1]:
        kpi("Existing loans", inr(fs.existing_loans_inr) if fs.existing_loans_inr else "none recorded",
            f"debt/income {fs.debt_to_income:.0%}" if fs.debt_to_income is not None and fs.existing_loans_inr else "")
    with c[2]:
        kpi("Indicative credit limit", inr(fs.estimated_credit_inr), f"{fs.credit_rating} · rule-based, not a sanction")
    with c[3]:
        kpi("Credit need", (ctx.finance.loan_purpose or "none").replace("_", " "), "KCC held" if f.has_kcc else "no KCC", badge("collateral", "grey") if ctx.finance.collateral_available else "")
    with c[4]:
        kpi("Documents", f"{fs.document_readiness_pct:.0f}% ready" if fs.document_readiness_pct is not None else "n/a",
            f"{len(fs.documents_missing)} to arrange for top matches" if fs.documents_missing else "key documents in hand")

    st.subheader("My eligibility & recommendations")
    cards = fs.cards()
    c = st.columns(3)
    with c[0]:
        kpi("Loan eligibility", cards["loan_eligibility"]["value"], cards["loan_eligibility"]["sub"], badge("KNOWLEDGE BASE", "green"))
        kpi("Potential subsidies", cards["potential_subsidies"]["value"], cards["potential_subsidies"]["sub"], badge("KNOWLEDGE BASE", "green"))
    with c[1]:
        kpi("Scheme matches", cards["scheme_matches"]["value"], cards["scheme_matches"]["sub"], badge("KNOWLEDGE BASE", "green"))
        kpi("Financial readiness", cards["financial_readiness"]["value"], cards["financial_readiness"]["sub"], badge("RULE-BASED", "grey"))
    with c[2]:
        kpi("Insurance matches", cards["insurance_matches"]["value"], cards["insurance_matches"]["sub"], badge("KNOWLEDGE BASE", "green"))
        top_loan = kr.loans.products[0] if kr.loans.products else None
        kpi("Recommended loan", top_loan.title if top_loan else "—", f"{top_loan.score:.0f}% match · {top_loan.payload.get('interest_rate')}" if top_loan else "no match", badge("KNOWLEDGE BASE", "green"))

    # ------------------------------------------------------------ readiness + top matches
    left, right = st.columns([1, 1.4])
    with left:
        st.subheader("Financial readiness")
        plot(gauge(fs.financial_readiness, fs.readiness_label, score_color(fs.financial_readiness)), key="readiness_gauge")
        why_expander(fs.readiness_explanation, "How readiness is scored", key="readiness_why")
        if fs.profile_gaps:
            md('<div class="an-note">Add <b>' + esc(", ".join(fs.profile_gaps)) + "</b> to sharpen your matches (Crop / Farm Intelligence → Edit farm).</div>")
    with right:
        st.subheader("Top matches")
        rows = []
        for m in kr.loans.products[:2]:
            rows.append(("💰 Loan", m.title, m.score, f"{m.payload.get('interest_rate')} · up to {inr(m.payload.get('amount_max'))}"))
        for m in kr.schemes[:2]:
            rows.append(("🎯 Scheme", m.title, m.score, m.payload.get("scheme_type") or ""))
        for m in kr.insurance[:1]:
            rows.append(("🛡️ Insurance", m.title, m.score, m.payload.get("covered_risk") or ""))
        for m in kr.subsidies[:1]:
            rows.append(("💸 Subsidy", m.title, m.score, f"up to {inr(m.payload.get('maximum_amount'))}" if m.payload.get("maximum_amount") else ""))
        for kind, title, score, sub in rows:
            md(f'<div class="an-card tight" style="display:flex;justify-content:space-between;gap:.8rem;align-items:center">'
               f'<div><div style="font-size:.74rem;color:#6B7A72;font-weight:600">{kind}</div><div class="title" style="font-size:.95rem">{esc(title)}</div><div class="sub">{esc(sub)}</div></div>'
               f'<div style="min-width:120px;text-align:right"><b style="color:{score_color(score)}">{score:.0f}%</b>{bar(score, score_color(score))}</div></div>')
        st.caption("Open Loans, Government Schemes and Insurance for full cards with documents and reasons.")

    if fs.documents_missing:
        st.subheader("Documents to arrange")
        md("".join(f'<div class="an-doc miss">✗ {esc(d)}</div>' for d in fs.documents_missing))
    footer()
