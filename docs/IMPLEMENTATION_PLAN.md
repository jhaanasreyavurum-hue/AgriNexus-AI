# AgriNexus AI — Inspection Findings & Implementation Plan

*Prepared 2026-09-04 · Phase 0 deliverable (no application code written yet)*

---

## 1. What was actually provided

| Item | Status |
|---|---|
| Project definition (24 sections) | ✅ Read in full |
| Knowledge Base — 10 PDFs | ✅ Inspected, parsed, validated |
| **Existing AgriNexus application code** | ❌ **Not present in the workspace** |

> **Important:** Section 23 asks me to inspect and reuse the existing AgriNexus application (GIS logic, crop recommendation logic, finance logic, etc.). **No source code was uploaded — only the 10 knowledge-base PDFs.** If an existing codebase exists, please upload it (zip or individual files) before Phase 1 so I can migrate rather than rebuild. The plan below is written so that existing modules can slot in wherever they exist.

---

## 2. Knowledge Base — what was recovered

The PDFs are monospace print-outs of CSV files, hard-wrapped at 55 characters. I reversed the wrapping, reconstructed the original CSVs, and validated every file by column count, ID pattern (`CROPnnn`, `SCHMnnn`, `RULEnnnn` …), and duplicate check.

**Reconstructed files → `data/knowledge_base/*.csv`** (already in the workspace, ready for Pandas)

| File | Rows | Cols | Key fields | Integrity |
|---|---|---|---|---|
| `agrinexus_crop_master.csv` | 120 | 11 | crop, season, soil_type, min/max rainfall, water_requirement, market_category, recommended_schemes, recommended_loans | ✅ clean |
| `agrinexus_state_district_master.csv` | 68 | 8 | state, district, lat/lon, agriculture_zone, major_crop | ✅ (36 states/UTs, 33 Telangana districts) |
| `agrinexus_government_schemes.csv` | 80 | 31 | scheme_type, level, state, eligible_crop, eligible_farmer, min/max land, income_limit, age, doc flags, documents_required, subsidy, portal, priority_score | ✅ clean |
| `agrinexus_eligibility_rules.csv` | 300 | 14 | crop × state × soil × farmer_category × land range × income → recommended scheme / loan / insurance, priority | ✅ clean |
| `ai_recommendation_rules.csv` | 500 | 8 | `condition_json` {state, crop, land_acres band, income band} → schemes, loans, insurances, priority, confidence, **reason text** | ✅ clean |
| `agrinexus_agri_loan_products.csv` | 120 | 22 | bank, loan_type (12 types), interest min/max, amount min/max, tenure, collateral, crop_specific, docs, eligibility_summary, loan_score | ✅ clean |
| `agrinexus_agricultural_subsidies.csv` | 100 | 12 | subsidy, parent scheme, crop, state, subcategory, max amount, %, eligibility, docs, process | ✅ clean |
| `agrinexus_crop_insurance_products.csv` | 60 | 15 | product, provider, coverage_type, covered_crop, covered_risk, premium %, govt subsidy %, coverage amt, eligible_farmer, district_applicable | ✅ clean |
| `agrinexus_required_documents.csv` | 150 | 8 | document → scheme / loan, mandatory, format, issuing authority | ✅ clean |
| `agrinexus_bank_branches.csv` | 200 | 15 | bank, branch, district, IFSC, lat/lon, loan/insurance available | ✅ (Telangana only) |

**Referential integrity (verified):** every `recommended_scheme` in eligibility rules, subsidies, documents and crop master resolves to a row in `government_schemes`; every `recommended_loan` resolves to a `loan_type` in loan products. This means the KB can be joined as a proper relational knowledge graph.

### 2.1 Vocabulary mismatches that need a mapping layer

These are real and must be handled in code, not ignored:

| Dimension | Vocabulary A | Vocabulary B | Resolution |
|---|---|---|---|
| **Soil** | crop_master: `Sandy Loam Soil`, `Clay Loam Soil`, `Well-Drained Loamy Soil`, `Saline / Alkaline Tolerant Soil` | eligibility_rules: `Sandy Soil`, `Clay Soil`, `Loamy Soil`, `Saline / Alkaline Soil` | Canonical soil enum + mapping table |
| **Crop** | crop_master: 120 specific crops (`Paddy (Rice)`, `Pigeon Pea (Tur/Arhar)`) | schemes/rules/insurance: 17–26 groups (`Paddy`, `Red Gram (Tur Dal)`, `Pulses`, `Oilseeds`, `Vegetables`, `Horticulture Crops`) | Crop → crop-group hierarchy table |
| **Land** | schemes/eligibility: continuous acres | ai_rules: bands `<2`, `2-5`, `5-10`, `>10`, `<5` | Band function |
| **Income** | schemes: numeric limit | ai_rules: bands `<200000`, `200000-300000`, … | Band function |
| **Geography** | KB deep for Telangana (33 districts, all branches, 37 state schemes), 1 district for other states | — | Coverage-aware matching + honest "limited coverage" flag |

