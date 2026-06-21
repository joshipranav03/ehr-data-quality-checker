"""Pydantic response models — used to document the API in OpenAPI/Swagger.

The full report payload is dynamic, so it is typed loosely as a dict with a
documented example rather than an exhaustive schema.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    profiles: int = Field(..., description="Number of supported EHR datasets")


class RuleMeta(BaseModel):
    rule_id: str
    title: str
    category: str
    severity: str
    column: Optional[str] = None


class ProfileMeta(BaseModel):
    key: str
    title: str
    description: str
    id_column: str
    columns: list[str]
    parent_tables: list[str]
    rule_count: int
    rules: list[RuleMeta]


class SamplesResponse(BaseModel):
    datasets: list[str]
    samples: dict[str, list[str]]


class ErrorResponse(BaseModel):
    detail: str


# The report payload is intentionally an open object; this documents its shape.
class Report(BaseModel):
    dataset: str
    dataset_title: str
    generated_at: str
    row_count: int
    column_count: int
    columns: list[str]
    summary: dict[str, Any]
    dimensions: dict[str, Any]
    results: list[dict[str, Any]]
    auto_detected: Optional[bool] = None
    variant: Optional[str] = None
