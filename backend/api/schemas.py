"""Pydantic schemas for the PDF-to-HTML API."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Processing status of a conversion job."""

    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ConvertResponse(BaseModel):
    """Response returned immediately after submitting a PDF."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(default=JobStatus.queued)
    message: str = Field(default="PDF queued for processing.")


class JobInfo(BaseModel):
    """Detailed status of a conversion job."""

    job_id: str
    status: JobStatus
    filename: str
    page_count: Optional[int] = None
    diagram_count: Optional[int] = None
    created_at: str
    completed_at: Optional[str] = None
    error: Optional[str] = None
    download_url: Optional[str] = None
    progress: int = Field(default=0, ge=0, le=100)
    message: str = Field(default="")


class ErrorResponse(BaseModel):
    """Error response body."""

    detail: str
    code: str | None = None
