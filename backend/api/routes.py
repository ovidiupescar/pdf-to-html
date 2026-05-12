"""API routes for PDF-to-HTML conversion."""

from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.api.schemas import ConvertResponse, ErrorResponse, JobInfo, JobStatus
from backend.pipeline.classifier import classify_diagram
from backend.pipeline.html.assembler import assemble_html
from backend.pipeline.mermaid.converter import convert_diagram_to_mermaid
from backend.pipeline.parser import parse_pdf
from backend.pipeline.pre_validation import validate_pdf

logger = logging.getLogger(__name__)

router = APIRouter()
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job store (replace with Redis/Celery in production)
_jobs: dict[str, JobInfo] = {}

_HEADING_PATTERNS = re.compile(
    r"^(\d+[\.\)]\s|Chapter\s|\d+\s+[A-Z]|NOTE:|WARNING:|IMPORTANT:|#{1,6}\s)",
    re.IGNORECASE,
)


def _process_pdf_background(
    job_id: str,
    file_path: Path,
    upload_dir: Path,
    original_filename: str,
) -> None:
    job = _jobs[job_id]
    try:
        _jobs[job_id] = job.model_copy(
            update={"status": JobStatus.processing, "progress": 5}
        )

        validation = validate_pdf(file_path)
        if not validation.valid:
            _jobs[job_id] = job.model_copy(
                update={
                    "status": JobStatus.failed,
                    "error": validation.error,
                    "progress": 0,
                }
            )
            return

        page_count = validation.page_count
        _jobs[job_id] = _jobs[job_id].model_copy(
            update={"page_count": page_count, "progress": 15}
        )

        raw_elements = parse_pdf(file_path)

        transformed: list[dict] = []
        for elem in raw_elements:
            transformed.append(_transform_element(elem, upload_dir, job_id))

        _jobs[job_id] = _jobs[job_id].model_copy(update={"progress": 80})

        output_html_path = upload_dir / "output.html"
        assemble_html(
            title="Converted Document",
            source_filename=original_filename,
            page_count=page_count,
            elements=transformed,
            output_path=output_html_path,
        )

        _jobs[job_id] = _jobs[job_id].model_copy(
            update={
                "status": JobStatus.completed,
                "progress": 100,
                "download_url": f"/api/download/{job_id}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "diagram_count": sum(
                    1 for e in transformed if e.get("type") in ("diagram", "image")
                ),
            }
        )
        logger.info("Job %s completed successfully", job_id)

    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        _jobs[job_id] = _jobs[job_id].model_copy(
            update={
                "status": JobStatus.failed,
                "error": str(exc),
                "progress": 0,
            }
        )


def _transform_element(
    elem: dict, upload_dir: Path, job_id: str
) -> dict:
    if "text" in elem:
        text = elem["text"]
        is_heading = (
            len(text) < 80 and text.strip().isupper()
        ) or bool(_HEADING_PATTERNS.match(text.strip()))

        if is_heading:
            return {
                "type": "text",
                "text": text,
                "style": "heading",
                "level": 2,
            }
        return {
            "type": "text",
            "text": text,
        }

    if "dataframe" in elem:
        records = elem["dataframe"]
        columns = elem.get("columns", [])
        rows = [[str(rec.get(col, "")) for col in columns] for rec in records]
        return {
            "type": "table",
            "columns": columns,
            "rows": rows,
        }

    if "image_path" in elem:
        image_path = Path(elem["image_path"])
        diagram_type, clip_confidence = classify_diagram(image_path)
        mermaid_result = convert_diagram_to_mermaid(image_path)
        # CLIP returns 0-1 probability; template expects 0-100
        confidence = round(clip_confidence * 100)

        if "error" in mermaid_result:
            rel = image_path.relative_to(upload_dir.parent.parent)
            return {
                "type": "image",
                "src": f"/output/{rel}",
            }

        return {
            "type": "diagram",
            "id": str(uuid.uuid4()),
            "diagram_type": diagram_type,
            "confidence": confidence,
            "mermaid_code": mermaid_result["mermaid_code"],
            "model_used": "gpt-4o",
        }

    return {"type": "text", "text": str(elem)}


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
        created_at=datetime.now(timezone.utc).isoformat(),
        progress=0,
    )

    threading.Thread(
        target=_process_pdf_background,
        args=(job_id, upload_path, upload_path.parent, file.filename),
        daemon=True,
    ).start()

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
