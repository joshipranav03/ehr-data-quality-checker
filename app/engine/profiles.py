"""EHR dataset profiles — the domain knowledge of the checker.

Each :class:`Profile` describes one logical table from a typical EHR/EDW
extract (patients, encounters, billing, ...) and the rules that govern it.
Profiles are plain data: adding support for a new table or tightening a rule
is a config change, not an engine change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .rules import (
    AllowedValues,
    BooleanType,
    Consistency,
    DateValid,
    ForeignKey,
    IntegerType,
    NotNull,
    NumericRange,
    Regex,
    Rule,
    Unique,
    ERROR,
    WARNING,
)

# ICD-10-CM: a letter, two alphanumerics, optional dotted extension.
ICD10_PATTERN = r"^[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$"
US_STATE_PATTERN = r"^[A-Z]{2}$"


@dataclass
class Profile:
    key: str
    title: str
    description: str
    id_column: str
    detect_columns: list[str]  # columns that must be present to auto-detect
    rules: list[Rule] = field(default_factory=list)
    parent_tables: list[str] = field(default_factory=list)

    def matches(self, columns) -> bool:
        cols = set(columns)
        return all(c in cols for c in self.detect_columns)

    def match_score(self, columns) -> float:
        cols = set(columns)
        if not self.matches(columns):
            return 0.0
        # Prefer the profile whose schema is closest to the file.
        known = set(self.detect_columns)
        return len(known & cols) / max(len(known | cols), 1)

    def describe_rules(self) -> list[dict]:
        return [
            {
                "rule_id": r.rule_id,
                "title": r.title,
                "category": r.category,
                "severity": r.severity,
                "column": r.column,
            }
            for r in self.rules
        ]


def _req(prefix, *columns, severity=ERROR):
    """Build NotNull rules for required columns."""
    return [
        NotNull(f"{prefix}.not_null.{c}", f"{c} is required", column=c, severity=severity)
        for c in columns
    ]


# ---------------------------------------------------------------------------
# departments
# ---------------------------------------------------------------------------
departments = Profile(
    key="departments",
    title="Departments",
    description="Clinical departments reference table.",
    id_column="department_id",
    detect_columns=["department_id", "department_name", "department_type", "floor"],
    rules=[
        *_req("departments", "department_id", "department_name", "department_type", "floor"),
        Unique("departments.unique.id", "department_id must be unique", "department_id"),
        IntegerType("departments.int.id", "department_id must be an integer", "department_id"),
        IntegerType("departments.int.floor", "floor must be an integer", "floor"),
        AllowedValues(
            "departments.enum.type", "department_type is recognised", "department_type",
            ["Inpatient", "Outpatient", "Emergency", "Surgical", "Diagnostic"],
            severity=WARNING,
        ),
    ],
)

# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------
providers = Profile(
    key="providers",
    title="Providers",
    description="Doctors and their department/specialty.",
    id_column="provider_id",
    detect_columns=["provider_id", "first_name", "last_name", "specialty", "department_id"],
    parent_tables=["departments"],
    rules=[
        *_req("providers", "provider_id", "first_name", "last_name", "specialty",
              "department_id", "hire_date"),
        Unique("providers.unique.id", "provider_id must be unique", "provider_id"),
        IntegerType("providers.int.id", "provider_id must be an integer", "provider_id"),
        IntegerType("providers.int.dept", "department_id must be an integer", "department_id"),
        DateValid("providers.date.hire", "hire_date is a valid past date", "hire_date",
                  not_future=True, min_date="1950-01-01"),
        ForeignKey("providers.fk.dept", "department_id links to a department",
                   "department_id", "departments", "department_id"),
    ],
)

# ---------------------------------------------------------------------------
# patients
# ---------------------------------------------------------------------------
patients = Profile(
    key="patients",
    title="Patients",
    description="Patient demographics, location, and insurance.",
    id_column="patient_id",
    detect_columns=["patient_id", "first_name", "last_name", "gender", "birth_date"],
    rules=[
        *_req("patients", "patient_id", "first_name", "last_name", "gender",
              "birth_date", "city", "state", "insurance_provider", "registration_date"),
        Unique("patients.unique.id", "patient_id must be unique", "patient_id"),
        IntegerType("patients.int.id", "patient_id must be an integer", "patient_id"),
        AllowedValues("patients.enum.gender", "gender is M or F", "gender", ["M", "F"]),
        Regex("patients.regex.state", "state is a 2-letter code", "state",
              US_STATE_PATTERN, severity=WARNING, hint="a 2-letter US state code"),
        DateValid("patients.date.birth", "birth_date is valid and not in the future",
                  "birth_date", not_future=True, min_date="1900-01-01"),
        DateValid("patients.date.registration", "registration_date is valid and not future",
                  "registration_date", not_future=True, min_date="1990-01-01"),
        Consistency(
            "patients.consistency.birth_before_registration",
            "birth_date must be on or before registration_date",
            failing_mask=lambda df: _dt(df, "birth_date") > _dt(df, "registration_date"),
            columns=["birth_date", "registration_date"],
        ),
        Consistency(
            "patients.consistency.plausible_age",
            "patient age must be under 120 years",
            failing_mask=lambda df: (
                (pd.Timestamp.today().normalize() - _dt(df, "birth_date")).dt.days > 120 * 365.25
            ),
            columns=["birth_date"],
            severity=WARNING,
        ),
    ],
)

# ---------------------------------------------------------------------------
# encounters
# ---------------------------------------------------------------------------
encounters = Profile(
    key="encounters",
    title="Encounters",
    description="Hospital visits — the central fact table.",
    id_column="encounter_id",
    detect_columns=["encounter_id", "patient_id", "provider_id", "admit_date", "discharge_date"],
    parent_tables=["patients", "providers", "departments"],
    rules=[
        *_req("encounters", "encounter_id", "patient_id", "provider_id", "department_id",
              "admit_date", "discharge_date", "admission_type", "discharge_disposition"),
        Unique("encounters.unique.id", "encounter_id must be unique", "encounter_id"),
        IntegerType("encounters.int.id", "encounter_id must be an integer", "encounter_id"),
        DateValid("encounters.date.admit", "admit_date is a valid date", "admit_date"),
        DateValid("encounters.date.discharge", "discharge_date is a valid date", "discharge_date"),
        AllowedValues("encounters.enum.admission", "admission_type is recognised",
                      "admission_type", ["Emergency", "Elective", "Urgent", "Newborn"]),
        AllowedValues(
            "encounters.enum.disposition", "discharge_disposition is recognised",
            "discharge_disposition",
            ["Home", "Home Health Care", "Skilled Nursing Facility", "Rehabilitation",
             "Transferred", "Left Against Medical Advice", "Expired"],
            severity=WARNING,
        ),
        Consistency(
            "encounters.consistency.discharge_after_admit",
            "discharge_date must be on or after admit_date",
            failing_mask=lambda df: _dt(df, "discharge_date") < _dt(df, "admit_date"),
            columns=["admit_date", "discharge_date"],
        ),
        Consistency(
            "encounters.consistency.los_plausible",
            "length of stay must be 365 days or fewer",
            failing_mask=lambda df: (
                (_dt(df, "discharge_date") - _dt(df, "admit_date")).dt.days > 365
            ),
            columns=["admit_date", "discharge_date"],
            severity=WARNING,
        ),
        ForeignKey("encounters.fk.patient", "patient_id links to a patient",
                   "patient_id", "patients", "patient_id"),
        ForeignKey("encounters.fk.provider", "provider_id links to a provider",
                   "provider_id", "providers", "provider_id"),
        ForeignKey("encounters.fk.dept", "department_id links to a department",
                   "department_id", "departments", "department_id"),
    ],
)

# ---------------------------------------------------------------------------
# diagnoses
# ---------------------------------------------------------------------------
diagnoses = Profile(
    key="diagnoses",
    title="Diagnoses",
    description="ICD-10 coded diagnoses, one or more per encounter.",
    id_column="diagnosis_id",
    detect_columns=["diagnosis_id", "encounter_id", "icd10_code", "is_primary"],
    parent_tables=["encounters"],
    rules=[
        *_req("diagnoses", "diagnosis_id", "encounter_id", "icd10_code",
              "diagnosis_description", "is_primary"),
        Unique("diagnoses.unique.id", "diagnosis_id must be unique", "diagnosis_id"),
        IntegerType("diagnoses.int.id", "diagnosis_id must be an integer", "diagnosis_id"),
        Regex("diagnoses.regex.icd10", "icd10_code is a valid ICD-10 code", "icd10_code",
              ICD10_PATTERN, hint="an ICD-10-CM code such as 'S72.0' or 'E11.9'"),
        BooleanType("diagnoses.bool.primary", "is_primary is a boolean", "is_primary"),
        ForeignKey("diagnoses.fk.encounter", "encounter_id links to an encounter",
                   "encounter_id", "encounters", "encounter_id"),
        Consistency(
            "diagnoses.consistency.one_primary",
            "each encounter must have exactly one primary diagnosis",
            failing_mask=lambda df: _one_primary_violation(df),
            columns=["encounter_id", "is_primary"],
            severity=WARNING,
        ),
    ],
)

# ---------------------------------------------------------------------------
# procedures
# ---------------------------------------------------------------------------
procedures = Profile(
    key="procedures",
    title="Procedures",
    description="Procedures performed during an encounter.",
    id_column="procedure_id",
    detect_columns=["procedure_id", "encounter_id", "procedure_name", "procedure_date"],
    parent_tables=["encounters"],
    rules=[
        *_req("procedures", "procedure_id", "encounter_id", "procedure_name", "procedure_date"),
        Unique("procedures.unique.id", "procedure_id must be unique", "procedure_id"),
        IntegerType("procedures.int.id", "procedure_id must be an integer", "procedure_id"),
        DateValid("procedures.date.performed", "procedure_date is a valid date",
                  "procedure_date"),
        ForeignKey("procedures.fk.encounter", "encounter_id links to an encounter",
                   "encounter_id", "encounters", "encounter_id"),
    ],
)

# ---------------------------------------------------------------------------
# prescriptions
# ---------------------------------------------------------------------------
prescriptions = Profile(
    key="prescriptions",
    title="Prescriptions",
    description="Medications prescribed during an encounter.",
    id_column="prescription_id",
    detect_columns=["prescription_id", "encounter_id", "medication_name", "route"],
    parent_tables=["encounters"],
    rules=[
        *_req("prescriptions", "prescription_id", "encounter_id", "medication_name", "route"),
        Unique("prescriptions.unique.id", "prescription_id must be unique", "prescription_id"),
        IntegerType("prescriptions.int.id", "prescription_id must be an integer",
                    "prescription_id"),
        AllowedValues("prescriptions.enum.route", "route is recognised", "route",
                      ["Oral", "Injection", "Inhalation", "IV", "IM", "Topical",
                       "Subcutaneous"], severity=WARNING),
        ForeignKey("prescriptions.fk.encounter", "encounter_id links to an encounter",
                   "encounter_id", "encounters", "encounter_id"),
    ],
)

# ---------------------------------------------------------------------------
# billing
# ---------------------------------------------------------------------------
billing = Profile(
    key="billing",
    title="Billing",
    description="Charges, payments, and payment status per encounter.",
    id_column="encounter_id",
    detect_columns=["encounter_id", "total_charge", "insurance_paid", "patient_paid",
                    "payment_status"],
    parent_tables=["encounters"],
    rules=[
        *_req("billing", "encounter_id", "total_charge", "insurance_paid", "patient_paid",
              "payment_status"),
        Unique("billing.unique.id", "encounter_id must be unique (one bill per encounter)",
               "encounter_id"),
        NumericRange("billing.num.total", "total_charge must be >= 0", "total_charge",
                     min_value=0),
        NumericRange("billing.num.insurance", "insurance_paid must be >= 0", "insurance_paid",
                     min_value=0),
        NumericRange("billing.num.patient", "patient_paid must be >= 0", "patient_paid",
                     min_value=0),
        AllowedValues("billing.enum.status", "payment_status is recognised", "payment_status",
                      ["Paid", "Partially Paid", "Pending", "Written Off"]),
        Consistency(
            "billing.consistency.not_overpaid",
            "payments must not exceed the total charge",
            failing_mask=lambda df: (
                _num(df, "insurance_paid") + _num(df, "patient_paid")
                > _num(df, "total_charge") + 0.01
            ),
            columns=["total_charge", "insurance_paid", "patient_paid"],
            severity=WARNING,
        ),
        ForeignKey("billing.fk.encounter", "encounter_id links to an encounter",
                   "encounter_id", "encounters", "encounter_id"),
    ],
)


# ---------------------------------------------------------------------------
# Helpers used by the lambda-based consistency rules
# ---------------------------------------------------------------------------
def _dt(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_datetime(df[col], errors="coerce")


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce")


def _one_primary_violation(df: pd.DataFrame) -> pd.Series:
    """True for rows whose encounter does not have exactly one primary diagnosis."""
    primary = df["is_primary"].astype("string").str.lower().isin({"true", "1", "t", "yes"})
    counts = primary.groupby(df["encounter_id"]).transform("sum")
    return counts != 1


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
PROFILES: dict[str, Profile] = {
    p.key: p
    for p in [
        departments,
        providers,
        patients,
        encounters,
        diagnoses,
        procedures,
        prescriptions,
        billing,
    ]
}


def get_profile(key: str) -> Optional[Profile]:
    return PROFILES.get(key)


def detect_profile(columns) -> Optional[Profile]:
    """Pick the profile whose schema best matches the given columns."""
    best, best_score = None, 0.0
    for profile in PROFILES.values():
        score = profile.match_score(columns)
        if score > best_score:
            best, best_score = profile, score
    return best
