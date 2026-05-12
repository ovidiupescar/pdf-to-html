"""Docling-based PDF parser — extracts text blocks, tables, and figures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter


def _get_label(item: Any) -> str:
    """Extract the label/type from a Docling item, handling API changes."""
    # New Docling API: iterate_items yields (item, level) tuples
    if isinstance(item, tuple):
        item = item[0]

    if hasattr(item, "label"):
        label = item.label
        if hasattr(label, "value"):
            return label.value
        return str(label)

    # Fallback: try DocItemType enum
    if hasattr(item, "doc_type"):
        dt = item.doc_type
        if hasattr(dt, "value"):
            return dt.value
        return str(dt)

    return "unknown"


def _get_text(item: Any) -> str | None:
    """Extract text from a Docling item, handling API changes."""
    if isinstance(item, tuple):
        item = item[0]
    if hasattr(item, "text") and item.text:
        return item.text
    return None


def _get_dataframe(item: Any) -> Any | None:
    """Extract dataframe from a Docling item."""
    if isinstance(item, tuple):
        item = item[0]
    if hasattr(item, "dataframe") and item.dataframe is not None:
        return item.dataframe
    return None


def _get_image(item: Any) -> Any | None:
    """Extract image from a Docling item."""
    if isinstance(item, tuple):
        item = item[0]
    if hasattr(item, "image") and item.image:
        return item.image
    return None


def _get_bbox(item: Any) -> tuple | None:
    """Extract bounding box from a Docling item."""
    if isinstance(item, tuple):
        item = item[0]
    if hasattr(item, "bbox") and item.bbox:
        if hasattr(item.bbox, "as_tuple"):
            return item.bbox.as_tuple()
        return item.bbox
    return None


def _get_page_number(item: Any) -> int:
    """Extract page number from a Docling item."""
    if isinstance(item, tuple):
        item = item[0]
    if hasattr(item, "prov") and item.prov:
        prov = item.prov[0]
        if hasattr(prov, "page"):
            return prov.page
    return 0


def parse_pdf(path: str | Path) -> list[dict[str, Any]]:
    """Parse a PDF into structured elements using Docling.

    Returns:
        List of element dicts, each with:
        - type: "text" | "table" | "figure"
        - text / dataframe / image_path (depending on type)
        - bbox: bounding box [x1, y1, x2, y2]
        - page_number: int
    """
    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document

    elements: list[dict[str, Any]] = []

    for item in doc.iterate_items():
        label = _get_label(item)
        entry: dict[str, Any] = {
            "type": label,
            "bbox": _get_bbox(item),
            "page_number": _get_page_number(item),
        }

        text = _get_text(item)
        if text:
            entry["text"] = text
            elements.append(entry)
            continue

        df = _get_dataframe(item)
        if df is not None:
            entry["dataframe"] = df.to_dict(orient="records")
            entry["columns"] = list(df.columns)
            elements.append(entry)
            continue

        img = _get_image(item)
        if img is not None:
            # Save cropped figure image
            fig_dir = Path(path).parent / "figures"
            fig_dir.mkdir(exist_ok=True)
            fig_path = fig_dir / f"figure_{len(elements)}.png"
            img.save(str(fig_path))
            entry["image_path"] = str(fig_path)
            elements.append(entry)
            continue

    return elements