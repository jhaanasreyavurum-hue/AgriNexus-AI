"""💰 Finance & Schemes — Scheme Finder, Loan Advisor, Insurance, Subsidies,
Document Resolver, Opportunity Engine. Renders Phase-3 MatchResults as cards."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import state
from ui.components import (badge, bar, demo_banner, doc_checklist, esc, explanation_block, footer, inr, kpi, match_header, md,
                           opportunity_card, plot, positives_and_limits, score_bars, score_color, table)
from ui.match_cards import insurance_card as _insurance_card, loan_card as _loan_card, scheme_card as _scheme_card, subsidy_card as _subsidy_card


def render() -> None:
    ctx = state.ensure_context()
    st.title("💰 Finance & Schemes")
    demo_banner(ctx)
    a = state.get_assessment()
    kr = a.knowledge
    if kr is None:
        st.error("Knowledge engines did not run.")
        return
    f = kr.facts
    md(f'<div class="an-note">{esc(kr.coverage_note)}</div>')

    # ------------------------------------------------------------ profile strip
    c = st.columns(6)
    with c[0]:
        kpi("Farmer category", f.category, f"{f.acres:.2f} ac · {f.hectares:.2f} ha")
    with c[1]:
        kpi("Annual income", inr(f.income) if f.income else "not provided", "used for income-limit checks")
    with c[2]:
        kpi("Profile", ", ".join(x.replace("_", " ") for x in f.profile_attrs if x != "any") or "—", ("livestock" if f.livestock else "no livestock"))
    with c[3]:
        kpi("Documents on record", str(len(f.documents_held)), "incl. implied by profile")
    with c[4]:
        kpi("KB rules fired", f"{len(kr.fired_eligibility_rules)} + {len(kr.fired_ai_rules)}", "eligibility + segment rules")
    with c[5]:
        kpi("Insured / KCC", ("yes" if f.has_insurance else "no") + " / " + ("yes" if f.has_kcc else "no"), "crop insurance / Kisan Credit Card")

    tabs = st.tabs([f"🏛️ Schemes ({len(kr.schemes)})", f"💳 Loans ({len(kr.loans.products)})", f"☂️ Insurance ({len(kr.insurance)})",
                    f"💰 Subsidies ({len(kr.subsidies)})", f"✨ Opportunities ({len(kr.opportunities)})", "📄 Documents", "🧠 Rules fired"])

    # ------------------------------------------------------------------ schemes
    with tabs[0]:
        st.caption("Personalised match % from state · income · age (hard) and crop · farmer term · land · prerequisites · KB rules (soft). Knowledge-base lookup — not a guarantee of sanction.")
        if not kr.schemes:
            st.info("No scheme reached the minimum match score for this profile.")
        else:
            l, r = st.columns([1, 1.4])
            with l:
                plot(score_bars(kr.schemes[:8], "Top scheme matches"))
            with r:
                strong = [m for m in kr.schemes if m.score >= 75]
                md(f'<div class="an-card"><div class="title">At a glance</div><div class="sub">{len(strong)} strong match(es), '
                   f'{len(kr.schemes) - len(strong)} possible. Highest document readiness: '
                   f'{esc(max(kr.schemes, key=lambda m: m.payload.get("document_readiness_pct", 0)).title)}.</div></div>')
                types = pd.Series([m.payload.get("scheme_type") for m in kr.schemes]).value_counts()
                md("".join(f'<span class="an-chip">{esc(k)} × {v}</span>' for k, v in types.items()))
            show = st.slider("Show top", 3, len(kr.schemes), min(6, len(kr.schemes)), key="n_schemes")
            for i, m in enumerate(kr.schemes[:show], 1):
                _scheme_card(m, i, f"sch{i}")

    # -------------------------------------------------------------------- loans
    with tabs[1]:
        la = kr.loans
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            kpi("Indicative eligibility", inr(la.estimated_eligibility_inr), "from KB product caps · not a sanction")
        with c2:
            kpi("Eligibility rating", la.eligibility_rating, f"{la.rating_score:.0f}/100")
        with c3:
            kpi("Purpose", (la.purpose or "not specified").replace("_", " "), ", ".join(la.relevant_loan_types[:2]))
        with c4:
            kpi("Bank branches in district", str(len(la.branches)), la.branch_coverage_note[:60])
        with st.expander("How the indicative eligibility was derived"):
            explanation_block(la.explanation, limit=8)
        if not la.products:
            st.info("No loan product in the KB matches the stated purpose and profile.")
        for i, m in enumerate(la.products[:6], 1):
            _loan_card(m, i, f"loan{i}")
        st.subheader("Bank branches nearby")
        if la.branches:
            df = pd.DataFrame(la.branches)
            df["offers_matched_product"] = df["offers_matched_product"].map({True: "★ yes", False: ""})
            table(df[["bank_name", "branch_name", "ifsc", "phone", "working_days", "insurance_available", "offers_matched_product"]]
                         .rename(columns={"bank_name": "Bank", "branch_name": "Branch", "ifsc": "IFSC", "phone": "Phone", "working_days": "Days",
                                          "insurance_available": "Insurance desk", "offers_matched_product": "Matched product"}))
            pts = df.dropna(subset=["latitude", "longitude"])
            if len(pts):
                st.map(pts.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]], size=40, zoom=9)
        else:
            md(f'<div class="an-warn">{esc(la.branch_coverage_note)}</div>')

    # ---------------------------------------------------------------- insurance
    with tabs[2]:
        md('<div class="an-warn">Informational only — premiums and sums insured are knowledge-base figures, not live quotes. '
           'PMFBY/RWBCIS notification changes each season; confirm with your bank, CSC or insurer.</div>')
        if kr.insurance_gap_note:
            md(f'<div class="an-note">⚠️ {esc(kr.insurance_gap_note)}</div>')
        if not kr.insurance:
            st.info("No insurance product in the KB applies to this crop and district.")
        for i, m in enumerate(kr.insurance[:6], 1):
            _insurance_card(m, i, f"ins{i}")

    # ---------------------------------------------------------------- subsidies
    with tabs[3]:
        st.caption("Ranked by fit to the farm's *situation* (water stress, flood irrigation, low organic carbon, rainfed…) and the parent scheme's match.")
        if not kr.subsidies:
            st.info("No subsidy in the KB matched this farm's situation.")
        for i, m in enumerate(kr.subsidies[:8], 1):
            _subsidy_card(m, i, f"sub{i}")

    # ------------------------------------------------------------ opportunities
    with tabs[4]:
        st.caption("Cross-engine opportunities ranked by relevance — each links back to the KB record and the reasoning behind it.")
        if not kr.opportunities:
            st.info("No opportunities detected.")
        for i, o in enumerate(kr.opportunities):
            opportunity_card(o, key=f"opp{i}")
            with st.expander("Why?"):
                explanation_block(o.explanation, limit=6)

    # ----------------------------------------------------------------- documents
    with tabs[5]:
        st.caption("Document Resolver — one consolidated view across your top matches (canonical names; KB spellings merged).")
        held = sorted(f.documents_held)
        md('<div class="an-card"><div class="title">On record</div>' + ("".join(f'<span class="an-chip">✓ {esc(d)}</span>' for d in held) or "none") + "</div>")
        need = {}
        for m in kr.schemes[:5] + kr.loans.products[:3] + kr.insurance[:2] + kr.subsidies[:3]:
            for d in m.documents_missing:
                need.setdefault(d, []).append(m.title)
        if need:
            rows = sorted(need.items(), key=lambda kv: -len(kv[1]))
            md('<div class="an-card"><div class="title">To arrange — unlocks the most matches first</div>' +
               "".join(f'<div class="an-doc miss">✗ <b>{esc(d)}</b> <span style="color:#5B6B63">— needed by {len(t)}: {esc("; ".join(t[:3]))}{"…" if len(t) > 3 else ""}</span></div>' for d, t in rows) + "</div>")
        else:
            st.success("All blocking documents for your top matches are on record.")

    # --------------------------------------------------------------- rules fired
    with tabs[6]:
        st.caption("Knowledge-base rules that applied to this farm (transparency view, not raw tables).")
        if kr.fired_eligibility_rules:
            st.markdown("**Eligibility rules**")
            table(pd.DataFrame(kr.fired_eligibility_rules))
        else:
            st.info("No eligibility rule matched (state × crop × farmer category × income).")
        if kr.fired_ai_rules:
            st.markdown("**Segment (ai_recommendation) rules**")
            for r in kr.fired_ai_rules:
                md(f'<div class="an-card tight"><b>Rule {esc(r["rule_id"])}</b> · {esc(r["cond_state"])} / {esc(r["cond_crop"])} / {esc(r["cond_land_band"])} / income {esc(r["cond_income_band"])} '
                   f'· confidence {r["confidence"]} · priority {r["priority"]}<div class="sub">{esc(r["reason"])}</div></div>')
    footer()
