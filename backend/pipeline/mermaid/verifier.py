"""Round-trip verification for Mermaid output.

Strategy: Mermaid → SVG → describe SVG with LLM → compare description
to original diagram description. If they diverge significantly, flag
for human review or trigger fallback.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI


def round_trip_verify(
    original_description: str,
    mermaid_code: str,
) -> dict:
    """Verify that the Mermaid code produces a diagram matching the original.

    Renders Mermaid to SVG, then asks a second LLM call to describe the SVG.
    Compares the two descriptions for consistency.

    Args:
        original_description: LLM's description of the original diagram.
        mermaid_code: The generated Mermaid code to verify.

    Returns:
        dict with keys:
        - passed: bool
        - match_score: float (0-100)
        - rendered_description: str
        - svg_path: str or None
        - error: str or None
    """
    # 1. Render Mermaid to SVG
    svg_path = _render_to_svg(mermaid_code)
    if svg_path is None:
        return {
            "passed": False,
            "match_score": 0.0,
            "rendered_description": "",
            "svg_path": None,
            "error": "Failed to render Mermaid to SVG (mmdc not available or syntax error).",
        }

    # 2. Ask LLM to describe the rendered SVG
    rendered_desc = _describe_svg(svg_path)

    if rendered_desc is None:
        return {
            "passed": False,
            "match_score": 0.0,
            "rendered_description": "",
            "svg_path": svg_path,
            "error": "Failed to describe rendered SVG.",
        }

    # 3. Compare descriptions — simple overlap heuristic
    from rapidfuzz import fuzz

    similarity = fuzz.token_sort_ratio(
        original_description.lower(),
        rendered_desc.lower(),
    )

    passed = similarity >= 60.0

    return {
        "passed": passed,
        "match_score": round(similarity, 1),
        "rendered_description": rendered_desc,
        "svg_path": svg_path,
        "error": None,
    }


def _render_to_svg(mermaid_code: str) -> str | None:
    """Render Mermaid code to SVG using mmdc (mermaid-cli)."""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".mmd", delete=False, dir="/tmp"
        ) as f:
            f.write(mermaid_code)
            mmd_path = f.name

        svg_path = mmd_path.replace(".mmd", ".svg")
        result = subprocess.run(
            ["mmdc", "-i", mmd_path, "-o", svg_path, "-e", "svg"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        Path(mmd_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return None

        if Path(svg_path).exists():
            return svg_path
        return None

    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _describe_svg(svg_path: str) -> str | None:
    """Ask an LLM to describe what the SVG diagram shows."""
    try:
        import base64

        client = OpenAI()
        path = Path(svg_path)
        b64 = base64.b64encode(path.read_bytes()).decode("utf-8")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this SVG diagram. List all nodes, their labels, relationships, arrows, and any text. Be thorough.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/svg+xml;base64,{b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1024,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""

    except Exception:
        return None
