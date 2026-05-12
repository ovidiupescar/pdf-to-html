"""CLIP-based diagram type classifier."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock

from PIL import Image

logger = logging.getLogger(__name__)

DIAGRAM_TYPES = [
    "flowchart",
    "UML class diagram",
    "BPMN business process diagram",
    "circuit schematic",
    "chemical structure",
    "UI wireframe",
    "block diagram",
    "sequence diagram",
    "photograph",
    "chart or graph",
]

_MODEL_ID = "openai/clip-vit-base-patch32"

# Module-level singletons. CLIP weights are ~600MB to load and tokenize —
# without caching, every figure in a PDF re-triggers the full
# from_pretrained() pipeline (398 weight shards), which looks like
# the server is in a loop.
_model = None
_processor = None
_load_failed = False
_load_lock = Lock()


def _load_model_once():
    """Load CLIP model + processor once, on first call, behind a lock."""
    global _model, _processor, _load_failed

    if _model is not None or _load_failed:
        return

    with _load_lock:
        if _model is not None or _load_failed:
            return
        try:
            from transformers import CLIPModel, CLIPProcessor

            logger.info("Loading CLIP model %s (first call)...", _MODEL_ID)
            _processor = CLIPProcessor.from_pretrained(_MODEL_ID)
            _model = CLIPModel.from_pretrained(_MODEL_ID)
            _model.eval()
            logger.info("CLIP model loaded.")
        except Exception as exc:
            logger.exception("CLIP model load failed: %s", exc)
            _load_failed = True


def classify_diagram(image_path: str | Path) -> tuple[str, float]:
    """Classify a figure image into a diagram type using CLIP.

    Returns:
        Tuple of (diagram_type, confidence_0_to_1).
        Returns ("unknown", 0.0) on any failure so the caller can fall
        back to the default Mermaid pipeline.
    """
    import torch

    _load_model_once()
    if _model is None or _processor is None:
        return "unknown", 0.0

    try:
        image = Image.open(image_path).convert("RGB")
        inputs = _processor(
            text=DIAGRAM_TYPES,
            images=image,
            return_tensors="pt",
            padding=True,
        )
        with torch.no_grad():
            outputs = _model(**inputs)
        probs = (
            outputs.logits_per_image.softmax(dim=1)
            .squeeze(0)
            .detach()
            .numpy()
        )

        best_idx = int(probs.argmax())
        return DIAGRAM_TYPES[best_idx], float(probs[best_idx])
    except Exception as exc:
        logger.warning("classify_diagram(%s) failed: %s", image_path, exc)
        return "unknown", 0.0
