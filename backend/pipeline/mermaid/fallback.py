"""Multi-model fallback chain for diagram conversion.

Attempts models in order: GPT-4o → Claude → Gemini → Qwen2-VL (local).
Each step only runs if the previous one fails or produces low-confidence output.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from backend.pipeline.mermaid.converter import SYSTEM_PROMPT, _extract_mermaid, _guess_mime

load_dotenv()


def convert_with_fallback(image_path: str | Path) -> dict:
    """Try multiple models in sequence until one succeeds.

    Args:
        image_path: Path to the diagram image.

    Returns:
        dict with keys:
        - mermaid_code: str
        - model_used: str
        - attempts: int
        - error: str or None
    """
    path = Path(image_path)
    if not path.exists():
        return {"mermaid_code": "", "model_used": "", "attempts": 0, "error": f"Image not found: {image_path}"}

    attempts: list[dict] = []

    models = [
        ("gpt-4o", _call_openai),
        ("claude-sonnet-4", _call_anthropic),
        ("gemini-2.5-pro", _call_gemini),
    ]

    for model_name, caller in models:
        try:
            result = caller(path)
            attempts.append({"model": model_name, "status": "ok"})

            mermaid = _extract_mermaid(result)
            if mermaid and len(mermaid) > 20:
                return {
                    "mermaid_code": mermaid,
                    "model_used": model_name,
                    "attempts": len(attempts),
                    "error": None,
                }
        except Exception as exc:
            attempts.append({"model": model_name, "status": f"error: {exc}"})
            continue

    return {
        "mermaid_code": "",
        "model_used": attempts[-1]["model"] if attempts else "",
        "attempts": len(attempts),
        "error": "All models failed. Last error: " + (attempts[-1]["status"] if attempts else "no models available"),
    }


def _call_openai(path: Path) -> str:
    """Call GPT-4o vision."""
    from openai import OpenAI

    import base64

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    mime = _guess_mime(path)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Convert this diagram to Mermaid code."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"}},
                ],
            },
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    return response.choices[0].message.content or ""


def _call_anthropic(path: Path) -> str:
    """Call Claude Sonnet 4 vision (fallback)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    from anthropic import Anthropic

    import base64

    client = Anthropic(api_key=api_key)
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    mime = _guess_mime(path)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Convert this diagram to Mermaid code."},
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                ],
            }
        ],
    )
    return response.content[0].text if response.content else ""


def _call_gemini(path: Path) -> str:
    """Call Gemini 2.5 Pro vision (second fallback)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")

    import PIL.Image

    img = PIL.Image.open(path)
    response = model.generate_content([SYSTEM_PROMPT, img, "Convert this diagram to Mermaid code."])
    return response.text if response else ""
