from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import pandas as pd

from core.auth import Permission, User, authorize

# table -> (primary key, permission needed to modify)
MANAGED_TABLES: Dict[str, tuple] = {
    "loans": ("loan_id", Permission.LOAN_PRODUCTS_MANAGE),
    "schemes": ("scheme_id", Permission.REGISTRY_MANAGE),
    "banks": ("bank_name", Permission.REGISTRY_MANAGE),          # virtual table derived from branches
}

LOAN_EDITABLE = ["loan_name", "bank_name", "loan_type", "interest_rate", "minimum_interest", "maximum_interest", "loan_amount_min", "loan_amount_max",
                 "repayment_years", "processing_fee", "collateral_required", "crop_specific", "government_linked", "approval_days", "required_documents",
                 "eligibility_summary", "loan_score"]
SCHEME_EDITABLE = ["scheme_name", "scheme_type", "government_level", "state", "ministry", "objective", "eligible_crop", "eligible_farmer",
                   "minimum_land", "maximum_land", "income_limit", "maximum_subsidy", "subsidy_percentage", "application_mode", "official_portal", "active_status"]


@dataclass
class ChangeRecord:
    change_id: int
    table: str
    op: str                    # add | update | deactivate
    key: str
    fields: Dict[str, Any]
    by: str
    role: str
    at: str
    persisted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RegistryBackend:
    """Interface. Implement ``append`` / ``changes`` against a database for persistence."""
    persistent = False
    label = "abstract"

    def append(self, rec: ChangeRecord) -> None:
        raise NotImplementedError

    def changes(self) -> List[ChangeRecord]:
        raise NotImplementedError


class InMemoryBackend(RegistryBackend):
    persistent = False
    label = "in-memory (this server session only — changes are NOT persisted)"

    def __init__(self) -> None:
        self._log: List[ChangeRecord] = []
        self._lock = threading.Lock()

    def append(self, rec: ChangeRecord) -> None:
        with self._lock:
            self._log.append(rec)

    def changes(self) -> List[ChangeRecord]:
        with self._lock:
            return list(self._log)


