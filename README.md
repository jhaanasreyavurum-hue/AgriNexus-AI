# AgriNexus AI

**AI-powered Agricultural Financial Intelligence Platform** — one integrated
Streamlit application with four roles:

| Role | What the platform does for them |
|---|---|
| 🌾 **Farmer** | Profile → farm → finances → *Analyze My Farm* → personalised loans, schemes, insurance, subsidies, EMI, document checklist, PDF report, **Next Best Action** |
| 🏦 **Bank Manager** | Agricultural Credit Intelligence: modelled loan demand, eligible segments, crop trends, high-potential district map, loan-product management, credit report |
| 🏛️ **Government Officer** | Financial Inclusion & Scheme Monitoring: scheme reach, district performance, inclusion index, low-adoption intervention list, observed-adoption upload, report |
| 🛠️ **Administrator** | Users & permissions, banks, loan and scheme registries, knowledge-base health, data quality, system monitoring |

```
PROFILE + FARM + FINANCE + KB + ENVIRONMENT → ANALYTICS → ELIGIBILITY → MATCHING
        → RISK / OPPORTUNITY → EXPLANATION (result · score · factors · reason · source · method)
        → NEXT BEST ACTION
```

Stack: Python · Streamlit · Pandas · NumPy · Plotly · PyDeck · fpdf2 (scikit-learn only where
a model genuinely exists — none is claimed today). Deployable to Streamlit Community Cloud with
`streamlit run app.py`. No React/Node.

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | KB recovered from PDFs, validated, plan | ✅ |
| 1 | Knowledge layer, Farm Digital Twin, weather provider, demo farms | ✅ |
| 2 | Analytics engines, farm health, risk, Next Best Action, `generate_farm_advice()` | ✅ |
| 3 | Knowledge engines: Crop Advisor, Scheme Matcher, Loan Advisor, Insurance, Subsidy, Documents, Opportunities | ✅ |
| 4A | Role shell: login gate, session, role-based `st.navigation`, four distinctive dashboards | ✅ |
| 4B | Farmer journey (onboarding wizard, My Farm, Loans + EMI, Schemes, Insurance, Intelligence, Copilot, Report) | ✅ |
| 4C | Bank Manager modules (Loan Demand, Crop Trends, Segments, High-Potential Areas, Loan Products, Report, Copilot) | ✅ |
| 4D | Government modules (Scheme Adoption + observed upload, District Performance, Inclusion, Low-Adoption, Report, Copilot) | ✅ |
| 4E | Admin modules (Users, Banks, Loan Schemes, Government Schemes, Knowledge Base, System Monitoring) | ✅ |
| 4F | Reports: farmer PDF, Credit Intelligence PDF, Inclusion PDF, CSV/JSON exports | ✅ |
| 4G | Role-aware Copilot (farmer: farm advice; bank/government: analytics tables; optional LLM narrator) | ✅ |
| 5 | Deploy hardening, persistence backend (optional), polish | ⏳ |

**Demo accounts** (`data/config/users.yaml`, password `agrinexus`): `ramulu`, `sunita`, `newfarmer`
(farmers) · `bank.manager` · `officer` · `admin`. Farmers can also self-register (session-only).

## Data honesty — read this first

* **KNOWLEDGE BASE** — 10 client CSVs, read-only, checksums pinned; 48 documented corrections applied
  in memory via `data/config/kb_overrides.yaml`. Never shown as raw tables — always converted into
  personalised results.
* **MODELLED (KB-derived)** — the bank and government analytics. The KB contains **no observed loan
  demand, scheme adoption or inclusion statistics**. The platform runs the real KB engines over an
  explicit grid of farmer-segment archetypes for every KB district (`data/derived/segment_matrix.csv`,
  1,012 rows) and weights them by a stated household scenario. Every chart, KPI, PDF and Copilot answer
  carries that label and normalises per 10,000 households. Officers can upload *observed* adoption
  (session-only) to compute a modelled-vs-observed gap.
* **DEMO / user-entered / WEATHER API / RULE-BASED / LLM-GENERATED** badges everywhere else.
* **Session-only registry** — loan products, schemes and banks can be added/updated by authorised
  roles. There is no database in this deployment: changes are held in memory for the server process,
  applied on top of the KB for farmer matching immediately, logged and exportable, and labelled
  *not persisted*. `core/store/registry.py → RegistryBackend` is the extension point for a database.
