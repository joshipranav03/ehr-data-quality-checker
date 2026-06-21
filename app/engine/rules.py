"""Rule primitives for the data-quality engine.

A *rule* inspects a pandas DataFrame and returns a :class:`RuleResult`
describing how many records passed/failed and a small sample of offending
rows. Rules are pure and side-effect free, which makes them trivial to unit
test and to reuse across the API, CLI, and batch contexts.

Every rule belongs to one of five quality *dimensions*:

* ``completeness`` — is the value present?
* ``validity``     — is the value well-formed / in the allowed domain?
* ``uniqueness``   — are key values free of duplicates?
* ``consistency``  — do related fields agree (cross-field logic)?
* ``integrity``    — do foreign keys resolve to a parent record?
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

import pandas as pd

# --- Quality dimensions ----------------------------------------------------
COMPLETENESS = "completeness"
VALIDITY = "validity"
UNIQUENESS = "uniqueness"
CONSISTENCY = "consistency"
INTEGRITY = "integrity"

# --- Severities ------------------------------------------------------------
ERROR = "error"
WARNING = "warning"

SAMPLE_SIZE = 8  # max offending rows attached to a result


@dataclass
class RuleResult:
    """Outcome of evaluating a single rule against a dataset."""

    rule_id: str
    title: str
    category: str
    severity: str
    column: Optional[str]
    checked: int
    failed: int
    message: str
    sample: list[dict] = field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None
    # Full set of offending row indices — used internally for row-level
    # health scoring; not serialised to keep API payloads small.
    failed_indices: list[int] = field(default_factory=list, repr=False)

    @property
    def passed(self) -> bool:
        return not self.skipped and self.failed == 0

    @property
    def pass_rate(self) -> float:
        if self.checked == 0:
            return 1.0
        return 1.0 - self.failed / self.checked

    def to_dict(self) -> dict:
        status = "skipped" if self.skipped else ("passed" if self.passed else "failed")
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "column": self.column,
            "status": status,
            "checked": self.checked,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "message": self.message,
            "sample": self.sample,
            "skip_reason": self.skip_reason,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _csv_line(index: Any) -> int:
    """Translate a 0-based DataFrame index to a 1-based CSV data-line number.

    Line 1 of the file is the header, so the first data row is line 2.
    """
    return int(index) + 2


def _clean(value: Any) -> Any:
    """Make a cell JSON-serialisable (NaN -> None)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _sample_rows(df: pd.DataFrame, mask: pd.Series, columns: Optional[Sequence[str]] = None) -> list[dict]:
    """Return up to ``SAMPLE_SIZE`` offending rows as JSON-friendly dicts."""
    cols = list(columns) if columns else list(df.columns)
    rows: list[dict] = []
    for idx in df.index[mask][:SAMPLE_SIZE]:
        record = {"_line": _csv_line(idx)}
        for col in cols:
            if col in df.columns:
                record[col] = _clean(df.at[idx, col])
        rows.append(record)
    return rows


def _present(series: pd.Series) -> pd.Series:
    """Boolean mask of non-missing values (NaN and blank strings are missing)."""
    not_na = series.notna()
    blank = series.astype("string").str.strip().eq("").fillna(False)
    return not_na & ~blank


# ---------------------------------------------------------------------------
# Base rule
# ---------------------------------------------------------------------------
class Rule:
    """Base class. Subclasses implement :meth:`evaluate`."""

    category: str = VALIDITY
    severity: str = ERROR

    def __init__(
        self,
        rule_id: str,
        title: str,
        column: Optional[str] = None,
        severity: Optional[str] = None,
    ):
        self.rule_id = rule_id
        self.title = title
        self.column = column
        if severity:
            self.severity = severity

    # -- utilities for subclasses ------------------------------------------
    def _result(
        self,
        df: pd.DataFrame,
        mask: pd.Series,
        checked: int,
        message: str,
        sample_columns: Optional[Sequence[str]] = None,
    ) -> RuleResult:
        failed = int(mask.sum())
        return RuleResult(
            rule_id=self.rule_id,
            title=self.title,
            category=self.category,
            severity=self.severity,
            column=self.column,
            checked=int(checked),
            failed=failed,
            message=message,
            sample=_sample_rows(df, mask, sample_columns) if failed else [],
            failed_indices=[int(i) for i in df.index[mask]] if failed else [],
        )

    def _skipped(self, reason: str) -> RuleResult:
        return RuleResult(
            rule_id=self.rule_id,
            title=self.title,
            category=self.category,
            severity=self.severity,
            column=self.column,
            checked=0,
            failed=0,
            message=f"Skipped: {reason}",
            skipped=True,
            skip_reason=reason,
        )

    def _missing_column(self) -> RuleResult:
        return self._skipped(f"column '{self.column}' not present in dataset")

    def evaluate(self, df: pd.DataFrame, context: Optional[dict] = None) -> RuleResult:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------
