# API reference

Base URL: `http://localhost:8000`. Interactive docs are generated automatically
at `/docs` (Swagger UI) and `/redoc`. The OpenAPI schema is at `/openapi.json`.

All responses are JSON. Errors use standard HTTP status codes with a body of
`{"detail": "..."}`.

---

## `GET /api/health`

Liveness probe.

```json
{ "status": "ok", "app": "EHR Data Quality Checker", "version": "1.0.0", "profiles": 8 }
```

---

## `GET /api/profiles`

List supported datasets and the rules applied to each.

```json
[
  {
    "key": "patients",
    "title": "Patients",
    "description": "Patient demographics, location, and insurance.",
    "id_column": "patient_id",
    "columns": ["patient_id", "first_name", "last_name", "gender", "birth_date"],
    "parent_tables": [],
    "rule_count": 17,
    "rules": [
      { "rule_id": "patients.enum.gender", "title": "gender is M or F",
        "category": "validity", "severity": "error", "column": "gender" }
    ]
  }
]
```

---

## `GET /api/samples`

List the bundled sample datasets.

```json
{
  "datasets": ["departments", "providers", "patients", "encounters", "..."],
  "samples": {
    "clean": ["billing", "departments", "diagnoses", "..."],
    "dirty": ["billing", "departments", "diagnoses", "..."]
  }
}
```

---

## `POST /api/check`

Run checks on an uploaded CSV.

**Request:** `multipart/form-data`

| Field | In | Required | Description |
|-------|----|----------|-------------|
| `file` | form | yes | A CSV extract of one EHR table |
| `dataset` | query | no | Dataset name. Auto-detected from columns when omitted. |

```bash
curl -F "file=@patients.csv" "http://localhost:8000/api/check?dataset=patients"
```

