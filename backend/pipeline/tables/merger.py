"""Multi-page table detection and merging."""

from __future__ import annotations

from typing import Any


def merge_table_fragments(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect and merge tables that span multiple PDF pages.

    Compares consecutive tables by column structure (count + header similarity).
    If they match, appends rows from the continuation to the first fragment.

    Args:
        tables: List of table element dicts, each with:
            - columns: list[str]
            - rows: list[list]
            - page_number: int

    Returns:
        Merged list of table elements — consecutive fragments are combined.
    """
    if not tables:
        return []

    merged: list[dict[str, Any]] = [tables[0].copy()]

    for table in tables[1:]:
        prev = merged[-1]

        # Check if consecutive pages
        prev_page = prev.get("page_number", 0) if isinstance(prev.get("page_number"), (int, float)) else 0
        curr_page = table.get("page_number", 0) if isinstance(table.get("page_number"), (int, float)) else 0
        is_next_page = (curr_page - prev_page) == 1

        # Check matching column structure
        prev_cols = [c.strip().lower() for c in prev.get("columns", [])]
        curr_cols = [c.strip().lower() for c in table.get("columns", [])]
        same_columns = prev_cols == curr_cols

        if is_next_page and same_columns:
            prev["rows"].extend(table.get("rows", []))
            prev.get("_merged_pages", []).append(curr_page)
        else:
            merged.append(table.copy())

    return merged
