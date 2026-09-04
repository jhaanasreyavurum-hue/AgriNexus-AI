"""Document Resolver — required documents for a scheme / loan / subsidy /
insurance product, reconciled against what the farmer already holds.

Sources (all KB):
  * the item's own ``documents_required`` / ``documents`` column, and
  * ``agrinexus_required_documents`` rows linked by scheme_name / loan_name
    (which add mandatory flag, accepted format and issuing authority).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from core.engines.facts import FarmerFacts


@dataclass
class DocumentItem:
    name: str                      # canonical
    kb_names: List[str]            # spellings seen in KB
    mandatory: Optional[bool]      # from required_documents table if linked; None if unknown
    held: bool
    obtainable_at_application: bool
    not_applicable: bool = False   # conditional document whose condition the farmer does not meet
    optional: bool = False         # only listed as non-mandatory in the linked required_documents table
    applies_when: Optional[str] = None
    accepted_format: Optional[str] = None
    issuing_authority: Optional[str] = None
    verification_required: Optional[bool] = None
    document_ids: List[str] = field(default_factory=list)


@dataclass
class DocumentChecklist:
    items: List[DocumentItem]
    readiness_pct: float           # held / total (excluding obtainable-at-application)
    missing_blocking: List[str]    # not held, not obtainable at application
    missing_obtainable: List[str]
    not_applicable: List[str] = field(default_factory=list)
    optional_missing: List[str] = field(default_factory=list)   # "may be requested" — not counted in readiness

    @property
    def held(self) -> List[str]:
        return [i.name for i in self.items if i.held]

    @property
    def applicable(self) -> List[DocumentItem]:
        """Core checklist: applicable and not merely optional."""
        return [i for i in self.items if not i.not_applicable and not i.optional]


def _active_contexts(facts: FarmerFacts, extra: Iterable[str]) -> set:
    ctx = set(extra or [])
    if facts.livestock:
        ctx.add("livestock")
    if facts.is_fpo:
        ctx.add("fpo_member")
    if facts.is_tenant_or_sharecropper:
        ctx.add("tenant_or_sharecropper")
    return ctx


def resolve_documents(kb, facts: FarmerFacts, item_docs: Iterable[str], scheme_name: Optional[str] = None,
                      loan_type: Optional[str] = None, contexts: Iterable[str] = ()) -> DocumentChecklist:
    """``contexts`` adds item-level conditions (e.g. ``collateral_loan`` for a secured loan,
    ``livestock`` for a livestock scheme) that make conditional documents applicable."""
    v = kb.vocab
    merged: dict[str, DocumentItem] = {}
    active = _active_contexts(facts, contexts)
    cond_of = {d: k for k, docs in v.doc_conditional.items() for d in docs}

    def add(raw: str, mandatory=None, fmt=None, auth=None, verif=None, doc_id=None, from_link=False):
        canon = v.canonical_document(raw)
        if not canon:
            return
        it = merged.get(canon)
        if it is None:
            it = DocumentItem(canon, [], mandatory, canon in facts.documents_held, canon in v.doc_obtainable,
                              optional=bool(from_link and mandatory is False))
            cond = cond_of.get(canon)
            if cond and cond not in active and not it.held:
                it.not_applicable, it.applies_when = True, cond.replace("_", " ")
            merged[canon] = it
        if raw not in it.kb_names:
            it.kb_names.append(raw)
        if mandatory is not None:
            it.mandatory = bool(it.mandatory) or bool(mandatory) if it.mandatory is not None else bool(mandatory)
        if not from_link or mandatory:
            it.optional = False
        it.accepted_format = it.accepted_format or fmt
        it.issuing_authority = it.issuing_authority or auth
        if verif is not None:
            it.verification_required = bool(verif)
        if doc_id and doc_id not in it.document_ids:
            it.document_ids.append(doc_id)

    for d in item_docs or []:
        add(d)
    df = kb.documents
    mask = None
    if scheme_name:
        mask = df["scheme_name"] == scheme_name
    if loan_type:
        m2 = df["loan_name"] == loan_type
        mask = m2 if mask is None else (mask | m2)
    if mask is not None:
        for _, r in df[mask].iterrows():
            add(r.document_name, r.mandatory_bool, r.accepted_format, r.issuing_authority, r.verification_required_bool, r.document_id, from_link=True)

    items = sorted(merged.values(), key=lambda i: (i.not_applicable, i.optional, i.held, not (i.mandatory or False), i.name))
    core = [i for i in items if not i.not_applicable and not i.optional]
    scored = [i for i in core if not i.obtainable_at_application]
    ready = round(100.0 * sum(i.held for i in scored) / len(scored), 0) if scored else 100.0
    return DocumentChecklist(
        items, ready,
        [i.name for i in core if not i.held and not i.obtainable_at_application],
        [i.name for i in core if not i.held and i.obtainable_at_application],
        [i.name for i in items if i.not_applicable],
        [i.name for i in items if i.optional and not i.held],
    )