### 2.2 Data-quality caveats you should know about

The KB appears to be synthetically generated. Several rows contradict established facts, e.g.:

- PM-KISAN typed as *Mechanization Subsidy* under *Ministry of Rural Development*; KCC under *Ministry of Consumer Affairs*; PM-KMY typed as *Irrigation Support*.
- Crop master: Paddy = *Rabi*, Barley = *Kharif*, Cotton = *Year-round (Perennial)*, Bajra = *High water, 1250–1850 mm*.
- Scheme eligibility columns are narrow and arbitrary (e.g. PM-KISAN: `eligible_crop = Soybean`, `eligible_farmer = Women-headed`).

**Decision needed (see §6):** Per your instruction I will *not* silently overwrite KB values. My recommended approach is to use the KB as-is for matching **but surface a `source: knowledge_base` badge and a small, explicit override file (`data/kb_overrides.yaml`) for the handful of factual corrections you approve.** Nothing gets overridden without being listed there.

---

## 3. Mapping KB → AgriNexus architecture

```
                    ┌──────────────────────────────────────────────────────────┐
                    │                  FARM DIGITAL TWIN (context dict)         │
                    │ farmer · location · area · crop · stage · soil · irrig.  │
                    │ weather · rainfall · NDVI/NDWI · finance · risk flags     │
                    └────────────┬─────────────────────────────┬───────────────┘
                                 │                             │
     ┌───────────────────────────▼──────────┐   ┌──────────────▼──────────────────────┐
     │  ENVIRONMENTAL ANALYTICS (rule/model)│   │  KNOWLEDGE ENGINE (KB lookups)      │
     │  · farm_health  (6 sub-scores)       │   │  · crop_suitability   ← crop_master │
     │  · ndvi_analytics (trend/Δ%)         │   │  · scheme_matcher     ← schemes +   │
     │  · soil_intelligence                 │   │       eligibility_rules + ai_rules  │
     │  · weather_intelligence              │   │  · loan_advisor       ← loans + docs│
     │  · water_balance / irrigation need   │   │  · insurance_matcher  ← insurance   │
     │  · risk_engine (7 risk types)        │   │  · subsidy_finder     ← subsidies   │
     └───────────────────────────┬──────────┘   │  · document_resolver  ← documents   │
                                 │              │  · geo_master         ← state/dist  │
                                 │              └──────────────┬──────────────────────┘
                                 └──────────────┬──────────────┘
                                                ▼
                    ┌──────────────────────────────────────────────────────────┐
                    │  REASONING LAYER   generate_farm_advice(ctx, question)   │
                    │  · opportunity_engine  · next_best_action                │
                    │  · explanation builder (WHY: data, +, −, risk, source)   │
                    │  · optional LLM narrator (label: "LLM-generated")        │
                    └────────────┬─────────────────────────────────────────────┘
                                 ▼
          Streamlit pages: Home · Intelligence · Crop · Finance · Copilot · Reports
```

### 3.1 Feature → data source → method label

| Feature (spec §) | Inputs | KB tables | Method label shown to user |
|---|---|---|---|
| Farm Health (§2) | NDVI, soil, moisture, weather, stage, risks | — | **Rule-based index** |
| Next Best Action (§3) | health + risk + weather + stage | crop_master (water_requirement) | **Rule-based decision** |
| NDVI analytics (§6) | NDVI series | — | **Remote-sensing result** (or *demo* if no imagery) |
| Soil intelligence (§7) | pH, SOC, texture | canonical soil map | **Measured / modelled / demo** (tagged per field) |
| Weather intelligence (§8) | Open-Meteo forecast (no key) or OpenWeather (key via secrets) | — | **Weather result** |
| Crop Advisor (§9) | soil, rainfall, season, irrigation, objective | crop_master | **Rule-based suitability score** (explained factor-by-factor) |
| Scheme Finder (§11) | state, land, income, category, crop, soil, docs held | government_schemes, eligibility_rules, ai_recommendation_rules, required_documents | **Knowledge-base match** |
| Loan Advisor (§12) | land, crop, purpose, collateral, category | agri_loan_products, required_documents, bank_branches | **Knowledge-base match** |
| Insurance (§13) | crop, district, farmer type, detected risks | crop_insurance_products | **Knowledge-base match** (informational, not a quote) |
| Opportunity Engine (§14) | all of the above | subsidies + schemes + loans + insurance + crop_master | **Rule-based aggregation** |
| Risk Center (§15) | weather, NDVI, soil, finance | insurance `covered_risk` (risk → cover link) | **Rule-based** |
| Crop Timeline (§16) | sowing date, crop, NDVI series | crop_master (season) + stage-duration table | **Rule-based** |
| AI Copilot (§17) | full context + question | everything via reasoning layer | **Rule-based reasoning; LLM narration only if key configured** |
| Reports (§18) | all engine outputs | — | PDF via ReportLab/fpdf2 |

