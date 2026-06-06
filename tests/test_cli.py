"""CLI surface: verbs, exit codes, JSON-on-stdout contract."""

import json

from click.testing import CliRunner

from conftest import BASELINE, SPIKE_GROUP
from duck_spc.cli import cli


def test_baseline_check_chart_end_to_end(dataset, tmp_path):
    out, _ = dataset
    runner = CliRunner()
    limits_path = tmp_path / "limits.json"

    res = runner.invoke(cli, [
        "baseline",
        "--source", str(out),
        "--ts", "ts", "--value", "value",
        "--group-by", "region,service",
        "--derive", "day:mean",
        "--window", f"{BASELINE[0]}:{BASELINE[1]}",
        "-o", str(limits_path),
    ])
    assert res.exit_code == 0, res.output
    artifact = json.loads(limits_path.read_text())
    assert artifact["version"] == 1
    assert len(artifact["groups"]) == 4

    # quiet early window: no injected signal active yet -> exit 0
    res = runner.invoke(cli, [
        "check", "--limits", str(limits_path), "--until", "2026-02-04",
    ])
    assert res.exit_code == 0, res.output
    report = json.loads(res.stdout)  # narrative goes to stderr, JSON to stdout
    assert report["ok"] is True

    # full window: spike + shift present -> exit 1, signals in the JSON
    res = runner.invoke(cli, ["check", "--limits", str(limits_path)])
    assert res.exit_code == 1, res.output
    report = json.loads(res.stdout)
    assert report["ok"] is False
    assert any(s["group"] == SPIKE_GROUP for s in report["signals"])

    # chart the spike group
    png = tmp_path / "spike.png"
    res = runner.invoke(cli, [
        "chart", "--limits", str(limits_path),
        "--group", "us-east,checkout", "-o", str(png),
    ])
    assert res.exit_code == 0, res.output
    assert png.stat().st_size > 10_000  # a real rendered figure, not a stub


def test_check_missing_limits_is_exit_2(tmp_path):
    runner = CliRunner()
    res = runner.invoke(cli, ["check", "--limits", str(tmp_path / "nope.json")])
    assert res.exit_code == 2


def test_chart_wrong_group_arity_is_usage_error(dataset, tmp_path, limits):
    limits_path = tmp_path / "limits.json"
    limits.save(limits_path)
    runner = CliRunner()
    res = runner.invoke(cli, [
        "chart", "--limits", str(limits_path), "--group", "us-east", "-o", str(tmp_path / "x.png"),
    ])
    assert res.exit_code == 2
