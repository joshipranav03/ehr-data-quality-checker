"""Runtime configuration and filesystem paths."""

from __future__ import annotations

import os

APP_NAME = "EHR Data Quality Checker"

# Repository layout
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SAMPLE_DIR = os.path.join(BASE_DIR, "sample_data")
SAMPLE_VARIANTS = ("clean", "dirty")

# Upload guard rails
MAX_UPLOAD_BYTES = int(os.getenv("EHR_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))  # 25 MB
MAX_ROWS = int(os.getenv("EHR_MAX_ROWS", "500000"))

# Persistence (report-summary history). Stored under var/ by default; override
# with EHR_DB_PATH, or disable history entirely with EHR_HISTORY=off.
VAR_DIR = os.path.join(BASE_DIR, "var")
DEFAULT_DB_PATH = os.path.join(VAR_DIR, "reports.db")
