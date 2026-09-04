"""Shared helpers for administrator pages."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import Permission, Role, User
from ui import auth, state
from ui.components import badge, esc, md, table


def guard(perm: Permission) -> User:
    return auth.require(Role.ADMINISTRATOR, perm=perm)


def storage_notice(reg) -> None:
    if reg.persistent:
        md(f'<div class="an-note">Changes are persisted ({esc(reg.storage_label)}).</div>')
    else:
        md(f'<div class="an-warn">⚠️ <b>No persistent database in this deployment.</b> Additions and updates are held {esc(reg.storage_label)} — applied on top of the '
           'read-only knowledge base for every user of this server until it restarts, logged below and exportable. The original KB CSVs are never modified. '
           'Wire a database backend (core/store/registry.py → RegistryBackend) to make changes permanent.</div>')


def flash(key: str) -> None:
    if st.session_state.get(key):
        st.success(st.session_state.pop(key))


def change_log_panel(reg, table_name: str, fname: str) -> None:
    log = reg.change_log(table_name)
    if log:
        table(pd.DataFrame([{"#": r.change_id, "op": r.op, "key": r.key, "fields": ", ".join(f"{k}={v}" for k, v in r.fields.items())[:140], "by": r.by, "role": r.role, "at": r.at,
                             "persisted": r.persisted} for r in log]))
        st.download_button("Export change log (JSON)", pd.DataFrame([r.to_dict() for r in log]).to_json(orient="records", indent=2), fname, "application/json", key=f"dl_log_{table_name}")
    else:
        st.caption("No changes this session.")


def origin_badge(origin: str) -> str:
    o = str(origin)
    return badge("KB", "green") if o == "KB" else badge("session", "amber")


def rerun_after(key: str, msg: str) -> None:
    st.session_state[key] = msg
    state._assess_cached.clear()
    st.rerun()