* **Authorization is enforced in core functions** (`authorize(user, permission)`), not just by hiding
  navigation.

## Layout

```
app.py                     # entry point: login gate → role NAV → st.navigation → ui.pages.<role>.<module>.render()
ui/
├── auth.py / login.py     # session user, require(*roles, perm=), login/register screen
├── state.py               # KB / matrix / registry caches, farm selection, cached run_full_assessment() on the effective KB
├── onboarding.py          # farmer wizard: profile → farm → finances → Analyze My Farm
├── theme.py / components.py / match_cards.py / analytics_components.py   # cards, KPIs, badges, WHY panels, Plotly, PyDeck maps
├── report_pdf.py / analytics_pdf.py     # farmer PDF · credit-intelligence PDF · inclusion PDF (fpdf2)
├── analytics_copilot.py   # shared chat UI for bank / government Copilot
└── pages/
    ├── farmer/      home · loans · schemes · insurance · intelligence · copilot · report
    ├── bank/        home · loan_demand · crop_trends · segments · areas · products · report · copilot
    ├── government/  home · adoption · districts · inclusion · low_adoption · report · copilot
    └── admin/       home · users · banks · loan_schemes · gov_schemes · knowledge_base · monitoring
```

```
agrinexus/
├── app.py                      # (Phase 4) Streamlit entry
├── core/                       # NO Streamlit imports anywhere under core/
│   ├── kb/                     # loader.py (KB + overrides + checksums), vocab.py (canonicalisation)
│   ├── models/                 # farm_context.py (Digital Twin), results.py (explainable result objects)
│   ├── integrations/weather/   # base.py (interface), open_meteo.py (default), openweathermap.py (keyed)
│   ├── analytics/              # crop_stage, ndvi, soil, weather, water_balance, risk, farm_health
│   ├── engines/                # Phase 3 knowledge engines (facts, documents, crop, scheme, loan, insurance, subsidy, opportunity)
│   ├── reasoning/              # assessment.py (run_full_assessment), next_best_action.py, financial_summary.py,
│   │                           # advisor.py (farmer Copilot), analytics_advisor.py (bank/government Copilot), narrator.py (optional LLM)
│   ├── auth/                   # Role, Permission, User, authenticate(), authorize() — enforced inside core functions
│   ├── intelligence/           # segments.py (11 archetypes), scenario.py, matrix.py (build/load), credit.py, inclusion.py  [MODELLED]
│   ├── store/registry.py       # session-only registry for loans / schemes / banks + effective_kb() overlay; RegistryBackend extension point
│   └── admin/health.py         # platform counts, KB health, data-quality checks, system status
├── data/
│   ├── knowledge_base/         # 10 client CSVs — SOURCE OF TRUTH, never edited; CHECKSUMS.sha256 pinned
│   ├── config/
│   │   ├── kb_overrides.yaml   # explicit, reviewed corrections (applied in memory, logged)
│   │   ├── vocab_mappings.yaml # soil / crop-group / land / income / farmer-category mappings
│   │   └── crop_stages.yaml    # FAO-56 / ICAR stage lengths + Kc (reference, not client KB)
│   └── demo_farms/             # 2 sample twins, every block labelled source: demo
│   ├── config/users.yaml       # demo user directory (salted hashes) — not a production IdP
│   └── derived/segment_matrix.csv (+ .meta.json)   # MODELLED analytics backbone, KB-fingerprinted
├── scripts/build_segment_matrix.py   # rebuild the matrix after KB/override changes (~8-10 min on 2 CPUs)
├── scripts/kb_inspect.py · assess_demo.py · knowledge_demo.py
├── tests/                      # pytest (134 tests: KB, engines, analytics, farmer UI, roles/registry/role pages)
└── .streamlit/                 # config.toml theme, secrets.toml.example
```

## Knowledge-base policy

* The ten CSVs in `data/knowledge_base/` are loaded verbatim; SHA-256 checksums
  are verified on every load and a warning is raised if a file changed.
* Factual corrections live **only** in `data/config/kb_overrides.yaml`, each with
  an id, reason, public reference and an `enabled` switch. They are applied in
  memory and logged; the UI can show "corrected from KB" badges.
