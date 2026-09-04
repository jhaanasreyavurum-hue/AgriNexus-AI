"""Segment-level intelligence for bank managers and government officers.

Everything here is **modelled from the knowledge base**: the real eligibility /
matching engines are run over an explicit grid of farmer-segment archetypes
for every district in the KB district master. The KB contains **no observed**
loan-demand, scheme-adoption or financial-inclusion statistics, so:

* figures are normalised *per 10,000 farmer households* unless the user supplies
  observed household counts / adoption data (session-only upload);
* every output carries ``basis = "MODELLED (KB-derived)"`` and the scenario
  assumptions used, and the UI must badge them as such.
"""
from .segments import SEGMENTS, Segment, segment_context
from .scenario import Scenario, DEFAULT_SCENARIO
from .matrix import SegmentMatrix, load_segment_matrix, build_segment_matrix
from .credit import credit_intelligence, CreditIntelligence
from .inclusion import inclusion_intelligence, InclusionIntelligence

__all__ = ["SEGMENTS", "Segment", "segment_context", "Scenario", "DEFAULT_SCENARIO", "SegmentMatrix",
           "load_segment_matrix", "build_segment_matrix", "credit_intelligence", "CreditIntelligence",
           "inclusion_intelligence", "InclusionIntelligence"]
