"""XmR chart rendering: X chart + mR chart pair, matplotlib Agg.

Doctrine: values as a connected line with dots, center solid, limits
dashed, signals in red, baseline window shaded — a chart whose limits
can't be traced to a baseline is just decoration.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

if TYPE_CHECKING:
    from duck_spc.core import Limits

BLUE, RED, GREY, AMBER = "#4c9be8", "#e85d5d", "#777777", "#e8a33d"


def render_xmr(
    limits: Limits,
    entry: dict[str, Any],
    points: list[dict[str, Any]],
    out: Path,
    mr_rule: bool = False,
) -> Path:
    """Render one group's evaluated points against its frozen limits."""
    if not points:
        raise ValueError(f"no points to chart for group {entry['key']!r}")
    ts = [p["ts"] for p in points]
    xs = [p["value"] for p in points]
    x_flag = [p["rule1"] or p["rule2"] for p in points]
    mrs = [p["mr"] for p in points]
    mr_flag = [bool(p["rule_mr"]) for p in points]

    b0, b1 = (datetime.fromisoformat(t) for t in limits.baseline_window)
    title_key = ", ".join(f"{k}={v}" for k, v in entry["key"].items())

    fig, (ax_x, ax_mr) = plt.subplots(
        2, 1, figsize=(11, 6.5), sharex=True, height_ratios=[2, 1]
    )

    # X chart
    ax_x.plot(ts, xs, marker="o", ms=3.2, lw=1, color=BLUE, zorder=2)
    flagged = [(t, v) for t, v, f in zip(ts, xs, x_flag, strict=True) if f]
    if flagged:
        ax_x.plot(*zip(*flagged, strict=True), "o", ms=6, color=RED, zorder=3)
    ax_x.axhline(entry["center"], color=GREY, lw=1)
    for lv in (entry["unpl"], entry["lnpl"]):
        ax_x.axhline(lv, color=GREY, lw=1, ls="--")
    ax_x.axvspan(b0, b1, color=BLUE, alpha=0.08)
    ax_x.set_title(
        f"{limits.value} · {limits.derive} · {title_key}\n"
        f"limits frozen from [{limits.baseline_window[0]}, {limits.baseline_window[1]})"
        f" · computed {limits.computed_at}",
        fontsize=10,
    )
    ax_x.set_ylabel("X")

    # mR chart
    mr_pts = [(t, m) for t, m in zip(ts, mrs, strict=True) if m is not None]
    if mr_pts:
        ax_mr.plot(*zip(*mr_pts, strict=True), marker="o", ms=2.8, lw=0.9, color=BLUE)
    mr_flagged = [
        (t, m) for t, m, f in zip(ts, mrs, mr_flag, strict=True) if f and m is not None
    ]
    if mr_flagged:
        color = RED if mr_rule else AMBER  # advisory unless the rule is opted in
        ax_mr.plot(*zip(*mr_flagged, strict=True), "o", ms=5.5, color=color)
    ax_mr.axhline(entry["mr_ucl"], color=GREY, lw=1, ls="--")
    ax_mr.axvspan(b0, b1, color=BLUE, alpha=0.08)
    ax_mr.set_ylabel("mR")
    ax_mr.set_ylim(bottom=0)

    fig.autofmt_xdate()
    fig.tight_layout()
    out = Path(out)
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
