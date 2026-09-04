from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from core import DATA_DIR, KB_DIR, CONFIG_DIR
from core.auth import Permission, User, authorize, list_users, Role

_START = time.time()


def platform_counts(user: User, kb, registry) -> Dict[str, Any]:
    authorize(user, Permission.SYSTEM_MONITOR, "view platform counts")
    users = list_users()
    loans = registry.view("loans")
    schemes = registry.view("schemes")
    return {
        "users": len(users),
        "users_by_role": {r.value: sum(1 for u in users if u.role == r) for r in Role},
        "banks": int(registry.view("banks")["bank_name"].nunique()),
        "branches": int(len(kb.branches)),
        "loan_products": int((loans["status"] == "active").sum()),
        "loan_products_session_added": int(loans["origin"].astype(str).str.startswith("added").sum()),
        "government_schemes": int((schemes["status"] == "active").sum()),
        "insurance_products": int((~kb.insurance["excluded"]).sum()),
        "subsidies": int((~kb.subsidies["excluded"]).sum()),
        "crops": int(len(kb.crops)),
        "districts": int(len(kb.geo)),
        "eligibility_rules": int((~kb.eligibility_rules["excluded"]).sum()),
        "ai_rules": int((~kb.ai_rules["excluded"]).sum()),
        "documents": int(len(kb.documents)),
        "session_changes": len(registry.change_log()),
        "storage": registry.storage_label,
    }


def kb_health(user: User, kb) -> Dict[str, Any]:
    authorize(user, Permission.KB_ADMIN, "view knowledge-base health")
    s = kb.summary()
    files = []
    for p in sorted(KB_DIR.glob("*.csv")):
        with open(p, "rb") as fh:
            n_rows = sum(1 for _ in fh) - 1
        files.append({"file": p.name, "rows": int(n_rows), "size_kb": round(p.stat().st_size / 1024, 1),
                      "checksum": s["checksums"].get(p.stem, "unknown")})
    overrides = [{"id": o.override_id, "table": o.table, "key": ", ".join(f"{k}={v}" for k, v in o.key.items()), "column": o.column,
                  "original": str(o.original)[:60], "new": str(o.new)[:60], "reason": o.reason} for o in kb.override_log]
    return {"tables": s["tables"], "files": files, "overrides": overrides, "exclusions": s["exclusions"], "checksums_ok": all(v == "ok" for v in s["checksums"].values()),
            "coverage": {"deep": kb.interpretation.get("deep_coverage_states", []), "moderate": kb.interpretation.get("moderate_coverage_states", [])}}


def data_quality(user: User, kb) -> pd.DataFrame:
    """Simple, explainable checks over the loaded KB (post-overrides)."""
    authorize(user, Permission.KB_ADMIN, "run data-quality checks")
    rows: List[Dict[str, Any]] = []

    def add(table, check, n, sev, detail=""):
        rows.append({"table": table, "check": check, "count": int(n), "severity": sev if n else "ok", "detail": detail})

    l = kb.loans
    add("loans", "min interest > max interest", (l["minimum_interest"] > l["maximum_interest"]).sum(), "high")
    add("loans", "amount_min > amount_max", (l["loan_amount_min"] > l["loan_amount_max"]).sum(), "high")
    add("loans", "excluded via overrides", l["excluded"].sum(), "info")
    add("loans", "crop_specific crop not in crop master", sum(1 for c in l["crop_specific"] if str(c).lower() not in ("no", "nan", "") and kb.vocab.resolve_crop_name(str(c)) is None), "medium")
    s = kb.schemes
    add("schemes", "inactive status", (~s["is_active"]).sum(), "info")
    add("schemes", "minimum_land > maximum_land", ((s["minimum_land"] > s["maximum_land"]) & s["maximum_land"].notna()).sum(), "high")
    add("schemes", "excluded via overrides", s["excluded"].sum(), "info")
    i = kb.insurance
    add("insurance", "covered crop not in crop master (non-livestock)", sum(1 for c, lv in zip(i["covered_crop"], i["is_livestock"]) if not lv and kb.vocab.resolve_crop_name(str(c)) is None), "medium")
    add("insurance", "premium % missing", i["premium_percentage"].isna().sum(), "medium")
    c = kb.crops
    add("crops", "soil type not canonicalised", c["soil_canonical"].isna().sum(), "medium")
    add("crops", "min rainfall > max rainfall", (c["minimum_rainfall"] > c["maximum_rainfall"]).sum(), "high")
    g = kb.geo
    add("geo", "district without coordinates", (g["latitude"].isna() | g["longitude"].isna()).sum(), "high")
    add("geo", "major crop not in crop master", sum(1 for x in g["major_crop"] if not str(x).startswith("Not Applicable") and kb.vocab.resolve_crop_name(str(x)) is None), "low",
        "e.g. 'Vegetables' is a group, not a crop")
    b = kb.branches
    add("branches", "district not in district master", (~b["district"].isin(set(g["district_name"]))).sum(), "medium")
    add("branches", "missing IFSC", b["ifsc"].isna().sum(), "low")
    e = kb.eligibility_rules
    add("eligibility_rules", "recommended scheme not in schemes table", (~e["recommended_scheme"].isin(set(s["scheme_name"])) & e["recommended_scheme"].notna()).sum(), "medium")
    d = kb.documents
    add("documents", "scheme_name not in schemes table", (~d["scheme_name"].isin(set(s["scheme_name"])) & d["scheme_name"].notna()).sum(), "low")
    return pd.DataFrame(rows, columns=["table", "check", "count", "severity", "detail"])


def system_status(user: User, kb, matrix) -> Dict[str, Any]:
    authorize(user, Permission.SYSTEM_MONITOR, "view system status")
    import streamlit, pandas, numpy, plotly, pydeck
    secrets_path = Path.cwd() / ".streamlit" / "secrets.toml"
    return {
        "python": sys.version.split()[0], "platform": platform.platform(), "streamlit": streamlit.__version__, "pandas": pandas.__version__,
        "numpy": numpy.__version__, "plotly": plotly.__version__, "pydeck": pydeck.__version__,
        "uptime_s": int(time.time() - _START), "pid": os.getpid(),
        "kb_dir": str(KB_DIR), "config_dir": str(CONFIG_DIR), "derived_dir": str(DATA_DIR / "derived"),
        "matrix_available": matrix.available, "matrix_stale": matrix.stale, "matrix_meta": matrix.meta,
        "secrets_file": secrets_path.exists(),
        "checksums_ok": all(v == "ok" for v in kb.checksum_status.values()),
    }
