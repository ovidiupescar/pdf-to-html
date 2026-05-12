"""Docling-based PDF parser — extracts text blocks, tables, and figures.

Compatible with Docling 2.x (iterate_items yields (item, level) tuples).

Figure extraction is best-effort with multiple fallbacks:
  1. Docling PictureItem.get_image(doc) — canonical path
  2. PictureItem bbox + PyMuPDF render — works when Docling generated
     no PIL but at least classified the region as a picture
  3. PyMuPDF whole-page image scan — finds embedded raster images that
     Docling's layout model may have missed entirely
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

logger = logging.getLogger(__name__)

# 2.0 ~= 144 DPI — high enough for GPT-4o vision to read diagram text.
_IMAGES_SCALE = 2.0

# Verbose dump of every iterate_items() element. Toggle via env to keep
# normal logs readable but flip on when figures go missing.
_DEBUG_DUMP = os.getenv("PDF2HTML_DEBUG_PARSER", "0") == "1"


def _build_converter() -> DocumentConverter:
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
    return item[0] if isinstance(item, tuple) else item


def _get_label(item: Any) -> str:
    item = _unpack(item)
    if hasattr(item, "label"):
        label = item.label
        if hasattr(label, "value"):
            return label.value
        return str(label)
    return "unknown"


def _get_text(item: Any) -> str | None:
    item = _unpack(item)
    if hasattr(item, "text") and item.text:
        return str(item.text)
    return None


def _get_dataframe(item: Any) -> Any | None:
    item = _unpack(item)
    if hasattr(item, "data") and item.data is not None:
        if hasattr(item.data, "export_to_dataframe"):
            return item.data.export_to_dataframe()
        import pandas as pd
        if isinstance(item.data, pd.DataFrame):
            return item.data
    return None


def _is_picture(item: Any) -> bool:
    item = _unpack(item)
    try:
        from docling_core.types.doc import PictureItem  # type: ignore
        if isinstance(item, PictureItem):
            return True
    except Exception:
        pass
    label = _get_label(item).lower()
    return label in {"picture", "figure", "chart", "image"}


def _docling_get_image(item: Any, doc: Any) -> Any | None:
    """Try Docling's own image accessors. Returns PIL or None."""
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
        if hasattr(img_attr, "save"):
            return img_attr

    return None


def _get_bbox(item: Any, doc: Any = None) -> tuple | None:
    """Return bbox as (x0, y0, x1, y1) in TOP-LEFT pixel coordinates,
    y0 < y1, ready for fitz.Rect.

    Docling-core BoundingBox uses CoordOrigin.BOTTOMLEFT by default
    (PDF native), so t > b in the input. We convert to TOPLEFT using
    the page height when needed.
    """
    item = _unpack(item)
    bbox = None
    page_no = None

    if hasattr(item, "prov") and item.prov:
        prov = item.prov[0]
        bbox = getattr(prov, "bbox", None)
        page_no = getattr(prov, "page_no", None) or getattr(prov, "page", None)
    if bbox is None:
        bbox = getattr(item, "bbox", None)

    if bbox is None:
        return None

    # Extract numeric edges.
    if hasattr(bbox, "l") and hasattr(bbox, "t") and hasattr(bbox, "r") and hasattr(bbox, "b"):
        l, t, r, b = float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)
    elif hasattr(bbox, "as_tuple"):
        l, t, r, b = (float(x) for x in bbox.as_tuple()[:4])
    elif isinstance(bbox, (tuple, list)) and len(bbox) >= 4:
        l, t, r, b = (float(x) for x in bbox[:4])
    else:
        return None

    origin = getattr(bbox, "coord_origin", None)
    origin_str = getattr(origin, "value", str(origin)) if origin is not None else "TOPLEFT"
    is_bottom_left = origin_str.upper() == "BOTTOMLEFT"

    if is_bottom_left and doc is not None and page_no is not None:
        try:
            page = doc.pages.get(int(page_no))
            ph = float(page.size.height)
            # BOTTOMLEFT: t > b. Convert: y_top = ph - t, y_bot = ph - b
            y0, y1 = ph - t, ph - b
        except Exception:
            # Fallback when we cannot get page height: assume already TOPLEFT.
            y0, y1 = min(t, b), max(t, b)
    else:
        y0, y1 = min(t, b), max(t, b)

    x0, x1 = min(l, r), max(l, r)
    return (x0, y0, x1, y1)


