"""Docling-based PDF parser — extracts text blocks, tables, and figures.

Compatible with Docling 2.x (iterate_items yields (item, level) tuples).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter


def _unpack(item: Any) -> Any:
    """Unpack (item, level) tuple if needed."""
    return item[0] if isinstance(item, tuple) else item


def _get_label(item: Any) -> str:
    """Extract the label/type from a Docling item."""
    item = _unpack(item)
    if hasattr(item, "label"):
        label = item.label
        if hasattr(label, "value"):
            return label.value
        return str(label)
    return "unknown"


def _get_text(item: Any) -> str | None:
    """Extract text from a Docling item."""
    item = _unpack(item)
    if hasattr(item, "text") and item.text:
        return str(item.text)
    return None


def _get_dataframe(item: Any) -> Any | None:
    """Extract pandas DataFrame from a Docling TableItem."""
    item = _unpack(item)
    # Docling 2.x: TableItem.data (TableData) with export_to_dataframe()
    if hasattr(item, "data") and item.data is not None:
        if hasattr(item.data, "export_to_dataframe"):
            return item.data.export_to_dataframe()
        # Fallback: might be a raw DataFrame
        import pandas as pd
        if isinstance(item.data, pd.DataFrame):
            return item.data
    return None


def _get_image(item: Any) -> Any | None:
    """Extract PIL Image from a Docling PictureItem."""
    item = _unpack(item)
    if hasattr(item, "image") and item.image is not None:
        return item.image
    return None


def _get_bbox(item: Any) -> tuple | None:
    """Extract bounding box from a Docling item."""
    item = _unpack(item)
    if hasattr(item, "bbox") and item.bbox:
        if hasattr(item.bbox, "as_tuple"):
            return item.bbox.as_tuple()
        return item.bbox
    return None


def _get_page_number(item: Any) -> int:
    """Extract page number from a Docling item."""
    item = _unpack(item)
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

    for raw_item in doc.iterate_items():
        item = _unpack(raw_item)
        label = _get_label(item)

        # ── Text items ──
        text = _get_text(item)
        if text:
            elements.append(
                {
                    "type": label or "text",
                    "text": text,
                    "bbox": _get_bbox(item),
                    "page_number": _get_page_number(item),
                }
            )
            continue

        # ── Table items (Docling 2.x: item.data = TableData) ──
        df = _get_dataframe(item)
        if df is not None:
            elements.append(
                {
                    "type": "table",
                    "dataframe": df.to_dict(orient="records"),
                    "columns": list(df.columns),
                    "bbox": _get_bbox(item),
                    "page_number": _get_page_number(item),
                }
            )
            continue

        # ── Figure / Picture items ──
        img = _get_image(item)
        if img is not None:
            # Save cropped figure image
            fig_dir = Path(path).parent / "figures"
            fig_dir.mkdir(parents=True, exist_ok=True)
            fig_path = fig_dir / f"figure_{len(elements)}.png"
            img.save(str(fig_path))
            elements.append(
                {
                    "type": "figure",
                    "image_path": str(fig_path),
                    "bbox": _get_bbox(item),
                    "page_number": _get_page_number(item),
                }
            )
            continue

    return elements