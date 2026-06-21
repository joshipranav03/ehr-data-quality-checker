---
title: "I pointed a data-quality checker at 'clean' healthcare data. It found 32 bugs."
published: false
description: "Building an EHR data quality checker — and what it caught in a dataset that was supposed to be spotless."
tags: healthcare, python, datascience, showdev
cover_image: ""
canonical_url: ""
---

> A practical look at building a data-quality tool for Electronic Health Record
> (EHR) data — and a reminder that "clean-looking" data almost never is.

## The 30-second version

I built [EHR Data Quality Checker](https://github.com/joshipranav03/ehr-data-quality-checker):
upload a CSV of healthcare data, get a scored report of everything wrong with it.
To test it, I ran it on a synthetic hospital dataset that was *supposed* to be
clean. It immediately found **32 patients whose records say they were born
*after* they registered at the hospital** — a physically impossible timeline
that had been sitting in the data unnoticed.

That's the whole pitch for data quality work in one example: the problems are
invisible until something looks for them.

## Why healthcare data is a special kind of messy

Healthcare data is typed in by busy humans, copied between systems that don't
agree on formats, and merged across decades. The result is predictably broken:

- blank birth dates and missing genders
- diagnosis codes that aren't valid ICD-10
- the same patient entered twice
- bills with negative amounts
- a hospital visit whose discharge date precedes its admission date
- a visit that references a patient who doesn't exist in the patient table

None of these are exotic. All of them break downstream analytics, billing, and —
in the worst case — clinical decisions. A duplicate patient record is a known
contributor to medication errors. So before EHR data reaches a warehouse or a
model, *something* should check it.

## The five dimensions of data quality

I organized the checks around five standard quality dimensions. This framing is
worth internalizing — it turns a vague "is this data good?" into specific,
testable questions:

| Dimension | The question it answers | Example check |
|-----------|------------------------|---------------|
| **Completeness** | Is the value there at all? | `birth_date` is not blank |
| **Validity** | Is the value well-formed? | `gender ∈ {M, F}`; valid ICD-10 code |
| **Uniqueness** | Are keys free of duplicates? | no duplicate `patient_id` |
| **Consistency** | Do related fields agree? | `discharge_date ≥ admit_date` |
| **Integrity** | Do references resolve? | every `encounter.patient_id` exists |

The 32-bug finding was a **consistency** failure: `birth_date ≤ registration_date`
is an invariant that must hold, and 32 rows violated it.

## How the engine is built

The core design decision: **the rule engine knows nothing about the web.** Rules
are pure functions over a pandas DataFrame that return a structured result. The
API, the CLI, and the test suite all call the same engine.

A rule is small and self-contained:

```python
class AllowedValues(Rule):
    category = VALIDITY

    def evaluate(self, df, context=None):
        present = _present(df[self.column])           # ignore missing — that's completeness's job
        bad = present & ~df[self.column].isin(self.allowed)
        return self._result(df, bad, checked=int(present.sum()),
                            message=f"'{self.column}' must be one of {self.allowed}.")
```

Cross-field consistency rules take a small callable that returns the *failing*
rows — which is how the famous 32-bug check is expressed:

```python
Consistency(
    "patients.consistency.birth_before_registration",
    "birth_date must be on or before registration_date",
    failing_mask=lambda df: to_date(df, "birth_date") > to_date(df, "registration_date"),
    columns=["birth_date", "registration_date"],
)
```

Datasets are just **configuration** — a profile lists detection columns and a set
of rules. Adding support for a new table (lab results, immunizations) is a config
change, not an engine change. Today there are profiles for 8 EHR tables and 94
rules.

## Referential integrity is the interesting one

Most checks look at one table. Integrity looks *across* tables: does
`encounters.patient_id` actually exist in `patients`? You can only answer that if
you have both tables. So the engine takes an optional `context` of sibling
tables; foreign-key rules run when the parent is available and cleanly report as
*skipped* (not failed) when it isn't. Running a full 8-table audit, the checker
resolves every cross-table link and flags the orphans.

## What the report looks like

Each run produces a weighted score (errors count more than warnings), a count of
issues by severity and dimension, and — the useful part — a **sample of the exact
offending rows with their CSV line numbers**. On the full "dirty" sample
database (39,544 rows across 8 tables) it surfaced 71 errors and 8 warnings, each
traceable to a specific row.

A subtle but important scoring choice: a perfect 100 is reserved for *genuinely
zero issues*. If even one bad cell exists, the score is floored just below 100 so
rounding can never hide a problem.

## Three interfaces, one engine

- A **web dashboard** for humans — drag in a CSV, see the issues visually.
- A **JSON API** (`POST /api/check`) so other systems can validate data
  automatically — e.g. gate a nightly load before it pollutes the warehouse.
- A **CLI** with `--fail-on-error` for CI pipelines.

Because the engine is decoupled, all three are thin wrappers. That's the payoff
of keeping business logic out of the framework.

## It speaks FHIR and HL7, too

CSV is fine for a warehouse extract, but real clinical systems exchange data as
**HL7 FHIR** bundles and **HL7 v2** messages. So the checker has adapters that map
those into the same table model and run the identical rules.

FHIR is genuinely awkward to flatten — references are `urn:uuid:…` strings, a
diagnosis carries a SNOMED code *and* an ICD-10 code only sometimes, there's no
"primary diagnosis" flag, and IDs are UUIDs rather than integers. The ingester
handles all of that (assigning surrogate integer keys, the way a real ETL would)
and then something nice happens: pointed at a stack of [Synthea](https://github.com/synthetichealth/synthea)-generated
patients — data I didn't create — it flags diagnoses with no ICD-10 mapping,
encounters with impossible timing, and the fields FHIR simply doesn't carry that
your warehouse schema expects. The mapping gaps are findings too.

## Watching quality over time

A one-off score is useful; a *trend* is better. Every run is recorded — **summary
only, never patient rows** — so the dashboard can chart whether a feed is getting
cleaner or quietly degrading. That turns a checker into a monitor.

## A note on PHI

The check path is stateless — uploads are parsed in memory and discarded. The
optional history feature stores only aggregate scores (counts and a number),
never row data. Both are deliberate choices for regulated health data: the less
PHI you touch and keep, the smaller your compliance surface.

## Takeaways

1. **"Clean" data isn't.** The most convincing demo was running it on data that
   wasn't supposed to have problems — and finding 32.
2. **Frame quality as dimensions.** Completeness / validity / uniqueness /
   consistency / integrity turns a fuzzy goal into a checklist.
3. **Decouple the engine.** Pure functions over a DataFrame are trivial to test
   and reuse across a web app, a CLI, and a pipeline.
4. **Make the score honest.** Don't let rounding paper over real defects.

## Try it

Code, docs, and a live demo: **https://github.com/joshipranav03/ehr-data-quality-checker**

```bash
pip install ehr-data-quality-checker
ehr-dq check your_data.csv
```

If you work with healthcare data, point it at an extract you *think* is clean.
I'd bet it finds something.
