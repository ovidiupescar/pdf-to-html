"""Jinja2 HTML assembly — converts parsed elements into a rendered HTML page."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def assemble_html(
    title: str,
    source_filename: str,
    page_count: int,
    elements: list[dict[str, Any]],
    output_path: str | Path,
    source_url: str | None = None,
) -> Path:
    """Assemble parsed elements into a complete HTML file.

    Args:
        title: Document title.
        source_filename: Original PDF filename.
        page_count: Number of pages in original PDF.
        elements: List of element dicts from the pipeline.
            Each element has:
            - type: "text" | "table" | "diagram" | "image" | "equation" | "bpmn"
            - Plus type-specific fields (text, mermaid_code, columns, rows, src, etc.)
        output_path: Where to write the HTML file.
        source_url: Optional link to original PDF.

    Returns:
        Path to the generated HTML file.
    """
    template = ENV.get_template("default.html")

    diagram_count = sum(1 for e in elements if e.get("type") == "diagram")

    html = template.render(
        title=title,
        source_filename=source_filename,
        page_count=page_count,
        diagram_count=diagram_count,
        elements=elements,
        source_url=source_url,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")

    return output
