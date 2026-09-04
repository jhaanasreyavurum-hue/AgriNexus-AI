"""🧠 Knowledge Base — table inventory, checksums, override log, data-quality findings, coverage."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.admin import data_quality, kb_health
from core.auth import Permission
from ui import state
from ui.analytics_components import bar_chart, kpi_row
from ui.components import badge, esc, footer, md, table
from ui.pages.admin._common import guard

_SEV = {"high": "red", "medium": "amber", "low": "grey", "info": "blue", "ok": "green"}


def render() -> None:
    user = guard(Permission.KB_ADMIN)
    st.title("🧠 Knowledge Base")
    kb = state.get_kb()
    h = kb_health(user, kb)
    dq = data_quality(user, kb)
    files = pd.DataFrame(h["files"])
    n_rows = int(files["rows"].sum())
    kpi_row([("Tables", str(len(h["tables"])), f"{n_rows:,} rows · {files['size_kb'].sum():.0f} KB"),
             ("Checksums", "verified" if h["checksums_ok"] else "MISMATCH", "pinned in CHECKSUMS.sha256"),
             ("Overrides applied", str(len(h["overrides"])), "kb_overrides.yaml (documented)"),
             ("Exclusions", str(sum(h["exclusions"].values())), "rows hidden from engines"),
             ("DQ findings", str(int((dq["severity"].isin(["high", "medium"])).sum())), "medium/high, post-overrides")],
            badge("KNOWLEDGE BASE", "green") + (badge("read-only", "grey")))
    md('<div class="an-note">The knowledge base is loaded <b>read-only</b> from the original CSVs. Known data errors are corrected at load time through an explicit, referenced overrides file; '
       'the originals are never edited and their checksums are verified on every start. This page shows the state of that pipeline — it is not a table viewer.</div>')

    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.subheader("Tables & integrity")
        inv = files.copy()
        inv["table"] = inv["file"].str.replace("agrinexus_", "", regex=False).str.replace(".csv", "", regex=False)
        inv["checksum"] = inv["checksum"].map(lambda v: "✅ ok" if v == "ok" else f"⚠️ {v}")
        inv["loaded rows"] = inv["table"].map(lambda t: next((n for k, n in h["tables"].items() if k in t or t in k), None))
        table(inv[["table", "rows", "loaded rows", "size_kb", "checksum"]].rename(columns={"rows": "file rows", "size_kb": "KB"}), height=400)
    with c2:
        st.subheader("Coverage")
        md(f'<div class="an-card tight"><div class="title">Deep coverage</div><div class="sub">{esc(", ".join(h["coverage"]["deep"]) or "—")} — schemes, rules, branches, districts, insurance all present.</div></div>'
           f'<div class="an-card tight"><div class="title">Moderate coverage</div><div class="sub">{esc(", ".join(h["coverage"]["moderate"]) or "—")} — central schemes + partial state data; no branch directory.</div></div>'
           f'<div class="an-card tight"><div class="title">Other states</div><div class="sub">Central schemes, national loan products and crop master only; district analytics limited to the {len(kb.geo)} KB districts.</div></div>')
        geo = kb.geo.groupby("state_name").size().rename("districts").reset_index()
        bar_chart(geo.sort_values("districts"), "state_name", "districts", "KB districts per state", key="kb_geo", height=220, text_fmt="%{text}")

    st.subheader("Data-quality findings (post-overrides)")
    sev_counts = dq["severity"].value_counts().reindex(["high", "medium", "low", "info", "ok"]).fillna(0).astype(int)
    md("".join(badge(f"{k}: {v}", _SEV[k]) for k, v in sev_counts.items()))
    show_ok = st.checkbox("Show passing checks", value=False, key="kb_show_ok")
    d = dq if show_ok else dq[dq["count"] > 0]
    table(d.sort_values(["severity", "count"], key=lambda s: s.map({"high": 0, "medium": 1, "low": 2, "info": 3, "ok": 4}) if s.name == "severity" else -s), height=340)
    st.caption("Checks are simple and explainable (range sanity, referential integrity, vocabulary resolution). Findings at medium/high are candidates for a new documented override — never a direct CSV edit.")

    st.subheader(f"Override log ({len(h['overrides'])})")
    ov = pd.DataFrame(h["overrides"])
    if len(ov):
        c3, c4 = st.columns([1, 2])
        with c3:
            bar_chart(ov.groupby("table").size().rename("n").reset_index().sort_values("n"), "table", "n", "Overrides by table", key="kb_ov_bar", height=300, text_fmt="%{text}")
        with c4:
            t_pick = st.multiselect("Table", sorted(ov["table"].unique()), key="kb_ov_table", placeholder="All tables")
            v = ov if not t_pick else ov[ov["table"].isin(t_pick)]
            table(v[["id", "table", "key", "column", "original", "new", "reason"]], height=300)
    ex = {k: v for k, v in h["exclusions"].items() if v}
    if ex:
        md('<div class="an-note">Excluded rows (hidden from all engines): ' + ", ".join(f"<b>{esc(k)}</b> {v}" for k, v in ex.items()) + "</div>")
    footer()
