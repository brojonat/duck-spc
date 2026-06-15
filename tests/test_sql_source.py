"""The custom-SQL entry point: shape arbitrary Parquet into the contract.

A SQL-backed Source must produce identical limits to the equivalent
Parquet-backed Source when the query is just a projection, and must handle
schemas whose columns don't match the contract by renaming them.
"""

import json

import duckdb
import pytest
from click.testing import CliRunner

from conftest import BASELINE
from duck_spc import Limits, Source
from duck_spc.cli import cli


def test_sql_source_matches_parquet_source(dataset, source):
    """An identity projection over the same Parquet yields identical limits."""
    out, _ = dataset
    glob = f"{out}/**/*.parquet"
    q = (
        f"SELECT ts, region, service, value "
        f"FROM read_parquet('{glob}') WHERE value IS NOT NULL"
    )
    sql_src = Source.from_query(q, ts="ts", value="value", group_by=("region", "service"))

    direct = source.derive("day:mean").baseline(*BASELINE)
    viaSql = sql_src.derive("day:mean").baseline(*BASELINE)
    assert viaSql.groups == direct.groups
    assert viaSql.source is None and viaSql.source_sql == q


def test_sql_source_renames_mismatched_schema(tmp_path):
    """Columns that don't match the contract are renamed in the query."""
    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT * FROM (VALUES
            (TIMESTAMP '2026-01-01 01:00', 'us', 120.0),
            (TIMESTAMP '2026-01-02 01:00', 'us', 130.0),
            (TIMESTAMP '2026-01-03 01:00', 'us', 600.0)
          ) AS t(event_time, site, latency)
        ) TO '{tmp_path / "raw.parquet"}' (FORMAT PARQUET)
        """
    )
    q = (
        f"SELECT event_time AS ts, site AS region, latency AS value "
        f"FROM read_parquet('{tmp_path / 'raw.parquet'}')"
    )
    src = Source.from_query(q, ts="ts", value="value", group_by=("region",))
    limits = src.derive("none").baseline("2026-01-01", "2026-01-03")
    assert len(limits.groups) == 1
    # the 600 spike on day 3 is outside limits frozen on the first two days
    report = limits.check()
    assert not report.ok


def test_sql_source_with_window_function_deseasonalizes(dataset):
    """A query that subtracts a per-weekday average (window function) runs
    end to end — the derived stream is materialized so the user's window
    nests cleanly under our detection windows."""
    out, _ = dataset
    q = (
        "SELECT ts, region, service, "
        "value - avg(value) OVER (PARTITION BY region, service, dayofweek(ts)) AS value "
        f"FROM read_parquet('{out}/**/*.parquet')"
    )
    src = Source.from_query(q, ts="ts", value="value", group_by=("region", "service"))
    report = src.derive("day:mean").baseline(*BASELINE).check()
    assert report.points_checked == 4 * 42
    assert report.groups_checked == 4


def test_sql_source_artifact_roundtrips(dataset, tmp_path):
    """source_sql survives save/load and reproduces the same verdict."""
    out, _ = dataset
    q = f"SELECT ts, region, service, value FROM read_parquet('{out}/**/*.parquet')"
    src = Source.from_query(q, ts="ts", value="value", group_by=("region", "service"))
    limits = src.derive("day:mean").baseline(*BASELINE)

    path = tmp_path / "limits.json"
    limits.save(path)
    loaded = Limits.load(path)
    assert loaded.source_sql == q
    assert loaded.source is None
    assert loaded.check().to_dict() == limits.check().to_dict()


def test_v1_artifact_without_source_sql_still_loads(dataset, tmp_path):
    """Backward compatibility: a v1 artifact (no source_sql) loads as parquet."""
    out, _ = dataset
    src = Source(str(out), ts="ts", value="value", group_by=("region", "service"))
    d = src.derive("day:mean").baseline(*BASELINE).to_dict()
    d["version"] = 1
    del d["source_sql"]
    loaded = Limits.from_dict(d)
    assert loaded.source_sql is None
    assert loaded.source == str(out)


def test_source_requires_exactly_one_of_path_or_sql():
    with pytest.raises(ValueError, match="exactly one"):
        Source(path="x", sql="SELECT 1", value="v", group_by=("g",))
    with pytest.raises(ValueError, match="exactly one"):
        Source(value="v", group_by=("g",))  # neither


def test_cli_query_entry_point(dataset, tmp_path):
    out, _ = dataset
    q = f"SELECT ts, region, service, value FROM read_parquet('{out}/**/*.parquet')"
    runner = CliRunner()
    limits_path = tmp_path / "l.json"
    res = runner.invoke(cli, [
        "baseline", "--query", q,
        "--value", "value", "--group-by", "region,service",
        "--derive", "day:mean", "--window", f"{BASELINE[0]}:{BASELINE[1]}",
        "-o", str(limits_path),
    ])
    assert res.exit_code == 0, res.output
    artifact = json.loads(limits_path.read_text())
    assert artifact["source_sql"] == q and artifact["source"] is None

    # check reuses the embedded query — no --source/--query needed
    res = runner.invoke(cli, ["check", "--limits", str(limits_path)])
    assert res.exit_code in (0, 1), res.output  # ran (signals or not), not error 2


def test_cli_rejects_both_source_and_query(dataset, tmp_path):
    out, _ = dataset
    runner = CliRunner()
    res = runner.invoke(cli, [
        "baseline", "--source", str(out), "--query", "SELECT 1",
        "--value", "value", "--group-by", "region", "--window", "2026-01-01:2026-01-29",
    ])
    assert res.exit_code == 2