* Interpretation rules (land unit = acres, soft vs hard eligibility columns,
  universal terms such as "All Crops") are declared in the same file.
* Coverage is deepest for Telangana; the loader exposes
  `kb.coverage_level(state)` so the UI can be honest about thin regions.

## Data provenance

Every block of the Farm Digital Twin carries a `Provenance(source, detail)`.
Sources: `measured · modelled · remote_sensing · weather_api · user_entered ·
knowledge_base · reference · demo`. Demo farms are `source: demo` throughout
and the UI must badge them. No satellite, soil, weather or financial value is
ever generated by code — missing data is `None` and reported as unavailable.

## The reasoning chain (Phase 2)

```
FarmContext ─► analyse_stage ─► analyse_ndvi ─► analyse_soil ─► analyse_weather
            ─► analyse_water (FAO-56-style balance) ─► detect_risks
            ─► compute_farm_health (6 weighted components, missing ones excluded)
            ─► generate_next_best_actions  (actions[0] = NEXT BEST ACTION)
            ─► generate_farm_advice(ctx, kb, question)  (Copilot; intent-routed)
```

Every result carries an `Explanation` (summary, data considered, positive /
limiting / risk / missing factors, `Method` label, provenance sources,
`demo_data_used`). Rule-based logic is labelled *Rule-based*; weather results
*Weather result*; NDVI *Remote-sensing result*; KB joins *Knowledge-base lookup*;
optional LLM output *LLM-generated explanation*. The LLM narrator only
rephrases a finished `Advice` and is discarded if it introduces any number not
present in the source material.

## The knowledge engines (Phase 3)

```
FarmContext + FarmAssessment ─► build_facts()            FarmerFacts: land bands, KB farmer terms, crop groups,
                                                          canonical documents held, active risks, soil limits
   ├─► recommend_crops()      crop_master × soil similarity, district rainfall, irrigation, season, rotation, objective
   ├─► match_schemes()        hard: active/state/income/age · soft: crop, farmer term, land range, prerequisites
   │                          + eligibility_rules (soil & land band soft-weighted) + ai_recommendation_rules boosts
   ├─► find_subsidies()       subcategory ↔ farm situation tags (water stress, flood irrigation, low OC, rainfed …)
   ├─► advise_loans()         purpose → loan types, indicative eligibility from KB caps, bank branches in district
   ├─► match_insurance()      crop & district hard filters, covered_risk ↔ Risk Center, farmer-share premium
   ├─► resolve_documents()    canonical names, held / to-arrange / obtainable-at-application / not-applicable
   └─► detect_opportunities() ranked cross-engine opportunities (subsidy, scheme, credit, insurance, crop, quick wins)
run_full_assessment() = assess_farm() + run_knowledge_engines() + append_knowledge_actions()
```

Every match is a `MatchResult` with a 0–100 score, label, `Explanation`
(positive / limiting / risk factors, KB record ids, method label) and a
document checklist. KB quirks are handled only through
`data/config/kb_overrides.yaml` (record corrections + *interpretation* rules,
e.g. soft crop/farmer criteria, hectare interpretation of eligibility-rule
land bands, soft soil-card/insurance prerequisites) and
`data/config/vocab_mappings.yaml` (synonyms, document aliases, conditional
documents, subsidy relevance). Original CSVs are never modified
(`CHECKSUMS.sha256`). When the KB has no applicable record (e.g. no crop cover
notified for a Maharashtra district) the engines say so rather than inventing
one.

## The UI (Phase 4) — four journeys

**Farmer** — Register/Login → wizard (profile · farm · finances; only fields the engines use) → *Analyze My Farm* →
**My Farm** (MY FARM / MY FINANCIAL PROFILE / MY ELIGIBILITY / MY RECOMMENDATIONS cards + NEXT BEST ACTION hero) →
**Loans** (ranked product cards: match score, amount range, interest, tenure, collateral, crop suitability, documents,
reason; EMI calculator with product comparison; KB branches) → **Government Schemes** (match score, why eligible,
conditions, benefits, documents, application mode/portal) → **Insurance** (informational covers vs risks; gap note) →
**Crop / Farm Intelligence** → **AI Copilot** → **My Report** (PDF/JSON/CSV).

