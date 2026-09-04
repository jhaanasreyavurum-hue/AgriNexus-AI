# Knowledge layer

| File | Role |
|---|---|
| `loader.py` | Loads the 10 client CSVs verbatim, verifies SHA-256 checksums, applies `data/config/kb_overrides.yaml` in memory, adds `*_canonical` / list / bool helper columns. Logs every override to `KnowledgeBase.override_log`. |
| `vocab.py` | Soil / crop / land-band / income-band / farmer-category canonicalisation from `data/config/vocab_mappings.yaml`. |

The original CSVs in `data/knowledge_base/` are never edited by code.
