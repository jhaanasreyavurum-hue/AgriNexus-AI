"""🗺️ Farm Intelligence — GIS view, NDVI analytics, Soil, Weather, Water balance, Risk Center."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ui import state
from ui.components import (badge, bar, demo_badge, demo_banner, esc, explanation_block, footer, health_color, kpi, md, plot,
                           risk_card, score_color, table, why_expander)
from ui.theme import AMBER, BLUE, GREEN, GREY, RED

SEV_BADGE = {"info": "grey", "watch": "blue", "warning": "amber", "alert": "red"}


# ------------------------------------------------------------------------------ map
def _map(ctx, branches) -> None:
    try:
        import pydeck as pdk
    except Exception:
        pdk = None
    lat, lon = ctx.location.latitude, ctx.location.longitude
    if lat is None or lon is None:
        md('<div class="an-note">No coordinates for this farm — district not in the KB geo master. Map unavailable.</div>')
        return
    gj = ctx.geometry.to_geojson()
    if pdk is None:
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=11)
        return
    layers = []
    if gj:
        layers.append(pdk.Layer("GeoJsonLayer", data={"type": "FeatureCollection", "features": [gj]}, stroked=True, filled=True,
                                get_fill_color=[27, 127, 76, 80], get_line_color=[15, 90, 53, 220], line_width_min_pixels=2, pickable=True))
    layers.append(pdk.Layer("ScatterplotLayer", data=pd.DataFrame({"lat": [lat], "lon": [lon], "name": [ctx.farm_name]}),
                            get_position="[lon, lat]", get_radius=120, get_fill_color=[27, 127, 76, 200], pickable=True))
    if branches:
        bdf = pd.DataFrame(branches).dropna(subset=["latitude", "longitude"])
        if len(bdf):
            bdf["name"] = bdf["bank_name"] + " — " + bdf["branch_name"]
            layers.append(pdk.Layer("ScatterplotLayer", data=bdf, get_position="[longitude, latitude]", get_radius=160,
                                    get_fill_color=[31, 95, 168, 180], pickable=True))
    view = pdk.ViewState(latitude=lat, longitude=lon, zoom=13 if gj else 10, pitch=0)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style="light", tooltip={"text": "{name}"}), height=380)
    st.caption(f"Farm point: {ctx.location.provenance.label()} · boundary: {ctx.geometry.provenance.label()} · blue = KB bank branches in district")


# ----------------------------------------------------------------------------- NDVI
def _ndvi_chart(nd, stage) -> go.Figure:
    df = pd.DataFrame(nd.series)
    fig = go.Figure()
    for s in (stage.stages if stage.available else []):
        if s.start_date and s.end_date:
            fig.add_vrect(x0=s.start_date, x1=s.end_date, fillcolor="#1B7F4C" if s.status == "current" else "#EEF2F0",
                          opacity=0.18 if s.status == "current" else 0.35, line_width=0, annotation_text=s.name, annotation_position="top left",
                          annotation_font_size=10, annotation_font_color=GREY)
    fig.add_trace(go.Scatter(x=df["date"], y=df["ndvi"], mode="lines+markers", name="NDVI", line=dict(color=GREEN, width=3), marker=dict(size=8)))
    if "ndwi" in df and df["ndwi"].notna().any():
        fig.add_trace(go.Scatter(x=df["date"], y=df["ndwi"], mode="lines+markers", name="NDWI", line=dict(color=BLUE, width=2, dash="dot"), marker=dict(size=6)))
    for y, lbl, c in ((0.3, "sparse", AMBER), (0.5, "moderate", GREY), (0.7, "dense", GREEN)):
        fig.add_hline(y=y, line=dict(color=c, width=1, dash="dash"), annotation_text=lbl, annotation_position="right", annotation_font_size=10)
    fig.update_layout(height=340, margin=dict(l=0, r=40, t=10, b=0), yaxis=dict(range=[-0.2, 1], title="index"), legend=dict(orientation="h", y=1.08),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def _ndvi_tab(a, ctx) -> None:
    nd = a.ndvi
    if not nd.available:
        md('<div class="an-note">No NDVI series. Upload a CSV (date, ndvi[, ndwi]) via Farm Home → Edit farm. '
           'The code is structured so a Sentinel-2 / Sentinel Hub source can be plugged in later; no satellite data is fabricated.</div>')
        explanation_block(nd.explanation)
        return
    if nd.is_demo:
        md('<div class="an-demo">🧪 <b>DEMO NDVI series</b> — synthetic values for demonstration, not satellite-derived.</div>')
    c = st.columns(5)
    with c[0]:
        kpi("Current NDVI", f"{nd.current:.2f}", nd.condition or "", demo_badge(nd.is_demo))
    with c[1]:
        kpi("Change", f"{nd.change:+.2f}" if nd.change is not None else "—", f"{nd.change_pct:+.0f}% vs previous" if nd.change_pct is not None else "")
    with c[2]:
        kpi("Trend", nd.trend or "—", f"slope {nd.trend_slope_per_10d:+.3f}/10 d" if nd.trend_slope_per_10d is not None else "")
    with c[3]:
        kpi("Season peak", f"{nd.peak:.2f}" if nd.peak is not None else "—", nd.peak_date or "")
    with c[4]:
        kpi("Vegetation score", f"{nd.score:.0f}" if nd.score is not None else "—", "stress signal" if nd.stress_signal else "no stress signal")
    plot(_ndvi_chart(nd, a.stage), key="ndvi_chart")
    st.caption(f"Source: {ctx.remote_sensing.provenance.label()} · sensor: {ctx.remote_sensing.sensor or 'n/a'} · shaded band = current crop stage (stage-aware interpretation)")
    why_expander(nd.explanation, "Why? — NDVI interpretation", key="ndvi")
    if a.stage.available and any(s.ndvi_mean is not None for s in a.stage.stages):
        table(pd.DataFrame([{"Stage": s.name, "Days": f"{s.start_day}–{s.end_day}", "Kc": s.kc, "Mean NDVI": s.ndvi_mean, "Status": s.status} for s in a.stage.stages]))


# ----------------------------------------------------------------------------- soil
def _soil_tab(a, ctx) -> None:
    so = a.soil
    if not so.available:
        md('<div class="an-note">No soil data. Add soil type / Soil Health Card values via Farm Home → Edit farm.</div>')
        explanation_block(so.explanation)
        return
    if so.is_demo:
        md('<div class="an-demo">🧪 <b>DEMO soil values</b> — illustrative Soil Health Card numbers.</div>')
    c = st.columns(4)
    with c[0]:
        kpi("Soil type", so.soil_type or "—", f"canonical: {so.soil_canonical}", demo_badge(so.is_demo))
    with c[1]:
        kpi("Soil score", f"{so.score:.0f}" if so.score is not None else "—", "0–100 from measured parameters")
    with c[2]:
        kpi("Fit for current crop", f"{so.crop_soil_fit:.0%}" if so.crop_soil_fit is not None else "—", "KB crop_master preferred soil")
    with c[3]:
        kpi("Limitations", str(len(so.limitations)), ", ".join(so.limitations[:2]) or "none flagged")
    rows = [p for p in so.params if p.available]
    if rows:
        fig = go.Figure(go.Bar(x=[p.score if p.score is not None else 0 for p in rows], y=[p.label for p in rows], orientation="h",
                               marker_color=[health_color(p.score) for p in rows],
                               text=[f"{p.value:g} {p.unit} · {p.rating}" if p.value is not None else "" for p in rows], textposition="outside",
                               hovertext=[p.implication for p in rows], hoverinfo="text"))
        fig.update_layout(height=60 + 38 * len(rows), margin=dict(l=0, r=160, t=4, b=4), xaxis=dict(range=[0, 135], showticklabels=False, showgrid=False),
                          yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        plot(fig, key="soil_chart")
        for p in rows:
            md(f'<div class="an-factor"><div class="ic">•</div><div><span class="nm">{esc(p.label)}</span> {p.value:g} {esc(p.unit)} '
               f'{badge(p.rating or "", "grey")} <span class="dt">{esc(p.implication)}</span></div></div>')
    missing = [p.label for p in so.params if not p.available]
    if missing:
        st.caption("Not provided: " + ", ".join(missing))
    why_expander(so.explanation, "Why? — soil interpretation", key="soil")


# --------------------------------------------------------------------------- weather
def _weather_tab(a, ctx) -> None:
    w = a.weather
    if not w.available:
        md('<div class="an-note">Weather unavailable — switch the sidebar to <b>Live weather</b> (Open-Meteo, no key needed) or check connectivity. '
           'Analytics fall back to qualitative mode; nothing is estimated.</div>')
        explanation_block(w.explanation)
        return
    c = st.columns(5)
    with c[0]:
        kpi("Max temp", f"{w.temp_max_c:.1f} °C" if w.temp_max_c is not None else "—", "heat stress" if w.heat_stress else "within crop range")
    with c[1]:
        kpi("Rain last 7 d", f"{w.rain_last_7d_mm:.0f} mm" if w.rain_last_7d_mm is not None else "—", "dry spell" if w.dry_spell else "")
    with c[2]:
        kpi("Rain next 24 h", f"{w.rain_next_24h_mm:.0f} mm" if w.rain_next_24h_mm is not None else "—", "heavy rain expected" if w.heavy_rain_expected else "")
    with c[3]:
        kpi("Rain next 7 d", f"{w.rain_next_7d_mm:.0f} mm" if w.rain_next_7d_mm is not None else "—", f"ET0 7 d {w.et0_next_7d_mm:.0f} mm" if w.et0_next_7d_mm is not None else "")
    with c[4]:
        kpi("Weather score", f"{w.score:.0f}" if w.score is not None else "—", "0–100 condition sub-score")
    st.caption(f"Provider: {w.provider_label or ctx.weather.provenance.label()} · observed {ctx.weather.observed_at or 'n/a'}")
    fd = ctx.weather.forecast_daily
    if fd:
        df = pd.DataFrame(fd)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["date"], y=df["rain_mm"], name="Rain (mm)", marker_color=[BLUE if f else "#9DB8D9" for f in df.get("is_forecast", [True] * len(df))], yaxis="y"))
        if "et0_mm" in df:
            fig.add_trace(go.Scatter(x=df["date"], y=df["et0_mm"], name="ET0 (mm)", line=dict(color=AMBER, width=2), yaxis="y"))
        if "tmax_c" in df:
            fig.add_trace(go.Scatter(x=df["date"], y=df["tmax_c"], name="Tmax (°C)", line=dict(color=RED, width=2), yaxis="y2"))
        if "tmin_c" in df:
            fig.add_trace(go.Scatter(x=df["date"], y=df["tmin_c"], name="Tmin (°C)", line=dict(color=GREY, width=1, dash="dot"), yaxis="y2"))
        today = ctx.today().isoformat()
        if today in set(df["date"]):
            fig.add_shape(type="line", x0=today, x1=today, y0=0, y1=1, xref="x", yref="paper", line=dict(color=GREEN, dash="dash"))
            fig.add_annotation(x=today, y=1.02, xref="x", yref="paper", text="today", showarrow=False, font=dict(size=10, color=GREEN))
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(title="mm"), yaxis2=dict(title="°C", overlaying="y", side="right"),
                          legend=dict(orientation="h", y=1.1), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", barmode="group")
        plot(fig, key="wx_chart")
    st.subheader("What the weather means for this field")
    if not w.signals:
        md('<div class="an-note">No notable weather signals for the coming week.</div>')
    for s in w.signals:
        md(f'<div class="an-card tight"><div style="display:flex;justify-content:space-between"><div class="title">{esc(s.title)} · {esc(s.value)}</div>'
           f'{badge(s.severity, SEV_BADGE.get(s.severity, "grey"))}</div><div class="sub">{esc(s.meaning)}</div>'
           f'<div style="font-size:.86rem;margin-top:.3rem"><b>→</b> {esc(s.action)}</div></div>')
    why_expander(w.explanation, "Why? — weather interpretation", key="wx")


# ----------------------------------------------------------------------------- water
def _water_tab(a, ctx) -> None:
    wa = a.water
    c = st.columns(5)
    with c[0]:
        kpi("Status", wa.status.replace("_", " ").title(), f"{wa.mode} mode")
    with c[1]:
        kpi("Root-zone deficit", f"{wa.deficit_mm:.0f} mm" if wa.deficit_mm is not None else "—", f"RAW {wa.raw_mm:.0f} mm" if wa.raw_mm is not None else "needs weather + soil")
    with c[2]:
        kpi("Stress ratio", f"{wa.stress_ratio:.2f}" if wa.stress_ratio is not None else "—", "deficit / readily available water")
    with c[3]:
        kpi("Crop ET 7 d", f"{wa.etc_7d_mm:.0f} mm" if wa.etc_7d_mm is not None else "—", f"effective rain {wa.rain_eff_7d_mm:.0f} mm" if wa.rain_eff_7d_mm is not None else "")
    with c[4]:
        kpi("Advice", wa.irrigation_advice.replace("_", " "), f"apply ≈{wa.net_mm_recommended:.0f} mm net" if wa.net_mm_recommended else "")
    if wa.deficit_mm is not None and wa.raw_mm:
        fig = go.Figure(go.Indicator(mode="gauge+number", value=wa.deficit_mm, number=dict(suffix=" mm"), title=dict(text="Root-zone deficit vs RAW"),
                                     gauge=dict(axis=dict(range=[0, max(wa.raw_mm * 1.5, wa.deficit_mm * 1.1)]), bar=dict(color=score_color(100 - 100 * wa.stress_ratio)),
                                                steps=[dict(range=[0, wa.raw_mm * 0.7], color="#E6F4EC"), dict(range=[wa.raw_mm * 0.7, wa.raw_mm], color="#FFF3DF"),
                                                       dict(range=[wa.raw_mm, wa.raw_mm * 1.5], color="#FCE8E6")],
                                                threshold=dict(line=dict(color=RED, width=3), value=wa.raw_mm))))
        fig.update_layout(height=240, margin=dict(l=20, r=20, t=40, b=0))
        plot(fig, key="water_gauge")
    md(f'<div class="an-card"><div class="title">Irrigation decision</div><div class="sub">{esc(wa.explanation.summary)}</div>'
       f'<div style="margin-top:.4rem">{badge("Modelled · FAO-56 style balance", "blue")}{badge(wa.mode, "grey")}'
       f'{badge(f"last irrigation {wa.days_since_irrigation} d ago", "grey") if wa.days_since_irrigation is not None else ""}</div></div>')
    why_expander(wa.explanation, "Why? — water balance factors", key="water")


# ------------------------------------------------------------------------------ risk
def _risk_tab(a, kr) -> None:
    if not a.risks:
        md('<div class="an-note">No active risks detected from the available data.</div>')
        return
    df = pd.DataFrame([{"risk": r.title, "score": r.score, "severity": r.severity.value} for r in a.risks])
    fig = go.Figure(go.Bar(x=df["score"], y=df["risk"], orientation="h", text=df["severity"], textposition="outside",
                           marker_color=[{"low": GREY, "moderate": AMBER, "high": RED, "critical": "#7A0C0C"}[s] for s in df["severity"]]))
    fig.update_layout(height=60 + 40 * len(df), margin=dict(l=0, r=80, t=4, b=4), xaxis=dict(range=[0, 115], showticklabels=False, showgrid=False),
                      yaxis=dict(autorange="reversed"), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    plot(fig, key="risk_chart")
    cover = {m.item_id: m for m in (kr.insurance if kr else []) if not m.payload.get("is_livestock")}
    for i, r in enumerate(a.risks):
        risk_card(r)
        linked = [m for m in cover.values() if any(h == r.risk_type for h in m.payload.get("risk_hits", []))]
        if linked:
            md('<div style="margin:-.5rem 0 .8rem .5rem;font-size:.82rem">☂️ KB insurance covering this risk: ' +
               ", ".join(f'<span class="an-chip">{esc(m.title)} ({m.score:.0f}%)</span>' for m in linked[:3]) + "</div>")
        why_expander(r.explanation, "Why? — risk detection", key=f"risk{i}")


def render() -> None:
    ctx = state.ensure_context()
    st.title("🗺️ Farm Intelligence")
    demo_banner(ctx)
    render_body(ctx, state.get_assessment())


def render_body(ctx, a) -> None:
    kr = a.knowledge
    top = st.columns([1.5, 1])
    with top[0]:
        _map(ctx, kr.loans.branches if kr else [])
    with top[1]:
        md(f'<div class="an-card"><div class="title">Field</div><div class="sub">'
           f'<b>{esc(ctx.location.village or "")}</b> {esc(ctx.location.district)}, {esc(ctx.location.state)}<br>'
           f'Zone: {esc(ctx.location.agro_climatic_zone or "—")}<br>Area: {ctx.area_acres:.2f} ac ({ctx.area_hectares:.2f} ha)<br>'
           f'Lat/Lon: {ctx.location.latitude}, {ctx.location.longitude}<br>'
           f'Irrigation: {"yes" if ctx.irrigation.available else "rainfed"}{(" · " + esc(ctx.irrigation.source) + " · " + esc(ctx.irrigation.method or "")) if ctx.irrigation.available else ""}'
           f'</div></div>')
        md('<div class="an-card"><div class="title">Data provenance</div>' +
           "".join(f'<div style="font-size:.8rem"><b>{esc(k)}</b>: {esc(v)}</div>' for k, v in ctx.data_sources().items()) + "</div>")
    tabs = st.tabs(["🛰️ NDVI", "🧪 Soil", "🌦️ Weather", "💧 Water balance", f"⚠️ Risk Center ({len(a.risks)})"])
    with tabs[0]:
        _ndvi_tab(a, ctx)
    with tabs[1]:
        _soil_tab(a, ctx)
    with tabs[2]:
        _weather_tab(a, ctx)
    with tabs[3]:
        _water_tab(a, ctx)
    with tabs[4]:
        _risk_tab(a, kr)
    footer()
