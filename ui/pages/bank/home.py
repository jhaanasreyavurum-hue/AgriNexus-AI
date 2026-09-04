"""🏠 Bank Dashboard — Agricultural Credit Intelligence overview (MODELLED)."""
from __future__ import annotations

import streamlit as st

from ui import state
from ui.analytics_components import bar_chart, basis_badge, district_map, donut, kpi_row, modelled_banner, ranking_table
from ui.components import esc, footer, inr, md, badge
from ui.pages.bank._common import guard, header


def render() -> None:
    user = guard()
    sc, _, _, ci = header("🏠 Bank Dashboard — Agricultural Credit Intelligence", user)
    kb = state.get_kb()
    modelled_banner("credit", ci.notes, ci.stale)
    k = ci.kpis
    scope_txt = sc or "All KB districts"

    md(f'<div class="an-hero" style="background:linear-gradient(120deg,#123C69,#1F5F9E)"><div class="eyebrow">Credit opportunity summary · {esc(scope_txt)} · {esc(ci.basis)}</div>'
       f'<div class="action">Modelled potential loan demand {inr(k["demand_inr"])} across {k["districts"]} district(s) — '
       f'{k["eligible_pct"]:.0f}% of scenario households potentially eligible, average ticket {inr(k["avg_ticket_inr"])}.</div>'
       f'<div class="why">Top modelled product: {esc(k["top_product"] or "—")} ({esc(k["top_loan_type"] or "—")}) · highest-attractiveness crop: {esc(k["top_crop"] or "—")} · '
       f'{k["high_potential_districts"]} high-potential district(s), {k["untapped_districts"]} with no KB agri-loan desk.</div>'
       f'<div class="meta"><span>per 10,000 households: {inr(k["demand_per_10k_inr"])}</span><span>avg product fit {k["avg_fit_score"]:.0f}/100</span>'
       f'<span>crop cover notified for {k["crop_cover_pct"]:.0f}% of households</span><span>{k["kb_branches"]} KB branches in scope</span></div></div>')

    kpi_row([("Potential loan demand", inr(k["demand_inr"]), "modelled, scenario households"),
             ("Potentially eligible farmers", f"{k['eligible_households']:,.0f}", f"{k['eligible_pct']:.0f}% of {k['households_modelled']:,.0f} modelled households"),
             ("Average ticket", inr(k["avg_ticket_inr"]), "KB product ranges × segment scale"),
             ("High-potential districts", str(k["high_potential_districts"]), f"of {k['districts']} in scope"),
             ("Document readiness", f"{k['doc_readiness_pct']:.0f}%" if k.get("doc_readiness_pct") is not None else "—", "avg for best-fit product (archetype docs)")],
            basis_badge())

    c1, c2 = st.columns([1.35, 1])
    with c1:
        if len(ci.by_district):
            district_map(kb, ci.by_district, "potential_score", "district", "potential", title="Credit potential by district",
                         tooltip_cols=["crop", "potential", "credit_opportunity"], height=400)
    with c2:
        bar_chart(ci.by_segment.head(8), "segment_label", "demand_inr", "Modelled demand by farmer segment", key="home_seg", height=400)

    c3, c4, c5 = st.columns(3)
    with c3:
        bar_chart(ci.by_crop.head(8), "crop", "credit_attractiveness", "Crop credit attractiveness (0-100)", key="home_crop", height=330)
    with c4:
        donut(ci.by_product.groupby("loan_type", as_index=False)["eligible_households"].sum().head(8), "loan_type", "eligible_households", "Product-type demand mix", key="home_prod")
    with c5:
        bar_chart(ci.by_bank.head(9), "bank_name", "modelled_eligible_households", "Bank reach: modelled eligible households", key="home_bank", height=330)

    st.subheader("Credit opportunity areas")
    st.caption("Ranked by potential score = demand depth + product fit + risk cover + under-served bonus. Use High-Potential Areas for the full ranking and filters.")
    ranking_table(ci.by_district.head(10), {"district": ("District", "str"), "state": ("State", "str"), "crop": ("Major crop", "str"), "eligible_pct": ("Eligible %", "pct"),
                                             "demand_inr": ("Modelled demand", "inr"), "avg_loan_est_inr": ("Avg ticket", "inr"), "loan_desks": ("KB loan desks", "int"),
                                             "potential_score": ("Potential score", "num"), "potential": ("Potential", "str"), "credit_opportunity": ("Opportunity", "str")})

    st.subheader("Inclusion indicators in this scope")
    seg = ci.by_segment.set_index("segment_id") if len(ci.by_segment) else None
    if seg is not None:
        def _pct(sid):
            return f"{seg.loc[sid, 'eligible_pct']:.0f}%" if sid in seg.index else "—"
        kpi_row([("Women farmers eligible", _pct("WOMEN_MARG"), "women · marginal archetype"), ("Tenant farmers eligible", _pct("TENANT"), "tenant / sharecropper archetype"),
                 ("Rainfed marginal eligible", _pct("MARG_RAINFED"), "largest household share"), ("FPO members eligible", _pct("FPO_SMALL"), "FPO · small archetype")], basis_badge())
        if "TENANT" in seg.index and seg.loc["TENANT", "eligible_pct"] < 50:
            md('<div class="an-note">⚠️ Tenant / sharecropper archetype is rated <b>Limited</b> by the KB rules (no land records, no cultivator certificate). '
               'This is the most under-served segment in the model — JLG / tenant-certificate products are the lever.</div>')
    footer()