class NotNull(Rule):
    category = COMPLETENESS
    severity = ERROR

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        missing = ~present
        return self._result(
            df, missing, checked=len(df),
            message=f"'{self.column}' must not be blank or missing.",
            sample_columns=self._sample_cols(df),
        )

    def _sample_cols(self, df):
        return [c for c in df.columns][:6]


# ---------------------------------------------------------------------------
# Uniqueness
# ---------------------------------------------------------------------------
class Unique(Rule):
    category = UNIQUENESS
    severity = ERROR

    def __init__(self, rule_id, title, columns, severity=None):
        self.columns = [columns] if isinstance(columns, str) else list(columns)
        super().__init__(rule_id, title, column=", ".join(self.columns), severity=severity)

    def evaluate(self, df, context=None):
        missing = [c for c in self.columns if c not in df.columns]
        if missing:
            return self._skipped(f"column(s) {missing} not present")
        # Only consider rows where all key columns are present.
        present_mask = pd.Series(True, index=df.index)
        for c in self.columns:
            present_mask &= _present(df[c])
        sub = df[present_mask]
        dup = sub.duplicated(subset=self.columns, keep=False)
        dup_full = pd.Series(False, index=df.index)
        dup_full.loc[sub.index] = dup
        return self._result(
            df, dup_full, checked=int(present_mask.sum()),
            message=f"Key {self.columns} must be unique; duplicate values found.",
            sample_columns=self.columns,
        )


# ---------------------------------------------------------------------------
# Validity
# ---------------------------------------------------------------------------
class AllowedValues(Rule):
    category = VALIDITY

    def __init__(self, rule_id, title, column, allowed, severity=ERROR, case_sensitive=True):
        super().__init__(rule_id, title, column=column, severity=severity)
        self.allowed = set(allowed)
        self.case_sensitive = case_sensitive
        if not case_sensitive:
            self.allowed = {str(v).lower() for v in self.allowed}

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        values = df[self.column].astype("string")
        cmp = values if self.case_sensitive else values.str.lower()
        bad = present & ~cmp.isin(self.allowed)
        allowed_preview = ", ".join(sorted(map(str, self.allowed))[:8])
        return self._result(
            df, bad, checked=int(present.sum()),
            message=f"'{self.column}' must be one of: {allowed_preview}.",
            sample_columns=[self.column],
        )


class Regex(Rule):
    category = VALIDITY

    def __init__(self, rule_id, title, column, pattern, severity=ERROR, hint=""):
        super().__init__(rule_id, title, column=column, severity=severity)
        self.pattern = re.compile(pattern)
        self.hint = hint

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        values = df[self.column].astype("string")
        matches = values.fillna("").map(lambda v: bool(self.pattern.match(v)))
        bad = present & ~matches
        msg = f"'{self.column}' is malformed."
        if self.hint:
            msg += f" Expected {self.hint}."
        return self._result(df, bad, checked=int(present.sum()), message=msg,
                            sample_columns=[self.column])


class IntegerType(Rule):
    category = VALIDITY

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        parsed = pd.to_numeric(df[self.column], errors="coerce")
        is_int = parsed.notna() & (parsed == parsed.round())
        bad = present & ~is_int
        return self._result(
            df, bad, checked=int(present.sum()),
            message=f"'{self.column}' must be an integer.",
            sample_columns=[self.column],
        )