### 3.2 Where existing code would plug in (once uploaded)

| If existing project has… | Migrate into |
|---|---|
| Crop recommendation function / ML model | `core/engines/crop_advisor.py` (keep model, wrap with explanation) |
| GIS / Folium / boundary logic | `core/geo/` + `ui/pages/2_farm_intelligence.py` |
| NDVI / raster processing | `core/analytics/remote_sensing.py` |
| Weather fetch code | `core/integrations/weather.py` (keys → `st.secrets`) |
| Scheme / loan / finance logic | `core/engines/finance.py`, `scheme_matcher.py` — merge rules with KB |
| Any existing CSV/Excel datasets | `data/` alongside the KB, registered in `core/kb/loader.py` |

---

## 4. Proposed repository structure

```
agrinexus/
├── app.py                          # Streamlit entry — nav + farm selector + theme
├── requirements.txt
├── .streamlit/config.toml          # theme
├── .streamlit/secrets.toml.example # WEATHER_API_KEY, LLM_API_KEY (never committed)
├── data/
│   ├── knowledge_base/*.csv        # ✅ already reconstructed
│   ├── mappings/                   # soil_map.csv, crop_group_map.csv, stage_durations.csv
│   ├── kb_overrides.yaml           # explicit, reviewed factual corrections (opt-in)
│   └── demo_farms/                 # 3–4 sample Farm Digital Twins (clearly labelled DEMO)
├── core/
│   ├── models/farm_context.py      # FarmContext dataclass = Digital Twin (+ provenance per field)
│   ├── kb/loader.py                # cached KB load, normalisation, joins
│   ├── kb/vocab.py                 # soil/crop/land/income canonicalisation
│   ├── analytics/                  # farm_health, ndvi, soil, weather, water_balance, risk
│   ├── engines/                    # crop_advisor, scheme_matcher, loan_advisor,
│   │                               # insurance_matcher, subsidy_finder, opportunity, next_best_action
│   ├── reasoning/advisor.py        # generate_farm_advice(farm_context, question)
│   ├── reasoning/explain.py        # Explanation object → WHY card
│   ├── integrations/weather.py     # Open-Meteo default; keyed provider optional
│   └── reports/                    # pdf builders
├── ui/
│   ├── theme.py                    # CSS, palette, card components
│   ├── components/                 # metric_card, why_card, risk_badge, score_ring
│   └── pages/ 1_home … 6_reports
└── tests/                          # unit tests for engines & KB integrity
```

Design principle: **`core/` has zero Streamlit imports.** Every engine returns a typed result object (`score`, `label`, `factors[+/−]`, `action`, `method`, `sources`) that the UI renders and the Copilot reasons over.

---

## 5. Phased implementation plan

| Phase | Scope | Output |
|---|---|---|
| **0 — Foundation** *(done)* | Parse KB, validate, establish plan | this document + `data/knowledge_base/` |
| **1 — Knowledge layer** | `kb/loader.py`, `vocab.py`, mapping tables, `FarmContext` model, demo farms, KB integrity tests | importable, tested knowledge layer |
| **2 — Analytics engines** | farm_health, NDVI analytics, soil, weather (Open-Meteo), water balance, risk engine, **next_best_action**, explanation objects | `generate_farm_advice()` works from CLI |
| **3 — Knowledge engines** | crop_advisor, scheme_matcher, loan_advisor, insurance_matcher, subsidy_finder, document_resolver, opportunity engine | ranked + explained matches |
| **4 — Streamlit UI** | theme + components; Farm Home → Farm Intelligence (Folium map, layers) → Crop Advisor → Finance & Schemes → Copilot → Reports | runnable `streamlit run app.py` |
| **5 — Reports & deploy** | PDF reports, `requirements.txt` pinned, secrets template, README, Streamlit Cloud check | deployable repo |
| *(optional)* **6 — LLM narration** | Wrap rule outputs in natural-language narration, clearly labelled | — |

