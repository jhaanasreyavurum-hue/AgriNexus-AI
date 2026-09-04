# Phase 5 — Deployment Verification Report

**Date:** 2026-09-04 · **Method:** real clean installs, not code reading.
Three fresh virtual environments were created from `requirements.txt` alone (Python 3.12.14 ×2, Python 3.13.14 ×1);
the app was started exactly the way Streamlit Community Cloud starts it (`streamlit run app.py`) from a *copy*
of the repository, and every page of every role was loaded over the Streamlit websocket protocol (the same
messages a browser sends) while the server log was watched for exceptions.

No features were added, nothing was redesigned, KB CSVs are unchanged (`sha256sum -c CHECKSUMS.sha256` → OK).

---

## Scorecard

| # | Category | Grade | Evidence |
|---|---|---|---|
| 1 | Startup (`streamlit run app.py`, no extra flags) | **PASS** | Boots in ~1 s on 3.12 and 3.13; log contains only the Uvicorn/URL banner after 40+ page loads |
| 2 | Entry point, imports, paths | **PASS** | `app.py` roots `sys.path` at its own directory; all 43 `ui.pages.*` modules import in a runtime-only venv; `grep` for `/home/`, `C:\`, `os.chdir` → none |
| 3 | requirements.txt / clean install | **PASS** | Rewritten to 8 runtime packages with upper bounds (streamlit, pandas, numpy, plotly, pydeck, fpdf2, PyYAML, requests, pyarrow). Fresh installs resolve on 3.12 & 3.13 (streamlit 1.63.0, pandas 2.3.3, numpy 2.5.2, plotly 7.0.0, pydeck 0.9.3, fpdf2 2.8.8). pytest moved to `requirements-dev.txt` |
| 4 | Python version compatibility | **PASS** (after fix) | One PEP-701 f-string (3.12-only syntax) in `ui/pages/government/low_adoption.py` — fixed. `ast.parse(feature_version=(3,11))` + tokenizer scan now clean for every file. 134 tests pass on 3.12 and 3.13 |
| 5 | Secrets handling | **PASS** | No `secrets.toml`, `.env` or key literals in repo; every key read via `st.secrets`/env with defaults; keyed weather provider never rendered; example file documents all keys as optional |
| 6 | `.gitignore` | **PASS** | Excludes `secrets.toml`, `.env*`, venvs, caches, `*.db/sqlite`, uploads, `*.tif`, IDE files |
| 7 | Knowledge base integrity | **PASS** | 10 CSV checksums verified; 54 overrides from `kb_overrides.yaml` applied in memory only; loader + segment matrix fingerprint `5d9e1a1510e46b2a` load in ~1.5 s |
| 8 | Roles, login, authorization | **PASS** | 6 demo users log in; wrong password denied; direct URL of another role's page → denied; `newfarmer` lands on onboarding; function-level `require_role` checks intact (tests in `test_roles.py`) |
| 9 | All pages, all roles (live) | **PASS** | 29 pages (7 farmer, 8 bank, 7 government, 7 admin) × real websocket loads: 0 exceptions, all Plotly/pydeck/dataframe/download elements present |
| 10 | Engine wiring (farmer assessment) | **PASS** | Demo farm → 12 schemes, 8 loans (Good), 3 insurance, 10 subsidies, 10 crops, document resolver, 3 eligibility + 1 AI rule fired, NBA produced |
| 11 | Weather | **PASS** | Default Open-Meteo, keyless, live fetch 0.6 s; `WEATHER_PROVIDER=openweathermap` without key → silent fallback to Open-Meteo; with key → OWM |
| 12 | Copilot without LLM key | **PASS** | `narrator_enabled` False with no/empty key; all intents answer rule-based with KB references; `narrated=None` |
| 13 | PDF reports (5) | **PASS** | Farmer (both demo farms), Credit (Telangana + all-India), Inclusion: valid `%PDF-1.3`, 3–4 pages, core Helvetica only (no font files), `Rs` amounts, DEMO/MODELLED labels present, no `nan`/`None`/`₹` glyph errors |
| 14 | Data-honesty labels | **PASS** | KNOWLEDGE BASE / RULE-BASED / MODELLED / DEMO DATA / WEATHER API badges and banners present on analytics, NDVI, soil pages |
| 15 | Maps without keys/GIS files | **PASS** | pydeck with Carto basemap (`map_style` light/None); no Mapbox token, no shapefiles, no folium/geopandas dependency |
| 16 | Caching / session / no local writes | **PASS** | `st.cache_resource`/`cache_data` for KB, matrix, advisors; no pickle, sqlite or runtime file writes |
| 17 | UI ↔ core boundary | **PASS** | Pages call only `run_full_assessment, generate_farm_advice, credit_intelligence, inclusion_intelligence, bank_advice, gov_advice, recommend_crops, emi`; core imports streamlit only in `core/admin/health.py` for version reporting |
| 18 | Resource leaks / warnings | **PASS** (after fix) | Unclosed `open()` in `core/admin/health.py` fixed; no ResourceWarning/DeprecationWarning under `-W error` import |
| 19 | Repository size | **NEEDS ATTENTION (informational)** | 17 MB total; `data/derived/segment_matrix.csv` is 15 MB — well under GitHub's 100 MB limit and required at runtime. Keep it committed |
| 20 | Python version on Community Cloud | **NEEDS ATTENTION (one click)** | Cloud ignores `runtime.txt`/`.python-version` — select **Python 3.12** in *Advanced settings* when deploying |
| 21 | Loan-product / registry persistence | **NEEDS ATTENTION (by design)** | `RegistryBackend` is in-memory; UI states changes are *not persisted*; correct architecture for a DB later. Not changed per your instruction |

**Overall: READY TO DEPLOY.** No FAIL.

---

## Files changed in Phase 5 (all minimal, no behaviour change)

| File | Change |
|---|---|
| `core/admin/health.py` | unclosed `open()` → `with` block |
| `ui/pages/government/low_adoption.py` | nested same-quote f-string (3.12-only) → `%`-format |
| `requirements.txt` | runtime-only, 8 packages, upper bounds, pytest removed |
| `requirements-dev.txt` | **new** — `-r requirements.txt` + pytest |
| `.gitignore` | expanded (secrets, env files, DBs, uploads, rasters, IDE) |
| `.streamlit/secrets.toml.example` | rewritten; every key documented as optional |
| `README.md` | "Run locally" + "Deploy" sections rewritten with verified steps |
| `docs/PHASE5_DEPLOYMENT_VERIFICATION.md` | this report |

Tried and removed: `.python-version` (Community Cloud does not honour it).

## Problems fixed
1. Python 3.11 syntax break (would have crashed the Low-Adoption page if Cloud defaulted to <3.12).
2. Resource warning in admin health check.
3. `requirements.txt` carried a test dependency and no upper bounds (a future breaking release could break Cloud rebuilds).

## Remaining items (none blocking)
* Choose Python 3.12 in Cloud Advanced settings.
* Registry edits are in-memory until a database backend is added.
* Optional keys (OpenWeatherMap, LLM narrator) unlock extra features; app is fully functional without them.

---

## Deploy steps

**GitHub**
```bash
cd agrinexus
git init && git add . && git commit -m "AgriNexus AI — four-role platform"
git remote add origin https://github.com/<you>/agrinexus-ai.git
git branch -M main && git push -u origin main
```

**Streamlit Community Cloud**
1. share.streamlit.io → *New app* → repo `<you>/agrinexus-ai`, branch `main`, main file **`app.py`**.
2. *Advanced settings* → Python **3.12**.
3. *Secrets* → leave empty (or paste optional keys below).
4. Deploy.

**Secrets (all optional)**
```toml
# WEATHER_PROVIDER = "openweathermap"
# OPENWEATHER_API_KEY = "..."
# LLM_PROVIDER = "openai"
# LLM_API_KEY = "..."
# LLM_MODEL = "gpt-4o-mini"
```

**Local run**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
# tests: pip install -r requirements-dev.txt && pytest -q   (134 passed)
```

Demo logins: `ramulu`, `sunita`, `newfarmer`, `bank.manager`, `officer`, `admin` — password `agrinexus`.
