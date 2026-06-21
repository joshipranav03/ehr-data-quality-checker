"""Command-line interface for the EHR Data Quality Checker.

The same engine that powers the web API is available from the terminal — handy
for CI pipelines and batch validation.

Examples:
    python -m app.cli check sample_data/dirty/patients.csv
    python -m app.cli check data/encounters.csv --dataset encounters
    python -m app.cli check data/billing.csv --json > report.json
    python -m app.cli audit --variant dirty
    python -m app.cli profiles
"""

from __future__ import annotations

import argparse
import json
import sys

from .services import (
    CheckError,
    check_sample,
    list_profiles,
    read_csv_bytes,
    check_dataframe,
    run_full_audit,
)

# ANSI colours (disabled when output is not a TTY)
_TTY = sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def _bar(pct: float, width: int = 24) -> str:
    filled = int(round(pct / 100 * width))
    return "█" * filled + "·" * (width - filled)


def _print_report(report: dict) -> None:
    s = report["summary"]
    title = report["dataset_title"]
    score = s["score"]
    grade = s["grade"]
    rows = report["row_count"]
    cols = report["column_count"]
    colour = "32" if score >= 90 else "33" if score >= 75 else "31"
    print()
    print(_c(f"  {title}  ", "1;37"), f"({rows:,} rows, {cols} columns)")
    print("  " + "-" * 52)
    score_txt = _c(f"{score:>5.1f}  {grade}", "1;" + colour)
    print(f"  Quality score : {score_txt}  {_bar(score)}")
    print(f"  Issues        : {_c(str(s['errors']), '31')} errors, "
          f"{_c(str(s['warnings']), '33')} warnings")
    print(f"  Clean rows    : {s['clean_rows']:,} / {report['row_count']:,} "
          f"({s['clean_row_pct']}%)")
    print(f"  Rules         : {s['rules_passed']} passed, "
          f"{s['rules_failed']} failed, {s['rules_skipped']} skipped")
    print()
    failed = [r for r in report["results"] if r["status"] == "failed"]
    if failed:
        print("  Findings:")
        for r in sorted(failed, key=lambda x: (x["severity"] != "error", -x["failed"])):
            sev = _c("ERR ", "31") if r["severity"] == "error" else _c("WARN", "33")
            print(f"    [{sev}] {r['failed']:>5} / {r['checked']:<6}  "
                  f"{r['category']:<12} {r['message']}")
    else:
        print(_c("  No issues found. ", "32"))
    print()


def _cmd_check(args) -> int:
    try:
        with open(args.path, "rb") as fh:
            df = read_csv_bytes(fh.read())
        report = check_dataframe(df, dataset=args.dataset)
    except FileNotFoundError:
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2
    except CheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    # Non-zero exit when errors exist — useful as a CI gate.
    if args.fail_on_error and report["summary"]["errors"] > 0:
        return 1
    return 0


def _cmd_audit(args) -> int:
    try:
        result = run_full_audit(args.variant)
    except CheckError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    agg = result["aggregate"]
    print()
    print(_c(f"  Full database audit  ({args.variant})", "1;37"))
    print("  " + "=" * 52)
    for report in result["tables"]:
        s = report["summary"]
        flag = _c("OK ", "32") if s["errors"] == 0 else _c("!! ", "31")
        print(f"  {flag} {report['dataset_title']:<16} "
              f"score {s['score']:>5.1f}  "
              f"{s['errors']:>4} err  {s['warnings']:>4} warn")
    print("  " + "-" * 52)
    print(f"  TOTAL  {agg['tables']} tables, {agg['rows']:,} rows, "
          f"{_c(str(agg['errors']), '31')} errors, "
          f"{_c(str(agg['warnings']), '33')} warnings")
    print()
    return 0


def _cmd_profiles(args) -> int:
    profiles = list_profiles()
    if args.json:
        print(json.dumps(profiles, indent=2))
        return 0
    print()
    for p in profiles:
        print(f"  {_c(p['key'], '1;37'):<24} {p['rule_count']:>2} rules  "
              f"- {p['description']}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ehr-dq", description="EHR Data Quality Checker — CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("check", help="check a single CSV file")
    pc.add_argument("path", help="path to a CSV file")
    pc.add_argument("--dataset", help="dataset name (auto-detected if omitted)")
    pc.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    pc.add_argument("--fail-on-error", action="store_true",
                    help="exit non-zero if any error-level issues are found")
    pc.set_defaults(func=_cmd_check)

    pa = sub.add_parser("audit", help="audit the bundled sample database")
    pa.add_argument("--variant", default="dirty", choices=["clean", "dirty"])
    pa.add_argument("--json", action="store_true")
    pa.set_defaults(func=_cmd_audit)

    pp = sub.add_parser("profiles", help="list supported datasets and rules")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=_cmd_profiles)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
