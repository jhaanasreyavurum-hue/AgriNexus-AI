"""⚙️ System Monitoring — runtime, integrations, caches, analytics backbone, engine self-test, registry activity."""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from core.admin import platform_counts, system_status
from core.auth import Permission
from core.integrations.weather import get_provider
from core.reasoning.narrator import narrator_enabled
from ui import state
from ui.analytics_components import kpi_row
from ui.components import badge, esc, footer, md, table
from ui.pages.admin._common import guard


def _integration_rows(secrets) -> pd.DataFrame:
    try:
        wp = get_provider(secrets)
        weather = (wp.name, "configured" if not wp.requires_key else "keyed provider", "green")
    except Exception as exc:  # misconfigured keyed provider
        weather = ("—", f"error: {str(exc)[:60]}", "red")
    llm = ("LLM narrator", "enabled (rephrase-only)" if narrator_enabled(secrets) else "off — no LLM_API_KEY secret", "green" if narrator_enabled(secrets) else "grey")
    rows = [
        {"integration": "Weather", "provider": weather[0], "status": weather[1], "basis": "WEATHER API (live) / offline fallback", "secret keys": "WEATHER_PROVIDER, OPENWEATHER_API_KEY (optional)"},
        {"integration": "Remote sensing (NDVI)", "provider": "DEMO series + user upload", "status": "no satellite credentials configured", "basis": "DEMO / user-supplied", "secret keys": "— (Sentinel Hub not wired)"},
        {"integration": llm[0], "provider": "openai / anthropic / gemini", "status": llm[1], "basis": "LLM-GENERATED explanation only", "secret keys": "LLM_PROVIDER, LLM_API_KEY, LLM_MODEL"},
        {"integration": "Persistence", "provider": "in-memory registry", "status": "session-only (no database)", "basis": "—", "secret keys": "— (RegistryBackend extension point)"},
    ]
    return pd.DataFrame(rows)


def _self_test(kb):
    """Run the real engines on the primary demo farm and time them — a smoke test, not a benchmark."""
    from core.models.farm_context import load_farm_context
    from core.reasoning import run_full_assessment
    from core.models.farm_context import list_demo_farms
    farms = list_demo_farms()
    if not farms:
        return None
    farms.sort(key=lambda f: 0 if str(f["farm_id"]).startswith("TS_") else 1)   # primary demo farm first
    t0 = time.time()
    ctx = load_farm_context(farms[0]["path"])
    a = run_full_assessment(ctx, kb)
    dt = time.time() - t0
    nba = a.next_best_action
    return {"farm": farms[0]["farm_name"], "seconds": round(dt, 2), "schemes": len(a.knowledge.schemes), "loans": len(a.knowledge.loans.products),
            "insurance": len(a.knowledge.insurance), "subsidies": len(a.knowledge.subsidies), "nba": nba.action if nba else "—"}


def render() -> None:
    user = guard(Permission.SYSTEM_MONITOR)
    st.title("⚙️ System Monitoring")
    kb = state.get_kb()
    reg = state.get_registry()
    matrix = state.get_matrix()
    s = system_status(user, kb, matrix)
    c = platform_counts(user, kb, reg)
    ok = s["checksums_ok"] and matrix.available and not matrix.stale
    kpi_row([("Status", "nominal" if ok else "attention", f"pid {s['pid']} · uptime {s['uptime_s'] // 60} min"),
             ("Runtime", f"Py {s['python']}", f"Streamlit {s['streamlit']} · pandas {s['pandas']}"),
             ("KB checksums", "ok" if s["checksums_ok"] else "MISMATCH", f"{len(kb.override_log)} overrides"),
             ("Segment matrix", "ready" if matrix.available else "missing", ("stale — rebuild" if matrix.stale else f"{matrix.meta.get('rows', 0):,} rows") if matrix.available else "run build script"),
             ("Registry changes", str(c["session_changes"]), c["storage"])], badge("system", "grey"))

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.subheader("Integrations & secrets")
        table(_integration_rows(state.secrets()), height=200)
        st.caption(f"Secrets file present: {'yes' if s['secrets_file'] else 'no'} (.streamlit/secrets.toml). Keys are read via st.secrets / environment and never displayed.")
    with c2:
        st.subheader("Environment")
        table(pd.DataFrame([{"component": k, "value": v} for k, v in {"platform": s["platform"], "python": s["python"], "streamlit": s["streamlit"], "pandas": s["pandas"], "numpy": s["numpy"],
                                                                        "plotly": s["plotly"], "pydeck": s["pydeck"], "kb_dir": s["kb_dir"], "derived_dir": s["derived_dir"]}.items()]), height=200)

    st.subheader("Modelled analytics backbone (segment matrix)")
    m = matrix.meta
    if matrix.available:
        md(f'<div class="an-card tight"><div class="title">segment_matrix.csv {badge("stale — KB/overrides changed since build", "amber") if matrix.stale else badge("current", "green")}</div>'
           f'<div class="sub">{m.get("rows", 0):,} rows · {m.get("districts", 0)} districts · {len(m.get("segments", []))} segments · built {esc(m.get("built_at", "?"))} · fingerprint {esc(m.get("fingerprint", "?"))} · errors {m.get("errors", 0)}</div>'
           f'<div class="sub" style="margin-top:.3rem">{esc(m.get("basis", ""))}</div></div>')
    else:
        st.error("Segment matrix not built — bank and government analytics are unavailable.")
    md('<div class="an-note">Rebuild from a shell: <code>python3 scripts/build_segment_matrix.py --workers 2</code> (≈ 8–10 min on a 2-CPU host; runs the real KB engines over every district × segment). '
       'It is deliberately not triggered from the web UI — it would block the server for all users.</div>')

    st.subheader("Caches")
    b1, b2, b3 = st.columns(3)
    if b1.button("Clear farm-assessment cache", key="mon_clear_assess"):
        state._assess_cached.clear()
        st.success("Assessment cache cleared — next farmer page load recomputes.")
    if b2.button("Clear analytics caches", key="mon_clear_analytics"):
        try:
            from ui.pages.bank._common import _ci_cached
            from ui.pages.government._common import _ii_cached
            _ci_cached.clear()
            _ii_cached.clear()
            st.success("Credit / inclusion intelligence caches cleared.")
        except Exception as exc:
            st.error(str(exc))
    if b3.button("Run engine self-test", key="mon_selftest"):
        with st.spinner("Running the full assessment on the primary demo farm…"):
            try:
                r = _self_test(kb)
            except Exception as exc:
                st.error(f"Self-test failed: {exc}")
            else:
                if r:
                    st.success(f"OK in {r['seconds']} s — {r['farm']}: {r['schemes']} schemes, {r['loans']} loan products, {r['insurance']} covers, {r['subsidies']} subsidies matched; NBA: {r['nba']}")
                else:
                    st.warning("No demo farm available for the self-test.")

    st.subheader("Registry activity (all tables, session-only)")
    log = reg.change_log()
    if log:
        table(pd.DataFrame([{"#": r.change_id, "table": r.table, "op": r.op, "key": r.key, "by": r.by, "role": r.role, "at": r.at, "persisted": r.persisted} for r in log[::-1]]), height=260)
    else:
        st.caption("No registry changes in this server session.")
    footer()
