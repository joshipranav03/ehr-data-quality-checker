"""Run the data-quality checker over a directory of Synthea FHIR bundles.

Synthea (https://github.com/synthetichealth/synthea) emits one FHIR R4 Bundle
per patient under ``output/fhir/``. This merges them into a single bundle so
surrogate keys and cross-patient referential integrity are consistent, then
runs the full audit.

Usage:
    python tools/synthea_to_report.py path/to/synthea/output/fhir
    python tools/synthea_to_report.py path/to/output/fhir --json > report.json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# Allow running as a plain script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import check_fhir_bundle, CheckError  # noqa: E402


def merge_bundles(directory: str) -> dict:
    paths = sorted(glob.glob(os.path.join(directory, "*.json")))
    if not paths:
        raise SystemExit(f"No .json bundles found in {directory}")
    entries = []
    for path in paths:
        try:
            bundle = json.load(open(path))
        except (ValueError, OSError):
            continue
        if isinstance(bundle, dict) and bundle.get("resourceType") == "Bundle":
            entries.extend(bundle.get("entry", []))
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit Synthea FHIR output.")
    parser.add_argument("directory", help="directory of Synthea FHIR bundles")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    bundle = merge_bundles(args.directory)
    print(f"merged {len(bundle['entry'])} resources from {args.directory}",
          file=sys.stderr)
    try:
        result = check_fhir_bundle(json.dumps(bundle).encode())
    except CheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    agg = result["aggregate"]
    print(f"\n  Synthea FHIR audit — {agg['tables']} tables, {agg['rows']:,} rows")
    print("  " + "=" * 52)
    for report in result["tables"]:
        s = report["summary"]
        flag = "OK " if s["errors"] == 0 else "!! "
        print(f"  {flag} {report['dataset_title']:<14} score {s['score']:>5} "
              f"{s['errors']:>5} err {s['warnings']:>4} warn")
    print("  " + "-" * 52)
    print(f"  TOTAL {agg['errors']} errors, {agg['warnings']} warnings, "
          f"avg score {agg['score']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
