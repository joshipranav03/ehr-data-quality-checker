"""Application services: glue between the web layer and the engine.

Handles CSV parsing, dataset detection, loading bundled samples, and running
single-table or full-database audits.
"""

from __future__ import annotations

import io
import json
import os
from typing import Optional

import pandas as pd

from . import config, store
from .engine.checker import DataQualityChecker
from .engine.profiles import PROFILES, detect_profile, get_profile
from .ingest import (
    FhirIngestError,
    Hl7IngestError,
    ingest_fhir_bundle,
    ingest_hl7v2,
)


class CheckError(Exception):
    """Raised for user-facing problems (bad file, unknown dataset, ...)."""


# ---------------------------------------------------------------------------
# Persistence helpers — never let a history write break a check (read-only FS,
# disabled history, etc. are all non-fatal).
# ---------------------------------------------------------------------------
def _persist(report: dict, source: str) -> None:
    try:
        store.save_report(report, source)
    except Exception:  # pragma: no cover - best-effort logging only
        pass


def _persist_many(reports: list[dict], source: str) -> None:
    try:
        store.save_many(reports, source)
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------
def _check_upload_size(content: bytes) -> None:
    """Reject oversized uploads (shared by the CSV, FHIR, and HL7 paths)."""
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise CheckError(
            f"File is too large (limit {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."
        )


def _check_row_total(tables: dict) -> None:
    """Reject ingested payloads with too many derived rows."""
    total = sum(len(df) for df in tables.values())
    if total > config.MAX_ROWS:
        raise CheckError(f"Too many rows (limit {config.MAX_ROWS:,}).")


