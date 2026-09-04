"""🌱 Crop Advisor — ranked crop options with factor-level reasons, plus crop timeline."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.engines import recommend_crops
from ui import state
from ui.components import (badge, bar, demo_banner, esc, explanation_block, factor_lines, footer, kpi, match_header, md, plot,
                           positives_and_limits, score_color, table)
from ui.theme import GREEN, GREY

FACTOR_LABEL = {"soil": "Soil", "rain": "Rainfall", "water": "Water need", "season": "Season", "rotation": "Rotation", "objective": "Objective", "region": "Region"}
SEASONS = ["Kharif", "Rabi", "Zaid (Summer)"]


@st.cache_data(show_spinner=False, max_entries=16)
def _crops_for(ctx_dict: dict, fingerprint: str, season: str, top_n: int):
    """Crop Advisor for a chosen target season (re-uses the assessed facts)."""
    from core.engines.facts import build_facts
    from core.models import FarmContext
    from core.reasoning.assessment import assess_farm
    kb = state.get_kb()
    ctx = FarmContext.from_dict(ctx_dict)
    a = assess_farm(ctx, kb)
    facts = build_facts(ctx, kb, a)
    return recommend_crops(ctx, kb, facts, target_season=season, top_n=top_n)


def _radar(items) -> go.Figure:
    cats = list(FACTOR_LABEL.values())
    fig = go.Figure()
    for m in items:
        fs = m.payload.get("factor_scores", {})
        vals = [fs.get(k) if fs.get(k) is not None else 0 for k in FACTOR_LABEL]
        fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=cats + cats[:1], fill="toself", name=m.title, opacity=0.55))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False)), height=360, margin=dict(l=30, r=30, t=30, b=30),
                      legend=dict(orientation="h", y=-0.1), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def _crop_card(m, rank: int) -> None:
    p = m.payload
    chips = [p.get("market_category"), f"season: {', '.join(p.get('seasons_all', []))}", f"soil: {p.get('soil_type')}",
             f"rain {p['rainfall_range_mm'][0]}–{p['rainfall_range_mm'][1]} mm", f"water need {p.get('water_requirement')}",
             "insurance available (KB)" if p.get("insurance_available") else None]
    with st.container(border=True):
        match_header(m, rank, "Currently in the field" if p.get("is_current_crop") else "Alternative option", chips)
        fs = p.get("factor_scores", {})
        cols = st.columns(len(FACTOR_LABEL))
        for (k, lbl), c in zip(FACTOR_LABEL.items(), cols):
            v = fs.get(k)
            with c:
                md(f'<div style="font-size:.72rem;color:#5B6B63;font-weight:600">{lbl}</div>'
                   f'<div style="font-weight:700;color:{score_color(v)}">{"n/a" if v is None else f"{v:.0f}"}</div>{bar(v)}')
        positives_and_limits(m, limit=4)
        t1, t2 = st.tabs(["🔍 Why this score", "🔗 KB links"])
        with t1:
            explanation_block(m.explanation, limit=10)
        with t2:
            md(f'<div style="font-size:.86rem"><b>Recommended schemes (KB):</b> {esc(", ".join(p.get("recommended_schemes", [])) or "—")}<br>'
               f'<b>Recommended loans (KB):</b> {esc(", ".join(p.get("recommended_loans", [])) or "—")}<br>'
               f'<b>KB record:</b> {esc(m.item_id)}' + (f' · corrected fields: {esc(", ".join(p["kb_overrides"]))}' if p.get("kb_overrides") else "") + "</div>")


def render() -> None:
    ctx = state.ensure_context()
    st.title("🌱 Crop Advisor")
    demo_banner(ctx)
    render_body(ctx, state.get_assessment())


def render_body(ctx, a) -> None:
    kr = a.knowledge

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        default_season = ctx.crop.season if ctx.crop.season in SEASONS else "Kharif"
        season = st.selectbox("Plan for season", SEASONS, index=SEASONS.index(default_season))
    with c2:
        top_n = st.slider("Options to show", 3, 15, 8)
    with c3:
        md('<div class="an-note">Rule-based suitability from the KB crop master × your soil, district rainfall, irrigation, season, previous crop and objective. '
           'Scores are agronomic fit — not yield or price forecasts.</div>')

    if season == (ctx.crop.season or "Kharif") and kr is not None and top_n <= len(kr.crops):
        crops = kr.crops[:top_n]
    else:
        from ui.state import _ctx_fingerprint
        crops = _crops_for(ctx.to_dict(), _ctx_fingerprint(ctx), season, top_n)
    if not crops:
        st.info("No crop in the knowledge base fits this season and farm profile.")
        footer()
        return

    cur = next((m for m in crops if m.payload.get("is_current_crop")), None)
    k = st.columns(4)
    with k[0]:
        kpi("Current crop", ctx.crop.current_crop or "none", f"suitability {cur.score:.0f}%" if cur else "not in this season's list")
    with k[1]:
        kpi("Best option", crops[0].title, f"{crops[0].score:.0f}% · {crops[0].payload.get('market_category')}")
    with k[2]:
        kpi("Objective", ctx.farmer.primary_objective.replace("_", " "), "weights category bonus")
    with k[3]:
        kpi("Previous crop", ctx.crop.previous_crop or "unknown", "drives rotation factor")

    left, right = st.columns([1.2, 1])
    with left:
        fig = go.Figure(go.Bar(x=[m.score for m in crops], y=[m.title for m in crops], orientation="h",
                               marker_color=[GREEN if m.payload.get("is_current_crop") else score_color(m.score) for m in crops],
                               text=[f"{m.score:.0f}%" + (" · current" if m.payload.get("is_current_crop") else "") for m in crops], textposition="outside"))
        fig.update_layout(height=60 + 34 * len(crops), margin=dict(l=0, r=90, t=8, b=8), xaxis=dict(range=[0, 118], showticklabels=False, showgrid=False),
                          yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        plot(fig, key="crop_bars")
    with right:
        plot(_radar(crops[:4]), key="crop_radar")

    st.subheader("Ranked options — with reasons")
    for i, m in enumerate(crops, 1):
        _crop_card(m, i)

    st.subheader("Crop timeline (current crop)")
    stg = a.stage
    if stg.available and stg.stages:
        rows = [{"Stage": s.name, "Window": f"{s.start_date} → {s.end_date}", "Days": f"{s.start_day}–{s.end_day}", "Kc": s.kc,
                 "Critical water": "yes" if s.critical_water else "", "Status": s.status, "Mean NDVI": s.ndvi_mean} for s in stg.stages]
        table(pd.DataFrame(rows))
        st.caption(f"{stg.explanation.summary} · reference: {stg.reference_used}")
    else:
        md('<div class="an-note">Timeline needs a current crop and sowing date.</div>')
    footer()
