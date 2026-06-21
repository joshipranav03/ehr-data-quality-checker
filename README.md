<div align="center">

# 🏥 EHR Data Quality Checker

**Validate Electronic Health Record data for completeness, validity, uniqueness, consistency, and referential integrity — through a web dashboard, a JSON API, or a CLI.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-58%20passing-success)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Code style](https://img.shields.io/badge/data-synthetic%20%C2%B7%20no%20PHI-blue)](#-a-note-on-data--phi)

[![Deploy to Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=white)](https://render.com/deploy?repo=https://github.com/joshipranav03/ehr-data-quality-checker)
[![Deploy to Heroku](https://img.shields.io/badge/Deploy-Heroku-430098?logo=heroku&logoColor=white)](https://heroku.com/deploy?template=https://github.com/joshipranav03/ehr-data-quality-checker)
[![Hugging Face Spaces](https://img.shields.io/badge/Demo-HF%20Spaces-FFD21E?logo=huggingface&logoColor=black)](deploy/huggingface/SETUP.md)
[![Cloud Run](https://img.shields.io/badge/Deploy-Cloud%20Run-4285F4?logo=googlecloud&logoColor=white)](docs/deployment.md#google-cloud-run--permanent-always-free-allowance)

**🔗 Live demo:** _deploy in one click above_ · **📦 Install:** `pip install ehr-data-quality-checker`

</div>

---

## Table of contents
- [Why this exists](#why-this-exists)
- [Key features](#-key-features)
- [The five quality dimensions](#-the-five-quality-dimensions)
- [Quick start](#-quick-start)
- [Deploy it (free)](#-deploy-it-free)
- [Using it](#-using-it)
- [API reference](#-api-reference)
- [Architecture](#-architecture)
- [Project structure](#-project-structure)
- [Rule coverage](#-rule-coverage)
- [FHIR / HL7 ingestion](#-fhir--hl7-ingestion)
- [Configuration](#%EF%B8%8F-configuration)
- [Testing](#-testing)
- [The "32 bugs in clean data" story](#-the-32-bugs-in-clean-data-story)
- [Roadmap](#-roadmap--productionising)
- [A note on data & PHI](#-a-note-on-data--phi)
- [License](#-license)

---

## Why this exists

Healthcare data is notoriously messy: blank fields, impossible dates, invalid
diagnosis codes, duplicate patient IDs, and broken links between tables. Those
defects are invisible until something looks for them — and by the time they
surface in a dashboard, a claim denial, or a clinical decision, they're
expensive (or dangerous).

This tool is a **quality gate**. Point it at an EHR extract — a CSV, an HL7 FHIR
bundle, or an HL7 v2 message — and it scores the data across five dimensions and
shows you the exact offending records *before* they reach a warehouse or a model.
It began as a command-line script and is now a deployable product with a backend
API, a browser front end, and healthcare-interchange ingestion.

> It ships with profiles for **8 EHR tables** (patients, providers, departments,
> encounters, diagnoses, procedures, prescriptions, billing) and **94 rules**.

---

## ✨ Key features

- **Five quality dimensions** — completeness, validity, uniqueness, consistency,
  and cross-table referential integrity.
- **Interactive dashboard** — drag in a file, get a scored report with a
  per-dimension breakdown and a drill-down to the **exact offending rows** (with
  CSV line numbers).
- **JSON API** with auto-generated **OpenAPI/Swagger** docs at `/docs`.
- **CLI** with a `--fail-on-error` gate for CI pipelines.
- **Speaks healthcare interchange formats** — ingests **HL7 FHIR R4** bundles and
  **HL7 v2 ADT** messages, mapping them to the table model (assigning surrogate
  integer keys) and running the identical rule set with cross-table integrity.
- **Quality trends over time** — every run is recorded (summary only, **never
  patient data**) so the dashboard can chart whether a feed is improving or
  degrading.
- **Config-driven engine** — add a table or tighten a rule by editing data, not
  code paths.
- **PHI-conscious by design** — stateless check path, in-memory parsing, no row
  data persisted.
- **Production-ready packaging** — Dockerfile (non-root, healthcheck), one-click
  deploy configs for six platforms, PyPI packaging, and CI.

---

## 📐 The five quality dimensions

| Dimension | The question it answers | Example checks |
|-----------|-------------------------|----------------|
| **Completeness** | Is the value present? | no blank `birth_date`, `gender`, `insurance_provider` |
| **Validity** | Is the value well-formed / in range? | `gender ∈ {M, F}`, valid ICD-10 codes, 2-letter state, parseable non-future dates, non-negative charges |
| **Uniqueness** | Are keys free of duplicates? | no duplicate `patient_id` / `encounter_id` |
| **Consistency** | Do related fields agree? | `discharge_date ≥ admit_date`, `birth_date ≤ registration_date`, payments ≤ charges, one primary diagnosis per encounter |
| **Referential integrity** | Do foreign keys resolve? | every `encounter.patient_id` exists in `patients`, every diagnosis links to a real encounter |

Each rule reports a **severity** (error or warning); the overall score weights
errors more heavily and is floored just below 100 whenever any defect exists, so
rounding can never hide a problem.

---

## 🚀 Quick start

### Install from PyPI

```bash
pip install ehr-data-quality-checker
ehr-dq check your_data.csv             # CLI on your own file
python -m uvicorn app.main:app         # or run the web app at :8000
```

### Run from source

```bash
git clone https://github.com/joshipranav03/ehr-data-quality-checker.git
cd ehr-data-quality-checker

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# (re)generate the bundled demo fixtures (deterministic)
python sample_data/make_dirty.py
python sample_data/fhir/make_fhir_sample.py
python sample_data/hl7/make_hl7_sample.py

uvicorn app.main:app --reload
```

Open **http://localhost:8000** for the dashboard, or
**http://localhost:8000/docs** for the Swagger API explorer.

### Run with Docker

```bash
docker compose up --build
# → http://localhost:8000

# or pull the published image:
docker run -p 8000:8000 ghcr.io/joshipranav03/ehr-data-quality-checker:latest
```

---

## ☁️ Deploy it (free)

One-click configs are included for several platforms — use the buttons at the
top, or:

| Target | How | Free tier? |
|--------|-----|-----------|
| **Hugging Face Spaces** | [`deploy/huggingface/SETUP.md`](deploy/huggingface/SETUP.md) | ✅ free CPU |
| **Render** | `render.yaml` Blueprint | ✅ free Docker web service |
| **Google Cloud Run** | `gcloud run deploy --source .` | ✅ permanent always-free allowance |
| **Railway** | `railway.json` | trial / paid |
| **Fly.io** | `fly.toml` (scale-to-zero) | pay-as-you-go |
| **Heroku** | `heroku.yml` + `app.json` | paid |

Full instructions, the production process model, scaling, observability, and PHI
notes are in **[docs/deployment.md](docs/deployment.md)**.

---

## 🖥️ Using it

### Web dashboard
Four tabs:
- **Try sample data** — check a single bundled table, or **audit the full
  database** (the only mode where cross-table integrity fires).
- **Upload a CSV** — drop in your own file; the dataset is auto-detected from its
  columns.
- **FHIR / HL7** — upload a FHIR R4 Bundle (`.json`) or HL7 v2 ADT (`.hl7`).
- **History & trends** — chart a dataset's quality score over time.

### CLI
```bash
ehr-dq check sample_data/dirty/encounters.csv     # pretty report
ehr-dq check data.csv --json > report.json        # machine-readable
ehr-dq check nightly_export.csv --fail-on-error   # exit 1 on errors → CI gate
ehr-dq audit --variant dirty                      # audit the bundled database
ehr-dq profiles                                   # list datasets + rule counts
```
(Or `python -m app.cli ...` when running from source.)

### Synthea
Run the checker over a whole [Synthea](https://github.com/synthetichealth/synthea)
dataset — synthetic patients you didn't generate:
```bash
python tools/synthea_to_report.py /path/to/synthea/output/fhir
```
See [tools/synthea.md](tools/synthea.md).

A full walkthrough of every interface and the complete rule catalogue lives in
**[docs/usage.md](docs/usage.md)**.

---

## 🔌 API reference

Interactive docs at `/docs` (Swagger) and `/redoc`. Full reference with examples:
**[docs/api.md](docs/api.md)**.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/check` | Validate an uploaded CSV (dataset auto-detected) |
| `POST` | `/api/check/sample` | Validate a bundled sample table (FK checks run) |
| `GET`  | `/api/audit` | Audit the whole bundled database, integrity included |
| `POST` | `/api/check/fhir` | Ingest a FHIR R4 Bundle and audit the derived tables |
| `POST` | `/api/check/hl7` | Ingest HL7 v2 ADT messages and audit the derived tables |
| `GET`  | `/api/history` | Recent report summaries (PHI-safe) |
| `GET`  | `/api/history/trends` | Score-over-time series for one dataset |
| `GET`  | `/api/profiles` | Supported datasets and their rules |
| `GET`  | `/api/samples` | Bundled sample datasets |
| `GET`  | `/api/health` · `/healthz` | Liveness probes |

```bash
# Validate an uploaded file (dataset auto-detected from its columns)
curl -F "file=@sample_data/dirty/patients.csv" http://localhost:8000/api/check

# Ingest a FHIR bundle
curl -F "file=@sample_data/fhir/sample_bundle.json" http://localhost:8000/api/check/fhir

# Audit the whole bundled database
curl "http://localhost:8000/api/audit?variant=dirty"
```

---

## 🧱 Architecture

```
              ┌─────────────────────┐
 Browser  ───▶│  Static dashboard   │  HTML/CSS/vanilla JS, no build step
              │  app/static/*       │
              └─────────┬───────────┘
                        │ fetch() JSON
 curl /        ┌────────▼────────────┐
 scripts   ───▶│   FastAPI app       │  app/main.py      ──  /docs, /redoc
               │   (REST + OpenAPI)  │  app/services.py  ──  parse · detect · run
               └────────┬────────────┘  app/store.py     ──  SQLite history (PHI-safe)
                        │
              ┌─────────▼───────────┐   app/ingest/   ──  FHIR R4 + HL7 v2 → tables
 CLI       ───▶│   Rule engine       │   app/engine/
               │   (pure, testable)  │     rules.py    ──  9 reusable rule types
               │                     │     profiles.py ──  per-table rule sets
               │                     │     checker.py  ──  runs a profile
               │                     │     report.py   ──  scoring + aggregation
               └─────────────────────┘
```

The engine is deliberately **decoupled from the web layer** — the API, the CLI,
the FHIR/HL7 adapters, and the test suite all call the same `DataQualityChecker`.
Rules are pure functions over a pandas `DataFrame`, which makes them trivial to
unit-test and to extend.

---

## 📂 Project structure

```
ehr-data-quality-checker/
├── app/
│   ├── main.py            FastAPI routes
│   ├── services.py        parsing, dataset detection, orchestration
│   ├── store.py           SQLite report history (summary-only, PHI-safe)
│   ├── models.py          Pydantic response models (for OpenAPI)
│   ├── cli.py             command-line interface
│   ├── config.py          env-driven configuration
│   ├── engine/            the rule engine (framework-agnostic)
│   │   ├── rules.py · profiles.py · checker.py · report.py
│   ├── ingest/            FHIR R4 + HL7 v2 adapters → table model
│   └── static/            the dashboard (index.html, styles.css, app.js)
├── sample_data/
│   ├── clean/ · dirty/    synthetic CSV data (+ injected defects)
│   ├── fhir/              a Synthea-shaped FHIR Bundle fixture
│   └── hl7/               an HL7 v2 ADT fixture
├── tools/                 Synthea audit script + guide
├── tests/                 pytest unit + API tests (58)
├── docs/                  usage · api · deployment · blog
├── Dockerfile · docker-compose.yml
├── render.yaml · fly.toml · railway.json · heroku.yml · app.json
├── pyproject.toml · requirements.txt
└── .github/workflows/     ci.yml · publish.yml
```

---

## 🧩 Rule coverage

Nine reusable rule types ([`app/engine/rules.py`](app/engine/rules.py)) power
every profile: `NotNull`, `Unique`, `AllowedValues`, `Regex`, `IntegerType`,
`NumericRange`, `BooleanType`, `DateValid`, `Consistency`, and `ForeignKey`.

| Dataset | Rules | Highlights |
|---------|------:|-----------|
| `patients` | 17 | gender enum, state code, birth/registration ordering, plausible age |
| `encounters` | 19 | discharge ≥ admit, length-of-stay bound, 3 foreign keys |
| `billing` | 12 | non-negative amounts, payments ≤ charges, payment-status enum |
| `diagnoses` | 11 | ICD-10 format, exactly-one-primary per encounter |
| `providers` | 11 | hire-date sanity, department FK |
| `procedures` | 8 | procedure-date validity, encounter FK |
| `prescriptions` | 8 | route enum, encounter FK |
| `departments` | 8 | reference table |

**Adding a dataset is a config change.** Drop a `Profile` into
[`app/engine/profiles.py`](app/engine/profiles.py) with its detection columns and
a list of rules — it appears in the API, dashboard, and CLI automatically, no
engine changes required.

```python
labs = Profile(
    key="lab_results", title="Lab Results",
    description="Laboratory results per encounter.",
    id_column="result_id",
    detect_columns=["result_id", "encounter_id", "loinc_code", "value"],
    rules=[
        *_req("labs", "result_id", "encounter_id", "loinc_code", "value"),
        Unique("labs.unique.id", "result_id must be unique", "result_id"),
        NumericRange("labs.num.value", "value must be >= 0", "value", min_value=0),
        ForeignKey("labs.fk.enc", "encounter_id links to an encounter",
                   "encounter_id", "encounters", "encounter_id"),
    ],
)
```

---

## 🔁 FHIR / HL7 ingestion

Real clinical systems exchange data as **HL7 FHIR** and **HL7 v2**, not CSV. The
[`app/ingest/`](app/ingest/) adapters map those into the same table model:

- **FHIR R4** — resolves `urn:uuid:` references, selects the ICD-10 coding over
  SNOMED, derives `is_primary` (FHIR has no such flag), joins `Claim` ↔
  `ExplanationOfBenefit` for billing, and assigns **surrogate integer keys** (a
  standard ETL step) while preserving every cross-table link.
- **HL7 v2 ADT** — parses PID/PV1 segments into patients + encounters.

Because FHIR and a warehouse CSV model don't line up perfectly, real-world data
surfaces both genuine defects *and* honest mapping gaps (fields FHIR doesn't
carry) — which is exactly what a quality tool should show you. See the
field-by-field mapping and its documented assumptions in
[`app/ingest/fhir.py`](app/ingest/fhir.py).

---

## ⚙️ Configuration

All configuration is via environment variables — no config files to mount.

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8000` | Port to bind |
| `EHR_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Reject larger uploads (HTTP 400) |
| `EHR_MAX_ROWS` | `500000` | Reject files / payloads with more rows |
| `EHR_HISTORY` | `on` | Set `off` on ephemeral hosts (Render/Fly/Cloud Run/Spaces) |
| `EHR_DB_PATH` | `var/reports.db` | SQLite file for report history (needs a persistent disk) |

---

## 🧪 Testing

```bash
pytest -q          # 58 unit + API tests
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the suite on
Python 3.11 and 3.12, regenerates the sample fixtures (proving determinism),
smoke-tests the CLI, and builds + boots the Docker image.
[`publish.yml`](.github/workflows/publish.yml) ships the package to PyPI and the
image to GHCR on each version tag.

---

## 🔍 The "32 bugs in clean data" story

To test the checker, I ran it on a synthetic hospital dataset that was *supposed*
to be clean. It immediately found **32 patients whose records say they were born
*after* they registered at the hospital** — a physically impossible timeline
(`birth_date > registration_date`) that the generator had introduced by picking
the two dates independently. That's the whole point of data-quality work: the
problems are invisible until something looks for them. The full write-up is in
[docs/blog/](docs/blog/finding-32-bugs-in-clean-healthcare-data.md).

---

## 🗺️ Roadmap / productionising

This is a portfolio-grade demonstrator. To take it into a real clinical
environment you'd add: authentication & multi-tenancy, database/FHIR-server
connectors (beyond file upload), configurable per-customer rule severities,
durable persistence for long-term trend tracking, and audit logging. The
architecture is built to absorb these — the engine, ingestion, persistence, and
web layers are already separated.

---

## 🔒 A note on data & PHI

The bundled sample data is **synthetic** and contains **no real patient
information (PHI)**. The check path is stateless — uploads are parsed in memory
and discarded; the optional history feature stores only aggregate scores, never
row data. Before pointing it at real clinical data, read the
[PHI section of the deployment guide](docs/deployment.md#handling-real-phi)
(HTTPS, private networking, authentication, BAA).

---

## 📝 License

MIT — see [LICENSE](LICENSE). You're free to use, modify, and distribute it,
including commercially; just keep the copyright notice.

---

<div align="center">
<sub>Built to demonstrate backend, frontend, API design, healthcare interoperability, and deployment thinking. Feedback welcome.</sub>
</div>
