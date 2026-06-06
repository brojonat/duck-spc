"""duck-spc CLI: baseline / check / chart.

JSON on stdout, narrative on stderr, the verdict in the exit code:
  0 — all streams within natural process limits (stop worrying)
  1 — signals detected (the process changed)
  2 — error
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from duck_spc.core import Limits, Source

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


def say(msg: str) -> None:
    """Narrative for humans -> stderr; stdout stays machine-readable."""
    click.echo(msg, err=True)


def parse_window(window: str) -> tuple[str, str]:
    parts = window.split(":")
    if len(parts) != 2:
        raise click.UsageError(
            f"--window must be START:END dates (half-open), e.g. "
            f"2026-01-01:2026-01-29 — got {window!r}"
        )
    return parts[0], parts[1]


def source_from(limits: Limits, override: str | None) -> Source | None:
    """An override path reuses the artifact's column contract."""
    if override is None:
        return None
    return Source(
        path=override,
        ts=limits.ts,
        value=limits.value,
        group_by=limits.group_by,
        exposure=limits.exposure,
    )


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(package_name="duck-spc")
def cli() -> None:
    """Statistical process control over Parquet, powered by DuckDB.

    Within natural limits, nothing happened. Go back to sleep.
    """


@cli.command()
@click.option("--source", required=True, help="parquet path/glob/prefix (local, s3://, gs://)")
@click.option("--ts", default="ts", show_default=True, help="timestamp column")
@click.option("--value", required=True, help="value column")
@click.option("--group-by", required=True, help="comma-separated stream-key columns")
@click.option("--exposure", default=None, help="exposure column (default: every row counts 1)")
@click.option("--derive", default="none", show_default=True,
              help="stream derivation: none | diff | <period>:<stat> (e.g. day:p95)")
@click.option("--window", required=True, help="baseline window START:END (dates, half-open)")
@click.option("-o", "--out", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="write the limits artifact here instead of stdout")
def baseline(source: str, ts: str, value: str, group_by: str, exposure: str | None,
             derive: str, window: str, out: Path | None) -> None:
    """Freeze per-group XmR limits from a baseline window."""
    start, end = parse_window(window)
    src = Source(
        path=source, ts=ts, value=value,
        group_by=tuple(c.strip() for c in group_by.split(",")),
        exposure=exposure,
    )
    limits = src.derive(derive).baseline(start, end)
    if not limits.groups:
        raise click.ClickException(
            f"no groups had >= 2 points in [{start}, {end}) — nothing to freeze"
        )
    say(f"froze limits for {len(limits.groups)} group(s) from [{start}, {end})")
    payload = json.dumps(limits.to_dict(), indent=2)
    if out is not None:
        out.write_text(payload + "\n")
        say(f"wrote {out}")
    else:
        click.echo(payload)


@cli.command()
@click.option("--limits", "limits_path", required=True,
              type=click.Path(exists=True, dir_okay=False), help="limits artifact (JSON)")
@click.option("--source", default=None, help="override the artifact's source path")
@click.option("--since", default=None, help="check from here (default: end of baseline window)")
@click.option("--until", default=None, help="check up to here (exclusive)")
@click.option("--mr-rule", is_flag=True,
              help="also flag moving ranges above mR_UCL "
                   "(spread changes; extra rule = extra false alarms)")
def check(limits_path: str, source: str | None, since: str | None, until: str | None,
          mr_rule: bool) -> None:
    """Score data against frozen limits. Exit 0 stable, 1 signals."""
    limits = Limits.load(limits_path)
    report = limits.check(source_from(limits, source), since=since, until=until, mr_rule=mr_rule)
    click.echo(report.to_json(indent=2))
    if report.ok:
        say(f"{report.points_checked} points / {report.groups_checked} groups: "
            "all within natural process limits — stop worrying.")
    else:
        say(f"{report.points_checked} points / {report.groups_checked} groups: "
            f"{len(report.signals)} signal point(s) — the process changed.")
        sys.exit(1)


@cli.command()
@click.option("--limits", "limits_path", required=True,
              type=click.Path(exists=True, dir_okay=False), help="limits artifact (JSON)")
@click.option("--group", required=True,
              help="comma-separated group values, in the artifact's group_by order")
@click.option("-o", "--out", required=True, type=click.Path(dir_okay=False, path_type=Path),
              help="output image path (.png, .svg, ...)")
@click.option("--source", default=None, help="override the artifact's source path")
@click.option("--since", default=None, help="chart from here (default: start of baseline window)")
@click.option("--until", default=None, help="chart up to here (exclusive)")
@click.option("--mr-rule", is_flag=True,
              help="render mR breaches as signals (red) not advisory (amber)")
def chart(limits_path: str, group: str, out: Path, source: str | None,
          since: str | None, until: str | None, mr_rule: bool) -> None:
    """Render the XmR chart pair (X + mR) for one group."""
    limits = Limits.load(limits_path)
    values = tuple(v.strip() for v in group.split(","))
    if len(values) != len(limits.group_by):
        raise click.UsageError(
            f"--group expects {len(limits.group_by)} values ({', '.join(limits.group_by)}) "
            f"— got {len(values)}"
        )
    path = limits.chart(values, out, source=source_from(limits, source),
                        since=since, until=until, mr_rule=mr_rule)
    say(f"wrote {path}")


def main() -> None:
    try:
        cli(standalone_mode=False)
    except click.ClickException as e:
        e.show()
        sys.exit(2)
    except click.Abort:
        sys.exit(2)
    except Exception as e:  # runtime errors: one line on stderr, exit 2
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
