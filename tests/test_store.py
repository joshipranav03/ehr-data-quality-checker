"""Tests for the report-history persistence layer."""

import importlib
import os

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A fresh store backed by a temp SQLite file, history forced on."""
    monkeypatch.setenv("EHR_DB_PATH", str(tmp_path / "reports.db"))
    monkeypatch.setenv("EHR_HISTORY", "on")
    from app import store as store_module
    importlib.reload(store_module)
    store_module.init_db()
    store_module.clear()
    return store_module


def _report(dataset="patients", score=99.9, errors=43, warnings=2):
    return {
        "dataset": dataset,
        "row_count": 2000,
        "variant": "dirty",
        "summary": {
            "score": score, "grade": "A+",
            "errors": errors, "warnings": warnings, "rules_failed": 9,
        },
    }


def test_save_and_list(store):
    assert store.save_report(_report(), "sample") is not None
    history = store.list_history("patients")
    assert len(history) == 1
    assert history[0]["dataset"] == "patients"
    assert history[0]["score"] == 99.9
    assert history[0]["source"] == "sample"


def test_trends_are_chronological(store):
    for s in (90.0, 95.0, 99.0):
        store.save_report(_report(score=s), "sample")
    t = store.trends("patients")
    assert t["enabled"] is True
    assert [p["score"] for p in t["points"]] == [90.0, 95.0, 99.0]  # oldest -> newest


def test_list_filters_by_dataset(store):
    store.save_report(_report("patients"), "sample")
    store.save_report(_report("billing"), "sample")
    assert len(store.list_history("patients")) == 1
    assert len(store.list_history()) == 2
    assert set(store.datasets_with_history()) == {"patients", "billing"}


def test_save_many(store):
    reports = [_report("patients"), _report("billing"), _report("encounters")]
    assert store.save_many(reports, "audit") == 3
    assert len(store.list_history()) == 3


def test_history_disabled_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("EHR_DB_PATH", str(tmp_path / "off.db"))
    monkeypatch.setenv("EHR_HISTORY", "off")
    import importlib
    from app import store as store_module
    importlib.reload(store_module)
    assert store_module.history_enabled() is False
    assert store_module.save_report(_report(), "sample") is None
    assert store_module.list_history() == []
    assert store_module.trends("patients")["enabled"] is False


def test_only_summary_fields_persisted(store):
    # Even if a full report (with sample rows) is passed, no row data is stored.
    rep = _report()
    rep["results"] = [{"sample": [{"_line": 7, "gender": "X", "ssn": "123-45-6789"}]}]
    store.save_report(rep, "upload")
    row = store.list_history("patients")[0]
    assert "ssn" not in row
    assert set(row.keys()) == {
        "id", "created_at", "dataset", "source", "variant",
        "row_count", "score", "grade", "errors", "warnings", "rules_failed",
    }
