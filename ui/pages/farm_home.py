"""🏠 Farm Home — the central decision dashboard."""
from __future__ import annotations

import streamlit as st

from ui import state
from ui.components import (HORIZON_LABEL, action_card, badge, bar, demo_badge, demo_banner, esc, explanation_block, footer,
                           gauge, health_breakdown_chart, health_color, kpi, md, nba_hero, opportunity_card, plot, risk_card, why_expander)
from ui.farm_form import farm_editor


def _stage_timeline(stage) -> None:
    if not stage.available or not stage.stages:
        md('<div class="an-note">Crop stage timeline needs a current crop and sowing date.</div>')
        return
    segs = "".join(
        f'<div class="seg {s.status}{" crit" if s.critical_water else ""}" title="day {s.start_day}–{s.end_day} · Kc {s.kc}">{esc(s.name)}</div>'
        for s in stage.stages)
    md(f'<div class="an-timeline">{segs}</div>'
       f'<div class="sub" style="font-size:.8rem;color:#5B6B63">Day {stage.days_after_sowing} of ~{stage.total_days} · {stage.progress_pct:.0f}% of season · '
       f'expected harvest {esc(stage.expected_harvest or "—")} · underline = critical water window · reference: {esc(stage.reference_used)}</div>')


def render() -> None:
    ctx = state.ensure_context()
    st.title("🏠 Farm Home")
    demo_banner(ctx)
    with st.expander("✏️ Edit farm / create your own farm profile", expanded=False):
        farm_editor(ctx)
    render_body(ctx, state.get_assessment())


def render_body(ctx, a) -> None:
    kr = a.knowledge

    # ------------------------------------------------------------------ farm identity
    c = st.columns([1.4, 1, 1, 1, 1, 1])
    with c[0]:
        kpi("Farm", ctx.farm_name.split("—")[0].strip() if "—" in ctx.farm_name else ctx.farm_name,
            ctx.farm_name.split("—")[-1].strip() if "—" in ctx.farm_name else "", demo_badge(ctx.is_demo))
    with c[1]:
        kpi("Location", f"{ctx.location.district}", f"{ctx.location.state} · {ctx.location.agro_climatic_zone or ''}".strip(" ·"))
    with c[2]:
        kpi("Area", f"{ctx.area_acres:.2f} ac", f"{ctx.area_hectares:.2f} ha · {ctx.farmer.land_ownership}")
    with c[3]:
        kpi("Current crop", ctx.crop.current_crop or "—", f"{ctx.crop.season or ''} · sown {ctx.crop.sowing_date or '—'}".strip(" ·"))
    with c[4]:
        kpi("Crop stage", a.stage.current_stage or "—", f"day {a.stage.days_after_sowing}" if a.stage.days_after_sowing is not None else "sowing date needed")
    with c[5]:
        kpi("KB coverage", a.kb_coverage.title(), "for " + ctx.location.state)

    # ------------------------------------------------------------- NEXT BEST ACTION
    st.markdown("")
    nba = a.next_best_action
    nba_hero(nba, ctx.is_demo)
    with st.expander("Why this action? — factors considered, method & sources", expanded=True):
        explanation_block(nba.explanation)

    # ------------------------------------------------------- health + risks + opps
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Farm Health")
        hc = st.columns([0.9, 1.5])
        with hc[0]:
            plot(gauge(a.health.score, a.health.label))
            md(f'<div style="text-align:center;margin-top:-.6rem">{badge(a.health.label, "green" if (a.health.score or 0) >= 65 else ("amber" if (a.health.score or 0) >= 50 else "red"))}'
               f'{badge(f"confidence {a.health.confidence:.0%}", "grey")}{badge(f"{a.health.assessed_weight:.0%} of components assessed", "grey")}{demo_badge(a.health.demo_data_used)}</div>')
        with hc[1]:
            plot(health_breakdown_chart(a.health.breakdown))
        with st.expander("Component details — how each score was derived"):
            for b in a.health.breakdown:
                md(f'<div style="display:flex;justify-content:space-between;align-items:center;margin-top:.5rem"><b>{esc(b.name)}</b>'
                   f'<span>{badge(b.label, "green" if (b.score or 0) >= 65 else ("amber" if (b.score or 0) >= 50 else ("grey" if b.score is None else "red")))}'
                   f'{badge(f"weight {b.weight:.0%}", "grey")}</span></div>{bar(b.score, health_color(b.score))}')
                explanation_block(b.explanation, limit=4)
        st.subheader("Crop timeline")
        _stage_timeline(a.stage)
        why_expander(a.stage.explanation, "Why? — stage model", key="stage")

    with right:
        st.subheader(f"Current risks ({len(a.risks)})")
        if not a.risks:
            md('<div class="an-note">No active risks detected from the available data.</div>')
        for r in a.risks[:5]:
            risk_card(r)
        if len(a.risks) > 5:
            st.caption(f"+{len(a.risks) - 5} more in Farm Intelligence → Risk Center")
        st.subheader("Opportunities")
        if kr and kr.opportunities:
            for i, o in enumerate(kr.opportunities[:4]):
                opportunity_card(o, key=f"opp{i}")
            st.caption("Full list and document checklists in Finance & Schemes.")
        else:
            md('<div class="an-note">No opportunities detected.</div>')

    # ------------------------------------------------------------- action list
    st.subheader("Action plan — ranked")
    st.caption("Generated from the farm data and knowledge base at each run (not a fixed list). Method and confidence shown per action.")
    for i, rec in enumerate(a.actions):
        action_card(rec, key=f"act{i}")

    # -------------------------------------------------------------- snapshot strip
    st.subheader("Snapshot")
    s = st.columns(4)
    with s[0]:
        kpi("Water status", a.water.status.replace("_", " ").title(), f"{a.water.mode} · " + (f"deficit {a.water.deficit_mm:.0f} mm" if a.water.deficit_mm is not None else a.water.irrigation_advice.replace("_", " ")))
    with s[1]:
        kpi("NDVI", f"{a.ndvi.current:.2f}" if a.ndvi.current is not None else "—",
            (f"{a.ndvi.trend} · {a.ndvi.change_pct:+.0f}% vs previous" if a.ndvi.change_pct is not None else "no series"), demo_badge(a.ndvi.is_demo))
    with s[2]:
        kpi("Weather", f"{a.weather.temp_max_c:.0f} °C max" if a.weather.temp_max_c is not None else "unavailable",
            (f"rain next 7 d {a.weather.rain_next_7d_mm:.0f} mm" if a.weather.rain_next_7d_mm is not None else a.weather.provider_label or "no provider"))
    with s[3]:
        kpi("Soil", a.soil.soil_type or "—", ("limits: " + ", ".join(a.soil.limitations[:2])) if a.soil.limitations else "no limitation flagged", demo_badge(a.soil.is_demo))
    footer()