Each phase produces something runnable; I'll check in with you at the end of each.

---

## 6. Decisions I need from you before Phase 1

1. **Existing code** — Is there an existing AgriNexus codebase to migrate? If yes, please upload it. If no, I proceed with a clean build on the architecture above.
2. **KB factual errors** — (a) use KB strictly as-is, (b) allow an explicit reviewed `kb_overrides.yaml` for clear factual errors (my recommendation), or (c) you correct the CSVs yourself first.
3. **Satellite data** — No NDVI imagery is provided. Options: (a) demo NDVI series clearly labelled *DEMO*, (b) integrate Sentinel-2 via Sentinel Hub/Copernicus API (needs your credentials), (c) allow farmer to upload a GeoTIFF/CSV NDVI series. Default: (a) + (c).
4. **Weather provider** — Open-Meteo (free, no key, works on Streamlit Cloud immediately) as default, with optional OpenWeatherMap via `st.secrets`? 
5. **Primary demo geography** — KB is deepest for **Telangana**. Should the default demo farm be in Telangana (e.g. Warangal, Cotton) so every feature has rich matches, with a Maharashtra farm as a second sample?
6. **LLM for Copilot** — Rule-based reasoning only (no key required), or also an optional LLM narrator (OpenAI/Anthropic/Gemini key via secrets)?


---

## Phase 3 — completed (status log)

Implemented in `core/engines/` and wired into `core/reasoning/` (`run_full_assessment`,
`append_knowledge_actions`, advisor intents `schemes / loans / insurance / opportunities / documents`).

Tuning decisions recorded as config (never code-only, never CSV edits):

| Decision | Where |
|---|---|
| `eligibility_rules.land_min/max` interpreted as **hectares** (bands match Agri-Census classes) | `kb_overrides.yaml → interpretation.eligibility_rules_land_unit` |
| Rule soil type and exact land band are **soft** (weights 0.6 / 0.8), state·crop·category·income hard | `scheme_matcher.fire_eligibility_rules` |
| `soil_card_required` / `insurance_required` are **soft prerequisites** (KB flags them on ~75 % of schemes) | `interpretation.scheme_soft_prerequisites` |
| PM-KISAN record corrected (no land cap / income limit / insurance prerequisite) | `OVR-SCHM-001` |
| Fisheries schemes excluded; livestock schemes −30 unless `farmer.livestock`; women-targeted −25 unless `gender: female`; crop-named schemes −12 for other crops | `scheme_matcher` |
| Conditional documents (ear-tag, FPO cert, tenant cert, collateral/DPR) reported *not applicable* unless the context applies | `vocab_mappings.yaml → documents.conditional` |
| Livestock covers never count as crop-risk hits; `insurance_gap_note` when no crop cover is notified for the district | `insurance_matcher` |
| Knowledge NBA: KB insurance action replaces the generic rule-based one; scheme pick = score + 0.2 × readiness; list re-numbered 1..n | `next_best_action.append_knowledge_actions` |
| Crop alternative is an *opportunity* only if it beats the current crop or fixes a ≥20-pt factor gap | `opportunity.detect_opportunities` |

Tests: `tests/test_engines.py` (25) — total 70 passing offline.

Next: Phase 4 Streamlit UI (6 pages) on top of `run_full_assessment()`.


---

## Phase 4 — completed (status log)

`app.py` + `ui/` (state, theme, components, farm_form, report_pdf, pages/). UI renders `run_full_assessment()`
results only; no agricultural logic in page files. Verified with `streamlit run app.py` (all six routes 200, sidebar
farm/weather switching), headless AppTest smoke tests for every page × both demo farms × sparse user farm, form
validation (empty, zero area, future sowing date, crop-less sowing date, malformed NDVI CSV), Copilot blank/nonsense
input, Crop Advisor season switch, PDF build for both farms. 94 tests passing.

Design decisions:
* One cached assessment per (farm fingerprint, weather mode); weather fetch cached 30 min; failures degrade to offline
  with a sidebar notice (never fabricated).
* Farm editor stores only entered values (blank → None) with `user_entered` provenance; district coordinates come from
  the KB geo master when available.
