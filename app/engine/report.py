"""Aggregation and scoring of rule results into a quality report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .rules import (
    COMPLETENESS,
    CONSISTENCY,
    ERROR,
    INTEGRITY,
    UNIQUENESS,
    VALIDITY,
    WARNING,
    RuleResult,
)

# Errors weigh more than warnings when scoring overall quality.
SEVERITY_WEIGHT = {ERROR: 1.0, WARNING: 0.4}

DIMENSIONS = [COMPLETENESS, VALIDITY, UNIQUENESS, CONSISTENCY, INTEGRITY]


def _grade(score: float) -> str:
    if score >= 97:
        return "A+"
    if score >= 93:
        return "A"
    if score >= 90:
        return "A-"
    if score >= 85:
        return "B"
    if score >= 75:
        return "C"
    if score >= 60:
        return "D"
    return "F"


@dataclass
class Report:
    dataset: str
    dataset_title: str
    columns: list[str]
    row_count: int
    results: list[RuleResult]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    # ----- derived metrics -------------------------------------------------
    @property
    def active(self) -> list[RuleResult]:
        """Rules that actually ran (not skipped)."""
        return [r for r in self.results if not r.skipped]

    def _score(self) -> float:
        weighted_checked = 0.0
        weighted_failed = 0.0
        for r in self.active:
            w = SEVERITY_WEIGHT.get(r.severity, 1.0)
            weighted_checked += r.checked * w
            weighted_failed += r.failed * w
        if weighted_checked == 0:
            return 100.0
        score = round(100.0 * (1 - weighted_failed / weighted_checked), 1)
        # A perfect 100 should mean genuinely zero issues; otherwise floor the
        # display so rounding can't hide a handful of bad records.
        if weighted_failed > 0 and score >= 100.0:
            return 99.9
        return score

    def _category_scores(self) -> dict:
        out = {}
        for dim in DIMENSIONS:
            rules = [r for r in self.active if r.category == dim]
            checked = sum(r.checked for r in rules)
            failed = sum(r.failed for r in rules)
            score = None
            if checked:
                score = round(100.0 * (1 - failed / checked), 1)
                if failed > 0 and score >= 100.0:
                    score = 99.9
            out[dim] = {
                "rules": len(rules),
                "checked": checked,
                "failed": failed,
                "score": score,
            }
        return out

    def _rows_with_errors(self) -> int:
        bad: set[int] = set()
        for r in self.active:
            if r.severity == ERROR:
                bad.update(r.failed_indices)
        return len(bad)

    def to_dict(self) -> dict:
        score = self._score()
        rows_with_errors = self._rows_with_errors()
        total_issues = sum(r.failed for r in self.active)
        errors = sum(r.failed for r in self.active if r.severity == ERROR)
        warnings = sum(r.failed for r in self.active if r.severity == WARNING)
        clean_rows = self.row_count - rows_with_errors
        return {
            "dataset": self.dataset,
            "dataset_title": self.dataset_title,
            "generated_at": self.generated_at,
            "row_count": self.row_count,
            "column_count": len(self.columns),
            "columns": self.columns,
            "summary": {
                "score": score,
                "grade": _grade(score),
                "total_issues": total_issues,
                "errors": errors,
                "warnings": warnings,
                "rules_total": len(self.results),
                "rules_run": len(self.active),
                "rules_passed": sum(1 for r in self.active if r.passed),
                "rules_failed": sum(1 for r in self.active if not r.passed),
                "rules_skipped": sum(1 for r in self.results if r.skipped),
                "rows_with_errors": rows_with_errors,
                "clean_rows": clean_rows,
                "clean_row_pct": round(100.0 * clean_rows / self.row_count, 1)
                if self.row_count
                else 100.0,
            },
            "dimensions": self._category_scores(),
            "results": [r.to_dict() for r in self.results],
        }