class Registry:
    def __init__(self, kb, backend: Optional[RegistryBackend] = None) -> None:
        self.kb = kb
        self.backend = backend or InMemoryBackend()

    # ------------------------------------------------------------- reads
    @property
    def persistent(self) -> bool:
        return self.backend.persistent

    @property
    def storage_label(self) -> str:
        return self.backend.label

    def change_log(self, table: Optional[str] = None) -> List[ChangeRecord]:
        return [c for c in self.backend.changes() if table is None or c.table == table]

    def _base(self, table: str) -> pd.DataFrame:
        if table == "banks":
            br = self.kb.branches
            g = br.groupby("bank_name", as_index=False).agg(branches=("branch_name", "count"), districts=("district", "nunique"),
                                                            loan_desks=("loan_available_bool", "sum"), insurance_desks=("insurance_available_bool", "sum"),
                                                            government_linked=("government_linked", lambda s: (s == "Yes").mean() * 100))
            loans = self.kb.loans[~self.kb.loans["excluded"]].copy()
            loans["bank_short"] = loans["bank_name"].str.replace(r"\s*\(.*?\)", "", regex=True).str.strip()
            prod = loans.groupby("bank_short", as_index=False).agg(loan_products=("loan_id", "count"))
            g = g.merge(prod, left_on="bank_name", right_on="bank_short", how="outer").drop(columns=["bank_short"])
            g["bank_name"] = g["bank_name"].fillna("")
            g["status"] = "active"
            g["origin"] = "KB"
            return g.fillna({"branches": 0, "districts": 0, "loan_desks": 0, "insurance_desks": 0, "loan_products": 0, "government_linked": 0})
        df = self.kb.tables[table]
        df = df[~df["excluded"]].copy()
        df["status"] = "active"
        df["origin"] = "KB"
        return df

    def view(self, table: str) -> pd.DataFrame:
        """KB rows + session changes applied (adds appended, updates overlaid, deactivations flagged)."""
        pk, _ = MANAGED_TABLES[table]
        df = self._base(table).astype(object)   # object dtype: appended rows may leave KB-only columns empty
        for c in self.change_log(table):
            if c.op == "add":
                row = {col: None for col in df.columns} | c.fields | {pk: c.key, "status": "active", "origin": f"added by {c.by} (session)"}
                df.loc[len(df)] = [row.get(col) for col in df.columns]
            elif c.op == "update":
                m = df[pk].astype(str) == str(c.key)
                for k, v in c.fields.items():
                    if k in df.columns:
                        df.loc[m, k] = v
                df.loc[m, "origin"] = f"KB · updated by {c.by} (session)"
            elif c.op == "deactivate":
                df.loc[df[pk].astype(str) == str(c.key), "status"] = "inactive"
        return df

    def _overlay_table(self, table: str, numeric: tuple, normalise, defaults: Dict[str, Any]) -> pd.DataFrame:
        v = self.view(table)
        t = v[v["status"] == "active"].drop(columns=["status", "origin"]).copy()
        for c in numeric:
            if c in t.columns:
                t[c] = pd.to_numeric(t[c], errors="coerce")
        for c, d in defaults.items():
            if c in t.columns:
                t[c] = t[c].fillna(d)
        t["excluded"] = False
        for c in t.columns:
            if c.endswith("_bool") or c.endswith("_list") or c in ("crop_specific_flag", "is_active"):
                continue
            t[c] = t[c].infer_objects()
        normalise(t)
        return t.reset_index(drop=True)

    def effective_kb(self):
        """KnowledgeBase with the session overlay applied to the loans and schemes tables (KB object itself untouched).
        Used by the farmer matching engines so product / scheme changes on this server take effect immediately."""
        if not self.change_log("loans") and not self.change_log("schemes"):
            return self.kb
        import copy
        from core.kb.loader import normalise_loans, normalise_schemes
        kb2 = copy.copy(self.kb)
        kb2.tables = dict(self.kb.tables)
        if self.change_log("loans"):
            kb2.tables["loans"] = self._overlay_table("loans", ("minimum_interest", "maximum_interest", "loan_amount_min", "loan_amount_max", "repayment_years", "approval_days", "loan_score", "maximum_subsidy"),
                                                      normalise_loans, {"loan_score": 7.0, "approval_days": 15, "repayment_years": 1, "processing_fee": "Not specified",
                                                                        "collateral_required": "No", "government_linked": "No", "crop_specific": "No", "required_documents": "Aadhaar Card",
                                                                        "eligibility_summary": "", "interest_rate": ""})
        if self.change_log("schemes"):
            kb2.tables["schemes"] = self._overlay_table("schemes", ("minimum_land", "maximum_land", "income_limit", "minimum_age", "maximum_age", "maximum_subsidy", "subsidy_percentage", "processing_time_days", "priority_score"),
                                                        normalise_schemes, {"priority_score": 5.0, "active_status": "Active", "state": "All India", "eligible_crop": "All Crops", "eligible_farmer": "All Farmers"})
        return kb2

    @property
    def version(self) -> int:
        return len(self.backend.changes())

    def next_id(self, table: str, prefix: str) -> str:
        pk, _ = MANAGED_TABLES[table]
        ids = self.view(table)[pk].astype(str)
        nums = pd.to_numeric(ids.str.extract(r"(\d+)$")[0], errors="coerce").dropna()
        return f"{prefix}{int(nums.max()) + 1 if len(nums) else 1:03d}"

    # ------------------------------------------------------------- writes (authorised)
    def _write(self, user: User, table: str, op: str, key: str, fields: Dict[str, Any]) -> ChangeRecord:
        pk, perm = MANAGED_TABLES[table]
        authorize(user, perm, f"{op} {table}")
        rec = ChangeRecord(len(self.backend.changes()) + 1, table, op, str(key), dict(fields), user.username, user.role.value,
                           time.strftime("%Y-%m-%d %H:%M:%S"), persisted=self.backend.persistent)
        self.backend.append(rec)
        return rec

    def add(self, user: User, table: str, fields: Dict[str, Any], key: Optional[str] = None) -> ChangeRecord:
        pk, perm = MANAGED_TABLES[table]
        authorize(user, perm, f"add {table}")            # authorise before validating or allocating an id
        prefix = {"loans": "LOAN", "schemes": "SCHM", "banks": ""}[table]
        key = key or (fields.get(pk) if table == "banks" else self.next_id(table, prefix))
        if not key:
            raise ValueError("A key / name is required.")
        self._validate(table, fields, adding=True)
        return self._write(user, table, "add", key, fields)

    def update(self, user: User, table: str, key: str, fields: Dict[str, Any]) -> ChangeRecord:
        pk, perm = MANAGED_TABLES[table]
        authorize(user, perm, f"update {table}")
        if not (self.view(table)[pk].astype(str) == str(key)).any():
            raise KeyError(f"{table}: {key} not found")
        self._validate(table, fields, adding=False)
        return self._write(user, table, "update", key, fields)

    def deactivate(self, user: User, table: str, key: str) -> ChangeRecord:
        return self._write(user, table, "deactivate", key, {})

    # ------------------------------------------------------------- validation
    @staticmethod
    def _validate(table: str, f: Dict[str, Any], adding: bool) -> None:
        if table == "loans":
            if adding and not (f.get("loan_name") and f.get("bank_name") and f.get("loan_type")):
                raise ValueError("loan_name, bank_name and loan_type are required.")
            if adding:
                for k in ("minimum_interest", "maximum_interest", "loan_amount_min", "loan_amount_max"):
                    if f.get(k) is None:
                        raise ValueError(f"{k} is required for a new loan product.")
            lo, hi = f.get("loan_amount_min"), f.get("loan_amount_max")
            if lo is not None and hi is not None and float(lo) > float(hi):
                raise ValueError("loan_amount_min cannot exceed loan_amount_max.")
            mi, ma = f.get("minimum_interest"), f.get("maximum_interest")
            if mi is not None and ma is not None and float(mi) > float(ma):
                raise ValueError("minimum_interest cannot exceed maximum_interest.")
            for k in ("minimum_interest", "maximum_interest"):
                if f.get(k) is not None and not (0 <= float(f[k]) <= 40):
                    raise ValueError(f"{k} must be between 0 and 40 %.")
            if f.get("repayment_years") is not None and not (0 < int(f["repayment_years"]) <= 30):
                raise ValueError("repayment_years must be 1–30.")
        elif table == "schemes":
            if adding and not (f.get("scheme_name") and f.get("scheme_type") and f.get("government_level")):
                raise ValueError("scheme_name, scheme_type and government_level are required.")
        elif table == "banks":
            if adding and not f.get("bank_name"):
                raise ValueError("bank_name is required.")


_REGISTRY: Optional[Registry] = None
_LOCK = threading.Lock()


def get_registry(kb) -> Registry:
    """Process-wide registry (shared by all sessions of this server process)."""
    global _REGISTRY
    with _LOCK:
        if _REGISTRY is None or _REGISTRY.kb is not kb:
            _REGISTRY = Registry(kb)
        return _REGISTRY
