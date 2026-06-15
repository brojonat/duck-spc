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
    assert artifact["version"] == 2
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


def test_look_one_shot(dataset):
    """Point at a bucket -> charts + verdicts in your face, exit carries verdict."""
    out, _ = dataset
    runner = CliRunner()
    res = runner.invoke(cli, [
        "look", "--source", str(out),
        "--value", "value", "--group-by", "region,service",
        "--derive", "day:mean", "--window", f"{BASELINE[0]}:{BASELINE[1]}",
    ])
    assert res.exit_code == 1, res.output  # injected signals exist
    assert "region=us-east, service=checkout" in res.stdout
    assert "●" in res.stdout  # signal points on the chart
    assert "✗" in res.stdout and "✓" in res.stdout  # mixed verdicts across groups
    assert "special-cause variation" in res.stdout


def test_look_default_window_and_json(dataset):
    out, _ = dataset
    runner = CliRunner()
    res = runner.invoke(cli, [
        "look", "--source", str(out),
        "--value", "value", "--group-by", "region,service",
        "--derive", "day:mean", "--json",
    ])
    assert res.exit_code == 1, res.output
    assert "baseline defaulted" in res.stderr
    report = json.loads(res.stdout)
    assert report["ok"] is False
    assert report["limits"]["derive"] == "day:mean"  # report carries provenance


def test_visualize_pipes_from_baseline_and_check(dataset, limits):
    """The Unix contract: baseline | visualize and check | visualize."""
    runner = CliRunner()

    artifact_json = json.dumps(limits.to_dict())
    res = runner.invoke(cli, ["visualize"], input=artifact_json)
    assert res.exit_code == 1, res.output
    assert "✗" in res.stdout and "·" in res.stdout

    report_json = limits.check().to_json()
    res = runner.invoke(cli, ["visualize"], input=report_json)
    assert res.exit_code == 1, res.output
    assert "go find the cause" in res.stdout

    res = runner.invoke(cli, ["visualize"], input='{"what": "is this"}')
    assert res.exit_code == 2


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
