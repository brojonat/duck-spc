"""Small helpers shared across tests."""

from typing import Any


def by_group(
    rows: list[dict[str, Any]], group_cols: tuple[str, ...]
) -> dict[tuple, list[dict[str, Any]]]:
    """Bucket rows by their group key, preserving ts order within each group."""
    out: dict[tuple, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(tuple(r[c] for c in group_cols), []).append(r)
    for pts in out.values():
        pts.sort(key=lambda p: p["ts"])
    return out
