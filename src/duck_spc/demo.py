"""End-to-end demo: generate synthetic telemetry with known special causes,
freeze a baseline, check against it. Report JSON on stdout, narrative on stderr.

Run via `make demo` (or `uv run python -m duck_spc.demo`).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from duck_spc import Source
from duck_spc.synth import Signal, generate

OUT = Path("demo_data")
BASELINE = ("2026-01-01", "2026-01-29")


def main() -> int:
    say = lambda *a: print(*a, file=sys.stderr)  # noqa: E731

    say(f"generating synthetic telemetry -> {OUT}/ ...")
    generate(
        OUT,
        start=date(2026, 1, 1),
        days=70,
        events_per_day=200,
        signals=[
            Signal({"region": "us-east", "service": "checkout"}, "spike", date(2026, 2, 10), 6.0),
            Signal({"region": "us-east", "service": "search"}, "shift", date(2026, 2, 5), 2.0),
        ],
    )

    src = Source(str(OUT), ts="ts", value="value", group_by=("region", "service"))
    say(f"freezing day:mean baseline over [{BASELINE[0]}, {BASELINE[1]}) ...")
    limits = src.derive("day:mean").baseline(*BASELINE)
    limits.save(OUT / "limits.json")
    say(f"limits for {len(limits.groups)} groups -> {OUT / 'limits.json'}")

    report = limits.check()
    say(
        f"checked {report.points_checked} points across {report.groups_checked} groups: "
        + ("all within natural process limits — stop worrying."
           if report.ok
           else f"{len(report.signals)} signal points — the process changed.")
    )
    print(report.to_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
