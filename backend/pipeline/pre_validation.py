"""Pre-validation gate for PDF documents."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF


class ValidationResult:
    """Result of PDF pre-validation."""

    def __init__(
        self,
        valid: bool,
        pdf_type: Literal["native", "scanned", "encrypted"] = "native",
        page_count: int = 0,
        error: str | None = None,
    ):
        self.valid = valid
        self.pdf_type = pdf_type
        self.page_count = page_count
        self.error = error


def validate_pdf(path: str | Path) -> ValidationResult:
    """Inspect a PDF before processing.

    Checks:
    - Is it encrypted? → fail with "Please decrypt"
    - Is it >200 pages? → fail with "Split file"
    - Is it scanned (no embedded text)? → route to OCR
    - Otherwise → native PDF, proceed to Docling

    Returns:
        ValidationResult with status and metadata.
    """
    path = Path(path)
    if not path.exists():
        return ValidationResult(valid=False, error="File not found.")

    doc = fitz.open(str(path))

    # Check encryption
    if doc.is_encrypted:
        doc.close()
        return ValidationResult(valid=False, pdf_type="encrypted", error="PDF is encrypted. Please decrypt first.")

    page_count = doc.page_count

    # Check page limit
    if page_count > 200:
        doc.close()
        return ValidationResult(
            valid=False, pdf_type="native", page_count=page_count,
            error=f"PDF has {page_count} pages (max 200). Please split the file.",
        )

    # Check if scanned (no extractable text on first 3 pages)
    text_pages = 0
    for i in range(min(3, page_count)):
        text = doc[i].get_text().strip()
        if len(text) > 50:
            text_pages += 1

    doc.close()

    if text_pages == 0 and page_count > 0:
        return ValidationResult(valid=True, pdf_type="scanned", page_count=page_count)
    else:
        return ValidationResult(valid=True, pdf_type="native", page_count=page_count)
