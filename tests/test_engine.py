"""Unit tests for the rule engine and dataset profiles."""

import pandas as pd
import pytest

from app.engine import rules
from app.engine.checker import DataQualityChecker
from app.engine.profiles import detect_profile, get_profile


def df(**cols):
    return pd.DataFrame(cols)


# --------------------------------------------------------------------- rules
def test_not_null_flags_blank_and_missing():
    data = df(x=["a", "", None, "b"])
    r = rules.NotNull("t", "x required", column="x").evaluate(data)
    assert r.failed == 2
    assert r.checked == 4
    assert not r.passed


def test_not_null_skips_when_column_absent():
    r = rules.NotNull("t", "x required", column="missing").evaluate(df(x=[1]))
    assert r.skipped
    assert "not present" in r.skip_reason


def test_unique_detects_duplicates():
    data = df(id=["1", "2", "2", "3", "3"])
    r = rules.Unique("t", "unique id", "id").evaluate(data)
    # 2 and 3 each appear twice -> 4 offending rows
    assert r.failed == 4
    assert not r.passed


def test_unique_ignores_missing_keys():
    data = df(id=["1", "", "", "2"])
    r = rules.Unique("t", "unique id", "id").evaluate(data)
    # blanks are not counted as duplicate key collisions
    assert r.failed == 0
    assert r.checked == 2


def test_allowed_values():
    data = df(gender=["M", "F", "X", None, "m"])
    r = rules.AllowedValues("t", "gender", "gender", ["M", "F"]).evaluate(data)
    assert r.failed == 2  # "X" and "m" (case sensitive); None is ignored
    assert r.checked == 4


def test_allowed_values_case_insensitive():
    data = df(route=["Oral", "oral", "ORAL", "iv"])
    r = rules.AllowedValues("t", "route", "route", ["oral"], case_sensitive=False).evaluate(data)
    assert r.failed == 1  # only "iv"


def test_regex_icd10():
    from app.engine.profiles import ICD10_PATTERN
    data = df(code=["E11.9", "S72.0", "12345", "ABC", ""])
    r = rules.Regex("t", "icd10", "code", ICD10_PATTERN).evaluate(data)
    assert r.failed == 2  # 12345 and ABC; blank is ignored (completeness covers it)


def test_integer_type():
    data = df(n=["1", "2", "3.5", "abc", None])
    r = rules.IntegerType("t", "int", "n").evaluate(data)
    assert r.failed == 2  # "3.5" and "abc"


def test_numeric_range_rejects_negative_and_nonnumeric():
    data = df(amt=["10", "-5", "0", "N/A"])
    r = rules.NumericRange("t", "amt", "amt", min_value=0).evaluate(data)
    assert r.failed == 2  # "-5" and "N/A"


def test_date_valid_rejects_bad_and_future():
    data = df(d=["2020-01-01", "2023-13-40", "2999-01-01", None])
    r = rules.DateValid("t", "d", "d", not_future=True).evaluate(data)
    assert r.failed == 2  # malformed + future


def test_consistency_cross_field():
    data = df(a=["2020-01-01", "2020-05-01"], b=["2020-02-01", "2020-04-01"])
    rule = rules.Consistency(
        "t", "a before b",
        failing_mask=lambda d: pd.to_datetime(d["a"]) > pd.to_datetime(d["b"]),
        columns=["a", "b"],
    )
    r = rule.evaluate(data)
    assert r.failed == 1  # second row: a is after b


def test_foreign_key_skips_without_parent():
    data = df(patient_id=["1", "2"])
    r = rules.ForeignKey("t", "fk", "patient_id", "patients", "patient_id").evaluate(data)
    assert r.skipped


def test_foreign_key_detects_dangling():
    data = df(patient_id=["1", "2", "999"])
    parents = df(patient_id=["1", "2", "3"])
    r = rules.ForeignKey("t", "fk", "patient_id", "patients", "patient_id").evaluate(
        data, context={"patients": parents}
    )
    assert r.failed == 1  # 999 has no parent


def test_sample_includes_csv_line_number():
    data = df(x=["a", None])
    r = rules.NotNull("t", "x", column="x").evaluate(data)
    assert r.sample[0]["_line"] == 3  # row index 1 -> CSV line 3 (header + 1-based)


# ------------------------------------------------------------------ profiles
def test_profile_detection_by_columns():
    cols = ["patient_id", "first_name", "last_name", "gender", "birth_date",
            "city", "state", "insurance_provider", "registration_date"]
    profile = detect_profile(cols)
    assert profile is not None
    assert profile.key == "patients"


def test_detection_returns_none_for_unknown():
    assert detect_profile(["foo", "bar", "baz"]) is None


def test_clean_patients_scores_well():
    data = pd.read_csv("sample_data/clean/patients.csv", dtype=str)
    report = DataQualityChecker(get_profile("patients")).run(data).to_dict()
    # Clean data has a few genuine birth/registration inconsistencies but no
    # completeness/validity/uniqueness errors.
    assert report["dimensions"]["completeness"]["failed"] == 0
    assert report["dimensions"]["uniqueness"]["failed"] == 0
    assert report["summary"]["score"] >= 99.0


def test_dirty_patients_finds_injected_defects():
    data = pd.read_csv("sample_data/dirty/patients.csv", dtype=str)
    report = DataQualityChecker(get_profile("patients")).run(data).to_dict()
    s = report["summary"]
    assert s["errors"] > 0
    # specific injected defects
    ids = {r["rule_id"]: r for r in report["results"]}
    assert ids["patients.enum.gender"]["failed"] >= 2
    assert ids["patients.unique.id"]["failed"] >= 2
    assert not ids["patients.enum.gender"]["status"] == "passed"


def test_score_floors_below_100_when_issues_exist():
    # A dataset with a single bad cell should never display a perfect 100.
    data = df(
        patient_id=[str(i) for i in range(1000)],
    )
    data.loc[0, "patient_id"] = "1"  # duplicate of index 1
    report = DataQualityChecker(get_profile("patients")).run(data).to_dict()
    assert report["summary"]["score"] < 100.0


def test_referential_integrity_runs_with_context():
    enc = pd.read_csv("sample_data/dirty/encounters.csv", dtype=str)
    patients = pd.read_csv("sample_data/dirty/patients.csv", dtype=str)
    providers = pd.read_csv("sample_data/dirty/providers.csv", dtype=str)
    departments = pd.read_csv("sample_data/dirty/departments.csv", dtype=str)
    ctx = {"patients": patients, "providers": providers, "departments": departments}
    report = DataQualityChecker(get_profile("encounters")).run(enc, context=ctx).to_dict()
    fk = [r for r in report["results"] if r["rule_id"] == "encounters.fk.patient"][0]
    assert fk["status"] != "skipped"
    assert fk["failed"] >= 1  # injected dangling patient_id
