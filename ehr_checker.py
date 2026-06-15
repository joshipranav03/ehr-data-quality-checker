"""
EHR Data Quality Checker
Author: PJ (Pranav Joshi)
Description: A Python/Pandas tool for validating EHR/EMR patient data quality,
reflecting real-world experience with PointClickCare, AxisCare, and healthcare operations.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import argparse
import sys
import os


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ CONFIG Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

REQUIRED_COLUMNS = [
    "patient_id", "first_name", "last_name", "date_of_birth",
    "gender", "admission_date", "discharge_date", "diagnosis_code",
    "medication_name", "dosage", "caregiver_id", "visit_date"
]

VALID_GENDERS = {"M", "F", "Male", "Female", "Non-binary", "Unknown"}
ICD10_PATTERN = r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$"


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ GENERATOR: sample dataset Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def generate_sample_data(n=50):
    """Create a realistic EHR dataset with intentional data quality issues."""
    np.random.seed(42)
    rng = np.random.default_rng(42)

    patient_ids = [f"P{str(i).zfill(4)}" for i in range(1, n + 1)]

    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer",
                   "Michael", "Linda", "William", "Barbara", None, "", "  "]
    last_names  = ["Smith", "Johnson", "Williams", "Brown", "Jones", None, ""]
    genders     = ["M", "F", "Male", "Female", "Unknown", "N/A", None, "X"]
    medications = ["Metformin 500mg", "Lisinopril 10mg", "Atorvastatin 20mg",
                   "Amlodipine 5mg", "Omeprazole 20mg", None, ""]
    caregiver_ids = [f"CG{str(i).zfill(3)}" for i in range(1, 10)] + [None, ""]

    records = []
    for pid in patient_ids:
        dob = pd.Timestamp("1930-01-01") + pd.to_timedelta(
            rng.integers(0, 30000), unit="D"
        )
        admission = pd.Timestamp("2023-01-01") + pd.to_timedelta(
            rng.integers(0, 365), unit="D"
        )
        if rng.random() < 0.1:
            discharge = admission - pd.to_timedelta(rng.integers(1, 30), unit="D")
        else:
            discharge = admission + pd.to_timedelta(rng.integers(1, 60), unit="D")

        visit = admission + pd.to_timedelta(rng.integers(0, 5), unit="D")

        valid_codes   = ["E11.9", "I10", "J18.9", "Z99.89", "F32.1"]
        invalid_codes = ["999", "ABCD", "", None, "xx-11"]
        dx = rng.choice(valid_codes + invalid_codes,
                        p=[0.14, 0.14, 0.14, 0.14, 0.14, 0.1, 0.1, 0.05, 0.05, 0.0])

        records.append({
            "patient_id":     pid,
            "first_name":     rng.choice(first_names),
            "last_name":      rng.choice(last_names),
            "date_of_birth":  dob if rng.random() > 0.05 else None,
            "gender":         rng.choice(genders),
            "admission_date": admission,
            "discharge_date": discharge,
            "diagnosis_code": dx,
            "medication_name": rng.choice(medications),
            "dosage":         rng.choice(["500mg", "10mg", "20mg", "5mg", None, ""]),
            "caregiver_id":   rng.choice(caregiver_ids),
            "visit_date":     visit if rng.random() > 0.05 else None,
        })

    # Inject duplicate patient IDs (only when dataset is large enough)
    if len(records) > 5:
        records[5]["patient_id"] = records[0]["patient_id"]
    if len(records) > 10:
        records[10]["patient_id"] = records[0]["patient_id"]

    return pd.DataFrame(records)


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ CHECKS Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def check_missing_fields(df):
    issues = []
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            issues.append({"check": "missing_column", "column": col,
                           "affected_rows": df.shape[0],
                           "details": "Column absent from dataset"})
            continue
        null_count  = df[col].isnull().sum()
        blank_count = df[col].astype(str).str.strip().eq("").sum()
        total_bad   = null_count + blank_count
        if total_bad > 0:
            issues.append({
                "check": "missing_value",
                "column": col,
                "affected_rows": int(total_bad),
                "details": f"{total_bad} null/blank values"
            })
    return issues


def check_duplicate_patients(df):
    if "patient_id" not in df.columns:
        return []
    dupes = df[df.duplicated("patient_id", keep=False)]
    if dupes.empty:
        return []
    ids = dupes["patient_id"].unique().tolist()
    return [{
        "check": "duplicate_patient_id",
        "column": "patient_id",
        "affected_rows": len(dupes),
        "details": f"Duplicate IDs: {ids}"
    }]


def check_date_logic(df):
    issues = []
    df = df.copy()
    for col in ["admission_date", "discharge_date", "date_of_birth", "visit_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    today = pd.Timestamp(datetime.today().date())

    if "discharge_date" in df.columns and "admission_date" in df.columns:
        bad_dates = df[
            df["discharge_date"].notna() & df["admission_date"].notna() &
            (df["discharge_date"] < df["admission_date"])
        ]
        if not bad_dates.empty:
            issues.append({
                "check": "invalid_date_range",
                "column": "discharge_date",
                "affected_rows": len(bad_dates),
                "details": "discharge_date is earlier than admission_date"
            })

    if "date_of_birth" in df.columns:
        future_dob = df[df["date_of_birth"] > today]
        if not future_dob.empty:
            issues.append({
                "check": "future_date",
                "column": "date_of_birth",
                "affected_rows": len(future_dob),
                "details": "date_of_birth is in the future"
            })
        bad_dob = df[df["date_of_birth"] > df["admission_date"]]
        if not bad_dob.empty:
            issues.append({
                "check": "dob_after_admission",
                "column": "date_of_birth",
                "affected_rows": len(bad_dob),
                "details": "date_of_birth is after admission_date"
            })
    return issues


def check_gender_values(df):
    if "gender" not in df.columns:
        return []
    invalid = df[~df["gender"].astype(str).str.strip().isin(VALID_GENDERS)]
    if invalid.empty:
        return []
    vals = invalid["gender"].unique().tolist()
    return [{
        "check": "invalid_gender",
        "column": "gender",
        "affected_rows": len(invalid),
        "details": f"Non-standard values: {vals}"
    }]


def check_diagnosis_codes(df):
    if "diagnosis_code" not in df.columns:
        return []
    codes = df["diagnosis_code"].fillna("").astype(str).str.strip()
    invalid_mask = ~codes.str.match(ICD10_PATTERN) | codes.eq("")
    if not invalid_mask.any():
        return []
    return [{
        "check": "invalid_diagnosis_code",
        "column": "diagnosis_code",
        "affected_rows": int(invalid_mask.sum()),
        "details": "Does not match ICD-10 format (e.g. E11.9, I10)"
    }]


def check_medication_dosage(df):
    issues = []
    for col in ["medication_name", "dosage"]:
        if col not in df.columns:
            continue
        empty = df[df[col].isnull() | df[col].astype(str).str.strip().eq("")]
        if not empty.empty:
            issues.append({
                "check": "incomplete_medication_record",
                "column": col,
                "affected_rows": len(empty),
                "details": f"{col} is missing Ã¢ÂÂ medication safety risk"
            })
    return issues


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ RUNNER Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def run_checks(df):
    all_issues = []
    all_issues += check_missing_fields(df)
    all_issues += check_duplicate_patients(df)
    all_issues += check_date_logic(df)
    all_issues += check_gender_values(df)
    all_issues += check_diagnosis_codes(df)
    all_issues += check_medication_dosage(df)
    return all_issues


def score_quality(df, issues):
    total_cells    = df.shape[0] * len(REQUIRED_COLUMNS)
    affected_cells = sum(i.get("affected_rows", 0) for i in issues)
    score = max(0, round(100 * (1 - affected_cells / max(total_cells, 1)), 1))
    return score


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ REPORT Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def print_report(df, issues, score):
    width = 72
    sep   = "Ã¢ÂÂ" * width

    print(f"\
{'Ã¢ÂÂ'*width}")
    print(f"  EHR DATA QUALITY REPORT".center(width))
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".center(width))
    print(f"{'Ã¢ÂÂ'*width}")

    print(f"\
  Dataset:  {df.shape[0]} rows ÃÂ {df.shape[1]} columns")
    print(f"  Issues:   {len(issues)} found")
    print(f"  Quality Score: {score}%")
    print(f"  Rating: {'Ã¢ÂÂ PASS' if score >= 90 else 'Ã¢ÂÂ Ã¯Â¸Â  WARNING' if score >= 70 else 'Ã¢ÂÂ FAIL'}")
    print(f"\
{sep}")

    if not issues:
        print("  Ã¢ÂÂ No data quality issues found. Dataset is clean.")
    else:
        print(f"  {'CHECK':<30} {'COLUMN':<22} {'ROWS':>5}  DETAILS")
        print(sep)
        for i in issues:
            check  = i.get("check", "")
            col    = i.get("column", "N/A")
            rows   = i.get("affected_rows", "N/A")
            detail = str(i.get("details", ""))[:35]
            print(f"  {check:<30} {col:<22} {str(rows):>5}  {detail}")

    print(f"\
{sep}\
")


def save_report(df, issues, score, path="ehr_quality_report.csv"):
    if issues:
        report_df = pd.DataFrame(issues)
        report_df["quality_score"] = score
        report_df["checked_at"]    = datetime.now().isoformat()
        report_df.to_csv(path, index=False)
        print(f"  Ã°ÂÂÂ Report saved Ã¢ÂÂ {path}")
    else:
        print("  Ã¢ÂÂ No issues to export.")


# Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂ CLI Ã¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂÃ¢ÂÂ

def main():
    parser = argparse.ArgumentParser(
        description="EHR Data Quality Checker Ã¢ÂÂ validates CSV EHR/EMR exports"
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to EHR CSV file. Omit to use built-in sample data.",
        default=None
    )
    parser.add_argument(
        "--output", "-o",
        help="Path for the CSV quality report (default: ehr_quality_report.csv)",
        default="ehr_quality_report.csv"
    )
    parser.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate and save a sample EHR CSV for testing"
    )
    args = parser.parse_args()

    if args.generate_sample:
        sample = generate_sample_data()
        sample.to_csv("sample_ehr_data.csv", index=False)
        print("Ã¢ÂÂ Sample EHR data saved Ã¢ÂÂ sample_ehr_data.csv")
        return

    if args.input:
        if not os.path.exists(args.input):
            print(f"Ã¢ÂÂ File not found: {args.input}")
            sys.exit(1)
        df = pd.read_csv(args.input)
        print(f"\
Ã°ÂÂÂ Loaded: {args.input}")
    else:
        print("\
Ã°ÂÂÂ¬ No input file specified. Running on built-in sample data...")
        df = generate_sample_data()

    issues = run_checks(df)
    score  = score_quality(df, issues)
    print_report(df, issues, score)
    save_report(df, issues, score, args.output)


if __name__ == "__main__":
    main()
