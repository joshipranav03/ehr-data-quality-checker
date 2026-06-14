"""
Unit tests for EHR Data Quality Checker
Run: pytest tests/
"""

import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ehr_checker import (
    generate_sample_data,
    check_missing_fields,
    check_duplicate_patients,
    check_date_logic,
    check_gender_values,
    check_diagnosis_codes,
    check_medication_dosage,
    score_quality,
)


@pytest.fixture
def clean_df():
    return pd.DataFrame([{
        "patient_id":     "P001",
        "first_name":     "Mary",
        "last_name":      "Smith",
        "date_of_birth":  "1945-03-12",
        "gender":         "F",
        "admission_date": "2024-01-10",
        "discharge_date": "2024-01-20",
        "diagnosis_code": "E11.9",
        "medication_name": "Metformin 500mg",
        "dosage":         "500mg",
        "caregiver_id":   "CG001",
        "visit_date":     "2024-01-11",
    }])


def test_clean_record_passes(clean_df):
    from ehr_checker import run_checks
    issues = run_checks(clean_df)
    assert issues == [], f"Clean record should have no issues, got: {issues}"


def test_duplicate_patient_ids():
    df = pd.DataFrame([
        {"patient_id": "P001", **{c: "x" for c in ["first_name","last_name","gender",
          "admission_date","discharge_date","diagnosis_code","medication_name",
          "dosage","caregiver_id","visit_date","date_of_birth"]}},
        {"patient_id": "P001", **{c: "x" for c in ["first_name","last_name","gender",
          "admission_date","discharge_date","diagnosis_code","medication_name",
          "dosage","caregiver_id","visit_date","date_of_birth"]}},
    ])
    issues = check_duplicate_patients(df)
    assert any(i["check"] == "duplicate_patient_id" for i in issues)


def test_discharge_before_admission():
    df = pd.DataFrame([{
        "patient_id":     "P002",
        "admission_date": "2024-05-10",
        "discharge_date": "2024-05-01",
        "date_of_birth":  "1960-01-01",
        "visit_date":     "2024-05-11",
    }])
    issues = check_date_logic(df)
    checks = [i["check"] for i in issues]
    assert "invalid_date_range" in checks


def test_invalid_gender():
    df = pd.DataFrame([{"gender": "Z"}, {"gender": "N/A"}])
    issues = check_gender_values(df)
    assert any(i["check"] == "invalid_gender" for i in issues)


def test_invalid_icd10_code():
    df = pd.DataFrame([
        {"diagnosis_code": "999"},
        {"diagnosis_code": "ABCD"},
        {"diagnosis_code": "E11.9"},
    ])
    issues = check_diagnosis_codes(df)
    assert any(i["check"] == "invalid_diagnosis_code" for i in issues)


def test_valid_icd10_passes():
    df = pd.DataFrame([{"diagnosis_code": "I10"}])
    issues = check_diagnosis_codes(df)
    assert issues == []


def test_missing_medication():
    df = pd.DataFrame([{"medication_name": None, "dosage": "500mg"}])
    issues = check_medication_dosage(df)
    assert any(i["check"] == "incomplete_medication_record" for i in issues)


def test_quality_score_perfect(clean_df):
    issues = []
    score = score_quality(clean_df, issues)
    assert score == 100.0


def test_sample_data_generates():
    df = generate_sample_data(10)
    assert len(df) == 10
    assert "patient_id" in df.columns