def read_csv_bytes(content: bytes) -> pd.DataFrame:
    """Parse raw CSV bytes into a string-typed DataFrame.

    Everything is read as text so the engine — not pandas — decides what a
    valid integer/date/number looks like. Blank cells become NaN.
    """
    _check_upload_size(content)
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    except Exception as exc:  # pandas raises a variety of parser errors
        raise CheckError(f"Could not parse CSV: {exc}") from exc
    if df.empty:
        raise CheckError("The uploaded file contains no data rows.")
    if len(df) > config.MAX_ROWS:
        raise CheckError(f"Too many rows (limit {config.MAX_ROWS:,}).")
    df.columns = [c.strip() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Profile metadata
# ---------------------------------------------------------------------------
def list_profiles() -> list[dict]:
    return [
        {
            "key": p.key,
            "title": p.title,
            "description": p.description,
            "id_column": p.id_column,
            "columns": p.detect_columns,
            "parent_tables": p.parent_tables,
            "rule_count": len(p.rules),
            "rules": p.describe_rules(),
        }
        for p in PROFILES.values()
    ]


def resolve_profile(df: pd.DataFrame, dataset: Optional[str]):
    """Return the profile to use, by explicit name or auto-detection."""
    if dataset:
        profile = get_profile(dataset)
        if profile is None:
            known = ", ".join(PROFILES.keys())
            raise CheckError(f"Unknown dataset '{dataset}'. Known datasets: {known}.")
        return profile, False
    profile = detect_profile(df.columns)
    if profile is None:
        raise CheckError(
            "Could not recognise this dataset from its columns. "
            "Pass an explicit dataset name. "
            f"Supported: {', '.join(PROFILES.keys())}."
        )
    return profile, True


# ---------------------------------------------------------------------------
# Running checks
# ---------------------------------------------------------------------------
def check_dataframe(
    df: pd.DataFrame,
    dataset: Optional[str] = None,
    context: Optional[dict] = None,
) -> dict:
    profile, auto = resolve_profile(df, dataset)
    report = DataQualityChecker(profile).run(df, context=context)
    payload = report.to_dict()
    payload["auto_detected"] = auto
    return payload


def check_upload(content: bytes, dataset: Optional[str] = None) -> dict:
    df = read_csv_bytes(content)
    payload = check_dataframe(df, dataset=dataset)
    _persist(payload, "upload")
    return payload


# ---------------------------------------------------------------------------
# Bundled sample data
# ---------------------------------------------------------------------------
def _sample_path(variant: str, name: str) -> str:
    return os.path.join(config.SAMPLE_DIR, variant, f"{name}.csv")


def list_samples() -> dict:
    out: dict[str, list[str]] = {}
    for variant in config.SAMPLE_VARIANTS:
        folder = os.path.join(config.SAMPLE_DIR, variant)
        if os.path.isdir(folder):
            out[variant] = sorted(
                f[:-4] for f in os.listdir(folder) if f.endswith(".csv")
            )
    return out


def load_sample(name: str, variant: str = "dirty") -> pd.DataFrame:
    if variant not in config.SAMPLE_VARIANTS:
        raise CheckError(f"Unknown variant '{variant}'.")
    path = _sample_path(variant, name)
    if not os.path.exists(path):
        raise CheckError(f"No sample '{name}' in '{variant}'.")
    return pd.read_csv(path, dtype=str)


def _load_variant_context(variant: str) -> dict:
    """Load every available table for a variant — used for FK resolution."""
    context = {}
    for key in PROFILES:
        path = _sample_path(variant, key)
        if os.path.exists(path):
            context[key] = pd.read_csv(path, dtype=str)
    return context


def check_sample(name: str, variant: str = "dirty") -> dict:
    """Check one bundled table, with sibling tables available for FK checks."""
    if get_profile(name) is None:
        raise CheckError(f"Unknown dataset '{name}'.")
    context = _load_variant_context(variant)
    df = context[name] if name in context else load_sample(name, variant)
    payload = check_dataframe(df, dataset=name, context=context)
    payload["variant"] = variant
    _persist(payload, "sample")
    return payload


def _audit_context(context: dict, source: str, **extra) -> dict:
    """Run every known profile present in ``context`` together (FKs resolved),
    aggregate the results, persist them, and return a combined payload."""
    tables = []
    agg = {"errors": 0, "warnings": 0, "total_issues": 0, "rows": 0, "rows_with_errors": 0}
    score_acc = 0.0
    for key, profile in PROFILES.items():
        if key not in context:
            continue
        report = DataQualityChecker(profile).run(context[key], context=context).to_dict()
        tables.append(report)
        s = report["summary"]
        agg["errors"] += s["errors"]
        agg["warnings"] += s["warnings"]
        agg["total_issues"] += s["total_issues"]
        agg["rows"] += report["row_count"]
        agg["rows_with_errors"] += s["rows_with_errors"]
        score_acc += s["score"]
    agg["tables"] = len(tables)
    score = round(score_acc / len(tables), 1) if tables else 100.0
    if (agg["errors"] or agg["warnings"]) and score >= 100.0:
        score = 99.9
    agg["score"] = score
    _persist_many(tables, source)
    return {"source": source, "aggregate": agg,
            "tables": tables, "recognised": [t["dataset"] for t in tables], **extra}


def run_full_audit(variant: str = "dirty") -> dict:
    """Audit every table of a variant together, resolving cross-table links."""
    context = _load_variant_context(variant)
    if not context:
        raise CheckError(f"No sample data found for variant '{variant}'.")
    return _audit_context(context, source="audit", variant=variant)


# ---------------------------------------------------------------------------
# FHIR / HL7 ingestion
# ---------------------------------------------------------------------------
def check_fhir_bundle(content: bytes) -> dict:
    """Parse a FHIR R4 Bundle, derive tables, and audit them together."""
    _check_upload_size(content)
    try:
        bundle = json.loads(content)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CheckError(f"Could not parse JSON: {exc}") from exc
    try:
        tables = ingest_fhir_bundle(bundle)
    except FhirIngestError as exc:
        raise CheckError(str(exc)) from exc
    _check_row_total(tables)
    return _audit_context(tables, source="fhir", format="FHIR R4")


def check_hl7v2(content: bytes) -> dict:
    """Parse one or more HL7 v2 ADT messages and audit the derived tables.

    HL7 v2 is historically 8-bit; decode as UTF-8 then fall back to latin-1
    (byte-lossless) rather than silently replacing undecodable bytes.
    """
    _check_upload_size(content)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    try:
        tables = ingest_hl7v2(text)
    except Hl7IngestError as exc:
        raise CheckError(str(exc)) from exc
    _check_row_total(tables)
    return _audit_context(tables, source="hl7v2", format="HL7 v2")


# ---------------------------------------------------------------------------
# History & trends
# ---------------------------------------------------------------------------
def get_history(dataset: Optional[str] = None, limit: int = 50) -> dict:
    return {
        "enabled": store.history_enabled(),
        "datasets": store.datasets_with_history(),
        "records": store.list_history(dataset, limit),
    }


def get_trends(dataset: str, limit: int = 30) -> dict:
    return store.trends(dataset, limit)
