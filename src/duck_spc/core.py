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

ARTIFACT_VERSION = 2  # v2 adds source_sql; v1 artifacts still load
SUPPORTED_VERSIONS = (1, 2)
LIMIT_FIELDS = ("n", "center", "mr_bar", "lnpl", "unpl", "mr_ucl")


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _stream_relation(con: duckdb.DuckDBPyConnection, stream: Stream) -> str:
    """The relation downstream SQL reads the derived stream from.

    Parquet sources inline as a subquery (pushdown, scanned efficiently).
    Custom-SQL sources are materialized into a temp table first: it runs the
    user's query once instead of re-nesting it under every downstream window
    function, which also sidesteps a DuckDB execution error on deeply nested
    window queries (e.g. a deseasonalizing `avg() OVER` under our `lag()`).
    """
    if stream.source.sql is None:
        return stream.sql()
    con.execute(f"CREATE TEMP TABLE _spc_stream AS {stream.sql()}")
    return "SELECT * FROM _spc_stream"


@dataclasses.dataclass(frozen=True)
class Source:
    """A dataset exposing the duck-spc column contract.

    Two ways to provide it:

    - `path=` — Parquet glob/prefix whose columns already *are*
      `(ts, *group_by, value[, exposure])`. The happy path.
    - `sql=` — a SQL query (use `Source.from_query`) that *projects* arbitrary
      Parquet into that shape, for schemas that don't line up. The query names
      the output columns; `ts`/`value`/`group_by`/`exposure` reference them.

    Everything upstream of the contract (joins, unit conversion, normalization,
    and — importantly — deseasonalizing/de-trending, see the README) is the
    caller's job. When `exposure` is None it is implicitly 1 for every row.
    """

    path: str | None = None
    sql: str | None = None
    ts: str = "ts"
    value: str = ""
    group_by: tuple[str, ...] = ()
    exposure: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_by", tuple(self.group_by))
        if not self.group_by:
            raise ValueError("group_by must name at least one column")
        if not self.value:
            raise ValueError("value column is required")
        if (self.path is None) == (self.sql is None):
            raise ValueError(
                "provide exactly one of path= (Parquet) or sql= "
                "(use Source.from_query for a custom query)"
            )

    @classmethod
    def from_query(
        cls,
        sql: str,
        *,
        ts: str = "ts",
        value: str,
        group_by: list[str] | tuple[str, ...],
        exposure: str | None = None,
    ) -> Source:
        """A Source backed by a SQL query that yields the contract columns.

        The query must SELECT a timestamp column, the group-by column(s), a
        value column, and optionally an exposure column — named so that the
        `ts`/`value`/`group_by`/`exposure` arguments reference them. It is
        self-contained (read your Parquet inside it with `read_parquet(...)`).
        """
        return cls(sql=sql, ts=ts, value=value, group_by=tuple(group_by), exposure=exposure)

    def relation(self) -> str:
        """The DuckDB relation everything else reads from."""
        if self.sql is not None:
            return f"({self.sql}) AS _spc_src"
        assert self.path is not None  # guaranteed by __post_init__
        return q.source_relation(self.path)

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
            s.relation(), s.ts, s.value, s.group_by, self.spec, s.exposure
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

    def default_baseline_window(self, fraction: float = 0.25) -> tuple[str, str]:
        """A baseline window covering the first `fraction` of the data's span.

        For exploration (`duck-spc look`) — production baselines should be
        chosen deliberately and passed explicitly.
        """
        row = _connect().execute(
            f"SELECT min(ts), max(ts) FROM ({self.sql()}) WHERE value IS NOT NULL"
        ).fetchone()
        t0, t1 = row if row is not None else (None, None)
        if t0 is None or t0 == t1:
            raise ValueError("not enough data to infer a baseline window")
        return str(t0), str(t0 + (t1 - t0) * fraction)

    def baseline(self, start: str, end: str) -> Limits:
        """Compute frozen per-group XmR limits from the window [start, end)."""
        s = self.source
        con = _connect()
        relation = _stream_relation(con, self)
        cur = con.execute(
            q.baseline_sql(relation, s.group_by), [str(start), str(end)]
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
            source_sql=s.sql,
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

    source: str | None
    ts: str
    value: str
    exposure: str | None
    group_by: tuple[str, ...]
    derive: str
    baseline_window: tuple[str, str]
    computed_at: str
    groups: list[dict[str, Any]]
    source_sql: str | None = None  # set instead of `source` for query-backed sources

    # -- artifact -----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["group_by"] = list(self.group_by)
        d["baseline_window"] = list(self.baseline_window)
        return {"version": ARTIFACT_VERSION, **d}

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Limits:
        d = dict(d)
        version = d.pop("version", None)
        if version not in SUPPORTED_VERSIONS:
            raise ValueError(f"unsupported limits artifact version: {version!r}")
        d.setdefault("source_sql", None)  # absent in v1 artifacts
        d["group_by"] = tuple(d["group_by"])
        d["baseline_window"] = tuple(d["baseline_window"])
        return cls(**d)

    @classmethod
    def load(cls, path: str | Path) -> Limits:
        return cls.from_dict(json.loads(Path(path).read_text()))

    # -- evaluation ---------------------------------------------------------

    def _default_source(self) -> Source:
        if self.source_sql is not None:
            return Source(
                sql=self.source_sql,
                ts=self.ts,
                value=self.value,
                group_by=self.group_by,
                exposure=self.exposure,
            )
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

        con = _connect()
        stream_sql = _stream_relation(con, Stream(src, self.derive))
        con.register(
            "limits_tbl",
            pa.Table.from_pylist(
                [
                    {**g["key"], **{f: g[f] for f in ("center", "lnpl", "unpl", "mr_ucl")}}
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
        mr_rule: bool = False,
    ) -> Report:
        """Score against frozen limits; Report.ok is the verdict.

        Detection is Rule 1 + Rule 2 by default. `mr_rule=True` opts in to
        flagging moving ranges above mR_UCL (catches spread changes the X
        chart misses) — opt-in because every added rule buys sensitivity
        with false alarms.
        """
        rules = ("rule1", "rule2") + (("rule_mr",) if mr_rule else ())
        points = self.evaluate(source, since, until)
        signals = [
            {
                "group": {c: p[c] for c in self.group_by},
                "ts": p["ts"],
                "value": p["value"],
                "rules": [r for r in rules if p[r]],
                "center": p["center"],
                "lnpl": p["lnpl"],
                "unpl": p["unpl"],
            }
            for p in points
            if any(p[r] for r in rules)
        ]
        return Report(
            ok=not signals,
            points_checked=len(points),
            groups_checked=len({tuple(p[c] for c in self.group_by) for p in points}),
            since=since if since is not None else self.baseline_window[1],
            until=until,
            mr_rule=mr_rule,
            signals=signals,
            limits=self.to_dict(),  # provenance: a report carries its limits
        )

    def chart(
        self,
        group: dict[str, str] | tuple[str, ...],
        out: str | Path,
        source: Source | None = None,
        since: str | None = None,
        until: str | None = None,
        mr_rule: bool = False,
    ) -> Path:
        """Render the XmR pair (X chart + mR chart) for one group to a file.

        By default the chart starts at the baseline window so readers can
        see the limits' provenance (the shaded region they were frozen from).
        """
        from duck_spc import chart as chart_mod

        key = group if isinstance(group, dict) else dict(zip(self.group_by, group, strict=True))
        entry = next((g for g in self.groups if g["key"] == key), None)
        if entry is None:
            known = [g["key"] for g in self.groups]
            raise ValueError(f"no limits for group {key!r}; known: {known}")
        points = [
            p
            for p in self.evaluate(source, since or self.baseline_window[0], until)
            if all(p[c] == v for c, v in key.items())
        ]
        return chart_mod.render_xmr(self, entry, points, Path(out), mr_rule=mr_rule)


@dataclasses.dataclass
class Report:
    """The verdict. ok=True means: trust the statistics, go back to sleep.

    Carries the limits artifact it was checked against, so a report is
    self-describing (and pipeable into `duck-spc visualize`).
    """

    ok: bool
    points_checked: int
    groups_checked: int
    since: str | None
    until: str | None
    mr_rule: bool
    signals: list[dict[str, Any]]
    limits: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), default=str, **kwargs)
