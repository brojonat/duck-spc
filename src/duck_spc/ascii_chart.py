"""ASCII XmR rendering for the terminal: BOOM, results in your face.

Hand-rolled canvas, zero dependencies — the chart stays inspectable and the
install stays light. ANSI color only when asked (the caller decides based on
TTY-ness); NO_COLOR is respected upstream.

Layout per group:

    ── region=us-east, service=checkout ────────────────────────
     335.2 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄●┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  UNPL
           ·  ·   ·  · ·   · ·    ·   ·  ·     ·  ·
     331.1 ──·──·─····──··──·──·····──··─··─····──··──  X̄
           ·   ··  ·    ·     ··  ·   ·· ·   ·   ·
     326.9 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  LNPL
           2026-01-01 ── dim = baseline ── 2026-03-11
    ✗ 2 signal point(s) — first 2026-02-10 (rule1)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

RESET = "\x1b[0m"
BLUE = "38;5;75"
RED = "1;38;5;203"
AMBER = "38;5;215"
GREEN = "38;5;78"
DIM = "2"
BOLD = "1"


def _paint(s: str, code: str | None, color: bool) -> str:
    return f"\x1b[{code}m{s}{RESET}" if color and code else s


def _is_signal(p: dict[str, Any], mr_rule: bool) -> bool:
    return bool(p["rule1"] or p["rule2"] or (mr_rule and p["rule_mr"]))


def render_group(
    entry: dict[str, Any],
    points: list[dict[str, Any]],
    *,
    baseline_window: tuple[str, str],
    width: int = 72,
    height: int = 12,
    color: bool = False,
    mr_rule: bool = False,
) -> tuple[str, bool]:
    """One group's X chart as text. `points` are evaluated rows, ts-ordered.

    Returns (text, has_signals).
    """
    base_end = datetime.fromisoformat(baseline_window[1])
    vals = [p["value"] for p in points]
    lo = min(min(vals), entry["lnpl"])
    hi = max(max(vals), entry["unpl"])
    pad = 0.06 * ((hi - lo) or 1.0)
    lo, hi = lo - pad, hi + pad

    # one column per point; if the stream is wider than the terminal, keep
    # the most interesting point per bucket (signals win, then excursion)
    per = max(1, math.ceil(len(points) / width))
    buckets = [points[i : i + per] for i in range(0, len(points), per)]

    def pick(bucket: list[dict[str, Any]]) -> dict[str, Any]:
        sigs = [p for p in bucket if _is_signal(p, mr_rule)]
        if sigs:
            return sigs[0]
        return max(bucket, key=lambda p: abs(p["value"] - entry["center"]))

    pts = [pick(b) for b in buckets]
    w, h = len(pts), height

    def row(v: float) -> int:
        return min(h - 1, max(0, round((hi - v) / (hi - lo) * (h - 1))))

    canvas = [[" "] * w for _ in range(h)]
    styles: list[list[str | None]] = [[None] * w for _ in range(h)]
    r_unpl, r_center, r_lnpl = row(entry["unpl"]), row(entry["center"]), row(entry["lnpl"])
    for x in range(w):
        for r, ch in ((r_unpl, "┄"), (r_lnpl, "┄"), (r_center, "─")):
            canvas[r][x], styles[r][x] = ch, DIM
    for x, p in enumerate(pts):
        r = row(p["value"])
        mr_only = mr_rule and p["rule_mr"] and not (p["rule1"] or p["rule2"])
        if _is_signal(p, mr_rule):
            ch, st = ("◆", AMBER) if mr_only else ("●", RED)
        elif p["ts"] < base_end:
            ch, st = "·", DIM
        else:
            ch, st = "·", BLUE
        canvas[r][x], styles[r][x] = ch, st

    labels = {
        r_unpl: f"{entry['unpl']:.4g}",
        r_center: f"{entry['center']:.4g}",
        r_lnpl: f"{entry['lnpl']:.4g}",
    }
    names = {r_unpl: "UNPL", r_center: "X̄", r_lnpl: "LNPL"}
    gutter = max(len(v) for v in labels.values())

    key = ", ".join(f"{k}={v}" for k, v in entry["key"].items())
    rule = "─" * max(4, width + gutter - len(key) - 4)
    lines = [_paint(f"── {key} {rule}", BOLD, color)]
    for r in range(h):
        body = "".join(_paint(c, styles[r][x], color) for x, c in enumerate(canvas[r]))
        label = labels.get(r, "").rjust(gutter)
        name = f"  {names[r]}" if r in names else ""
        lines.append(f" {_paint(label, DIM, color)} {body}{_paint(name, DIM, color)}")

    t0, t1 = pts[0]["ts"], pts[-1]["ts"]
    axis = f"{t0:%Y-%m-%d} ── dim = baseline, checked from {baseline_window[1]} ── {t1:%Y-%m-%d}"
    if per > 1:
        axis += f"  ({per} pts/col, signals kept)"
    lines.append(f" {' ' * gutter} {_paint(axis, DIM, color)}")

    checked = [p for p in points if p["ts"] >= base_end]
    sigs = [p for p in checked if _is_signal(p, mr_rule)]
    if sigs:
        first = sigs[0]
        rules = [
            r for r in ("rule1", "rule2", "rule_mr")
            if first.get(r) and (r != "rule_mr" or mr_rule)
        ]
        verdict = _paint(
            f" ✗ {len(sigs)} signal point(s) — first {first['ts']:%Y-%m-%d} ({', '.join(rules)})",
            RED, color,
        )
    else:
        verdict = _paint(
            f" ✓ stable — {len(checked)} points within natural process limits", GREEN, color
        )
    lines.append(verdict)
    return "\n".join(lines), bool(sigs)


def render_report(
    limits: Any,  # duck_spc.core.Limits (kept loose to avoid a cycle)
    points: list[dict[str, Any]],
    *,
    width: int = 72,
    height: int = 12,
    color: bool = False,
    mr_rule: bool = False,
) -> tuple[str, int, int]:
    """All groups, stacked, plus a one-line summary.

    Returns (text, unstable_groups, total_groups).
    """
    by_key: dict[tuple, list[dict[str, Any]]] = {}
    for p in points:
        by_key.setdefault(tuple(p[c] for c in limits.group_by), []).append(p)

    blocks, unstable = [], 0
    for entry in limits.groups:
        key = tuple(entry["key"].values())
        pts = sorted(by_key.get(key, []), key=lambda p: p["ts"])
        if not pts:
            continue
        block, has_signals = render_group(
            entry, pts, baseline_window=limits.baseline_window,
            width=width, height=height, color=color, mr_rule=mr_rule,
        )
        unstable += has_signals
        blocks.append(block)

    n = len(blocks)
    if unstable:
        summary = _paint(
            f"{unstable}/{n} group(s) show special-cause variation — go find the cause(s).",
            RED, color,
        )
    else:
        summary = _paint(
            f"all {n} group(s) stable — trust the statistics, go back to sleep.",
            GREEN, color,
        )
    return "\n\n".join(blocks) + f"\n\n{summary}", unstable, n
