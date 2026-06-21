"""Generate a small HL7 v2 ADT sample file for demos/tests.

Builds a couple of ADT^A01 messages with PID + PV1 segments, including one
patient with an invalid sex code and a discharge-before-admit error so the
checker finds something. Field positions are set by index to keep the
pipe-delimited layout correct.

Usage:  python sample_data/hl7/make_hl7_sample.py
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sample_adt.hl7")


def segment(name: str, fields: dict[int, str], width: int) -> str:
    cells = [""] * (width + 1)
    cells[0] = name
    for idx, val in fields.items():
        cells[idx] = val
    return "|".join(cells)


def msh(ctrl_id: str) -> str:
    # MSH is special: MSH-1 is the field separator itself.
    return (f"MSH|^~\\&|HIS|HOSPITAL|EHR|DEST|20240310090000||"
            f"ADT^A01|{ctrl_id}|P|2.5")


def pid(pid_id, family, given, dob, sex, city, state, reg) -> str:
    return segment("PID", {
        1: "1",
        3: f"{pid_id}^^^HOSP^MR",
        5: f"{family}^{given}",
        7: dob,
        8: sex,
        11: f"123 Main St^^{city}^{state}^02118",
        33: reg,
    }, width=33)


def pv1(visit, cls, admit_type, location, attending, admit, discharge, disp) -> str:
    return segment("PV1", {
        1: "1",
        2: cls,
        3: location,
        4: admit_type,
        7: attending,
        19: f"{visit}^^^HOSP",
        36: disp,
        44: admit,
        45: discharge,
    }, width=45)


def main() -> None:
    messages = [
        # Patient 1 — clean
        [msh("MSG0001"),
         "EVN|A01|20240310090000",
         pid("1001", "Sanford", "Aaron", "19680412", "M", "Boston", "MA", "20240301"),
         pv1("5001", "I", "E", "2W^201^A^HOSP", "9001^House^Gregory",
             "20240310090000", "20240312110000", "01")],
        # Patient 2 — invalid sex 'X' and discharge BEFORE admit
        [msh("MSG0002"),
         "EVN|A01|20240415080000",
         pid("1002", "Cole", "Brenda", "19850903", "X", "Boston", "MA", "20240401"),
         pv1("5002", "I", "C", "3E^305^B^HOSP", "9002^Wilson^James",
             "20240420080000", "20240415080000", "01")],
    ]
    text = "\r\n".join("\r\n".join(seg for seg in m) for m in messages)
    with open(OUT, "w") as fh:
        fh.write(text + "\r\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
