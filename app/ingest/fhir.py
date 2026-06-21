"""Convert an HL7 FHIR R4 Bundle into the checker's tabular model.

Tuned for Synthea output but tolerant of generic FHIR servers. The mapping and
its known limitations are documented inline; the headline gotchas:

* References are ``urn:uuid:<uuid>`` in Synthea (not ``Patient/<id>``). A
  resource's ``id`` equals the UUID, so a reference resolves to an id by
  stripping the prefix — and that id matches the parent row's primary key.
* A Condition/Procedure carries a SNOMED coding *and* an ICD-10-CM coding only
  when Synthea can map it — so we search ``code.coding[]`` for the ICD-10 system
  and fall back to SNOMED/text.
* FHIR has no "primary diagnosis" flag; we derive ``is_primary`` as the first
  encounter-diagnosis per encounter.
* Billing is split across ``Claim`` (charge) and ``ExplanationOfBenefit``
  (payments); we join them and derive a payment status.

Fields FHIR does not carry (e.g. a true ``registration_date``) are filled with a
documented proxy or left blank — and the quality checker will honestly flag the
gaps, which is itself a useful finding.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

# Code systems
ICD10 = "http://hl7.org/fhir/sid/icd-10-cm"
SNOMED = "http://snomed.info/sct"
ENCOUNTER_DX = "encounter-diagnosis"

GENDER_MAP = {"male": "M", "female": "F"}

# FHIR v3 ActCode encounter class -> our admission_type vocabulary (approximate).
CLASS_MAP = {
    "EMER": "Emergency",
    "IMP": "Elective",
    "ACUTE": "Urgent",
    "NONAC": "Elective",
    "AMB": "Elective",
    "OBSENC": "Elective",
    "PRENC": "Elective",
    "SS": "Elective",
    "VR": "Elective",
    "HH": "Elective",
}


class FhirIngestError(Exception):
    """Raised when a payload is not a usable FHIR Bundle."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _date(value: Optional[str]) -> Optional[str]:
    """Normalise a FHIR date/dateTime to YYYY-MM-DD."""
    if not value or not isinstance(value, str):
        return None
    return value[:10]  # ISO-8601 date prefix


def _ref_id(reference: Optional[Any]) -> Optional[str]:
    """Turn a reference into the referenced resource's id.

    Accepts a string ("urn:uuid:abc" / "Patient/abc") or a reference object
    ({"reference": "..."}). Works because a resource's id == its UUID.
    """
    if isinstance(reference, dict):
        reference = reference.get("reference")
    if not reference or not isinstance(reference, str):
        return None
    if reference.startswith("urn:uuid:"):
        return reference[len("urn:uuid:"):]
    if "/" in reference:
        return reference.rsplit("/", 1)[-1]
    return reference