class NumericRange(Rule):
    category = VALIDITY

    def __init__(self, rule_id, title, column, min_value=None, max_value=None, severity=ERROR):
        super().__init__(rule_id, title, column=column, severity=severity)
        self.min_value = min_value
        self.max_value = max_value

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        parsed = pd.to_numeric(df[self.column], errors="coerce")
        bad = present & parsed.isna()  # unparseable numbers
        if self.min_value is not None:
            bad |= present & parsed.notna() & (parsed < self.min_value)
        if self.max_value is not None:
            bad |= present & parsed.notna() & (parsed > self.max_value)
        bounds = []
        if self.min_value is not None:
            bounds.append(f">= {self.min_value}")
        if self.max_value is not None:
            bounds.append(f"<= {self.max_value}")
        bound_txt = " and ".join(bounds) if bounds else "numeric"
        return self._result(
            df, bad, checked=int(present.sum()),
            message=f"'{self.column}' must be {bound_txt}.",
            sample_columns=[self.column],
        )


class BooleanType(Rule):
    category = VALIDITY

    _TRUE = {"true", "false", "1", "0", "t", "f", "yes", "no"}

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        values = df[self.column].astype("string").str.lower()
        bad = present & ~values.isin(self._TRUE)
        return self._result(
            df, bad, checked=int(present.sum()),
            message=f"'{self.column}' must be a boolean (True/False).",
            sample_columns=[self.column],
        )


class DateValid(Rule):
    """Parseable calendar date, optionally constrained to a plausible window."""

    category = VALIDITY

    def __init__(self, rule_id, title, column, not_future=True,
                 min_date=None, max_date=None, severity=ERROR):
        super().__init__(rule_id, title, column=column, severity=severity)
        self.not_future = not_future
        self.min_date = pd.Timestamp(min_date) if min_date else None
        self.max_date = pd.Timestamp(max_date) if max_date else None

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        present = _present(df[self.column])
        parsed = pd.to_datetime(df[self.column], errors="coerce")
        bad = present & parsed.isna()
        today = pd.Timestamp.today().normalize()
        if self.not_future:
            bad |= present & parsed.notna() & (parsed > today)
        if self.min_date is not None:
            bad |= present & parsed.notna() & (parsed < self.min_date)
        if self.max_date is not None:
            bad |= present & parsed.notna() & (parsed > self.max_date)
        return self._result(
            df, bad, checked=int(present.sum()),
            message=f"'{self.column}' must be a valid, plausible date.",
            sample_columns=[self.column],
        )


# ---------------------------------------------------------------------------
# Consistency (cross-field) — driven by a small callable
# ---------------------------------------------------------------------------
class Consistency(Rule):
    """Flags rows where a cross-field invariant is violated.

    ``failing_mask`` receives the DataFrame and returns a boolean Series that
    is ``True`` for rows that VIOLATE the rule. Rows with missing inputs should
    be excluded by the callable (completeness rules cover those separately).
    """

    category = CONSISTENCY

    def __init__(self, rule_id, title, failing_mask, columns, severity=ERROR):
        super().__init__(rule_id, title, column=", ".join(columns), severity=severity)
        self.failing_mask = failing_mask
        self.columns = list(columns)

    def evaluate(self, df, context=None):
        missing = [c for c in self.columns if c not in df.columns]
        if missing:
            return self._skipped(f"column(s) {missing} not present")
        mask = self.failing_mask(df).fillna(False)
        return self._result(
            df, mask, checked=len(df), message=self.title,
            sample_columns=self.columns,
        )


# ---------------------------------------------------------------------------
# Referential integrity (needs a parent table from the context)
# ---------------------------------------------------------------------------
class ForeignKey(Rule):
    category = INTEGRITY

    def __init__(self, rule_id, title, column, ref_table, ref_column, severity=ERROR):
        super().__init__(rule_id, title, column=column, severity=severity)
        self.ref_table = ref_table
        self.ref_column = ref_column

    def evaluate(self, df, context=None):
        if self.column not in df.columns:
            return self._missing_column()
        context = context or {}
        ref_df = context.get(self.ref_table)
        if ref_df is None:
            return self._skipped(
                f"reference table '{self.ref_table}' not provided "
                f"(upload it together to check this link)"
            )
        if self.ref_column not in ref_df.columns:
            return self._skipped(f"'{self.ref_column}' missing from '{self.ref_table}'")
        present = _present(df[self.column])
        valid_keys = set(ref_df[self.ref_column].dropna().astype("string"))
        values = df[self.column].astype("string")
        bad = present & ~values.isin(valid_keys)
        return self._result(
            df, bad, checked=int(present.sum()),
            message=f"'{self.column}' must reference an existing "
                    f"{self.ref_table}.{self.ref_column}.",
            sample_columns=[self.column],
        )
