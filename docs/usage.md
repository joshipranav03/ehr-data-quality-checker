# Usage guide

Three interfaces, one engine: the **web dashboard**, the **JSON API**, and the
**CLI** all run identical checks. Pick whichever fits your workflow.

---

## 1. The web dashboard

Start the app and open <http://localhost:8000>.

```bash
uvicorn app.main:app --reload
```

### Try sample data
1. Choose a **Dataset** (e.g. *Patients*) and a **Variant**:
   - **Dirty** — the sample with injected defects, so every check has something to show.
   - **Clean** — the original synthetic data (still has a few genuine consistency issues — see below).
2. Press **Check table** to score a single table, or **Audit full database** to
   run all eight tables together (this is the only mode where cross-table
   referential-integrity checks fire).

### Upload your own CSV
1. Switch to the **Upload a CSV** tab.
2. Pick a file. Leave **Dataset** on *Auto-detect* (the app recognises the table
   from its column names) or choose one explicitly.
3. Press **Run check**.

### Reading the report
- **Quality score** — a 0–100 weighted score (errors count more than warnings).
  A perfect 100 means zero issues; anything with defects is floored below 100.
- **Stat cards** — error count, warning count, percentage of fully clean rows,
  and how many rules passed.
- **Quality dimensions** — per-dimension pass rate bars.
- **Findings** — every rule, filterable by status. Click a failed rule to expand
  a **sample of the offending rows**, with the exact CSV line number for each.

> **Why "clean" data still shows 32 issues:** the synthetic generator picked
> `birth_date` and `registration_date` independently, so ~32 patients appear to
> have been born *after* they registered. That's a real consistency defect the
> checker surfaces — a nice illustration that "clean-looking" data rarely is.

### FHIR / HL7 (the interop tab)
Upload an **HL7 FHIR R4 Bundle** (`.json`) or an **HL7 v2 ADT** message (`.hl7`)
and the app maps it to the table model, assigns surrogate integer keys, and
audits every derived table together (cross-table integrity included). Try the
bundled `sample_data/fhir/sample_bundle.json` or `sample_data/hl7/sample_adt.hl7`.
To run it over a whole Synthea dataset, see [../tools/synthea.md](../tools/synthea.md).

### History & trends
Every check is recorded — **summary only, never patient data**. The History tab
charts a dataset's quality score over time, so you can watch whether a feed is
getting cleaner (or worse) across runs. Disable persistence with
`EHR_HISTORY=off` (the default on ephemeral hosts).

---

## 2. The JSON API

Interactive docs: **<http://localhost:8000/docs>** (Swagger) and
**<http://localhost:8000/redoc>**. Full reference: [api.md](api.md).

```bash
# Auto-detect the dataset from the file's columns
curl -F "file=@sample_data/dirty/patients.csv" \
     http://localhost:8000/api/check | jq '.summary'

# Force a specific dataset
curl -F "file=@my_export.csv" \
     "http://localhost:8000/api/check?dataset=encounters"

# Check a bundled sample (siblings available, so FK checks run)
curl -X POST "http://localhost:8000/api/check/sample?name=billing&variant=dirty"

# Audit the whole bundled database
curl "http://localhost:8000/api/audit?variant=dirty" | jq '.aggregate'
```

---

## 3. The CLI

Useful in data pipelines and CI. Same engine, no server required.

```bash
# Pretty terminal report (colourised)
python -m app.cli check sample_data/dirty/billing.csv

# Machine-readable
python -m app.cli check data.csv --json > report.json

# CI gate: exit non-zero when any error-level issues exist
python -m app.cli check nightly_export.csv --fail-on-error

# Audit the bundled sample database
python -m app.cli audit --variant dirty

# List supported datasets and their rule counts
python -m app.cli profiles
```

If you install the package (`pip install -e .`), the console script `ehr-dq`
is available directly: `ehr-dq check data.csv`.

---

## How dataset detection works

Each profile declares a set of **detection columns**. On upload, the app picks
the profile whose schema best overlaps the file's header row. If nothing
matches, you get a `400` asking you to pass `?dataset=` explicitly. Values are
read as raw text so the *engine* — not pandas — decides what counts as a valid
integer, date, or number; blank cells are treated as missing.

---

## The rule catalogue

Nine reusable rule types power every profile
([`app/engine/rules.py`](../app/engine/rules.py)):

| Rule type | Dimension | What it flags |
|-----------|-----------|---------------|
| `NotNull` | completeness | blank or missing required values |
| `Unique` | uniqueness | duplicate primary-key values |
| `AllowedValues` | validity | values outside an enumerated set (e.g. `gender`, `payment_status`) |
| `Regex` | validity | malformed strings (ICD-10 codes, 2-letter state codes) |
| `IntegerType` | validity | non-integer values in ID/count columns |
| `NumericRange` | validity | non-numeric or out-of-range amounts (e.g. negative charges) |
| `BooleanType` | validity | non-boolean flags (`is_primary`) |
| `DateValid` | validity | unparseable, future, or implausibly-old dates |
| `Consistency` | consistency | cross-field rule violations (date ordering, payment totals, one-primary-diagnosis) |
| `ForeignKey` | integrity | values that don't resolve to a parent table |

### Per-table coverage

| Dataset | Rules | Highlights |
|---------|------:|-----------|
| `patients` | 17 | gender enum, state code, birth/registration ordering, plausible age |
| `encounters` | 19 | discharge ≥ admit, length-of-stay bound, 3 foreign keys |
| `billing` | 12 | non-negative amounts, payments ≤ charges, payment-status enum |
| `diagnoses` | 11 | ICD-10 format, exactly-one-primary per encounter |
| `providers` | 11 | hire-date sanity, department FK |
| `departments` | 8 | reference table for the others |
| `procedures` | 8 | procedure-date validity, encounter FK |
| `prescriptions` | 8 | route enum, encounter FK |

> **Foreign-key checks only run when parent tables are available.** A single-file
> upload can't resolve `encounter_id → encounters`, so those rules report as
> *skipped* (not failed). Use the **sample audit** or upload the full set to see
> them run.

To add a dataset or tweak a rule, edit `app/engine/profiles.py` — see the
[README](../README.md#-adding-a-new-dataset-or-rule).
