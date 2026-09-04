"""Knowledge-base layer: loading, overrides, vocabulary canonicalisation."""
from core.kb.loader import KnowledgeBase, load_knowledge_base
from core.kb.vocab import Vocab, load_vocab

__all__ = ["KnowledgeBase", "load_knowledge_base", "Vocab", "load_vocab"]
