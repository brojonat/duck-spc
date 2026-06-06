"""Library API: Source -> Stream -> Limits -> Report.

DuckDB does the heavy lifting; Python orchestrates and formats. Nothing
materializes here except derived-stream points and answers.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from duck_spc import sql as q

ARTIFACT_VERSION = 1
LIMIT_FIELDS = ("n", "center", "mr_bar", "lnpl", "unpl", "mr_ucl")


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


@dataclasses.dataclass(frozen=True)
class Source:
    """A Parquet dataset with the duck-spc column contract.

    (ts, *group_by, value[, exposure]) — everything upstream of this shape
    (joins, unit conversion, normalization inputs) is the caller's job.
    When `exposure` is None it is implicitly 1 for every row.
    """

    path: str
    ts: str
    value: str
    group_by: tuple[str, ...]
    exposure: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_by", tuple(self.group_by))
        if not self.group_by:
            raise ValueError("group_by must name at least one column")

    def derive(self, spec: str = "none") -> Stream:
        """Derive the stationary stream to chart (the most important bit)."""
        q.validate_derive(spec, self.exposure)
        return Stream(self, spec)


@dataclasses.dataclass(frozen=True)
class Stream:
    """A derived stream: (ts, *group_by, value), computed in SQL."""

    source: Source
    spec: str

    def sql(self) -> str:
        s = self.source
        return q.derive_sql(
            q.source_relation(s.path), s.ts, s.value, s.group_by, self.spec, s.exposure
        )

    def frame(self, since: str | None = None, until: str | None = None) -> list[dict[str, Any]]:
        """Materialize the derived stream (for tests/charts — not the hot path)."""
        clauses, params = ["value IS NOT NULL"], []
        if since is not None:
            clauses.append("ts >= CAST(? AS TIMESTAMP)")
            params.append(str(since))
        if until is not None:
            clauses.append("ts < CAST(? AS TIMESTAMP)")
            params.append(str(until))
        g = ", ".join(q.qident(c) for c in self.source.group_by)
        cur = _connect().execute(
            f"SELECT * FROM ({self.sql()}) WHERE {' AND '.join(clauses)} ORDER BY {g}, ts",
            params,
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def baseline(self, start: str, end: str) -> Limits:
        """Compute frozen per-group XmR limits from the window [start, end)."""
        s = self.source
        cur = _connect().execute(
            q.baseline_sql(self.sql(), s.group_by), [str(start), str(end)]
        )
        cols = [d[0] for d in cur.description]
        groups = []
        for row in cur.fetchall():
            rec = dict(zip(cols, row, strict=True))
            if rec["mr_bar"] is None:  # fewer than 2 baseline points: no limits
                continue
            groups.append(
                {
                    "key": {c: rec[c] for c in s.group_by},
                    **{f: rec[f] for f in LIMIT_FIELDS},
                }
            )
        return Limits(
            source=s.path,
            ts=s.ts,
            value=s.value,
            exposure=s.exposure,
            group_by=s.group_by,
            derive=self.spec,
            baseline_window=(str(start), str(end)),
            computed_at=datetime.now(UTC).isoformat(timespec="seconds"),
            groups=groups,
        )


@dataclasses.dataclass
class Limits:
    """Frozen per-group natural process limits, with provenance.

    The artifact is the contract between `baseline` and `check`.
    Re-baselining is a deliberate act: build a new Limits, never mutate.
    """

    source: str
    ts: str
    value: str
    exposure: str | None
    group_by: tuple[str, ...]
    derive: str
    baseline_window: tuple[str, str]
    computed_at: str
    groups: list[dict[str, Any]]

    # -- artifact -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["group_by"] = list(self.group_by)
        d["baseline_window"] = list(self.baseline_window)
        return {"version": ARTIFACT_VERSION, **d}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> Limits:
        d = json.loads(Path(path).read_text())
        version = d.pop("version", None)
        if version != ARTIFACT_VERSION:
            raise ValueError(f"unsupported limits artifact version: {version!r}")
        d["group_by"] = tuple(d["group_by"])
        d["baseline_window"] = tuple(d["baseline_window"])
        return cls(**d)

    # -- evaluation ---------------------------------------------------------

    def _default_source(self) -> Source:
        return Source(
            path=self.source,
            ts=self.ts,
            value=self.value,
            group_by=self.group_by,
            exposure=self.exposure,
        )

    def evaluate(
        self,
        source: Source | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        """Score every derived-stream point against the frozen limits.

        Defaults: the artifact's own source, from the end of the baseline
        window onward. Rule 2 runs are computed within the checked window.
        """
        src = source or self._default_source()
        if tuple(src.group_by) != tuple(self.group_by):
            raise ValueError(
                f"source group_by {src.group_by} != limits group_by {self.group_by}"
            )
        since = str(since) if since is not None else self.baseline_window[1]
        stream_sql = Stream(src, self.derive).sql()

        con = _connect()
        con.register(
            "limits_tbl",
            pa.Table.from_pylist(
                [
                    {**g["key"], **{f: g[f] for f in ("center", "lnpl", "unpl")}}
                    for g in self.groups
                ]
            ),
        )
        params = [since] if until is None else [since, str(until)]
        cur = con.execute(q.check_sql(stream_sql, self.group_by, until), params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def check(
        self,
        source: Source | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> Report:
        points = self.evaluate(source, since, until)
        signals = [
            {
                "group": {c: p[c] for c in self.group_by},
                "ts": p["ts"],
                "value": p["value"],
                "rules": [r for r in ("rule1", "rule2") if p[r]],
                "center": p["center"],
                "lnpl": p["lnpl"],
                "unpl": p["unpl"],
            }
            for p in points
            if p["rule1"] or p["rule2"]
        ]
        return Report(
            ok=not signals,
            points_checked=len(points),
            groups_checked=len({tuple(p[c] for c in self.group_by) for p in points}),
            since=since if since is not None else self.baseline_window[1],
            until=until,
            signals=signals,
        )


@dataclasses.dataclass
class Report:
    """The verdict. ok=True means: trust the statistics, go back to sleep."""

    ok: bool
    points_checked: int
    groups_checked: int
    since: str | None
    until: str | None
    signals: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), default=str, **kwargs)
