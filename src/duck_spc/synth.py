"""Synthetic telemetry generator with known injected signals.

Produces date-partitioned Parquet matching the duck-spc column contract —
(ts, *categories, value, exposure, dt) — plus a ground-truth manifest of
exactly which group received which signal on which date, so tests and
demos can assert detection instead of eyeballing it.

Signal magnitudes are expressed in units of the *daily-mean stream's*
sigma (sigma_event / sqrt(events_per_day)), so `magnitude=4.0` means "the
day:mean chart should see a 4-sigma excursion" regardless of event volume.
"""

from __future__ import annotations

import dataclasses
import itertools
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import duckdb
import numpy as np
import pyarrow as pa


@dataclasses.dataclass(frozen=True)
class Signal:
    """An injected special cause.

    kind:
      spike    — single-day excursion of `magnitude` daily-sigmas
      shift    — sustained level change of `magnitude` daily-sigmas from `start` on
      variance — event-level sigma multiplied by `magnitude` from `start` on
    """

    group: dict[str, str]
    kind: Literal["spike", "shift", "variance"]
    start: date
    magnitude: float


def generate(
    out_dir: str | Path,
    *,
    start: date = date(2026, 1, 1),
    days: int = 60,
    categories: dict[str, list[str]] | None = None,
    events_per_day: int = 200,
    signals: tuple[Signal, ...] | list[Signal] = (),
    seed: int = 7,
) -> dict[str, Any]:
    """Write hive-partitioned Parquet to out_dir; return the ground-truth manifest."""
    out_dir = Path(out_dir)
    categories = categories or {
        "region": ["us-east", "eu-west"],
        "service": ["checkout", "search"],
    }
    cat_cols = list(categories)
    group_keys = [
        dict(zip(cat_cols, combo, strict=True))
        for combo in itertools.product(*categories.values())
    ]

    cols: dict[str, list[Any]] = {"ts": [], "value": [], "exposure": [], "dt": []}
    for c in cat_cols:
        cols[c] = []

    manifest_groups = []
    for gi, key in enumerate(group_keys):
        rng = np.random.default_rng([seed, gi])
        mu = float(rng.uniform(50, 500))
        sigma = 0.05 * mu
        daily_sigma = sigma / math.sqrt(events_per_day)
        manifest_groups.append(
            {"key": key, "mu": mu, "sigma": sigma, "daily_sigma": daily_sigma}
        )
        my_signals = [s for s in signals if s.group == key]

        for d in range(days):
            day = start + timedelta(days=d)
            offset = sum(
                s.magnitude * daily_sigma
                for s in my_signals
                if (s.kind == "shift" and day >= s.start)
                or (s.kind == "spike" and day == s.start)
            )
            sd_mult = math.prod(
                s.magnitude
                for s in my_signals
                if s.kind == "variance" and day >= s.start
            )
            seconds = np.sort(rng.integers(0, 86_400, size=events_per_day))
            values = rng.normal(mu + offset, sigma * sd_mult, size=events_per_day)

            base = datetime(day.year, day.month, day.day)
            cols["ts"].extend(base + timedelta(seconds=int(s)) for s in seconds)
            cols["value"].extend(float(v) for v in values)
            cols["exposure"].extend([1.0] * events_per_day)
            cols["dt"].extend([day.isoformat()] * events_per_day)
            for c in cat_cols:
                cols[c].extend([key[c]] * events_per_day)

    table = pa.table(cols)
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.register("t", table)
    con.execute(
        f"COPY (SELECT * FROM t) TO '{out_dir}' "
        "(FORMAT PARQUET, PARTITION_BY (dt), COMPRESSION ZSTD, OVERWRITE_OR_IGNORE true)"
    )

    manifest = {
        "start": start.isoformat(),
        "days": days,
        "events_per_day": events_per_day,
        "seed": seed,
        "categories": categories,
        "groups": manifest_groups,
        "signals": [
            {**dataclasses.asdict(s), "start": s.start.isoformat()} for s in signals
        ],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
