"""Global CSS for the AgriNexus look (cards, badges, hero, score rings)."""
from __future__ import annotations

import streamlit as st

GREEN = "#1B7F4C"
GREEN_DARK = "#0F5A35"
GREEN_LIGHT = "#E6F4EC"
AMBER = "#C97A00"
AMBER_LIGHT = "#FFF3DF"
RED = "#B3261E"
RED_LIGHT = "#FCE8E6"
BLUE = "#1F5FA8"
BLUE_LIGHT = "#E8F0FB"
PURPLE = "#6B3FA0"
PURPLE_LIGHT = "#F0E9FA"
GREY = "#5B6B63"
GREY_LIGHT = "#EEF2F0"
INK = "#12261C"

CSS = f"""
<style>
:root {{ --an-green:{GREEN}; --an-green-dark:{GREEN_DARK}; --an-green-light:{GREEN_LIGHT};
        --an-amber:{AMBER}; --an-red:{RED}; --an-blue:{BLUE}; --an-ink:{INK}; --an-grey:{GREY}; }}
html, body, [class*="css"] {{ font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1280px; }}
section[data-testid="stSidebar"] {{ background: linear-gradient(180deg, #0F3D28 0%, #145A38 100%); }}
section[data-testid="stSidebar"] * {{ color: #E9F5EE !important; }}
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] .stRadio label {{ color: #12261C !important; }}
section[data-testid="stSidebar"] div[data-baseweb="select"] * {{ color: #12261C !important; }}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,.18); }}
h1, h2, h3 {{ color: var(--an-ink); letter-spacing: -0.01em; }}
h1 {{ font-weight: 800; }}
h2 {{ font-weight: 700; font-size: 1.35rem; margin-top: 1.4rem; }}
h3 {{ font-weight: 700; font-size: 1.05rem; }}

.an-brand {{ display:flex; align-items:center; gap:.6rem; padding:.2rem 0 .8rem 0; }}
.an-brand .logo {{ width:38px; height:38px; border-radius:10px; background:#E9F5EE; display:flex; align-items:center; justify-content:center; font-size:1.3rem; }}
.an-brand .name {{ font-weight:800; font-size:1.15rem; letter-spacing:-.01em; }}
.an-brand .tag {{ font-size:.72rem; opacity:.8; }}

.an-card {{ background:#fff; border:1px solid #E3EAE6; border-radius:14px; padding:1rem 1.15rem; margin-bottom:.9rem;
           box-shadow:0 1px 2px rgba(18,38,28,.04); }}
.an-card.tight {{ padding:.75rem .95rem; }}
.an-card .title {{ font-weight:700; font-size:1rem; color:var(--an-ink); margin-bottom:.15rem; }}
.an-card .sub {{ color:var(--an-grey); font-size:.86rem; }}
.an-kpi {{ background:#fff; border:1px solid #E3EAE6; border-radius:14px; padding:.85rem 1rem; min-height:92px; }}
.an-kpi .lbl {{ font-size:.74rem; text-transform:uppercase; letter-spacing:.06em; color:var(--an-grey); font-weight:600; }}
.an-kpi .val {{ font-size:1.35rem; font-weight:800; color:var(--an-ink); margin-top:.15rem; line-height:1.2; }}
.an-kpi .sub {{ font-size:.78rem; color:var(--an-grey); margin-top:.15rem; }}

.an-hero {{ border-radius:18px; padding:1.3rem 1.5rem; color:#fff; margin-bottom:1rem;
            background:linear-gradient(120deg, #0F5A35 0%, #1B7F4C 55%, #2E9E63 100%); box-shadow:0 8px 24px rgba(15,90,53,.25); }}
.an-hero .eyebrow {{ font-size:.75rem; text-transform:uppercase; letter-spacing:.14em; font-weight:700; opacity:.9; }}
.an-hero .action {{ font-size:1.45rem; font-weight:800; line-height:1.3; margin:.35rem 0 .5rem 0; }}
.an-hero .why {{ font-size:.95rem; opacity:.95; }}
.an-hero .meta {{ margin-top:.7rem; display:flex; gap:.5rem; flex-wrap:wrap; }}
.an-hero .meta span {{ background:rgba(255,255,255,.16); border:1px solid rgba(255,255,255,.3); border-radius:999px; padding:.18rem .65rem; font-size:.78rem; font-weight:600; }}

.an-badge {{ display:inline-block; border-radius:999px; padding:.14rem .6rem; font-size:.74rem; font-weight:700; letter-spacing:.02em; margin-right:.3rem; margin-bottom:.2rem; white-space:nowrap; }}
.an-badge.green {{ background:{GREEN_LIGHT}; color:{GREEN_DARK}; }}
.an-badge.amber {{ background:{AMBER_LIGHT}; color:{AMBER}; }}
.an-badge.red {{ background:{RED_LIGHT}; color:{RED}; }}
.an-badge.blue {{ background:{BLUE_LIGHT}; color:{BLUE}; }}
.an-badge.purple {{ background:{PURPLE_LIGHT}; color:{PURPLE}; }}
.an-badge.grey {{ background:{GREY_LIGHT}; color:{GREY}; }}
.an-badge.demo {{ background:#FFF0C2; color:#7A5300; border:1px dashed #D9A400; }}

.an-score {{ display:flex; align-items:center; gap:.9rem; }}
.an-ring {{ width:74px; height:74px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.15rem; color:var(--an-ink); flex-shrink:0; }}
.an-ring .inner {{ width:58px; height:58px; border-radius:50%; background:#fff; display:flex; align-items:center; justify-content:center; }}
.an-bar {{ height:8px; border-radius:999px; background:#EEF2F0; overflow:hidden; margin:.3rem 0; }}
.an-bar > div {{ height:100%; border-radius:999px; }}

.an-factor {{ display:flex; gap:.5rem; align-items:flex-start; font-size:.86rem; margin:.18rem 0; color:var(--an-ink); }}
.an-factor .ic {{ width:1.1rem; flex-shrink:0; text-align:center; }}
.an-factor .nm {{ font-weight:600; }}
.an-factor .dt {{ color:var(--an-grey); }}
.an-factor .src {{ color:#8A9891; font-size:.76rem; }}

.an-rank {{ width:30px; height:30px; border-radius:9px; background:var(--an-green-light); color:var(--an-green-dark); font-weight:800; display:flex; align-items:center; justify-content:center; flex-shrink:0; }}
.an-row {{ display:flex; gap:.8rem; align-items:flex-start; }}
.an-doc {{ font-size:.84rem; margin:.12rem 0; }}
.an-doc.ok {{ color:{GREEN_DARK}; }}
.an-doc.miss {{ color:{RED}; }}
.an-doc.form {{ color:{GREY}; }}
.an-doc.na {{ color:#9AA8A1; text-decoration:line-through; }}
.an-note {{ background:{BLUE_LIGHT}; border-left:4px solid {BLUE}; padding:.6rem .8rem; border-radius:8px; font-size:.86rem; margin:.5rem 0; }}
.an-warn {{ background:{AMBER_LIGHT}; border-left:4px solid {AMBER}; padding:.6rem .8rem; border-radius:8px; font-size:.86rem; margin:.5rem 0; }}
.an-demo {{ background:#FFF7DF; border:1px dashed #D9A400; padding:.5rem .8rem; border-radius:8px; font-size:.84rem; color:#5E4200; margin:.3rem 0 .8rem 0; }}
.an-timeline {{ display:flex; gap:4px; margin:.4rem 0; }}
.an-timeline .seg {{ flex:1; border-radius:6px; padding:.35rem .4rem; font-size:.72rem; text-align:center; border:1px solid #E3EAE6; }}
.an-timeline .seg.done {{ background:{GREEN_LIGHT}; color:{GREEN_DARK}; }}
.an-timeline .seg.current {{ background:{GREEN}; color:#fff; font-weight:700; }}
.an-timeline .seg.upcoming {{ background:#fff; color:{GREY}; }}
.an-timeline .seg.crit {{ box-shadow: inset 0 -3px 0 {AMBER}; }}
.an-chip {{ display:inline-block; background:#F3F6F4; border:1px solid #E3EAE6; border-radius:8px; padding:.18rem .5rem; font-size:.78rem; margin:.12rem .2rem .12rem 0; color:var(--an-ink); }}
.an-foot {{ color:#8A9891; font-size:.76rem; margin-top:2rem; border-top:1px solid #E3EAE6; padding-top:.6rem; }}
div[data-testid="stExpander"] details {{ border-radius:10px; border:1px solid #E3EAE6; }}
div[data-testid="stExpander"] summary {{ font-weight:600; }}
.stTabs [data-baseweb="tab"] {{ font-weight:600; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