def _str(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _first(seq, default=None):
    return seq[0] if isinstance(seq, list) and seq else default


def _codeable_text(concept: Optional[dict]) -> Optional[str]:
    """Best human label from a CodeableConcept."""
    if not isinstance(concept, dict):
        return None
    coding = _first(concept.get("coding"), {}) or {}
    return concept.get("text") or coding.get("display") or coding.get("code")


def _pick_icd10(concept: Optional[dict]) -> tuple[Optional[str], Optional[str]]:
    """Return (code, description), preferring an ICD-10-CM coding."""
    if not isinstance(concept, dict):
        return None, None
    codings = concept.get("coding") or []
    icd = next((c for c in codings if c.get("system") == ICD10), None)
    if icd:
        return icd.get("code"), icd.get("display") or concept.get("text")
    snomed = next((c for c in codings if c.get("system") == SNOMED), None)
    if snomed:  # no ICD-10 mapping available — surface the SNOMED code instead
        return snomed.get("code"), snomed.get("display") or concept.get("text")
    any_coding = _first(codings, {}) or {}
    return any_coding.get("code"), concept.get("text") or any_coding.get("display")


# ---------------------------------------------------------------------------
# Bundle parsing
# ---------------------------------------------------------------------------
def _resources(bundle: dict) -> tuple[list[dict], dict[str, dict]]:
    """Return (resources, index). Index maps fullUrl and 'Type/id' -> resource."""
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise FhirIngestError("Payload is not a FHIR Bundle (resourceType != 'Bundle').")
    entries = bundle.get("entry") or []
    if not entries:
        raise FhirIngestError("Bundle has no entries.")
    resources: list[dict] = []
    index: dict[str, dict] = {}
    for entry in entries:
        res = entry.get("resource") if isinstance(entry, dict) else None
        if not isinstance(res, dict):
            continue
        resources.append(res)
        full = entry.get("fullUrl")
        if full:
            index[full] = res
        rid, rtype = res.get("id"), res.get("resourceType")
        if rid and rtype:
            index[f"{rtype}/{rid}"] = res
            index[rid] = res
    return resources, index


def _by_type(resources: list[dict], rtype: str) -> list[dict]:
    return [r for r in resources if r.get("resourceType") == rtype]


# ---------------------------------------------------------------------------
# Per-table extractors
# ---------------------------------------------------------------------------
def _patients(resources) -> list[dict]:
    rows = []
    for r in _by_type(resources, "Patient"):
        names = [n for n in (r.get("name") or []) if isinstance(n, dict)]
        official = next((n for n in names if n.get("use") == "official"), _first(names, {}) or {})
        meta = r.get("meta") or {}
        addr = _first(r.get("address"), {}) or {}
        rows.append({
            "patient_id": _str(r.get("id")),
            "first_name": _str(_first(official.get("given"))),
            "last_name": _str(official.get("family")),
            "gender": GENDER_MAP.get(r.get("gender"), _str(r.get("gender"))),
            "birth_date": _date(r.get("birthDate")),
            "city": _str(addr.get("city")),
            "state": _str(addr.get("state")),
            "insurance_provider": None,  # populated from EOB Coverage when present
            "registration_date": _date(meta.get("lastUpdated")),  # proxy
        })
    return rows


def _encounters(resources) -> list[dict]:
    rows = []
    for r in _by_type(resources, "Encounter"):
        period = r.get("period") or {}
        cls_obj = r.get("class")
        cls = cls_obj.get("code") if isinstance(cls_obj, dict) else None
        hosp = r.get("hospitalization") or {}
        rows.append({
            "encounter_id": _str(r.get("id")),
            "patient_id": _ref_id(r.get("subject")),
            "provider_id": _participant(r),
            "department_id": _ref_id(r.get("serviceProvider")),  # facility ~ department
            "admit_date": _date(period.get("start")),
            "discharge_date": _date(period.get("end")),
            "admission_type": CLASS_MAP.get(cls, "Elective" if cls else None),
            "discharge_disposition": _codeable_text(hosp.get("dischargeDisposition")),
        })
    return rows


def _participant(encounter: dict) -> Optional[str]:
    for part in encounter.get("participant") or []:
        ind = part.get("individual")
        if ind:
            return _ref_id(ind)
    return None


def _diagnoses(resources) -> list[dict]:
    rows = []
    for r in _by_type(resources, "Condition"):
        code, desc = _pick_icd10(r.get("code"))
        cats = r.get("category") or []
        is_dx = any(
            (cc.get("code") == ENCOUNTER_DX)
            for c in cats for cc in (c.get("coding") or [])
        )
        rows.append({
            "diagnosis_id": _str(r.get("id")),
            "encounter_id": _ref_id(r.get("encounter")),
            "icd10_code": _str(code),
            "diagnosis_description": _str(desc),
            "is_primary": None,  # derived below
            "_sort": r.get("onsetDateTime") or r.get("recordedDate") or "",
            "_is_dx": is_dx,
        })
    # Derive is_primary: first encounter-diagnosis per encounter.
    seen_primary: set[str] = set()
    for row in sorted(rows, key=lambda x: x["_sort"]):
        enc = row["encounter_id"]
        if row["_is_dx"] and enc and enc not in seen_primary:
            row["is_primary"] = "True"
            seen_primary.add(enc)
        else:
            row["is_primary"] = "False"
    for row in rows:
        row.pop("_sort", None)
        row.pop("_is_dx", None)
    return rows


def _procedures(resources) -> list[dict]:
    rows = []
    for r in _by_type(resources, "Procedure"):
        performed = r.get("performedDateTime")
        if not performed:
            performed = (r.get("performedPeriod") or {}).get("start")
        rows.append({
            "procedure_id": _str(r.get("id")),
            "encounter_id": _ref_id(r.get("encounter")),
            "procedure_name": _codeable_text(r.get("code")),
            "procedure_date": _date(performed),
        })
    return rows


def _prescriptions(resources, index) -> list[dict]:
    rows = []
    for r in _by_type(resources, "MedicationRequest"):
        med = _codeable_text(r.get("medicationCodeableConcept"))
        if med is None and r.get("medicationReference"):
            rid = _ref_id(r.get("medicationReference")) or ""
            target = index.get(rid)
            if target is None and rid.startswith("#"):  # contained reference
                cid = rid[1:]
                target = next((c for c in (r.get("contained") or [])
                               if isinstance(c, dict) and c.get("id") == cid), None)
            if target:
                med = _codeable_text(target.get("code"))
        dosage = _first(r.get("dosageInstruction"), {}) or {}
        rows.append({
            "prescription_id": _str(r.get("id")),
            "encounter_id": _ref_id(r.get("encounter")),
            "medication_name": _str(med),
            "route": _codeable_text(dosage.get("route")),
        })
    return rows


def _billing(resources, index) -> list[dict]:
    """Join Claim (charge) + ExplanationOfBenefit (payments) per encounter."""
    rows = []
    for eob in _by_type(resources, "ExplanationOfBenefit"):
        enc = None
        for item in eob.get("item") or []:
            enc = _ref_id(_first(item.get("encounter")))
            if enc:
                break
        if not enc:
            enc = _ref_id(eob.get("encounter"))

        # total_charge: prefer the linked Claim, else EOB 'submitted' total
        total = None
        claim = index.get(_ref_id(eob.get("claim")) or "")
        if claim:
            total = (claim.get("total") or {}).get("value")
        if total is None:
            for t in eob.get("total") or []:
                if _codeable_text(t.get("category")) in ("Submitted Amount", "submitted"):
                    total = (t.get("amount") or {}).get("value")
                    break

        insurance_paid = ((eob.get("payment") or {}).get("amount") or {}).get("value")
        patient_paid = _sum_adjudication(eob, "coinsurance")

        status = _payment_status(total, insurance_paid, patient_paid)
        rows.append({
            "encounter_id": enc,
            "total_charge": _str(total),
            "insurance_paid": _str(insurance_paid if insurance_paid is not None else 0),
            "patient_paid": _str(patient_paid if patient_paid is not None else 0),
            "payment_status": status,
        })

    # Fall back to bare Claims for encounters with no EOB.
    billed = {r["encounter_id"] for r in rows}
    for claim in _by_type(resources, "Claim"):
        item = _first(claim.get("item")) or {}
        enc = _ref_id(_first(item.get("encounter"))) or _ref_id(claim.get("encounter"))
        if enc and enc not in billed:
            total = (claim.get("total") or {}).get("value")
            rows.append({
                "encounter_id": enc,
                "total_charge": _str(total),
                "insurance_paid": "0",
                "patient_paid": "0",
                "payment_status": "Pending",
            })
    return rows


def _sum_adjudication(eob: dict, needle: str) -> Optional[float]:
    total = 0.0
    found = False
    for item in eob.get("item") or []:
        if not isinstance(item, dict):
            continue
        for adj in item.get("adjudication") or []:
            if not isinstance(adj, dict):
                continue
            label = (_codeable_text(adj.get("category")) or "").lower()
            code = ""
            cat = adj.get("category")
            for c in (cat.get("coding") if isinstance(cat, dict) else []) or []:
                code = (c.get("code") or "").lower()
            if needle in label or needle in code:
                amt = (adj.get("amount") or {}).get("value")
                if amt is not None:
                    total += float(amt)
                    found = True
    return round(total, 2) if found else None


def _payment_status(total, insurance, patient) -> str:
    try:
        t = float(total) if total is not None else 0.0
        paid = (float(insurance) if insurance else 0.0) + (float(patient) if patient else 0.0)
    except (TypeError, ValueError):
        return "Pending"
    if t <= 0:
        return "Pending"
    if paid >= t - 0.01:
        return "Paid"
    if paid > 0:
        return "Partially Paid"
    return "Pending"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
TABLE_BUILDERS = {
    "patients": lambda res, idx: _patients(res),
    "encounters": lambda res, idx: _encounters(res),
    "diagnoses": lambda res, idx: _diagnoses(res),
    "procedures": lambda res, idx: _procedures(res),
    "prescriptions": lambda res, idx: _prescriptions(res, idx),
    "billing": lambda res, idx: _billing(res, idx),
}


# Columns that hold resource ids (primary or foreign keys). FHIR uses string
# UUIDs; the warehouse model expects integers, so we assign surrogate integer
# keys — a standard ETL step that keeps cross-table references consistent.
ID_COLUMNS = {
    "patient_id", "encounter_id", "provider_id", "department_id",
    "diagnosis_id", "procedure_id", "prescription_id",
}


def _fill_insurance(tables: dict, resources: list[dict]) -> None:
    """Derive insurance_provider for patients from EOB-contained Coverage."""
    if "patients" not in tables:
        return
    payer_by_patient: dict[str, str] = {}
    for eob in _by_type(resources, "ExplanationOfBenefit"):
        pid = _ref_id(eob.get("patient"))
        if not pid:
            continue
        for contained in eob.get("contained") or []:
            if contained.get("resourceType") == "Coverage":
                payor = _first(contained.get("payor"), {}) or {}
                name = payor.get("display") or _codeable_text(contained.get("type"))
                if name:
                    payer_by_patient[pid] = name
                    break
    if payer_by_patient:
        df = tables["patients"]
        df["insurance_provider"] = df["patient_id"].map(
            lambda pid: payer_by_patient.get(pid)
        ).where(lambda s: s.notna(), df["insurance_provider"])


def _assign_surrogate_keys(tables: dict) -> None:
    """Replace string UUIDs in id columns with stable surrogate integers."""
    mapping: dict[str, int] = {}
    counter = {"n": 0}

    def to_int(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return value
        key = str(value)
        if key not in mapping:
            counter["n"] += 1
            mapping[key] = counter["n"]
        return str(mapping[key])

    for df in tables.values():
        for col in df.columns:
            if col in ID_COLUMNS:
                df[col] = df[col].map(to_int)


def ingest_fhir_bundle(bundle: dict) -> dict[str, pd.DataFrame]:
    """Parse a FHIR Bundle into ``{table_name: DataFrame}`` (empty tables omitted)."""
    resources, index = _resources(bundle)
    tables: dict[str, pd.DataFrame] = {}
    for name, build in TABLE_BUILDERS.items():
        rows = build(resources, index)
        if rows:
            tables[name] = pd.DataFrame(rows)
    if not tables:
        raise FhirIngestError(
            "No recognised clinical resources found "
            "(expected Patient, Encounter, Condition, ...)."
        )
    _fill_insurance(tables, resources)
    _assign_surrogate_keys(tables)
    return tables
