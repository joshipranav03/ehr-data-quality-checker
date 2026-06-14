# 🏥 EHR Data Quality Checker

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Pandas](https://img.shields.io/badge/Pandas-2.0%2B-150458?logo=pandas)
![License](https://img.shields.io/badge/License-MIT-green)
![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=github-actions)

A **command-line Python tool** that validates and scores the data quality of
EHR/EMR patient datasets exported as CSV files. Built using only **Python** and
**Pandas** — no external BI tools required.

---

## 👤 About the Author

Built by Pranav Joshi, a healthcare operations professional. I have 8+ years of direct
experience working with **PointClickCare**, **AxisCare**, and clinical scheduling
systems at facilities including Zara HomeCare LLC, Brookdale Senior Living, and
Maryville Memory Care.

This project reflects real pain points encountered when working with EHR exports
that contained:
- Missing caregiver assignments that caused scheduling gaps
- Incorrect discharge dates that broke medication reconciliation reports
- Invalid ICD-10 codes that caused billing claim rejections
- Duplicate patient IDs from system migrations between PointClickCare facilities

---

## 🔍 What Does It Do?

The checker reads a CSV export of patient EHR records and runs **six categories
of data quality checks**, then produces a **quality score (0–100%)** and a
detailed CSV report.

| Check | What It Catches | Real-World Relevance |
|---|---|---|
| **Missing Fields** | Null/blank values in required columns | Missing caregiver IDs break AxisCare scheduling; missing DOB blocks PointClickCare admission |
| **Duplicate Patient IDs** | Same `patient_id` appearing on multiple rows | Common after EHR migrations or manual data entry in dual-system environments |
| **Date Logic** | Discharge before admission; DOB in the future; DOB after admission | Invalid dates corrupted census reports in PointClickCare at memory care facilities |
| **Gender Standardization** | Values outside `{M, F, Male, Female, Non-binary, Unknown}` | Non-standard entries fail HIPAA demographic reporting requirements |
| **ICD-10 Code Validation** | Codes not matching `[A-Z][0-9]{2}(.[0-9A-Z]{1,4})?` pattern | Malformed diagnosis codes cause CMS billing rejections |
| **Medication Safety** | Null/blank `medication_name` or `dosage` | Missing dosage information is a direct patient safety risk — critical in memory care |

### Quality Score Formula

```
Quality Score = 100 × (1 − affected_cells / total_cells)
```

| Score | Rating |
|---|---|
| ≥ 90% | ✅ PASS |
| 70–89% | ⚠️ WARNING |
| < 70% | ❌ FAIL |

---

## 🗂️ Project Structure

```
ehr-data-quality-checker/
├── ehr_checker.py              # Main script — all checks + CLI
├── requirements.txt            # pandas, numpy
├── README.md                   # This file
├── tests/
│   ├── __init__.py
│   └── test_ehr_checker.py     # pytest unit tests
└── .github/
    └── workflows/
        └── ci.yml              # GitHub Actions CI (runs tests on every push)
```

---

## 🛠️ Tools Used

| Tool | Version | Purpose |
|---|---|---|
| **Python** | 3.9+ | Core language |
| **Pandas** | 2.0+ | CSV loading, data filtering, groupBy, null detection |
| **NumPy** | 1.24+ | Random data generation for sample dataset |
| **argparse** | stdlib | Command-line interface |
| **re** (regex) | stdlib | ICD-10 code pattern matching |
| **pytest** | 7+ | Unit testing |
| **GitHub Actions** | — | CI/CD — runs tests automatically on push |

> No external databases, no BI tools, no API keys. Just Python and Pandas.

---

## ⚙️ Installation

```bash
# Clone the repository
git clone https://github.com/joshipranav03/ehr-data-quality-checker.git
cd ehr-data-quality-checker

# Install dependencies (Python 3.9+ recommended)
pip install -r requirements.txt
```

---

## 🚀 Usage

### Run on built-in sample data (no file needed)

```bash
python ehr_checker.py
```

### Generate a sample CSV to inspect or modify

```bash
python ehr_checker.py --generate-sample
# Creates: sample_ehr_data.csv
```

### Run on your own EHR CSV export

```bash
python ehr_checker.py --input your_ehr_export.csv
```

### Specify a custom output path for the report

```bash
python ehr_checker.py --input export.csv --output reports/quality_report.csv
```

### Full help

```bash
python ehr_checker.py --help
```

---

## 📊 Sample Output

```
════════════════════════════════════════════════════════════════════════
                     EHR DATA QUALITY REPORT
               Generated: 2026-06-14 09:00:00
════════════════════════════════════════════════════════════════════════

  Dataset:  50 rows × 12 columns
  Issues:   15 found
  Quality Score: 73.2%
  Rating: ⚠️  WARNING

────────────────────────────────────────────────────────────────────────
  CHECK                          COLUMN                  ROWS  DETAILS
────────────────────────────────────────────────────────────────────────
  missing_value                  first_name                12  12 null/blank values
  missing_value                  last_name                 15  15 null/blank values
  duplicate_patient_id           patient_id                 3  Duplicate IDs: ['P0001']
  invalid_date_range             discharge_date             3  discharge_date is earlier than...
  invalid_gender                 gender                    29  Non-standard values: ['N/A', 'X'...]
  invalid_diagnosis_code         diagnosis_code            10  Does not match ICD-10 format
  incomplete_medication_record   medication_name           16  medication_name is missing
────────────────────────────────────────────────────────────────────────

  📄 Report saved → ehr_quality_report.csv
```

---

## 📋 Expected CSV Format

Your input CSV should contain these columns (extra columns are ignored):

| Column | Format | Example |
|---|---|---|
| `patient_id` | String | `P0042` |
| `first_name` | String | `Mary` |
| `last_name` | String | `Smith` |
| `date_of_birth` | YYYY-MM-DD | `1945-03-12` |
| `gender` | M / F / Male / Female / Non-binary / Unknown | `F` |
| `admission_date` | YYYY-MM-DD | `2024-01-10` |
| `discharge_date` | YYYY-MM-DD | `2024-01-20` |
| `diagnosis_code` | ICD-10 (e.g. E11.9, I10) | `E11.9` |
| `medication_name` | String | `Metformin 500mg` |
| `dosage` | String | `500mg` |
| `caregiver_id` | String | `CG003` |
| `visit_date` | YYYY-MM-DD | `2024-01-11` |

---

## 🧪 Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Tests cover every check function individually, including edge cases for clean
records, duplicate IDs, invalid ICD-10 codes, date range violations, and missing
medication fields.

---

## 🔮 Future Enhancements

- [ ] HTML report output with summary charts (Matplotlib/Plotly)
- [ ] FHIR R4 JSON input support (HL7 interoperability)
- [ ] PointClickCare column name auto-mapping
- [ ] Streamlit web dashboard for non-technical staff
- [ ] Configurable rules via YAML (custom required columns, thresholds)
- [ ] Multi-facility batch processing (AxisCare multi-location support)

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

## 🤝 Contributing

Pull requests welcome. Please open an issue first to discuss what you would like
to change. All contributions must include updated tests.

---

*Built with ❤️ and the help of claude from 8+ years in healthcare operations because clean data saves lives.*
