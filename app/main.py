"""FastAPI application for the EHR Data Quality Checker.

Exposes a small JSON API plus a static single-page dashboard. Interactive
API docs are available at ``/docs`` (Swagger) and ``/redoc``.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config
from .models import (
    HealthResponse,
    ProfileMeta,
    Report,
    SamplesResponse,
)
from .services import (
    CheckError,
    check_fhir_bundle,
    check_hl7v2,
    check_sample,
    check_upload,
    get_history,
    get_trends,
    list_profiles,
    list_samples,
    run_full_audit,
)
from .engine.profiles import PROFILES

app = FastAPI(
    title=config.APP_NAME,
    version=__version__,
    description=(
        "Validate Electronic Health Record (EHR) data extracts for "
        "completeness, validity, uniqueness, consistency, and referential "
        "integrity. Upload a CSV or try the bundled sample data."
    ),
    contact={"name": "EHR Data Quality Checker"},
    license_info={"name": "MIT"},
)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
@app.exception_handler(CheckError)
async def _check_error_handler(_request, exc: CheckError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse, tags=["meta"])
async def health():
    return HealthResponse(
        status="ok", app=config.APP_NAME, version=__version__, profiles=len(PROFILES)
    )


@app.get("/healthz", tags=["meta"])
async def healthz():
    """Lightweight liveness probe — the conventional path most platforms poll."""
    return {"status": "ok"}


@app.get("/api/profiles", response_model=list[ProfileMeta], tags=["meta"])
async def profiles():
    """List the supported EHR datasets and the rules applied to each."""
    return list_profiles()


@app.get("/api/samples", response_model=SamplesResponse, tags=["meta"])
async def samples():
    """List bundled sample datasets (clean and dirty variants)."""
    return SamplesResponse(datasets=list(PROFILES.keys()), samples=list_samples())


@app.post("/api/check", response_model=Report, tags=["check"])
async def check(
    file: UploadFile = File(..., description="A CSV extract of one EHR table"),
    dataset: Optional[str] = Query(
        None,
        description="Dataset name (patients, encounters, ...). "
        "Auto-detected from columns when omitted.",
    ),
):
    """Run data-quality checks on an uploaded CSV file.

    Foreign-key rules are skipped for single-file uploads because parent
    tables are not available; use the sample audit to see them in action.
    """
    content = await file.read()
    return check_upload(content, dataset=dataset)


@app.post("/api/check/sample", response_model=Report, tags=["check"])
async def check_sample_endpoint(
    name: str = Query(..., description="Dataset name, e.g. 'patients'"),
    variant: str = Query("dirty", description="'clean' or 'dirty'"),
):
    """Run checks on a bundled sample table (with sibling tables for FK checks)."""
    return check_sample(name, variant)


@app.get("/api/audit", response_model=dict, tags=["check"])
async def audit(variant: str = Query("dirty", description="'clean' or 'dirty'")):
    """Audit the entire bundled EHR database, resolving cross-table links."""
    return run_full_audit(variant)


@app.post("/api/check/fhir", response_model=dict, tags=["interop"])
async def check_fhir(file: UploadFile = File(..., description="A FHIR R4 Bundle (JSON)")):
    """Ingest an HL7 FHIR R4 Bundle, derive tables, and audit them.

    Resources are mapped to the patient/encounter/diagnosis/... model, surrogate
    integer keys are assigned, and every derived table is validated together so
    cross-table referential integrity is checked.
    """
    content = await file.read()
    return check_fhir_bundle(content)


@app.post("/api/check/hl7", response_model=dict, tags=["interop"])
async def check_hl7(file: UploadFile = File(..., description="HL7 v2 ADT message(s)")):
    """Ingest HL7 v2 ADT messages (PID/PV1) and audit the derived tables."""
    content = await file.read()
    return check_hl7v2(content)


@app.get("/api/history", response_model=dict, tags=["history"])
async def history(
    dataset: Optional[str] = Query(None, description="Filter to one dataset"),
    limit: int = Query(50, ge=1, le=500),
):
    """Most-recent report summaries (history must be enabled)."""
    return get_history(dataset, limit)


@app.get("/api/history/trends", response_model=dict, tags=["history"])
async def history_trends(
    dataset: str = Query(..., description="Dataset to chart"),
    limit: int = Query(30, ge=1, le=365),
):
    """Score-over-time series for one dataset, oldest to newest."""
    return get_trends(dataset, limit)


# ---------------------------------------------------------------------------
# Frontend (served last so /api/* takes precedence)
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(os.path.join(config.STATIC_DIR, "index.html"))


if os.path.isdir(config.STATIC_DIR):
    app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
