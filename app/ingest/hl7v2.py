"""Minimal HL7 v2 ADT parser → patients + encounters tables.

HL7 v2 is the pipe-delimited format hospitals still use for registration and
admit/discharge/transfer (ADT) feeds. This is a pragmatic parser for the common
PID (patient) and PV1 (visit) segments — enough to validate an ADT feed, not a
full HL7 engine. Multiple messages may be concatenated.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


class Hl7IngestError(Exception):
    """Raised when the payload has no usable HL7 segments."""


SEX_MAP = {"M": "M", "F": "F"}  # O/U/A/N pass through and get flagged

# PV1-4 admission type codes -> our vocabulary
ADMIT_TYPE = {
    "E": "Emergency", "U": "Urgent", "C": "Elective",
    "N": "Newborn", "R": "Elective", "L": "Elective", "A": "Urgent",
}
# PV1-2 patient class fallback
CLASS_TYPE = {"E": "Emergency", "I": "Elective", "O": "Elective", "U": "Urgent"}
# A few common UB-04 discharge disposition codes
DISPOSITION = {
    "01": "Home", "02": "Transferred", "03": "Skilled Nursing Facility",
    "05": "Transferred", "06": "Home Health Care", "07": "Left Against Medical Advice",
    "20": "Expired", "62": "Rehabilitation",
}


def _hl7_date(value: Optional[str]) -> Optional[str]:
    """HL7 timestamp (YYYYMMDD[HHMM...]) -> YYYY-MM-DD."""
    if not value:
        return None
    digits = value.strip()
    if len(digits) >= 8 and digits[:8].isdigit():
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def _comp(field: str, idx: int) -> Optional[str]:
    """Component ``idx`` (0-based) of an HL7 field, split on '^'."""
    if not field:
        return None
    parts = field.split("^")
    val = parts[idx] if idx < len(parts) else None
    return val or None


def _get(fields: list[str], i: int) -> str:
    return fields[i] if i < len(fields) else ""


def _split_segments(text: str) -> list[list[str]]:
    raw = text.replace("\r\n", "\r").replace("\n", "\r")
    segments = []
    for line in raw.split("\r"):
        line = line.strip()
        if line:
            segments.append(line.split("|"))
    return segments


def ingest_hl7v2(message: str) -> dict[str, pd.DataFrame]:
    """Parse one or more HL7 v2 messages into ``{table: DataFrame}``."""
    segments = _split_segments(message)
    if not any(s and s[0] in {"MSH", "PID", "PV1"} for s in segments):
        raise Hl7IngestError("No HL7 v2 segments found (expected MSH/PID/PV1).")

    patients: list[dict] = []
    encounters: list[dict] = []
    current_pid: Optional[str] = None

    for seg in segments:
        kind = seg[0]
        if kind == "PID":
            pid = _comp(_get(seg, 3), 0)
            current_pid = pid
            patients.append({
                "patient_id": pid,
                "first_name": _comp(_get(seg, 5), 1),
                "last_name": _comp(_get(seg, 5), 0),
                "gender": SEX_MAP.get(_get(seg, 8).strip(), _get(seg, 8).strip() or None),
                "birth_date": _hl7_date(_get(seg, 7)),
                "city": _comp(_get(seg, 11), 2),
                "state": _comp(_get(seg, 11), 3),
                # Insurance lives in the IN1 segment, which this minimal ADT
                # parser does not read — left blank (the checker flags the gap).
                "insurance_provider": None,
                "registration_date": _hl7_date(_get(seg, 33)) or None,
            })
        elif kind == "PV1":
            admit_type = ADMIT_TYPE.get(_get(seg, 4).strip()) or CLASS_TYPE.get(_get(seg, 2).strip())
            disp = _get(seg, 36).strip()
            encounters.append({
                "encounter_id": _comp(_get(seg, 19), 0),
                "patient_id": current_pid,
                "provider_id": _comp(_get(seg, 7), 0),       # attending doctor id
                "department_id": _comp(_get(seg, 3), 0),     # assigned location point-of-care
                "admit_date": _hl7_date(_get(seg, 44)),
                "discharge_date": _hl7_date(_get(seg, 45)),
                "admission_type": admit_type,
                "discharge_disposition": DISPOSITION.get(disp, disp or None),
            })

    tables: dict[str, pd.DataFrame] = {}
    if patients:
        tables["patients"] = pd.DataFrame(patients)
    if encounters:
        tables["encounters"] = pd.DataFrame(encounters)
    if not tables:
        raise Hl7IngestError("No PID/PV1 segments produced any rows.")
    return tables
