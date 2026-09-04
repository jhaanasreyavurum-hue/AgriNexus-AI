"""Scenario assumptions that turn per-segment KB eligibility into district-level indicators.

The KB has no farm-household counts, so all aggregates are expressed
**per 10,000 farm households** with the segment shares below. Users can
override the shares (session-only) or upload observed household counts.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from .segments import SEGMENTS

HOUSEHOLD_BASE = 10_000


@dataclass
class Scenario:
    segment_shares: Dict[str, float] = field(default_factory=lambda: {s.segment_id: s.default_share for s in SEGMENTS})
    household_base: int = HOUSEHOLD_BASE
    eligible_min_loan_score: float = 50.0       # a product with match score ≥ this counts as "potentially eligible"
    eligible_min_scheme_score: float = 50.0
    observed_households: Optional[Dict[str, int]] = None   # district -> farm households (user-supplied, optional)
    label: str = "Default scenario (all-India holding distribution, Agriculture Census 2015-16 shape)"

    def normalised_shares(self) -> Dict[str, float]:
        tot = sum(self.segment_shares.values()) or 1.0
        return {k: v / tot for k, v in self.segment_shares.items()}

    def households_for(self, district: str) -> int:
        if self.observed_households and district in self.observed_households:
            return int(self.observed_households[district])
        return self.household_base

    @property
    def basis(self) -> str:
        return "OBSERVED household counts × KB-modelled eligibility" if self.observed_households else "MODELLED (KB-derived, per 10,000 farm households)"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT_SCENARIO = Scenario()
