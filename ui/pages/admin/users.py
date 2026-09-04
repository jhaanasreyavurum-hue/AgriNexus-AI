"""👥 Users — account directory, roles & permissions matrix, farmer self-registrations."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.auth import Permission, ROLE_LABELS, ROLE_PERMISSIONS, Role
from core.auth.service import user_directory
from ui.analytics_components import donut, kpi_row
from ui.components import badge, esc, footer, md, table
from ui.pages.admin._common import guard


def render() -> None:
    user = guard(Permission.USERS_MANAGE)
    st.title("👥 Users")
    md('<div class="an-note">Identity is a <b>demo directory</b> (<code>data/config/users.yaml</code>, salted SHA-256 hashes) plus farmer self-registrations held for this server process only. '
       'Other roles are provisioned by editing the directory file — there is no database or identity provider behind this deployment, and passwords are never shown here.</div>')
    rows = user_directory()
    df = pd.DataFrame(rows)
    df["role_label"] = df["role"].map(lambda r: ROLE_LABELS[Role(r)])
    by_role = df["role"].value_counts()
    demo_n = int(df["origin"].str.contains("demo").sum())
    kpi_row([("Accounts", str(len(df)), f"{demo_n} demo · {len(df) - demo_n} self-registered"),
             ("Farmers", str(int(by_role.get("farmer", 0))), f"{int(df[(df['role'] == 'farmer') & df['farm_id'].notna()].shape[0])} linked to a farm"),
             ("Bank managers", str(int(by_role.get("bank_manager", 0))), ""),
             ("Government officers", str(int(by_role.get("government_officer", 0))), ""),
             ("Administrators", str(int(by_role.get("administrator", 0))), "you: " + user.username)])

    c1, c2 = st.columns([1.6, 1])
    with c1:
        st.subheader("Directory")
        f_role = st.multiselect("Role", [r.value for r in Role], format_func=lambda r: ROLE_LABELS[Role(r)], key="usr_role", placeholder="All roles")
        v = df if not f_role else df[df["role"].isin(f_role)]
        show = v[["username", "display_name", "role_label", "organisation", "farm_id", "bank_name", "home_state", "origin"]].rename(
            columns={"username": "Username", "display_name": "Name", "role_label": "Role", "organisation": "Organisation", "farm_id": "Farm", "bank_name": "Bank", "home_state": "Home state", "origin": "Origin"})
        table(show.fillna("—"), height=330)
    with c2:
        donut(df["role_label"].value_counts().rename_axis("role").reset_index(name="n"), "role", "n", "Accounts by role", key="usr_donut", height=330)

    st.subheader("Role → permission matrix (enforced in core functions)")
    perms = list(Permission)
    mat = pd.DataFrame({ROLE_LABELS[r]: ["✅" if p in ROLE_PERMISSIONS[r] else "—" for p in perms] for r in Role}, index=[p.value for p in perms]).rename_axis("permission").reset_index()
    table(mat, height=420)
    st.caption("Every write in the data layer (registry adds/updates, farmer assessments, analytics) calls `authorize(user, permission)`; the navigation only mirrors this matrix.")

    st.subheader("Self-registered accounts (this server session)")
    sr = df[~df["origin"].str.contains("demo")]
    if len(sr):
        table(sr[["username", "display_name", "organisation"]].rename(columns={"username": "Username", "display_name": "Name", "organisation": "Location"}))
        md('<div class="an-warn">These accounts disappear when the server restarts. Self-registration is limited to the farmer role by <code>core.auth.register_farmer</code>.</div>')
    else:
        st.caption("None yet. Farmers can create an account from the login page; it is labelled session-only.")
    footer()