**Response `200`:** a [report object](#the-report-object).

**Errors:** `400` for an unparseable file, an oversize file (default limit 25 MB),
an unknown `dataset`, or columns that match no profile.

---

## `POST /api/check/sample`

Run checks on a bundled sample table. Sibling tables of the same variant are
loaded as context, so **referential-integrity rules run**.

| Param | In | Default | Description |
|-------|----|---------|-------------|
| `name` | query | — | Dataset name, e.g. `patients` |
| `variant` | query | `dirty` | `clean` or `dirty` |

```bash
curl -X POST "http://localhost:8000/api/check/sample?name=encounters&variant=dirty"
```

Returns a [report object](#the-report-object) with an extra `"variant"` field.

---

## `GET /api/audit`

Audit every table of a variant together, resolving cross-table foreign keys.

| Param | In | Default | Description |
|-------|----|---------|-------------|
| `variant` | query | `dirty` | `clean` or `dirty` |

```json
{
  "variant": "dirty",
  "aggregate": {
    "tables": 8, "rows": 39544,
    "errors": 71, "warnings": 8, "total_issues": 79,
    "rows_with_errors": 60, "score": 99.9
  },
  "tables": [ /* one report object per table */ ]
}
```

---

## `POST /api/check/fhir`

Ingest an HL7 **FHIR R4 Bundle**, map it to the table model, assign surrogate
integer keys, and audit every derived table together.

**Request:** `multipart/form-data` with a `file` field (the Bundle JSON).

```bash
curl -F "file=@sample_data/fhir/sample_bundle.json" \
     http://localhost:8000/api/check/fhir
```

**Response `200`:** an [audit object](#the-audit-object) with `"source": "fhir"`
and `"format": "FHIR R4"`. `400` if the JSON is invalid or contains no
recognised resources.

## `POST /api/check/hl7`

Ingest **HL7 v2 ADT** messages (PID/PV1 segments) and audit the derived
patients + encounters.

```bash
curl -F "file=@sample_data/hl7/sample_adt.hl7" \
     http://localhost:8000/api/check/hl7
```

Returns an [audit object](#the-audit-object) with `"source": "hl7v2"`.

## `GET /api/history`

Recent report summaries (requires history enabled — `EHR_HISTORY` not `off`).
Only aggregate fields are stored; **no patient rows are ever persisted**.

| Param | In | Default | Description |
|-------|----|---------|-------------|
| `dataset` | query | — | Filter to one dataset |
| `limit` | query | `50` | Max records (1–500) |

```json
{
  "enabled": true,
  "datasets": ["patients", "billing", "..."],
  "records": [
    {"id": 12, "created_at": "2026-06-21T11:30:00+00:00", "dataset": "patients",
     "source": "sample", "variant": "dirty", "row_count": 2000,
     "score": 99.9, "grade": "A+", "errors": 43, "warnings": 2, "rules_failed": 9}
  ]
}
```

## `GET /api/history/trends`

Score-over-time series for one dataset, oldest to newest (for charting).

| Param | In | Default | Description |
|-------|----|---------|-------------|
| `dataset` | query | — | Dataset to chart (required) |
| `limit` | query | `30` | Max points (1–365) |

```json
{
  "dataset": "patients", "enabled": true, "count": 3,
  "points": [
    {"created_at": "...", "score": 90.0, "errors": 50, "warnings": 2, "row_count": 2000},
    {"created_at": "...", "score": 99.9, "errors": 43, "warnings": 2, "row_count": 2000}
  ]
}
```

---

## The audit object

Returned by `/api/audit`, `/api/check/fhir`, and `/api/check/hl7`.

```jsonc
{
  "source": "fhir",              // audit | fhir | hl7v2
  "format": "FHIR R4",           // present for fhir/hl7 sources
  "variant": "dirty",            // present for the sample audit
  "recognised": ["patients", "encounters", "diagnoses"],
  "aggregate": {
    "tables": 6, "rows": 14,
    "errors": 5, "warnings": 1, "total_issues": 6,
    "rows_with_errors": 4, "score": 97.9
  },
  "tables": [ /* one report object per table */ ]
}
```

---

## The report object

Returned by `/api/check`, `/api/check/sample`, and inside `/api/audit`.

```jsonc
{
  "dataset": "patients",
  "dataset_title": "Patients",
  "generated_at": "2026-06-21T10:55:00+00:00",
  "row_count": 2000,
  "column_count": 9,
  "columns": ["patient_id", "first_name", "..."],
  "auto_detected": false,          // present on /api/check
  "variant": "dirty",              // present on sample/audit

  "summary": {
    "score": 99.9,                 // 0–100, weighted (errors > warnings)
    "grade": "A+",                 // A+ … F
    "total_issues": 45,
    "errors": 43,
    "warnings": 2,
    "rules_total": 17,
    "rules_run": 17,
    "rules_passed": 8,
    "rules_failed": 9,
    "rules_skipped": 0,
    "rows_with_errors": 42,
    "clean_rows": 1958,
    "clean_row_pct": 97.9
  },

  "dimensions": {
    "completeness": { "rules": 9, "checked": 18000, "failed": 3, "score": 99.9 },
    "validity":     { "rules": 4, "checked": 7996,  "failed": 5, "score": 99.9 },
    "uniqueness":   { "rules": 1, "checked": 2000,  "failed": 2, "score": 99.9 },
    "consistency":  { "rules": 2, "checked": 4000,  "failed": 35, "score": 99.1 },
    "integrity":    { "rules": 0, "checked": 0,     "failed": 0, "score": null }
  },

  "results": [
    {
      "rule_id": "patients.enum.gender",
      "title": "gender is M or F",
      "category": "validity",
      "severity": "error",          // error | warning
      "column": "gender",
      "status": "failed",           // passed | failed | skipped
      "checked": 2000,
      "failed": 2,
      "pass_rate": 0.999,
      "message": "'gender' must be one of: F, M.",
      "skip_reason": null,
      "sample": [
        { "_line": 7, "gender": "X" },   // _line = 1-based CSV line number
        { "_line": 20, "gender": "Male" }
      ]
    }
  ]
}
```

### Field notes
- **`score`** is weighted by severity (errors weight 1.0, warnings 0.4) across all
  validated cells. It is floored just below 100 whenever any issue exists.
- **`status: "skipped"`** means a rule could not run — usually a foreign-key rule
  with no parent table available, or a column absent from the file. `skip_reason`
  explains why.
- **`sample`** holds up to 8 offending rows; `_line` is the line in the original
  CSV (the header is line 1) so issues are easy to locate.

---

## Configuration

Set via environment variables (see [deployment.md](deployment.md)):

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORT` | `8000` | Port the server binds to |
| `EHR_MAX_UPLOAD_BYTES` | `26214400` (25 MB) | Reject larger uploads |
| `EHR_MAX_ROWS` | `500000` | Reject files with more rows |