def _get_page_number(item: Any) -> int:
    item = _unpack(item)
    if hasattr(item, "prov") and item.prov:
        prov = item.prov[0]
        page = getattr(prov, "page_no", None)
        if page is None:
            page = getattr(prov, "page", None)
        if page is not None:
            return int(page)
    return 0


def _pymupdf_crop(pdf_path: Path, page_no: int, bbox: tuple | None,
                   out_path: Path) -> bool:
    """Render a page region via PyMuPDF and save to PNG.

    page_no is 1-based. bbox is in TOPLEFT pixel coords (x0, y0, x1, y1)
    with y0 < y1 — _get_bbox normalizes Docling's BOTTOMLEFT input.
    """
    try:
        import fitz  # PyMuPDF
    except Exception as exc:
        logger.warning("PyMuPDF unavailable: %s", exc)
        return False

    try:
        with fitz.open(str(pdf_path)) as doc:
            idx = max(0, int(page_no) - 1)
            if idx >= doc.page_count:
                return False
            page = doc[idx]

            mat = fitz.Matrix(_IMAGES_SCALE, _IMAGES_SCALE)

            if bbox is None:
                pix = page.get_pixmap(matrix=mat)
            else:
                x0, y0, x1, y1 = (float(v) for v in bbox[:4])
                rect = fitz.Rect(x0, y0, x1, y1) & page.rect
                if rect.is_empty or rect.width < 4 or rect.height < 4:
                    logger.warning(
                        "PyMuPDF crop degenerate for page %d bbox %s "
                        "(intersect=%s) — rendering full page instead",
                        page_no, bbox, rect)
                    pix = page.get_pixmap(matrix=mat)
                else:
                    pix = page.get_pixmap(matrix=mat, clip=rect)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(out_path))
            return True
    except Exception as exc:
        logger.warning("PyMuPDF crop failed for page %d bbox %s: %s",
                       page_no, bbox, exc)
        return False


def _bbox_iou(a: tuple, b: tuple) -> float:
    """Intersection-over-union for two (x0,y0,x1,y1) tuples."""
    ax0, ay0, ax1, ay1 = (float(x) for x in a[:4])
    bx0, by0, bx1, by1 = (float(x) for x in b[:4])
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    a_area = max(0.0, (ax1 - ax0)) * max(0.0, (ay1 - ay0))
    b_area = max(0.0, (bx1 - bx0)) * max(0.0, (by1 - by0))
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0.0


def _overlaps_existing(extra: dict, existing: list[tuple[int, tuple]],
                        iou_threshold: float = 0.3) -> bool:
    """True if `extra` figure overlaps any (page, bbox) in `existing`."""
    bbox = extra.get("bbox")
    page = extra.get("page_number")
    if bbox is None:
        return False
    for ep, eb in existing:
        if ep != page or eb is None:
            continue
        if _bbox_iou(bbox, eb) >= iou_threshold:
            return True
    return False


def _cluster_rects(rects: list, gap: float = 20.0) -> list:
    """Greedy spatial clustering: group rects whose bboxes touch or are
    closer than `gap` (PDF points). Returns merged Rects.

    Used to turn a soup of vector path bboxes into diagram-shaped regions.
    """
    import fitz
    remaining = [r for r in rects if r.width > 0 and r.height > 0]
    clusters: list = []
    while remaining:
        seed = remaining.pop(0)
        cluster = fitz.Rect(seed)
        grew = True
        while grew:
            grew = False
            still: list = []
            for r in remaining:
                expanded = fitz.Rect(cluster) + (-gap, -gap, gap, gap)
                if r.intersects(expanded):
                    cluster |= r
                    grew = True
                else:
                    still.append(r)
            remaining = still
        clusters.append(cluster)
    return clusters


