"""SQL pushdown vs the numpy reference oracle, and detection of injected signals."""

from datetime import datetime

import numpy as np
import pytest

import reference
from conftest import (
    BASELINE,
    CLEAN_GROUP,
    SHIFT_DAY,
    SHIFT_GROUP,
    SPIKE_DAY,
    SPIKE_GROUP,
)
from duck_spc import Limits, Source
from tests_util import by_group


def key_of(d: dict) -> tuple:
    return (d["region"], d["service"])


def test_baseline_limits_match_numpy_reference(source, limits):
    """Per-group limits from SQL == skill's reference impl, to float precision."""
    stream = source.derive("day:mean").frame(since=BASELINE[0], until=BASELINE[1])
    groups = by_group(stream, ("region", "service"))
    assert len(limits.groups) == 4

    for g in limits.groups:
        pts = groups[tuple(g["key"].values())]
        ref = reference.xmr_limits(np.array([p["value"] for p in pts]))
        assert g["n"] == 28
        for field in ("center", "mr_bar", "lnpl", "unpl", "mr_ucl"):
            assert g[field] == pytest.approx(ref[field], rel=1e-9), (g["key"], field)


def test_rule_flags_match_numpy_reference(limits):
    """Rule 1/Rule 2 flags from the SQL (incl. gaps-and-islands run detection)
    == the reference loop, point for point, across all groups."""
    points = limits.evaluate()  # defaults: from baseline end onward
    lim_by_key = {tuple(g["key"].values()): g for g in limits.groups}

    checked = 0
    for key, pts in by_group(points, ("region", "service")).items():
        ref = reference.xmr_signals(
            np.array([p["value"] for p in pts]), lim_by_key[key]
        )
        assert [p["rule1"] for p in pts] == ref["outside_limits"].tolist(), key
        assert [p["rule2"] for p in pts] == ref["run_of_nine"].tolist(), key
        checked += len(pts)
    assert checked == 4 * 42  # days 28..69 for each group


def test_injected_signals_detected(limits):
    """The ground truth from the generator manifest is recovered:
    spike -> Rule 1 on its exact day; shift -> Rule 2; clean group silent."""
    report = limits.check()
    assert not report.ok
    assert report.points_checked == 4 * 42
    assert report.groups_checked == 4

    def signals_for(group):
        return [s for s in report.signals if s["group"] == group]

    spike_hits = [s for s in signals_for(SPIKE_GROUP) if "rule1" in s["rules"]]
    assert [s["ts"] for s in spike_hits] == [datetime.fromisoformat(SPIKE_DAY)]

    shift_hits = [s for s in signals_for(SHIFT_GROUP) if "rule2" in s["rules"]]
    assert shift_hits, "2-sigma sustained shift must produce a run-of-9 signal"
    assert all(s["ts"] >= datetime.fromisoformat(SHIFT_DAY) for s in shift_hits)

    assert signals_for(CLEAN_GROUP) == [], "stable process must stay silent"


def test_artifact_roundtrip(tmp_path, limits, source):
    """save -> load reproduces identical verdicts; provenance survives."""
    path = tmp_path / "limits.json"
    limits.save(path)
    loaded = Limits.load(path)

    assert loaded.baseline_window == tuple(BASELINE)
    assert loaded.derive == "day:mean"
    assert loaded.group_by == ("region", "service")
    assert loaded.groups == limits.groups

    original = limits.check(source)
    reloaded = loaded.check(source)
    assert reloaded.to_dict() == original.to_dict()


def test_rate_derivation_uses_sum_over_sum(tmp_path):
    """day:rate must be sum(value)/sum(exposure), not mean of row-wise ratios."""
    import duckdb

    con = duckdb.connect()
    con.execute(
        f"""
        COPY (
          SELECT * FROM (VALUES
            (TIMESTAMP '2026-01-01 01:00', 'a', 10.0, 1.0),
            (TIMESTAMP '2026-01-01 02:00', 'a', 10.0, 4.0),
            (TIMESTAMP '2026-01-02 01:00', 'a',  5.0, 1.0)
          ) AS t(ts, grp, v, exp)
        ) TO '{tmp_path / "tiny.parquet"}' (FORMAT PARQUET)
        """
    )
    src = Source(
        str(tmp_path / "tiny.parquet"),
        ts="ts",
        value="v",
        group_by=("grp",),
        exposure="exp",
    )
    rows = src.derive("day:rate").frame()
    rates = {str(r["ts"])[:10]: r["value"] for r in rows}
    # day 1: sum/sum = (10+10)/(1+4) = 4.0; the (wrong) mean of row-wise
    # ratios would be (10/1 + 10/4)/2 = 6.25 — this distinguishes them
    assert rates["2026-01-01"] == pytest.approx(4.0)
    assert rates["2026-01-02"] == pytest.approx(5.0)

    # exposure omitted -> implicitly 1 per row: rate = sum(v)/count = daily mean
    src_no_exp = Source(
        str(tmp_path / "tiny.parquet"), ts="ts", value="v", group_by=("grp",)
    )
    rows = src_no_exp.derive("day:rate").frame()
    rates = {str(r["ts"])[:10]: r["value"] for r in rows}
    assert rates["2026-01-01"] == pytest.approx(10.0)
