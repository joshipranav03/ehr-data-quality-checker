"""Derive an intentionally *dirty* copy of the clean EHR sample data.

This injects a realistic spread of data-quality defects — missing values,
bad enums, malformed codes, duplicate keys, broken cross-field logic, and
dangling foreign keys — so the checker has something to find in demos and
tests. The corruption is deterministic (fixed seed) so output is stable.

Usage:
    python sample_data/make_dirty.py
"""

from __future__ import annotations

import os
import random

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CLEAN = os.path.join(HERE, "clean")
DIRTY = os.path.join(HERE, "dirty")

SEED = 7


def _load(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(CLEAN, name), dtype=str)


def _save(df: pd.DataFrame, name: str) -> None:
    df.to_csv(os.path.join(DIRTY, name), index=False)


def corrupt_patients(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Missing required values
    df.loc[3, "birth_date"] = ""
    df.loc[11, "state"] = ""
    df.loc[27, "insurance_provider"] = ""
    # Invalid gender
    df.loc[5, "gender"] = "X"
    df.loc[18, "gender"] = "Male"
    # Malformed state code
    df.loc[8, "state"] = "Massachusetts"
    # Future birth date + impossible age
    df.loc[14, "birth_date"] = "2099-01-01"
    df.loc[20, "birth_date"] = "1820-05-05"
    # Born after registration (consistency)
    df.loc[2, "birth_date"] = "2025-01-01"
    df.loc[2, "registration_date"] = "2024-06-01"
    # Duplicate primary key
    df.loc[9, "patient_id"] = df.loc[0, "patient_id"]
    return df


def corrupt_encounters(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # discharge before admit
    df.loc[1, "discharge_date"] = "2023-05-10"  # admit is later
    df.loc[1, "admit_date"] = "2023-05-22"
    # invalid admission type
    df.loc[4, "admission_type"] = "Walk-in"
    # missing department
    df.loc[6, "department_id"] = ""
    # dangling patient FK
    df.loc[10, "patient_id"] = "999999"
    # absurd length of stay (> 1 year)
    df.loc[15, "admit_date"] = "2023-01-01"
    df.loc[15, "discharge_date"] = "2024-12-31"
    # duplicate encounter id
    df.loc[20, "encounter_id"] = df.loc[0, "encounter_id"]
    # bad date
    df.loc[8, "admit_date"] = "2023-13-40"
    return df


def corrupt_diagnoses(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # malformed ICD-10 codes
    df.loc[2, "icd10_code"] = "12345"
    df.loc[7, "icd10_code"] = "ABC"
    df.loc[19, "icd10_code"] = ""  # missing
    # bad boolean
    df.loc[5, "is_primary"] = "maybe"
    # dangling encounter FK
    df.loc[12, "encounter_id"] = "888888"
    return df


def corrupt_billing(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # negative charge
    df.loc[3, "total_charge"] = "-500.00"
    # overpaid (payments exceed charge)
    df.loc[6, "insurance_paid"] = "99999.00"
    # invalid status
    df.loc[9, "payment_status"] = "Refunded"
    # non-numeric amount
    df.loc[14, "patient_paid"] = "N/A"
    # missing required
    df.loc[2, "payment_status"] = ""
    return df


def corrupt_providers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc[1, "hire_date"] = "2099-01-01"  # future
    df.loc[3, "department_id"] = "404"      # dangling FK
    df.loc[5, "specialty"] = ""             # missing
    return df


def corrupt_procedures(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc[4, "procedure_date"] = "not-a-date"
    df.loc[9, "encounter_id"] = "777777"  # dangling FK
    return df


def corrupt_prescriptions(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.loc[2, "route"] = "Telepathy"  # invalid route
    df.loc[8, "medication_name"] = ""  # missing
    return df


def main() -> None:
    random.seed(SEED)
    os.makedirs(DIRTY, exist_ok=True)

    pipeline = {
        "patients.csv": corrupt_patients,
        "encounters.csv": corrupt_encounters,
        "diagnoses.csv": corrupt_diagnoses,
        "billing.csv": corrupt_billing,
        "providers.csv": corrupt_providers,
        "procedures.csv": corrupt_procedures,
        "prescriptions.csv": corrupt_prescriptions,
        "departments.csv": lambda d: d,  # leave reference table clean
    }

    for name, fn in pipeline.items():
        df = _load(name)
        _save(fn(df), name)
        print(f"wrote dirty/{name} ({len(df)} rows)")


if __name__ == "__main__":
    main()
