"""Mutable registries layered *over* the immutable knowledge base.

There is no database in this deployment. ``Registry`` keeps a change log of
additions / updates in memory (per server process) and applies them on read,
so the original KB CSVs are never modified and every change is explicitly
labelled *session-only (not persisted)*. Swapping the backend for a real DB
means implementing ``RegistryBackend`` — the UI and authorization stay as is.
"""
from .registry import Registry, RegistryBackend, InMemoryBackend, ChangeRecord, get_registry

__all__ = ["Registry", "RegistryBackend", "InMemoryBackend", "ChangeRecord", "get_registry"]
