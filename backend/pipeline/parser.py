"""Docling-based PDF parser — extracts text blocks, tables, and figures.

Compatible with Docling 2.x (iterate_items yields (item, level) tuples).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

logger = logging.getLogger(__name__)

# 2.0 ~= 144 DPI — high enough for GPT-4o vision to read diagram text.
_IMAGES_SCALE = 2.0


def _build_converter() -> DocumentConverter:
    """Build a converter that emits cropped picture images.

    Docling's default pipeline does NOT generate picture image data:
    PictureItems are detected but their image refs stay empty, so
    `item.image` / `get_image(doc)` return None and figures are silently
    dropped. We must enable `generate_picture_images` and keep page
    bitmaps at sufficient resolution via `images_scale`.
    """
    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = _IMAGES_SCALE
    pipeline_options.generate_picture_images = True
    pipeline_options.generate_page_images = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


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


def _get_image(item: Any, doc: Any) -> Any | None:
    """Extract a PIL Image from a Docling PictureItem.

    With `generate_picture_images=True`, Docling 2.x stores images as
    ImageRef objects (not raw PIL). `PictureItem.get_image(doc)` is the
    canonical accessor; older fallbacks kept for safety across versions.
    """
    item = _unpack(item)

    get_image = getattr(item, "get_image", None)
    if callable(get_image):
        try:
            pil = get_image(doc)
            if pil is not None:
                return pil
        except Exception as exc:
            logger.debug("get_image(doc) failed: %s", exc)

    img_attr = getattr(item, "image", None)
    if img_attr is not None:
        pil = getattr(img_attr, "pil_image", None)
        if pil is not None:
            return pil
        if hasattr(img_attr, "save"):  # raw PIL on older versions
            return img_attr

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
    converter = _build_converter()
    result = converter.convert(str(path))
    doc = result.document

    elements: list[dict[str, Any]] = []
    figure_idx = 0

    for raw_item in doc.iterate_items():
        item = _unpack(raw_item)
        label = _get_label(item)

        # ── Figure / Picture items ────────────────────────────────────
        # Check images BEFORE text, because some PictureItems also carry
        # caption text — we want the figure, not the caption swallowing it.
        img = _get_image(item, doc)
        if img is not None:
            fig_dir = Path(path).parent / "figures"
            fig_dir.mkdir(parents=True, exist_ok=True)
            fig_path = fig_dir / f"figure_{figure_idx}.png"
            try:
                img.save(str(fig_path))
                elements.append(
                    {
                        "type": "figure",
                        "image_path": str(fig_path),
                        "bbox": _get_bbox(item),
                        "page_number": _get_page_number(item),
                    }
                )
                figure_idx += 1
                continue
            except Exception as exc:
                logger.warning("Failed to save figure %d: %s", figure_idx, exc)

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

    logger.info(
        "Parsed %s: %d elements (%d figures)",
        Path(path).name,
        len(elements),
        figure_idx,
    )
    return elements