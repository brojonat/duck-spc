"""SQL builders. The math of record runs inside DuckDB, not Python.

Doctrine (see LEARNINGS.md — not configurable):
- sigma from the mean moving range: limits at center ± 2.66 * mR-bar
- 2.66 = 3/1.128 and 3.268 are constants, not knobs
- detection is Rule 1 (outside limits) + Rule 2 (run of 9) only
"""

from __future__ import annotations

XMR_X = 2.66  # 3 / 1.128 (d2 for n=2); do not tune
XMR_MR = 3.268  # do not tune
RUN_LENGTH = 9  # Rule 2

PERIODS = ("hour", "day", "week", "month")

# Per-period statistics for `<period>:<stat>` derivations. {v} = value column,
# {e} = exposure column (constant 1 when no exposure column is configured).
STATS = {
    "mean": "avg({v})",
    "median": "median({v})",
    "p90": "quantile_cont({v}, 0.90)",
    "p95": "quantile_cont({v}, 0.95)",
    "p99": "quantile_cont({v}, 0.99)",
    "sd": "stddev_samp({v})",
    "count": "count(*)",
    "sum": "sum({v})",
    "rate": "sum({v}) / sum({e})",  # NOT mean of row-wise ratios
}


def qident(name: str) -> str:
    """Quote a SQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def source_relation(path: str) -> str:
    """Turn a source path into a read_parquet() relation.

    A bare directory/prefix gets a recursive glob appended; explicit globs
    and .parquet paths are used as-is.
    """
    if "*" in path or path.endswith(".parquet"):
        glob = path
    else:
        glob = path.rstrip("/") + "/**/*.parquet"
    return f"read_parquet('{glob}')"


def validate_derive(spec: str, exposure: str | None) -> None:
    if spec in ("none", "diff"):
        return
    period, _, stat = spec.partition(":")
    if period in PERIODS and stat in STATS:
        return
    raise ValueError(
        f"invalid derive spec {spec!r}: expected 'none', 'diff', or "
        f"'<period>:<stat>' with period in {PERIODS} and stat in {tuple(STATS)}"
    )


def derive_sql(
    relation: str,
    ts: str,
    value: str,
    group_by: tuple[str, ...],
    spec: str,
    exposure: str | None = None,
) -> str:
    """SELECT producing the derived stream: columns (ts, *group_by, value)."""
    g = ", ".join(qident(c) for c in group_by)
    raw = f"SELECT {qident(ts)} AS ts, {g}, ({qident(value)})::DOUBLE AS value FROM {relation}"
    if spec == "none":
        return raw
    if spec == "diff":
        return (
            f"SELECT ts, {g}, "
            f"value - lag(value) OVER (PARTITION BY {g} ORDER BY ts) AS value "
            f"FROM ({raw})"
        )
    period, _, stat = spec.partition(":")
    expr = STATS[stat].format(
        v=qident(value),
        e=qident(exposure) if exposure else "1.0",
    )
    return (
        f"SELECT date_trunc('{period}', {qident(ts)}) AS ts, {g}, "
        f"({expr})::DOUBLE AS value FROM {relation} GROUP BY ALL"
    )


def baseline_sql(stream_sql: str, group_by: tuple[str, ...]) -> str:
    """Per-group XmR limits from a frozen baseline window.

    Parameters: [start, end) of the baseline window (half-open).
    """
    g = ", ".join(qident(c) for c in group_by)
    return f"""
WITH stream AS ({stream_sql}),
base AS (
  SELECT * FROM stream
  WHERE value IS NOT NULL
    AND ts >= CAST(? AS TIMESTAMP) AND ts < CAST(? AS TIMESTAMP)
),
mr AS (
  SELECT {g}, value,
         abs(value - lag(value) OVER (PARTITION BY {g} ORDER BY ts)) AS mr
  FROM base
)
SELECT {g},
       count(value)                       AS n,
       avg(value)                         AS center,
       avg(mr)                            AS mr_bar,
       avg(value) - {XMR_X} * avg(mr)     AS lnpl,
       avg(value) + {XMR_X} * avg(mr)     AS unpl,
       {XMR_MR} * avg(mr)                 AS mr_ucl
FROM mr
GROUP BY {g}
ORDER BY {g}
"""


def check_sql(
    stream_sql: str,
    group_by: tuple[str, ...],
    until: str | None,
) -> str:
    """Score every point in [since, until) against frozen limits.

    Expects a registered `limits_tbl` with the group columns plus
    center/lnpl/unpl. Parameters: [since] or [since, until].

    Rule 2 uses gaps-and-islands: consecutive points on the same side of
    the center line share an island; islands of >= RUN_LENGTH flag every
    point in the run (matching the numpy reference implementation). Points
    exactly on the center line (side = 0) break runs and never flag.
    """
    g = ", ".join(qident(c) for c in group_by)
    until_clause = "AND ts < CAST(? AS TIMESTAMP)" if until is not None else ""
    return f"""
WITH stream AS ({stream_sql}),
w AS (
  SELECT * FROM stream
  WHERE value IS NOT NULL AND ts >= CAST(? AS TIMESTAMP) {until_clause}
),
j AS (
  SELECT w.*, l.center, l.lnpl, l.unpl
  FROM w JOIN limits_tbl l USING ({g})
),
scored AS (
  SELECT *,
         CASE WHEN value > center THEN 1 WHEN value < center THEN -1 ELSE 0 END AS side,
         (value > unpl OR value < lnpl) AS rule1
  FROM j
),
runs AS (
  SELECT *,
         row_number() OVER (PARTITION BY {g} ORDER BY ts)
       - row_number() OVER (PARTITION BY {g}, side ORDER BY ts) AS island
  FROM scored
),
flagged AS (
  SELECT *, count(*) OVER (PARTITION BY {g}, side, island) AS run_len
  FROM runs
)
SELECT {g}, ts, value, rule1,
       (side <> 0 AND run_len >= {RUN_LENGTH}) AS rule2,
       center, lnpl, unpl
FROM flagged
ORDER BY {g}, ts
"""
