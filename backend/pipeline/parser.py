"""Docling-based PDF parser — extracts text blocks, tables, and figures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter


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
        entry: dict[str, Any] = {
            "type": item.label.value if hasattr(item.label, "value") else str(item.label),
            "bbox": item.bbox.as_tuple() if item.bbox else None,
            "page_number": item.prov[0].page if item.prov else 0,
        }

        if hasattr(item, "text") and item.text:
            entry["text"] = item.text
            elements.append(entry)

        elif hasattr(item, "dataframe") and item.dataframe is not None:
            entry["dataframe"] = item.dataframe.to_dict(orient="records")
            entry["columns"] = list(item.dataframe.columns)
            elements.append(entry)

        elif hasattr(item, "image") and item.image:
            # Save cropped figure image
            fig_dir = Path(path).parent / "figures"
            fig_dir.mkdir(exist_ok=True)
            fig_path = fig_dir / f"figure_{len(elements)}.png"
            item.image.save(str(fig_path))
            entry["image_path"] = str(fig_path)
            elements.append(entry)

    return elements
