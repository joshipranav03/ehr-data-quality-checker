"""API/integration tests using FastAPI's TestClient."""

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["profiles"] == 8


def test_profiles_listing():
    res = client.get("/api/profiles")
    assert res.status_code == 200
    keys = {p["key"] for p in res.json()}
    assert {"patients", "encounters", "billing", "diagnoses"} <= keys


def test_samples_listing():
    res = client.get("/api/samples")
    assert res.status_code == 200
    body = res.json()
    assert "patients" in body["datasets"]
    assert "dirty" in body["samples"]


def test_index_served():
    res = client.get("/")
    assert res.status_code == 200
    assert "EHR Data Quality Checker" in res.text


def test_upload_csv_autodetect():
    csv = (
        "patient_id,first_name,last_name,gender,birth_date,city,state,"
        "insurance_provider,registration_date\n"
        "1,Ada,Lovelace,F,1990-01-01,Boston,MA,Aetna,2020-01-01\n"
        "2,Alan,Turing,X,1995-02-02,Boston,MA,Aetna,2020-01-01\n"  # bad gender
    )
    res = client.post(
        "/api/check",
        files={"file": ("patients.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["dataset"] == "patients"
    assert body["auto_detected"] is True
    gender = [r for r in body["results"] if r["rule_id"] == "patients.enum.gender"][0]
    assert gender["failed"] == 1


def test_upload_explicit_dataset():
    csv = "encounter_id,total_charge,insurance_paid,patient_paid,payment_status\n1,100,60,40,Paid\n"
    res = client.post(
        "/api/check?dataset=billing",
        files={"file": ("b.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert res.status_code == 200
    assert res.json()["dataset"] == "billing"


def test_upload_unknown_dataset_returns_400():
    csv = "a,b\n1,2\n"
    res = client.post(
        "/api/check?dataset=nope",
        files={"file": ("x.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert res.status_code == 400
    assert "Unknown dataset" in res.json()["detail"]


def test_upload_unrecognised_columns_returns_400():
    csv = "alpha,beta,gamma\n1,2,3\n"
    res = client.post(
        "/api/check",
        files={"file": ("x.csv", io.BytesIO(csv.encode()), "text/csv")},
    )
    assert res.status_code == 400
    assert "recognise" in res.json()["detail"].lower()


def test_check_sample_endpoint():
    res = client.post("/api/check/sample?name=patients&variant=dirty")
    assert res.status_code == 200
    body = res.json()
    assert body["variant"] == "dirty"
    assert body["summary"]["errors"] > 0


def test_audit_endpoint():
    res = client.get("/api/audit?variant=dirty")
    assert res.status_code == 200
    body = res.json()
    assert body["aggregate"]["tables"] == 8
    assert body["aggregate"]["errors"] > 0
    # FK integrity actually runs in a full audit
    enc = [t for t in body["tables"] if t["dataset"] == "encounters"][0]
    assert enc["dimensions"]["integrity"]["rules"] > 0
    assert enc["dimensions"]["integrity"]["checked"] > 0


def test_openapi_schema_available():
    res = client.get("/openapi.json")
    assert res.status_code == 200
    assert "/api/check" in res.json()["paths"]


# ------------------------------------------------------------------ interop
def _fhir_bundle_bytes():
    bundle = {
        "resourceType": "Bundle", "type": "transaction",
        "entry": [
            {"fullUrl": "urn:uuid:p1", "resource": {
                "resourceType": "Patient", "id": "p1", "gender": "male",
                "birthDate": "1980-01-01",
                "name": [{"use": "official", "given": ["Joe"], "family": "Doe"}]}},
            {"fullUrl": "urn:uuid:e1", "resource": {
                "resourceType": "Encounter", "id": "e1",
                "subject": {"reference": "urn:uuid:p1"}, "class": {"code": "EMER"},
                "period": {"start": "2024-02-01T08:00:00Z", "end": "2024-02-02T08:00:00Z"}}},
        ],
    }
    return json.dumps(bundle).encode()


def test_check_fhir_endpoint():
    res = client.post(
        "/api/check/fhir",
        files={"file": ("bundle.json", io.BytesIO(_fhir_bundle_bytes()), "application/json")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "fhir"
    assert "patients" in body["recognised"]


def test_check_fhir_rejects_bad_json():
    res = client.post(
        "/api/check/fhir",
        files={"file": ("x.json", io.BytesIO(b"not json"), "application/json")},
    )
    assert res.status_code == 400


def test_interop_enforces_upload_size_limit(monkeypatch):
    from app import config
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)  # tiny cap for the test
    big = io.BytesIO(b'{"resourceType":"Bundle","entry":[]}' + b" " * 200)
    res = client.post(
        "/api/check/fhir",
        files={"file": ("big.json", big, "application/json")},
    )
    assert res.status_code == 400
    assert "too large" in res.json()["detail"].lower()


def test_check_hl7_endpoint():
    msg = (
        "MSH|^~\\&|H|H|E|D|20240201||ADT^A01|1|P|2.5\r"
        "PID|1||2001^^^H^MR||Roe^Jane||19750304|F|||St^^Boston^MA^02118\r"
        "PV1|1|I|2W||||9001^Dr^A|||||||||||E|||||||||||||||||||||"
        "|||||20240201080000|20240203080000"
    )
    res = client.post(
        "/api/check/hl7",
        files={"file": ("adt.hl7", io.BytesIO(msg.encode()), "text/plain")},
    )
    assert res.status_code == 200
    assert res.json()["source"] == "hl7v2"


# ------------------------------------------------------------------ history
def test_history_records_after_a_check():
    client.post("/api/check/sample?name=patients&variant=dirty")
    res = client.get("/api/history?dataset=patients")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert len(body["records"]) >= 1
    assert body["records"][0]["dataset"] == "patients"


def test_trends_endpoint():
    client.post("/api/check/sample?name=billing&variant=clean")
    res = client.get("/api/history/trends?dataset=billing")
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is True
    assert body["count"] >= 1
    assert "score" in body["points"][0]
