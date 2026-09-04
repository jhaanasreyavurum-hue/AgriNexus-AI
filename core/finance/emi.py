from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class EMIResult:
    principal: float
    annual_rate_pct: float
    tenure_months: int
    emi: float
    total_interest: float
    total_repayment: float
    method: str = "Standard reducing-balance EMI formula (deterministic arithmetic — not a bank quote)"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def emi(principal: float, annual_rate_pct: float, tenure_months: int) -> EMIResult:
    """Reducing-balance EMI. Rate 0 → straight-line."""
    if principal <= 0 or tenure_months <= 0:
        raise ValueError("Principal and tenure must be positive.")
    if annual_rate_pct < 0:
        raise ValueError("Interest rate cannot be negative.")
    r = annual_rate_pct / 12.0 / 100.0
    if r == 0:
        e = principal / tenure_months
    else:
        f = (1 + r) ** tenure_months
        e = principal * r * f / (f - 1)
    total = e * tenure_months
    return EMIResult(principal=float(principal), annual_rate_pct=float(annual_rate_pct), tenure_months=int(tenure_months),
                     emi=round(e, 2), total_interest=round(total - principal, 2), total_repayment=round(total, 2))


def amortisation_schedule(principal: float, annual_rate_pct: float, tenure_months: int) -> pd.DataFrame:
    res = emi(principal, annual_rate_pct, tenure_months)
    r = annual_rate_pct / 12.0 / 100.0
    bal = float(principal)
    rows = []
    for m in range(1, tenure_months + 1):
        interest = bal * r
        princ = res.emi - interest
        bal = max(bal - princ, 0.0)
        rows.append({"month": m, "emi": round(res.emi, 2), "interest": round(interest, 2), "principal": round(princ, 2), "balance": round(bal, 2)})
    return pd.DataFrame(rows, columns=["month", "emi", "interest", "principal", "balance"])


def compare_products(products: List[Dict[str, Any]], principal: float, tenure_months: Optional[int] = None) -> pd.DataFrame:
    """Compare KB loan products at a common principal. Each product dict needs
    ``title``, ``min_interest`` (pct), ``repayment_years``; amount range optional.
    Rate used = the product's minimum interest (KB) — the best-case published rate."""
    rows = []
    for p in products:
        rate = float(p.get("min_interest") or p.get("interest_rate_pct") or 0.0)
        months = int(tenure_months or int(p.get("repayment_years", 1)) * 12)
        amt_min, amt_max = p.get("amount_min"), p.get("amount_max")
        within = True
        if amt_min is not None and principal < float(amt_min):
            within = False
        if amt_max is not None and principal > float(amt_max):
            within = False
        try:
            r = emi(principal, rate, months)
            rows.append({"product": p.get("title"), "bank": p.get("bank_short") or p.get("bank"), "rate_pct": rate, "tenure_months": months,
                         "emi": r.emi, "total_interest": r.total_interest, "total_repayment": r.total_repayment,
                         "amount_within_product_range": within, "match_score": p.get("score")})
        except ValueError:
            continue
    df = pd.DataFrame(rows, columns=["product", "bank", "rate_pct", "tenure_months", "emi", "total_interest", "total_repayment", "amount_within_product_range", "match_score"])
    return df.sort_values(["amount_within_product_range", "total_repayment"], ascending=[False, True]).reset_index(drop=True)
