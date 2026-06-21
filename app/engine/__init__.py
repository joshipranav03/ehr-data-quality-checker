"""Data-quality rule engine.

The engine is intentionally decoupled from the web layer so it can be used
from the API, the CLI, a notebook, or a future batch job.
"""

from .rules import (  # noqa: F401
    COMPLETENESS,
    CONSISTENCY,
    INTEGRITY,
    UNIQUENESS,
    VALIDITY,
    ERROR,
    WARNING,
    RuleResult,
)
from .checker import DataQualityChecker  # noqa: F401
from .report import Report  # noqa: F401
