"""The orchestrator: run a profile's rules against a dataset."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .report import Report


class DataQualityChecker:
    """Runs every rule in a :class:`~app.engine.profiles.Profile`."""

    def __init__(self, profile):
        self.profile = profile

    def run(self, df: pd.DataFrame, context: Optional[dict] = None) -> Report:
        """Evaluate the profile against ``df``.

        ``context`` maps table name -> DataFrame and is used by referential
        integrity rules to resolve foreign keys. When a parent table is absent
        those rules report as *skipped* rather than failing.
        """
        df = df.reset_index(drop=True)
        results = [rule.evaluate(df, context) for rule in self.profile.rules]
        return Report(
            dataset=self.profile.key,
            dataset_title=self.profile.title,
            columns=list(df.columns),
            row_count=len(df),
            results=results,
        )
