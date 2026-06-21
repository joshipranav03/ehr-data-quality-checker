---
title: EHR Data Quality Checker
emoji: 🏥
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Validate EHR data for completeness, validity & integrity
---

# 🏥 EHR Data Quality Checker

Validate Electronic Health Record (EHR) data extracts for **completeness,
validity, uniqueness, consistency, and referential integrity** — with an
interactive dashboard and a JSON API.

- Upload a CSV (patients, encounters, billing, …) or try the bundled synthetic
  sample data.
- See a scored report with a per-dimension breakdown and the exact offending rows.
- API docs at `/docs`.

All sample data is synthetic — **no real patient information (PHI)**.

> Source code, CLI, tests, and full documentation:
> https://github.com/joshipranav03/ehr-data-quality-checker