def _pymupdf_page_image_fallback(pdf_path: Path, fig_dir: Path,
                                   starting_idx: int) -> list[dict[str, Any]]:
    """Last-resort scan for figures when Docling finds nothing.

    Two passes:
      1. Embedded raster images (page.get_images) — catches JPEGs/PNGs
         placed in the PDF.
      2. Vector drawings (page.get_drawings) — clustered into diagram-
         sized regions. Catches the technical-diagram case where the
         "figure" is just paths, rectangles, and text and Docling's
         layout model missed it.
    """
    try:
        import fitz
    except Exception:
        return []

    found: list[dict[str, Any]] = []
    idx = starting_idx
    try:
        with fitz.open(str(pdf_path)) as doc:
            for pno in range(doc.page_count):
                page = doc[pno]

                # Pass 1: embedded raster images
                for img_info in page.get_images(full=True):
                    xref = img_info[0]
                    try:
                        rects = page.get_image_rects(xref)
                    except Exception:
                        rects = []
                    if not rects:
                        continue
                    rect = rects[0]
                    if rect.width < 50 or rect.height < 50:
                        continue
                    fig_dir.mkdir(parents=True, exist_ok=True)
                    fig_path = fig_dir / f"figure_{idx}.png"
                    mat = fitz.Matrix(_IMAGES_SCALE, _IMAGES_SCALE)
                    try:
                        pix = page.get_pixmap(matrix=mat, clip=rect)
                        pix.save(str(fig_path))
                        found.append({
                            "type": "figure",
                            "image_path": str(fig_path),
                            "bbox": (rect.x0, rect.y0, rect.x1, rect.y1),
                            "page_number": pno + 1,
                            "source": "pymupdf_raster",
                        })
                        idx += 1
                        logger.info("PyMuPDF raster image on page %d", pno + 1)
                    except Exception as exc:
                        logger.debug("page.get_pixmap failed: %s", exc)

                # Pass 2: vector drawing clusters
                try:
                    drawings = page.get_drawings()
                except Exception as exc:
                    logger.debug("get_drawings failed on page %d: %s", pno + 1, exc)
                    drawings = []

                if not drawings:
                    continue

                draw_rects = []
                for d in drawings:
                    r = d.get("rect")
                    if r is None or r.is_empty:
                        continue
                    # Skip single thin lines and tiny shapes — likely
                    # rules or table borders, not diagrams.
                    if r.width < 5 and r.height < 5:
                        continue
                    draw_rects.append(fitz.Rect(r))

                if not draw_rects:
                    continue

                # Cluster nearby drawings; treat each cluster as one figure.
                clusters = _cluster_rects(draw_rects, gap=15.0)

                page_area = page.rect.get_area() or 1.0
                for cl in clusters:
                    cl = cl & page.rect
                    if cl.is_empty:
                        continue
                    area = cl.get_area()
                    # Require a substantial region — at least 3% of page,
                    # and at least 80x80 pt. Filters out single horizontal
                    # rules and inline glyphs.
                    if area / page_area < 0.03 or cl.width < 80 or cl.height < 80:
                        continue
                    # Also require it isn't basically the whole page (which
                    # would just be re-rendering the page).
                    if area / page_area > 0.85:
                        continue

                    fig_dir.mkdir(parents=True, exist_ok=True)
                    fig_path = fig_dir / f"figure_{idx}.png"
                    mat = fitz.Matrix(_IMAGES_SCALE, _IMAGES_SCALE)
                    # Pad a little so labels at the edges aren't clipped.
                    pad = 6.0
                    clip = fitz.Rect(
                        max(page.rect.x0, cl.x0 - pad),
                        max(page.rect.y0, cl.y0 - pad),
                        min(page.rect.x1, cl.x1 + pad),
                        min(page.rect.y1, cl.y1 + pad),
                    )
                    try:
                        pix = page.get_pixmap(matrix=mat, clip=clip)
                        pix.save(str(fig_path))
                        found.append({
                            "type": "figure",
                            "image_path": str(fig_path),
                            "bbox": (clip.x0, clip.y0, clip.x1, clip.y1),
                            "page_number": pno + 1,
                            "source": "pymupdf_vector",
                        })
                        idx += 1
                        logger.info(
                            "PyMuPDF vector cluster on page %d: "
                            "%.0fx%.0f pt (%.1f%% of page)",
                            pno + 1, clip.width, clip.height,
                            100.0 * area / page_area,
                        )
                    except Exception as exc:
                        logger.debug("vector cluster render failed: %s", exc)
    except Exception as exc:
        logger.warning("PyMuPDF page scan failed: %s", exc)
    return found


