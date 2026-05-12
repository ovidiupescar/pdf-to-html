"""Confidence scoring + element counting for Mermaid output."""

from __future__ import annotations

import re


def score_mermaid(mermaid_code: str, description: str | None = None) -> dict:
    """Score the quality of generated Mermaid code.

    Uses two signals:
    1. Self-rated confidence from the LLM (extracted from description)
    2. Element counting (nodes, edges, labels)

    Returns:
        dict with:
        - score: float (0-100)
        - node_count: int
        - edge_count: int
        - label_count: int
        - issues: list[str]
    """
    issues: list[str] = []

    node_count = len(re.findall(r"(?:^\s+[A-Za-z_]\w*\[|^\s+[A-Za-z_]\w*\(|^\s+[A-Za-z_]\w*\{)", mermaid_code, re.MULTILINE))
    edge_count = len(re.findall(r"--?>", mermaid_code))
    label_count = len(re.findall(r'\|[^|]+\|', mermaid_code))

    # Heuristic checks
    if node_count == 0:
        issues.append("No nodes detected in Mermaid code.")
    if edge_count > node_count * 3:
        issues.append(f"Unusually high edge-to-node ratio ({edge_count} edges vs {node_count} nodes).")
    if "flowchart" in mermaid_code.lower() and edge_count == 0:
        issues.append("Flowchart with no edges — likely incomplete.")
    if "```" in mermaid_code:
        issues.append("Code block markers still present in output.")

    # Self-confidence from description
    self_conf = 0.0
    if description:
        match = re.search(r"(?:confidence|CONFIDENCE)[:\s]+(\d{1,3})", description)
        if match:
            self_conf = min(float(match.group(1)), 100.0)

    # Composite score: weighted average of self-confidence and structural health
    structural_score = 100.0
    if node_count == 0:
        structural_score = 0.0
    elif node_count < 3:
        structural_score = 50.0
    if issues:
        structural_score -= len(issues) * 15.0
    structural_score = max(0.0, structural_score)

    combined = self_conf * 0.4 + structural_score * 0.6

    return {
        "score": round(combined, 1),
        "node_count": node_count,
        "edge_count": edge_count,
        "label_count": label_count,
        "issues": issues,
    }
