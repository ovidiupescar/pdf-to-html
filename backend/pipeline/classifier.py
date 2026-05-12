"""CLIP-based diagram type classifier."""

from pathlib import Path

import torch
from PIL import Image

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


def classify_diagram(image_path: str | Path) -> tuple[str, float]:
    """Classify a figure image into a diagram type using CLIP.

    Returns:
        Tuple of (diagram_type, confidence).
        diagram_type is one of DIAGRAM_TYPES or "unknown".
    """
    try:
        from transformers import CLIPModel, CLIPProcessor
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    except Exception:
        return "unknown", 0.0

    image = Image.open(image_path).convert("RGB")
    inputs = processor(text=DIAGRAM_TYPES, images=image, return_tensors="pt", padding=True)
    outputs = model(**inputs)
    probs = outputs.logits_per_image.softmax(dim=1).squeeze(0).detach().numpy()

    best_idx = probs.argmax()
    best_type = DIAGRAM_TYPES[best_idx]
    best_score = float(probs[best_idx])

    return best_type, best_score
