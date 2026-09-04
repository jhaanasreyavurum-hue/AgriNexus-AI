"""⚠️ Low-Adoption Areas — intervention shortlist with weakest pillar and suggested action."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import state
from ui.analytics_components import bar_chart, basis_badge, district_map, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import badge, esc, footer, md
from ui.pages.government._common import guard, header


def render() -> None:
    user = guard()
    sc, tags, ii = header("⚠️ Low-Adoption Areas", user, with_segments=True)
    kb = state.get_kb()
    modelled_banner("inclusion", ii.notes, ii.stale)
    low = ii.low_adoption
    if low.empty:
        st.info("No districts in scope.")
        footer()
        return
    pillar_counts = low["weakest_pillar"].value_counts()
    kpi_row([("Flagged districts", str(len(low)), "lowest 30% (min 5) of scope by inclusion index"),
             ("Most common gap", pillar_counts.index[0] if len(pillar_counts) else "—", f"{int(pillar_counts.iloc[0]) if len(pillar_counts) else 0} district(s)"),
             ("Lowest index", f"{low['inclusion_index'].min():.0f}", low.iloc[0]["district"]),
             ("Observed adoption", "uploaded" if st.session_state.get("observed_adoption") is not None else "not supplied", "add via Scheme Adoption")], basis_badge())
    st.caption("A district is flagged relative to the scope (bottom 30 %), not by an absolute threshold, because within one state the KB rules are uniform and differences are driven by the district's major crop, cover notification and branch access. "
               "Suggested interventions are rule-based (keyed to the weakest pillar) for field verification.")

    c1, c2 = st.columns([1.4, 1])
    with c1:
        district_map(kb, low.assign(band="Lower third"), "inclusion_index", "district", "band", title="Flagged districts", tooltip_cols=["crop", "weakest_pillar", "intervention"], height=430)
    with c2:
        bar_chart(pillar_counts.rename_axis("pillar").reset_index(name="districts"), "pillar", "districts", "Weakest pillar across flagged districts", orientation="v", key="low_pillar", height=430, text_fmt="%{text}")

    st.subheader("Intervention shortlist")
    cols = {"district": ("District", "str"), "state": ("State", "str"), "crop": ("Major crop", "str"), "inclusion_index": ("Index", "num"), "weakest_pillar": ("Weakest pillar", "str"),
            "scheme_reach_pct": ("Scheme %", "pct"), "credit_reach_pct": ("Credit %", "pct"), "insurance_reach_pct": ("Insurance %", "pct"), "subsidy_reach_pct": ("Subsidy %", "pct"),
            "branches": ("KB branches", "int"), "intervention": ("Suggested intervention", "str")}
    if "observed_adoption_pct" in low.columns and low["observed_adoption_pct"].notna().any():
        cols["observed_adoption_pct"] = ("Observed adoption % (upload)", "pct")
        cols["adoption_gap_pct"] = ("Gap (pp)", "num")
    ranking_table(low, cols, height=420)
    download_df(low, "Download intervention shortlist (CSV)", "low_adoption_areas.csv", "dl_low")

    st.subheader("Action cards")
    for _, r in low.head(6).iterrows():
        md(f'<div class="an-card tight"><div class="title">{esc(r["district"])}, {esc(r["state"])} {badge(r["weakest_pillar"], "red")} {badge("index %.0f" % r["inclusion_index"], "grey")}</div>'
           f'<div class="sub"><b>Do:</b> {esc(r["intervention"])}. <b>Why:</b> scheme {r["scheme_reach_pct"]:.0f}% · credit {r["credit_reach_pct"]:.0f}% · insurance {r["insurance_reach_pct"]:.0f}% · subsidy {r["subsidy_reach_pct"]:.0f}% reach; '
           f'major crop {esc(r["crop"] or "—")}; {int(r["branches"])} KB branches.</div></div>')
    footer()