* Streamlit ≥1.36 compatibility shim for `use_container_width` → `width` (`ui.components.plot/table`).
* requirements.txt trimmed to what is imported (folium/geopandas/sklearn/openpyxl removed until needed).

Next: Phase 5 deploy hardening (Cloud smoke deploy, `.streamlit/config.toml` review, error boundaries), optional Phase 6
LLM narrator provider tests.

---

## Phase 4 (revised) — Four-role Agricultural Financial Intelligence Platform — completed (status log)

Direction change: AgriNexus AI is **one integrated platform with four roles** (farmer · bank_manager ·
government_officer · administrator), not a farmer-only dashboard. Built in order 4A→4G, each phase verified headlessly
(AppTest) before the next.

| Sub-phase | Delivered | Verification |
|---|---|---|
| 4A shell | `app.py` login gate, `ui/auth.py` (`require(*roles, perm=)`), `ui/login.py` (sign-in, demo accounts, farmer self-registration), per-role `NAV` → `st.navigation`; four distinctive home dashboards | `/tmp/shell_test.py`; `tests/test_ui.py` routes each demo account to its own dashboard |
| Back end for roles | `core/auth` (Role, Permission, `authorize()` inside core functions), `core/intelligence` (11 segment archetypes × 68 districts = 1,012-row **MODELLED** matrix, `credit_intelligence`, `inclusion_intelligence`, household `Scenario`), `core/store/registry.py` (session registry + `effective_kb()` overlay), `core/admin/health.py`, `core/reasoning/financial_summary.py` | `tests/test_analytics.py`, `tests/test_roles.py` |
| 4B farmer | onboarding wizard; My Farm (4 cards + NBA hero); Loans (cards + EMI + branches); Schemes; Insurance; Intelligence; Copilot; Report | `/tmp/farmer_pages_test.py` 21/21; `tests/test_ui.py` |
| 4C bank | loan_demand · crop_trends · segments · areas · products (add/update/deactivate; session-only; flash after rerun) · report (PDF) · copilot | `tests/test_roles.py::test_role_page_renders`, product add flow test |
| 4D government | adoption (+ observed CSV upload → gap) · districts · inclusion · low_adoption · report (PDF) · copilot | role-page tests; upload path exercised via `st.session_state["observed_adoption"]` |
| 4E admin | users (directory + role→permission matrix) · banks · loan_schemes (reuses bank product manager) · gov_schemes (registry + override log) · knowledge_base · monitoring (integrations, matrix freshness, caches, self-test) | role-page tests; add/update/remove flows |
| 4F reports | `ui/analytics_pdf.py`: `build_credit_report`, `build_inclusion_report` (compact INR in tables) | pdfplumber text check; tests |
| 4G copilot | `core/reasoning/analytics_advisor.py` (`bank_advice`, `gov_advice`: rule-based intents over the intelligence tables only — district/crop/scheme detail, segments, products, banks, documents, basis) + `ui/analytics_copilot.py`; narrator optional | Q&A exercised in `/tmp/role_interact.py`; tests |

Key decisions
* **Modelled ≠ observed.** Bank/government numbers are labelled MODELLED (KB-derived) everywhere, normalised per
  10,000 households, with the scenario stated; a "How real are these numbers?" Copilot intent explains provenance.
  Within one state the KB rules are uniform, so district variation is driven by major crop / cover notification /
  branch access — pages say so and use *relative* bands for prioritisation.
* **Registry writes authorise first, validate second**, and never touch the KB (`effective_kb()` shallow-copies the
  KB and overlays active session rows for loans and schemes; farmer assessment cache is keyed by registry version so
  new products/schemes match immediately). Missing optional loan fields get explicit defaults in the overlay so a
  session-added product can never crash the loan engine.
* Streamlit `st.rerun()` after a write drops in-flight `st.success` → success messages are stashed in session state
  ("flash") and shown on the next run.
* Matrix rebuild is a CLI step (`scripts/build_segment_matrix.py --workers 2`), deliberately not triggered from the
  web UI; System Monitoring shows staleness against the KB fingerprint.

Tests: 134 passing offline (`pytest -q`). KB checksums verified unchanged.

Known leftovers (minor, unchanged from Phase 3/4): PM-KMY FPO-cert conditional doc, PM-KISAN Voter ID, Crop Advisor
score spread, Nashik ear-tag doc, `guard_with_farm` rerun-only button. Next: Phase 5 deploy hardening; optional
`RegistryBackend` on SQLite/Postgres for persistent product management.
