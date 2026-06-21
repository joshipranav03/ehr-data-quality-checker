"""Generate a small, Synthea-shaped FHIR R4 transaction Bundle for demos/tests.

Hand-built (deterministic UUIDs) to resemble real Synthea output — urn:uuid
references, SNOMED+ICD-10 codings, a Claim/EOB pair — with a few intentional
data-quality defects injected so the checker has something to find:

  * patient p2 has gender "unknown" (won't map to M/F)
  * patient p3 is missing birthDate
  * encounter e2 is discharged before it was admitted
  * condition c3 has only a SNOMED code (no ICD-10 mapping)
  * EOB for e2 records payments that exceed the charge

Usage:  python sample_data/fhir/make_fhir_sample.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_bundle.json")

# Fixed UUIDs (kept stable so output is reproducible)
P1, P2, P3 = "patient-0001", "patient-0002", "patient-0003"
E1, E2, E3 = "enc-0001", "enc-0002", "enc-0003"
ORG, PRACT = "org-0001", "pract-0001"


def urn(i):
    return f"urn:uuid:{i}"


def ref(i, display=None):
    r = {"reference": urn(i)}
    if display:
        r["display"] = display
    return r


def entry(resource):
    return {
        "fullUrl": urn(resource["id"]),
        "resource": resource,
        "request": {"method": "POST", "url": resource["resourceType"]},
    }


def patient(pid, given, family, gender, birth, state, *, no_birth=False):
    res = {
        "resourceType": "Patient",
        "id": pid,
        "meta": {"lastUpdated": "2024-01-15T10:00:00-05:00"},
        "name": [{"use": "official", "given": [given], "family": family}],
        "gender": gender,
        "address": [{"city": "Boston", "state": state, "postalCode": "02118"}],
    }
    if not no_birth:
        res["birthDate"] = birth
    return res


def encounter(eid, pid, cls, start, end, disposition="Home"):
    res = {
        "resourceType": "Encounter",
        "id": eid,
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": cls},
        "subject": ref(pid),
        "participant": [{"individual": ref(PRACT, "Dr. Gregory House")}],
        "period": {"start": start, "end": end},
        "serviceProvider": ref(ORG, "Boston General"),
    }
    if disposition:
        res["hospitalization"] = {
            "dischargeDisposition": {
                "coding": [{"display": disposition}], "text": disposition,
            }
        }
    return res


def condition(cid, eid, pid, icd10, snomed, display, recorded):
    coding = [{"system": "http://snomed.info/sct", "code": snomed, "display": display}]
    if icd10:
        coding.append({"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": icd10, "display": display})
    return {
        "resourceType": "Condition",
        "id": cid,
        "clinicalStatus": {"coding": [{"code": "active"}]},
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/condition-category",
            "code": "encounter-diagnosis",
        }]}],
        "code": {"coding": coding, "text": display},
        "subject": ref(pid),
        "encounter": ref(eid),
        "recordedDate": recorded,
    }


def procedure(prid, eid, name, snomed, start, end):
    return {
        "resourceType": "Procedure",
        "id": prid,
        "status": "completed",
        "code": {"coding": [{"system": "http://snomed.info/sct", "code": snomed, "display": name}],
                 "text": name},
        "encounter": ref(eid),
        "performedPeriod": {"start": start, "end": end},
    }


def medication(mid, eid, pid, name, rxnorm, route):
    return {
        "resourceType": "MedicationRequest",
        "id": mid,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": rxnorm, "display": name}],
            "text": name,
        },
        "subject": ref(pid),
        "encounter": ref(eid),
        "dosageInstruction": [{"route": {"coding": [{"display": route}], "text": route}}],
    }


def claim(cid, pid, eid, total):
    return {
        "resourceType": "Claim",
        "id": cid,
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type",
                             "code": "institutional"}]},
        "patient": ref(pid),
        "item": [{"sequence": 1, "encounter": [ref(eid)]}],
        "total": {"value": total, "currency": "USD"},
    }


def eob(eid_res, claim_id, pid, eid, total, insurance_paid, patient_paid, payer="BlueCross BlueShield"):
    return {
        "resourceType": "ExplanationOfBenefit",
        "id": eid_res,
        "status": "active",
        "type": {"coding": [{"code": "institutional"}]},
        "patient": ref(pid),
        "claim": ref(claim_id),
        "contained": [{
            "resourceType": "Coverage",
            "id": "coverage1",
            "status": "active",
            "payor": [{"display": payer}],
        }],
        "insurance": [{"focal": True, "coverage": {"reference": "#coverage1"}}],
        "item": [{
            "sequence": 1,
            "encounter": [ref(eid)],
            "adjudication": [
                {"category": {"coding": [{"code": "coinsurance"}], "text": "coinsurance"},
                 "amount": {"value": patient_paid, "currency": "USD"}},
            ],
        }],
        "total": [{"category": {"coding": [{"code": "submitted"}], "text": "Submitted Amount"},
                   "amount": {"value": total, "currency": "USD"}}],
        "payment": {"amount": {"value": insurance_paid, "currency": "USD"}},
    }


def build():
    resources = [
        # Reference data
        {"resourceType": "Organization", "id": ORG, "name": "Boston General"},
        {"resourceType": "Practitioner", "id": PRACT,
         "name": [{"family": "House", "given": ["Gregory"]}]},
        # Patients (p2: bad gender, p3: missing birthDate)
        patient(P1, "Aaron", "Sanford", "male", "1968-04-12", "MA"),
        patient(P2, "Brenda", "Cole", "unknown", "1985-09-03", "MA"),
        patient(P3, "Carlos", "Diaz", "male", "1990-01-01", "MA", no_birth=True),
        # Encounters (e2: discharge before admit)
        encounter(E1, P1, "AMB", "2024-03-10T09:00:00-05:00", "2024-03-10T11:00:00-05:00"),
        encounter(E2, P2, "IMP", "2024-04-20T08:00:00-05:00", "2024-04-15T08:00:00-05:00"),
        encounter(E3, P3, "EMER", "2024-05-01T22:00:00-05:00", "2024-05-02T03:00:00-05:00"),
        # Diagnoses (c3: SNOMED only, no ICD-10)
        condition("dx-0001", E1, P1, "E11.9", "44054006", "Type 2 diabetes mellitus", "2024-03-10"),
        condition("dx-0002", E1, P1, "I10", "59621000", "Essential hypertension", "2024-03-10"),
        condition("dx-0003", E2, P2, None, "230690007", "Cerebrovascular accident", "2024-04-20"),
        condition("dx-0004", E3, P3, "J45.909", "195967001", "Asthma", "2024-05-01"),
        # Procedure + medication
        procedure("proc-0001", E1, "Hemoglobin A1c measurement", "43396009",
                  "2024-03-10T09:30:00-05:00", "2024-03-10T09:45:00-05:00"),
        medication("med-0001", E1, P1, "Metformin 500 MG Oral Tablet", "860975", "Oral"),
        # Billing: e1 paid in full; e2 OVERPAID (payments exceed the charge)
        claim("claim-0001", P1, E1, 1200.00),
        eob("eob-0001", "claim-0001", P1, E1, 1200.00, 960.00, 240.00),
        claim("claim-0002", P2, E2, 500.00),
        eob("eob-0002", "claim-0002", P2, E2, 500.00, 9000.00, 200.00),
    ]
    return {"resourceType": "Bundle", "type": "transaction",
            "entry": [entry(r) for r in resources]}


def main():
    with open(OUT, "w") as fh:
        json.dump(build(), fh, indent=2)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
