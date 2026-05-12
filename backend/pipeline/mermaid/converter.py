"""GPT-4o vision → Mermaid code conversion."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

SYSTEM_PROMPT = """You are a diagram-to-Mermaid converter. Given a diagram image:

1. First, describe what you see — identify shapes, labels, arrows, and structure.
2. Then, generate valid Mermaid.js code that reproduces the diagram.
3. Use the correct Mermaid diagram type: flowchart TD, sequenceDiagram, classDiagram, erDiagram, etc.
4. Preserve all text labels, arrow directions, and node relationships.
5. If the diagram has colors that carry meaning, preserve them with Mermaid classDef styles.
6. Output ONLY valid Mermaid code inside ```mermaid ... ``` blocks.
7. If the diagram type cannot be represented in Mermaid, state why and suggest an alternative format."""


def convert_diagram_to_mermaid(image_path: str | Path) -> dict:
    """Convert a diagram image to Mermaid code using GPT-4o vision.

    Args:
        image_path: Path to the diagram image file.

    Returns:
        dict with keys:
            - mermaid_code: str (Mermaid syntax)
            - description: str (what the LLM saw)
            - raw_response: str (full LLM response)
            - confidence: float (0-100, self-rated)
        On error:
            - error: str describing the failure
    """
    path = Path(image_path)
    if not path.exists():
        return {"error": f"Image not found: {image_path}"}

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set in .env"}

    try:
        client = OpenAI(api_key=api_key)
        import base64

        image_bytes = path.read_bytes()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = _guess_mime(path)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Convert this diagram to Mermaid code."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_tokens=4096,
            temperature=0.1,
        )

        raw = response.choices[0].message.content or ""
        mermaid_code = _extract_mermaid(raw)
        description = _extract_description(raw)
        confidence = _extract_confidence(raw)

        return {
            "mermaid_code": mermaid_code,
            "description": description,
            "raw_response": raw,
            "confidence": confidence,
        }

    except Exception as exc:
        return {"error": f"GPT-4o API error: {exc}"}


def _guess_mime(path: Path) -> str:
    """Guess MIME type from file extension."""
    ext = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/png")


def _extract_mermaid(text: str) -> str:
    """Extract Mermaid code block from LLM response."""
    import re

    match = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Fallback: try PlantUML or anything between ``` ... ```
    match = re.search(r"```(?:\w+)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


def _extract_description(text: str) -> str:
    """Extract the natural-language description (before the code block)."""
    import re

    match = re.split(r"```", text, maxsplit=1)
    return match[0].strip() if match else ""


def _extract_confidence(text: str) -> float:
    """Try to extract a self-rated confidence score from the response."""
    import re

    match = re.search(r"(?:confidence|CONFIDENCE)[:\s]+(\d{1,3})", text)
    if match:
        return min(float(match.group(1)), 100.0)
    return 0.0
