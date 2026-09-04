"""🏠 Admin Dashboard — platform counts, KB health, session changes, system status."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.admin import kb_health, platform_counts, system_status, data_quality
from core.auth import Role, Permission, ROLE_LABELS
from ui import auth, state
from ui.analytics_components import bar_chart, kpi_row
from ui.components import badge, esc, footer, md, table


def render() -> None:
    user = auth.require(Role.ADMINISTRATOR, perm=Permission.SYSTEM_MONITOR)
    st.title("🏠 Admin Dashboard")
    kb = state.get_kb()
    reg = state.get_registry()
    matrix = state.get_matrix()
    c = platform_counts(user, kb, reg)
    h = kb_health(user, kb)
    s = system_status(user, kb, matrix)
    dq = data_quality(user, kb)
    issues = dq[dq["severity"].isin(["high", "medium"])]

    status_ok = h["checksums_ok"] and matrix.available and not matrix.stale
    md(f'<div class="an-hero" style="background:linear-gradient(120deg,#2B2D42,#4A4E69)"><div class="eyebrow">Platform status</div>'
       f'<div class="action">{"All systems nominal" if status_ok else "Attention needed"} — {c["users"]} users · {c["banks"]} banks · {c["loan_products"]} loan products · '
       f'{c["government_schemes"]} government schemes · {c["insurance_products"]} insurance covers.</div>'
       f'<div class="why">KB checksums {"verified" if h["checksums_ok"] else "MISMATCH"} · {len(h["overrides"])} overrides applied · '
       f'segment matrix {"ready" if matrix.available else "NOT BUILT"}{" (stale)" if matrix.stale else ""} · {c["session_changes"]} session change(s) in registries · '
       f'{len(issues)} data-quality finding(s) at medium/high.</div>'
       f'<div class="meta"><span>Streamlit {esc(s["streamlit"])}</span><span>Python {esc(s["python"])}</span><span>uptime {s["uptime_s"] // 60} min</span>'
       f'<span>storage: {esc(c["storage"])}</span></div></div>')

    kpi_row([("Users", str(c["users"]), " · ".join(f"{ROLE_LABELS[Role(r)].split()[0]} {n}" for r, n in c["users_by_role"].items())),
             ("Banks", str(c["banks"]), f"{c['branches']} KB branches"),
             ("Loan products", str(c["loan_products"]), f"{c['loan_products_session_added']} added this session"),
             ("Government schemes", str(c["government_schemes"]), f"{c['subsidies']} subsidies"),
             ("Insurance covers", str(c["insurance_products"]), f"{c['crops']} crops · {c['districts']} districts"),
             ("Rules", f"{c['eligibility_rules']} + {c['ai_rules']}", "eligibility + segment rules")])

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.subheader("Knowledge-base health")
        rows = pd.DataFrame([{"Table": f["file"].replace("agrinexus_", "").replace(".csv", ""), "Rows": f["rows"], "Size (KB)": f["size_kb"],
                              "Checksum": "✅ ok" if f["checksum"] == "ok" else f"⚠️ {f['checksum']}"} for f in h["files"]])
        table(rows, height=390)
    with c2:
        st.subheader("Data quality (post-overrides)")
        sev_counts = dq["severity"].value_counts().reindex(["high", "medium", "low", "info", "ok"]).fillna(0).astype(int)
        md("".join(badge(f"{k}: {v}", {"high": "red", "medium": "amber", "low": "grey", "info": "blue", "ok": "green"}[k]) for k, v in sev_counts.items()))
        table(dq[dq["count"] > 0][["table", "check", "count", "severity"]].sort_values(["severity", "count"]), height=330)
        st.caption("Full detail and override log under Knowledge Base.")

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Modelled analytics backbone")
        m = matrix.meta
        if matrix.available:
            md(f'<div class="an-card tight"><div class="title">Segment matrix {badge("stale — rebuild", "amber") if matrix.stale else badge("current", "green")}</div>'
               f'<div class="sub">{m.get("rows", 0):,} rows · {m.get("districts", 0)} districts · {len(m.get("segments", []))} segments · built {esc(m.get("built_at", "?"))} · fingerprint {esc(m.get("fingerprint", "?"))}</div>'
               f'<div class="sub" style="margin-top:.3rem">{esc(m.get("basis", ""))}</div></div>')
        else:
            st.error("Segment matrix not built — bank and government analytics are unavailable. Use System Monitoring → Rebuild.")
    with c4:
        st.subheader("Recent registry changes (session-only)")
        log = reg.change_log()
        if log:
            table(pd.DataFrame([{"#": r.change_id, "table": r.table, "op": r.op, "key": r.key, "by": r.by, "role": r.role, "at": r.at, "persisted": r.persisted} for r in log[-10:]]))
        else:
            st.caption("No changes made in this server session. Registry changes are held in memory and clearly labelled as not persisted.")
    footer()
