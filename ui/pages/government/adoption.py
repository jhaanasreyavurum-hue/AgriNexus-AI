"""🎯 Scheme Adoption — modelled scheme reach, coverage by type/level, crop association, observed-adoption upload."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from ui import state
from ui.analytics_components import bar_chart, basis_badge, donut, download_df, kpi_row, modelled_banner, ranking_table
from ui.components import esc, footer, md
from ui.pages.government._common import guard, header


def _observed_upload() -> None:
    with st.expander("Upload observed adoption (optional, session-only)"):
        st.caption("CSV with columns `district, observed_adoption_pct` (share of farm households enrolled in the scheme(s) you are monitoring). "
                   "It is held in this session only and compared against modelled reach to compute an adoption gap. Nothing is uploaded anywhere.")
        up = st.file_uploader("observed_adoption.csv", type=["csv"], key="obs_upload")
        if up is not None:
            try:
                df = pd.read_csv(io.BytesIO(up.getvalue()))
                cols = {c.lower().strip(): c for c in df.columns}
                if "district" not in cols or "observed_adoption_pct" not in cols:
                    raise ValueError("Need columns 'district' and 'observed_adoption_pct'.")
                df = df.rename(columns={cols["district"]: "district", cols["observed_adoption_pct"]: "observed_adoption_pct"})[["district", "observed_adoption_pct"]]
                df["observed_adoption_pct"] = pd.to_numeric(df["observed_adoption_pct"], errors="coerce")
                df = df.dropna()
                if df.empty or not df["observed_adoption_pct"].between(0, 100).all():
                    raise ValueError("observed_adoption_pct must be numbers between 0 and 100.")
                st.session_state["observed_adoption"] = df
                st.success(f"Loaded observed adoption for {len(df)} district(s) — labelled OBSERVED (user upload) wherever used.")
            except Exception as exc:
                st.error(f"Could not read file: {exc}")
        if st.session_state.get("observed_adoption") is not None and st.button("Clear uploaded data", key="obs_clear"):
            st.session_state.pop("observed_adoption", None)
            st.rerun()


def render() -> None:
    user = guard()
    sc, tags, ii = header("🎯 Scheme Adoption", user, with_segments=True)
    kb = state.get_kb()
    modelled_banner("inclusion", ii.notes, ii.stale)
    _observed_upload()
    k = ii.kpis
    sch = ii.by_scheme
    kpi_row([("Schemes with modelled reach", str(len(sch)), f"of {int((~kb.schemes['excluded']).sum())} active in KB"),
             ("Widest reach", (k["top_scheme"] or "—")[:40], f"{sch.iloc[0]['reach_pct']:.0f}% of households" if len(sch) else ""),
             ("Avg eligible schemes / household", f"{k['avg_schemes_per_household']:.1f}", "depth of scheme eligibility"),
             ("Central vs state", f"{int((sch['level'] == 'Central').sum())} / {int((sch['level'] != 'Central').sum())}" if len(sch) else "—", "schemes with reach"),
             ("Observed adoption", "uploaded" if st.session_state.get("observed_adoption") is not None else "not supplied", "session-only user data")], basis_badge())

    tabs = st.tabs(["Scheme reach", "Coverage by type & level", "Crop-wise association", "Modelled vs observed"])
    with tabs[0]:
        n = st.slider("Schemes to show", 5, max(5, len(sch)), min(15, max(5, len(sch))), key="adopt_n") if len(sch) > 5 else len(sch)
        bar_chart(sch.head(n), "scheme", "reach_pct", "Modelled reach — % of scenario households eligible", key="adopt_bar", height=520, text_fmt="%{text:.0f}%", color="level")
        ranking_table(sch, {"scheme": ("Scheme", "str"), "scheme_type": ("Type", "str"), "level": ("Level", "str"), "reach_pct": ("Reach %", "pct"),
                            "modelled_reach_households": ("Modelled households", "int"), "avg_score": ("Avg match", "num"), "districts": ("Districts", "int")}, height=400)
        download_df(sch, "Download scheme reach (CSV)", "scheme_reach.csv", "dl_adopt")
    with tabs[1]:
        if len(sch):
            c1, c2 = st.columns(2)
            with c1:
                donut(sch.groupby("scheme_type", as_index=False)["modelled_reach_households"].sum(), "scheme_type", "modelled_reach_households", "Reach by scheme type", key="adopt_type")
            with c2:
                donut(sch.groupby("level", as_index=False)["modelled_reach_households"].sum(), "level", "modelled_reach_households", "Reach by government level", key="adopt_level")
            kbt = kb.schemes[~kb.schemes["excluded"]].groupby("scheme_type").size().rename("in_kb").reset_index()
            cov = kbt.merge(sch.groupby("scheme_type").size().rename("with_reach").reset_index(), on="scheme_type", how="left").fillna({"with_reach": 0})
            cov["coverage_pct"] = 100 * cov["with_reach"] / cov["in_kb"]
            st.caption("Scheme coverage: share of KB schemes of each type that reach at least one archetype in this scope (zero coverage = a scheme type nobody in the scenario qualifies for, or state-specific schemes outside the scope).")
            ranking_table(cov.sort_values("coverage_pct"), {"scheme_type": ("Scheme type", "str"), "in_kb": ("Schemes in KB", "int"), "with_reach": ("With modelled reach", "int"), "coverage_pct": ("Coverage %", "pct")})
    with tabs[2]:
        cs = ii.by_crop_scheme
        if cs.empty:
            st.info("No crop-wise data in scope.")
        else:
            crops = sorted(cs["crop"].unique())
            pick = st.selectbox("Crop", crops, key="adopt_crop")
            sub = cs[cs["crop"] == pick].head(12)
            bar_chart(sub, "scheme", "households", f"Schemes associated with {pick} (modelled households)", key="adopt_cropbar", height=420)
            row = kb.crop_row(pick)
            if row is not None:
                md(f'<div class="an-note">KB crop master recommends for <b>{esc(pick)}</b>: schemes — {esc("; ".join(row["recommended_schemes_list"]))}; loans — {esc("; ".join(row["recommended_loans_list"]))}. '
                   f'Insurance available flag: {"yes" if row["insurance_available_bool"] else "no"}.</div>')
    with tabs[3]:
        d = ii.by_district
        if "observed_adoption_pct" in d.columns and d["observed_adoption_pct"].notna().any():
            v = d.dropna(subset=["observed_adoption_pct"]).copy()
            v["gap"] = v["adoption_gap_pct"]
            bar_chart(v.sort_values("gap", ascending=False).head(20), "district", "gap", "Adoption gap = modelled reach − observed adoption (pp)", key="adopt_gap", height=460, text_fmt="%{text:.0f}")
            ranking_table(v.sort_values("gap", ascending=False), {"district": ("District", "str"), "scheme_reach_pct": ("Modelled reach %", "pct"), "observed_adoption_pct": ("Observed adoption % (upload)", "pct"),
                                                                   "adoption_gap_pct": ("Gap (pp)", "num"), "inclusion_index": ("Inclusion index", "num")})
            st.caption("Positive gap = more households modelled as eligible than observed enrolled → awareness / access intervention candidates. Observed values are the officer's own upload (session-only).")
        else:
            st.info("No observed adoption uploaded. Modelled reach is shown alone; upload a CSV above to compute district-level adoption gaps.")
    footer()
