# Running the checker on Synthea data

[Synthea™](https://github.com/synthetichealth/synthea) is an open-source
synthetic patient generator from The MITRE Corporation. It produces realistic —
but entirely fake — patient records in FHIR R4, with no real PHI. Running the
checker on Synthea output is a great way to validate the FHIR ingestion against
data you didn't generate.

## 1. Generate Synthea FHIR data

You need Java 11+.

```bash
git clone https://github.com/synthetichealth/synthea.git
cd synthea
./run_synthea -p 100 Massachusetts      # 100 patients in MA
```

Output bundles land in `output/fhir/` — one transaction Bundle per patient,
plus `hospitalInformation*.json` and `practitionerInformation*.json`.

## 2. Audit it

From this project's root:

```bash
python tools/synthea_to_report.py /path/to/synthea/output/fhir
```

This merges every bundle into one (so surrogate keys and cross-patient
referential integrity are consistent), maps the FHIR resources to the table
model, and runs the full audit. Add `--json` for a machine-readable report.

You can also point the web app at a single bundle: open the **FHIR / HL7** tab
and upload any one of the `output/fhir/*.json` files.

## What to expect

The checker maps Patient, Encounter, Condition, Procedure, MedicationRequest,
and Claim/ExplanationOfBenefit resources. Because FHIR and a warehouse CSV model
don't line up perfectly, real Synthea output typically surfaces a mix of:

- **Real clinical/coding issues** — diagnoses with no ICD-10 mapping (SNOMED
  only), encounters with unusual timing, payments that don't reconcile.
- **Honest mapping gaps** — FHIR has no native `registration_date`, and some
  Synthea encounters omit a discharge disposition. These show up as
  completeness findings, which is the point: the tool shows you exactly what
  your FHIR→warehouse mapping drops.

See [`app/ingest/fhir.py`](../app/ingest/fhir.py) for the full field-by-field
mapping and its documented assumptions.

## A note on keys

FHIR uses string UUIDs; the warehouse model expects integer keys. The ingester
assigns **surrogate integer keys** (a standard ETL step) while preserving every
cross-table reference — so foreign-key integrity is still checked end to end.
