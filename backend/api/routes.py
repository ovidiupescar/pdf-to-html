"""API routes for PDF-to-HTML conversion."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.api.schemas import ConvertResponse, ErrorResponse, JobInfo, JobStatus

router = APIRouter()
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job store (replace with Redis/Celery in production)
_jobs: dict[str, JobInfo] = {}


@router.post(
    "/convert",
    response_model=ConvertResponse,
    responses={400: {"model": ErrorResponse}},
)
async def convert_pdf(file: UploadFile = File(...)):
    """Upload a PDF for conversion to HTML.

    The PDF is validated, queued for processing, and a job ID is returned.
    Use GET /status/{job_id} to poll for completion.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    job_id = str(uuid.uuid4())
    content = await file.read()

    # Save the uploaded file
    upload_path = OUTPUT_DIR / job_id / "input.pdf"
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(content)

    _jobs[job_id] = JobInfo(
        job_id=job_id,
        status=JobStatus.queued,
        filename=file.filename,
        created_at=str(uuid.uuid4()),  # placeholder — use datetime
        progress=0,
    )

    return ConvertResponse(job_id=job_id)


@router.get(
    "/status/{job_id}",
    response_model=JobInfo,
    responses={404: {"model": ErrorResponse}},
)
async def get_status(job_id: str):
    """Get the current status of a conversion job."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get(
    "/download/{job_id}",
    responses={404: {"model": ErrorResponse}},
)
async def download_result(job_id: str):
    """Download the converted HTML file."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != JobStatus.completed:
        raise HTTPException(status_code=400, detail="Job not yet completed.")

    html_path = OUTPUT_DIR / job_id / "output.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found.")

    return FileResponse(
        html_path,
        media_type="text/html",
        filename=f"{Path(job.filename).stem}.html",
    )
