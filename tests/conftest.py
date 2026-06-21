"""Shared test setup — isolate report history in a throwaway SQLite file."""

import os
import tempfile

_DB = os.path.join(tempfile.gettempdir(), "ehr_api_test.db")
os.environ["EHR_DB_PATH"] = _DB
os.environ["EHR_HISTORY"] = "on"

# Start each test session from a clean history file.
for _ext in ("", "-wal", "-shm"):
    try:
        os.remove(_DB + _ext)
    except FileNotFoundError:
        pass
