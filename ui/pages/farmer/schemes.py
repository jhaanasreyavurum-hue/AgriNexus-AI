"""🎯 Government Schemes — scheme finder, subsidies, document resolver, rules fired."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import badge, esc, explanation_block, footer, inr, kpi, md, opportunity_card, plot, score_bars, table
from ui.match_cards import scheme_card, subsidy_card
from ui.pages.farmer._common import guard_with_farm


def render() -> None:
    user, ctx, a = guard_with_farm("🎯 Government Schemes")
    kr = a.knowledge
    f = kr.facts
    md(f'<div class="an-note">{esc(kr.coverage_note)}</div>')

    strong = [m for m in kr.schemes if m.score >= 75]
    c = st.columns(5)
    with c[0]:
        kpi("Scheme matches", str(len(kr.schemes)), f"{len(strong)} strong · {len(kr.schemes) - len(strong)} possible", badge("KNOWLEDGE BASE", "green"))
    with c[1]:
        kpi("Farmer category", f.category, f"{f.acres:.2f} ac · " + (", ".join(x.replace("_", " ") for x in f.profile_attrs if x not in ("any",)) or "—"))
    with c[2]:
        kpi("Income check", inr(f.income) if f.income else "not provided", "income limits are hard filters")
    with c[3]:
        kpi("Subsidies matched", str(len(kr.subsidies)), f"largest cap {inr(max([(m.payload.get('maximum_amount') or 0) for m in kr.subsidies], default=0))}" if kr.subsidies else "")
    with c[4]:
        kpi("KB rules fired", f"{len(kr.fired_eligibility_rules)} + {len(kr.fired_ai_rules)}", "eligibility + segment rules", badge("RULE-BASED", "grey"))

    tabs = st.tabs([f"Scheme finder ({len(kr.schemes)})", f"Subsidies ({len(kr.subsidies)})", f"Opportunities ({len(kr.opportunities)})", "Document resolver", "Rules fired"])
    with tabs[0]:
        st.caption("Personalised match % from state · income · age (hard filters) and crop · farmer term · land · prerequisites · KB rules (soft). Cards show why you are eligible, conditions, benefits, documents and application mode.")
        if not kr.schemes:
            st.info("No scheme reached the minimum match score for this profile.")
        else:
            l, r = st.columns([1, 1.4])
            with l:
                plot(score_bars(kr.schemes[:8], "Top scheme matches"), key="scheme_bars")
            with r:
                types = pd.Series([m.payload.get("scheme_type") for m in kr.schemes]).value_counts()
                md('<div class="an-card"><div class="title">At a glance</div><div class="sub">'
                   f'{len(strong)} strong match(es). Highest document readiness: {esc(max(kr.schemes, key=lambda m: m.payload.get("document_readiness_pct", 0)).title)}.</div>'
                   + "".join(f'<span class="an-chip">{esc(k)} × {v}</span>' for k, v in types.items()) + "</div>")
                filt = st.multiselect("Filter by scheme type", list(types.index), key="scheme_type_filter", placeholder="All types")
            items = [m for m in kr.schemes if not filt or m.payload.get("scheme_type") in filt]
            show = st.slider("Show top", 3, max(3, len(items)), min(6, max(3, len(items))), key="n_schemes") if len(items) > 3 else len(items)
            for i, m in enumerate(items[:show], 1):
                scheme_card(m, i, f"sch{i}")
    with tabs[1]:
        st.caption("Ranked by fit to your farm's situation (water stress, irrigation method, soil, rainfed…) and the parent scheme's match. Caps are per subsidy and are not additive.")
        if not kr.subsidies:
            st.info("No subsidy in the KB matched this farm's situation.")
        for i, m in enumerate(kr.subsidies[:8], 1):
            subsidy_card(m, i, f"sub{i}")
    with tabs[2]:
        if not kr.opportunities:
            st.info("No opportunities detected.")
        for i, o in enumerate(kr.opportunities):
            opportunity_card(o, key=f"opp{i}")
            with st.expander("Why?"):
                explanation_block(o.explanation, limit=6)
    with tabs[3]:
        st.caption("One consolidated document view across your top loan, scheme, insurance and subsidy matches (KB spellings merged into canonical names).")
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
    with tabs[4]:
        st.caption("Knowledge-base rules that applied to this farm (transparency view).")
        if kr.fired_eligibility_rules:
            st.markdown("**Eligibility rules**")
            table(pd.DataFrame(kr.fired_eligibility_rules))
        else:
            st.info("No eligibility rule matched (state × crop × farmer category × income).")
        if kr.fired_ai_rules:
            st.markdown("**Segment rules**")
            for r in kr.fired_ai_rules:
                md(f'<div class="an-card tight"><b>Rule {esc(r["rule_id"])}</b> · {esc(r["cond_state"])} / {esc(r["cond_crop"])} / {esc(r["cond_land_band"])} / income {esc(r["cond_income_band"])} '
                   f'· confidence {r["confidence"]} · priority {r["priority"]}<div class="sub">{esc(r["reason"])}</div></div>')
    footer()