def parse_pdf(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    fig_dir = path.parent / "figures"

    logger.info("Parsing %s with Docling (images_scale=%s)", path.name, _IMAGES_SCALE)
    converter = _build_converter()
    result = converter.convert(str(path))
    doc = result.document

    # Diagnostic: count labels of everything iterate_items yields.
    label_counts: Counter[str] = Counter()
    picture_count_raw = 0
    elements: list[dict[str, Any]] = []
    figure_idx = 0

    for raw_item in doc.iterate_items():
        item = _unpack(raw_item)
        label = _get_label(item)
        label_counts[label] += 1

        is_pic = _is_picture(item)
        if is_pic:
            picture_count_raw += 1

        if _DEBUG_DUMP:
            logger.info(
                "  item label=%s picture=%s page=%s bbox=%s text=%r",
                label, is_pic,
                _get_page_number(item),
                _get_bbox(item, doc),
                (_get_text(item) or "")[:60],
            )

        # ── Figure / Picture items ────────────────────────────────────
        if is_pic:
            page_no = _get_page_number(item)
            bbox = _get_bbox(item, doc)
            fig_path = fig_dir / f"figure_{figure_idx}.png"

            # IMPORTANT: do NOT trust Docling's get_image() content.
            # On at least docling 2.93 / docling-core 2.75, a PictureItem
            # whose bbox covers a large diagram region returns the wrong
            # crop (often a footer logo). The bbox itself is reliable —
            # the image content is not. Render the bbox ourselves.
            saved = False
            if bbox is not None and _pymupdf_crop(path, page_no, bbox, fig_path):
                saved = True
                logger.info("Figure %d: PyMuPDF bbox crop saved (page %d bbox=%s)",
                            figure_idx, page_no, bbox)
            else:
                # Last resort: trust Docling's image (better than nothing,
                # and a few item types may still get it right).
                img = _docling_get_image(item, doc)
                if img is not None:
                    try:
                        fig_dir.mkdir(parents=True, exist_ok=True)
                        img.save(str(fig_path))
                        saved = True
                        logger.info("Figure %d: Docling image fallback (page %d)",
                                    figure_idx, page_no)
                    except Exception as exc:
                        logger.warning("Docling image save failed: %s", exc)

            if saved:
                elements.append(
                    {
                        "type": "figure",
                        "image_path": str(fig_path),
                        "bbox": bbox,
                        "page_number": page_no,
                    }
                )
                figure_idx += 1
                continue
            else:
                logger.warning(
                    "PictureItem on page %d could not be saved by any method",
                    page_no,
                )

        # ── Text items ──
        text = _get_text(item)
        if text:
            elements.append(
                {
                    "type": label or "text",
                    "text": text,
                    "bbox": _get_bbox(item, doc),
                    "page_number": _get_page_number(item),
                }
            )
            continue

        # ── Table items ──
        df = _get_dataframe(item)
        if df is not None:
            elements.append(
                {
                    "type": "table",
                    "dataframe": df.to_dict(orient="records"),
                    "columns": list(df.columns),
                    "bbox": _get_bbox(item, doc),
                    "page_number": _get_page_number(item),
                }
            )
            continue

    logger.info(
        "Docling labels seen: %s",
        ", ".join(f"{k}={v}" for k, v in label_counts.most_common()),
    )
    logger.info(
        "Docling produced %d raw PictureItems, %d saved as figures.",
        picture_count_raw, figure_idx,
    )

    # ── PyMuPDF fallback: catches diagrams Docling missed entirely.
    # Runs even when Docling found some figures — Docling often catches
    # the Infineon logo but misses the actual technical diagram. We
    # dedupe by spatial overlap so we don't double-count.
    logger.info("Running PyMuPDF fallback to catch missed figures")
    existing_regions: list[tuple[int, tuple]] = [
        (e["page_number"], e["bbox"])
        for e in elements
        if e.get("type") == "figure" and e.get("bbox") is not None
    ]
    extras = _pymupdf_page_image_fallback(path, fig_dir, starting_idx=figure_idx)
    kept = 0
    for extra in extras:
        if _overlaps_existing(extra, existing_regions):
            logger.info("  skip extra on page %d — overlaps existing figure",
                        extra["page_number"])
            continue
        elements.append(extra)
        figure_idx += 1
        kept += 1
    if kept:
        logger.info("PyMuPDF fallback added %d figure(s)", kept)
    elif not extras:
        logger.info("PyMuPDF found nothing additional.")

    logger.info(
        "Parsed %s: %d elements, %d figures total",
        path.name, len(elements), figure_idx,
    )
    return elements
