"""LaTeX-OCR for mathematical equation extraction."""

from __future__ import annotations

from pathlib import Path


def extract_equation(image_path: str | Path) -> dict:
    """Extract LaTeX from an equation image using LaTeX-OCR (pix2tex).

    Args:
        image_path: Path to cropped equation image.

    Returns:
        dict with:
        - latex: str (LaTeX code)
        - confidence: float
        - error: str or None
    """
    try:
        from pix2tex.cli import LatexOCR

        from PIL import Image

        model = LatexOCR()
        img = Image.open(str(image_path)).convert("RGB")
        latex = model(img)
        return {"latex": latex, "confidence": 0.0, "error": None}

    except ImportError:
        return {"latex": "", "confidence": 0.0, "error": "pix2tex not installed. Install with: pip install pix2tex"}
    except Exception as exc:
        return {"latex": "", "confidence": 0.0, "error": str(exc)}


def has_math_region(text_block: str) -> bool:
    """Heuristic check if a text block likely contains mathematics."""
    import re

    patterns = [
        r"∑|∫|∂|√|π|∞|Δ|λ|θ",
        r"[a-z]\^\{?\d",
        r"\\frac",
        r"\\sum",
        r"\\int",
        r"x\s*[=≡≈≠]\s*\d",
    ]
    return any(re.search(p, text_block) for p in patterns)