**Bank Manager** — Bank Dashboard (modelled demand, eligible households, top crops/districts/products, inclusion
indicators) · Loan Demand (district / product / bank / table) · Crop Trends (attractiveness grid) · Farmer Segments
(small/marginal/women/irrigated/rainfed/FPO/tenant… via the KB eligibility logic) · High-Potential Areas (map +
ranking + drill-down) · Loan Products (view for all; add/update/deactivate for authorised roles; session-only) ·
Analytics Report (PDF) · Copilot.

**Government Officer** — Scheme Dashboard · Scheme Adoption (reach by scheme/type/level, crop-wise association,
observed-adoption CSV upload → gap) · District Performance (map, pillars, ranking, drill-down) · Financial Inclusion
(four-pillar radar, exclusion hot-spots, branch access) · Low-Adoption Areas (relative bottom-30 % shortlist with
weakest pillar + rule-based intervention) · Government Report (PDF) · Copilot.

**Administrator** — Admin Dashboard · Users (directory, role→permission matrix) · Banks · Loan Schemes ·
Government Schemes (registry with KB override log) · Knowledge Base (integrity, coverage, data quality, overrides) ·
System Monitoring (integrations/secrets status, matrix freshness, caches, engine self-test, registry activity).

All pages call the existing engines (`run_full_assessment()`, `credit_intelligence()`, `inclusion_intelligence()`)
and only render; no agricultural or financial logic lives in `ui/`.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # runtime only (8 packages)
streamlit run app.py
```

Development extras and tests:

```bash
pip install -r requirements-dev.txt
pytest -q                                               # 134 tests, offline
python scripts/build_segment_matrix.py --workers 2      # rebuild MODELLED analytics after KB/override edits
```

## Deploy — GitHub → Streamlit Community Cloud

Verified 2026-09-04: clean virtual environments (Python 3.12 and 3.13) with only `requirements.txt`
installed → `streamlit run app.py` starts, all 29 role pages (7 farmer, 8 bank, 7 government, 7 admin) render without exceptions, 134 tests pass.

1. **GitHub**
   ```bash
   cd agrinexus
   git init && git add . && git commit -m "AgriNexus AI — four-role platform"
   git remote add origin https://github.com/<you>/agrinexus-ai.git
   git branch -M main && git push -u origin main
   ```
   `.gitignore` already excludes `.streamlit/secrets.toml`, `.env`, virtual environments, caches and IDE files.
   The repository is ~17 MB; the largest file is `data/derived/segment_matrix.csv` (15 MB) — required, keep it.
2. **Streamlit Community Cloud** → *New app* → repository `<you>/agrinexus-ai`, branch `main`,
   main file path **`app.py`**.
3. *Advanced settings* → **Python 3.12** (the version this was verified on; 3.11–3.13 all work).
   Community Cloud ignores `runtime.txt` / `.python-version`; the setting in the UI is what counts.
4. *Secrets* → leave empty, or paste any of the optional keys from `.streamlit/secrets.toml.example`.
5. Deploy. First boot loads the knowledge base (~0.5 s) and the segment matrix (~1 s).

**Secrets (all optional)**

| Key | Purpose | Without it |
|---|---|---|
| `WEATHER_PROVIDER` | `open_meteo` (default) or `openweathermap` | Open-Meteo, keyless |
| `OPENWEATHER_API_KEY` | key for OpenWeatherMap | falls back to Open-Meteo |
| `LLM_PROVIDER` / `LLM_API_KEY` / `LLM_MODEL` | rephrase-only Copilot narrator | narrator toggle disabled; rule-based Copilot works |

No secrets are read anywhere except through `st.secrets` / environment variables, and none are shown in the UI.

**Deployment facts**

* Entry point `app.py`; all paths are relative to the package (`core/__init__.py → PACKAGE_ROOT`), no OS-specific paths.
* Maps use pydeck on the Carto basemap — no Mapbox token, no local GIS files.
* PDFs use fpdf2 core fonts — no font files; rupee amounts are rendered as `Rs`.
* No database, no pickle, no local writes at runtime: registry changes are in-memory and labelled *not persisted*.
* `.streamlit/config.toml` sets theme + `headless = true`; port/address are supplied by the platform.
