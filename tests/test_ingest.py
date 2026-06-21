"""Tests for FHIR and HL7 v2 ingestion."""

import json
import os

import pytest

from app.ingest.fhir import ingest_fhir_bundle, FhirIngestError
from app.ingest.hl7v2 import ingest_hl7v2, Hl7IngestError

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_data")


# --------------------------------------------------------------------- FHIR
def _bundle(*resources):
    return {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"fullUrl": f"urn:uuid:{r['id']}", "resource": r} for r in resources
        ],
    }


def test_fhir_maps_patient_and_resolves_references():
    bundle = _bundle(
        {"resourceType": "Patient", "id": "pA", "gender": "female",
         "birthDate": "1990-05-01",
         "name": [{"use": "official", "given": ["Jane"], "family": "Doe"}],
         "address": [{"city": "Boston", "state": "MA"}]},
        {"resourceType": "Encounter", "id": "eA",
         "subject": {"reference": "urn:uuid:pA"},
         "class": {"code": "EMER"},
         "period": {"start": "2024-01-02T10:00:00Z", "end": "2024-01-03T10:00:00Z"}},
    )
    tables = ingest_fhir_bundle(bundle)
    assert "patients" in tables and "encounters" in tables
    pat = tables["patients"].iloc[0]
    assert pat["gender"] == "F"               # mapped from 'female'
    assert pat["birth_date"] == "1990-05-01"
    # surrogate integer keys, and the FK resolves to the same id
    enc = tables["encounters"].iloc[0]
    assert pat["patient_id"].isdigit()
    assert enc["patient_id"] == pat["patient_id"]   # reference resolved + remapped
    assert enc["admission_type"] == "Emergency"     # EMER -> Emergency


def test_fhir_prefers_icd10_over_snomed():
    bundle = _bundle(
        {"resourceType": "Condition", "id": "c1",
         "encounter": {"reference": "urn:uuid:e1"},
         "code": {"coding": [
             {"system": "http://snomed.info/sct", "code": "44054006", "display": "Diabetes"},
             {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9", "display": "Diabetes"},
         ]}},
    )
    dx = ingest_fhir_bundle(bundle)["diagnoses"].iloc[0]
    assert dx["icd10_code"] == "E11.9"


def test_fhir_falls_back_to_snomed_when_no_icd10():
    bundle = _bundle(
        {"resourceType": "Condition", "id": "c2",
         "encounter": {"reference": "urn:uuid:e1"},
         "code": {"coding": [
             {"system": "http://snomed.info/sct", "code": "230690007", "display": "Stroke"},
         ]}},
    )
    dx = ingest_fhir_bundle(bundle)["diagnoses"].iloc[0]
    assert dx["icd10_code"] == "230690007"   # surfaced so the ICD-10 check flags it


def test_fhir_derives_single_primary_per_encounter():
    bundle = _bundle(
        {"resourceType": "Condition", "id": "c1", "recordedDate": "2024-01-01",
         "encounter": {"reference": "urn:uuid:e1"},
         "category": [{"coding": [{"code": "encounter-diagnosis"}]}],
         "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9"}]}},
        {"resourceType": "Condition", "id": "c2", "recordedDate": "2024-01-02",
         "encounter": {"reference": "urn:uuid:e1"},
         "category": [{"coding": [{"code": "encounter-diagnosis"}]}],
         "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I10"}]}},
    )
    dx = ingest_fhir_bundle(bundle)["diagnoses"]
    primaries = dx[dx["is_primary"] == "True"]
    assert len(primaries) == 1   # exactly one primary for the encounter


def test_fhir_rejects_non_bundle():
    with pytest.raises(FhirIngestError):
        ingest_fhir_bundle({"resourceType": "Patient", "id": "x"})


def test_fhir_survives_null_payment_amount():
    # A denied/unpaid claim can have payment.amount = null; must not crash.
    bundle = _bundle(
        {"resourceType": "ExplanationOfBenefit", "id": "eob1",
         "patient": {"reference": "urn:uuid:p1"},
         "item": [{"encounter": [{"reference": "urn:uuid:e1"}]}],
         "payment": {"amount": None}},
    )
    tables = ingest_fhir_bundle(bundle)        # no exception
    assert "billing" in tables


@pytest.mark.parametrize("bad_name", ["oops", ["oops"], [123], None])
def test_fhir_survives_malformed_patient_name(bad_name):
    bundle = _bundle({"resourceType": "Patient", "id": "p1", "gender": "male",
                      "name": bad_name})
    tables = ingest_fhir_bundle(bundle)        # no exception
    assert len(tables["patients"]) == 1


def test_fhir_resolves_contained_medication():
    bundle = _bundle({
        "resourceType": "MedicationRequest", "id": "m1",
        "encounter": {"reference": "urn:uuid:e1"},
        "medicationReference": {"reference": "#med1"},
        "contained": [{"resourceType": "Medication", "id": "med1",
                       "code": {"text": "Amoxicillin 500mg"}}],
    })
    rx = ingest_fhir_bundle(bundle)["prescriptions"].iloc[0]
    assert rx["medication_name"] == "Amoxicillin 500mg"


def test_fhir_sample_file_ingests_and_has_defects():
    path = os.path.join(SAMPLE_DIR, "fhir", "sample_bundle.json")
    if not os.path.exists(path):
        pytest.skip("sample bundle not generated")
    tables = ingest_fhir_bundle(json.load(open(path)))
    assert set(tables) >= {"patients", "encounters", "diagnoses", "billing"}
    # the injected 'unknown' gender survives mapping (so the checker can flag it)
    assert (tables["patients"]["gender"] == "unknown").any()


# --------------------------------------------------------------------- HL7 v2
def test_hl7_parses_pid_and_pv1():
    msg = (
        "MSH|^~\\&|HIS|HOSP|EHR|D|20240310||ADT^A01|1|P|2.5\r"
        "PID|1||1001^^^H^MR||Doe^Jane||19900501|F|||123 St^^Boston^MA^02118\r"
        "PV1|1|I|2W^201^A||||9001^House^Greg|||||||||||E|||||||||||||||||||||"
        "|||||20240310090000|20240312110000"
    )
    tables = ingest_hl7v2(msg)
    assert "patients" in tables and "encounters" in tables
    pat = tables["patients"].iloc[0]
    assert pat["patient_id"] == "1001"
    assert pat["gender"] == "F"
    assert pat["birth_date"] == "1990-05-01"
    enc = tables["encounters"].iloc[0]
    assert enc["patient_id"] == "1001"
    assert enc["admit_date"] == "2024-03-10"
    assert enc["discharge_date"] == "2024-03-12"


def test_hl7_rejects_garbage():
    with pytest.raises(Hl7IngestError):
        ingest_hl7v2("this is not an HL7 message")


def test_hl7_sample_file_ingests():
    path = os.path.join(SAMPLE_DIR, "hl7", "sample_adt.hl7")
    if not os.path.exists(path):
        pytest.skip("sample HL7 not generated")
    tables = ingest_hl7v2(open(path).read())
    assert len(tables["patients"]) == 2
    assert len(tables["encounters"]) == 2
