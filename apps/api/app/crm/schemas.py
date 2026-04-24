"""Pydantic-схемы CRM endpoints."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CreateMockConnectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PatchConnectionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class DeleteConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ExportEstimateRequest(BaseModel):
    date_from: date
    date_to: date


class FullExportRequest(BaseModel):
    date_from: date
    date_to: date
    pipeline_ids: list[str] = Field(default_factory=list)


class JobCreatedResponse(BaseModel):
    job_id: str
