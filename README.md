# duck-spc

**How I learned to stop worrying and trust statistics.**

Statistical process control over large Parquet datasets, powered by DuckDB.
Point it at a bucket of date-partitioned Parquet files, tell it which column
is the timestamp, which columns define the streams (group-by), and which
column is the value — and it tells you, per stream, whether the process that
generates that value has actually changed, or whether you're about to page
someone over routine noise.

The orientation is deliberately calming: most "the metric looks weird"
investigations are chasing common-cause variation. If the process is
operating within its natural limits, the principled answer is *"nothing has
changed; do not react"* — and duck-spc exists to give you that answer with a
straight face and a paper trail.

## What it does

- **XmR (individuals + moving range) charts** computed per group, entirely
  inside DuckDB — limits, derived streams, and detection rules are SQL
  pushed down over `read_parquet()`. Thousands of streams in one scan;
  nothing materializes in Python except the answers.
- **Frozen baselines as artifacts.** Limits are computed once from an
  explicit baseline window and saved to a JSON file with full provenance
  (source, derivation, window, per-group `center` / `LNPL` / `UNPL` /
  `mR̄`). Checks always run against frozen limits. Re-baselining is a
  deliberate human act, never automatic.
- **Minimal detection rules**: Rule 1 (point outside natural process
  limits) and Rule 2 (run of 9 on one side of the center line). No
  Western Electric rule zoo.
- **Stream derivation first-class.** Raw telemetry is rarely chartable
  (seasonality, trend, noise). Derive a stationary stream — per-period
  mean/median/p95/SD, first differences — in the same SQL, then chart that.
- **Composable CLI**: JSON on stdout, status on stderr, exit code carries
  the verdict.

## Doctrine (baked in, not configurable)

- Sigma comes from the **mean moving range** (`2.66 · mR̄`), never from
  `std(data)`. The global SD is inflated by the very signals you're hunting.
- **2.66 is not a knob.** No sensitivity tuning back into arbitrary
  thresholds.
- **Limits are frozen.** No rolling windows — rolling limits absorb every
  anomaly into the baseline and go silent.
- **No data transformations** (logs, winsorizing, outlier removal) before
  charting. Deriving a stationary stream changes *what* you chart, not the
  values' integrity.

## CLI

```bash
# 1. Compute frozen limits from a baseline window (writes JSON to stdout)
duck-spc baseline \
  --source 's3://my-bucket/events/' \
  --ts ts --value latency_ms \
  --group-by region,service \
  --derive day:p95 \
  --window 2026-01-01:2026-01-28 \
  > limits.json

# 2. Check new data against the frozen limits
duck-spc check --limits limits.json --since 2026-06-01
# → JSON signal report on stdout
# → exit 0: all streams within natural limits ("stop worrying")
# → exit 1: signals detected (Rule 1 / Rule 2 hits, per group)
# → exit 2: error

# 3. Render the classic XmR chart pair for one stream
duck-spc chart --limits limits.json --group us-east,checkout -o chart.png
```

`--source` accepts anything DuckDB can read: local globs,
`s3://bucket/prefix/` (hive-partitioned by date), `gs://`, `az://`.

`--derive` shapes the stream before charting:

| Value | Meaning |
|---|---|
| `none` | chart raw individual values (default) |
| `<period>:<stat>` | per-period statistic, e.g. `day:mean`, `day:p95`, `hour:median`, `day:sd` |
| `diff` | first differences (de-trending) |

## Library

The CLI is a thin shell over the importable API:

```python
from duck_spc import Source, Limits

src = Source(
    "s3://my-bucket/events/",
    ts="ts",
    value="latency_ms",
    group_by=["region", "service"],
)

# Derive the stationary stream, then freeze limits from a baseline window
stream = src.derive("day:p95")
limits = stream.baseline("2026-01-01", "2026-01-28")
limits.save("limits.json")

# Later (different process, different month): check against frozen limits
limits = Limits.load("limits.json")
report = limits.check(src, since="2026-06-01")

report.ok            # True → trust the statistics, go back to sleep
report.signals       # [{group, rule, ts, value, ...}] when not ok
report.to_json()

# Charts (matplotlib): X chart + mR chart, baseline window shaded
limits.chart(src, group=("us-east", "checkout"), out="chart.png")
```

## The limits artifact

`limits.json` is the contract between `baseline` and `check`. It records
its own provenance so a chart's limits are always traceable:

```json
{
  "version": 1,
  "computed_at": "2026-06-06T00:00:00Z",
  "source": "s3://my-bucket/events/",
  "ts": "ts", "value": "latency_ms",
  "group_by": ["region", "service"],
  "derive": "day:p95",
  "baseline_window": ["2026-01-01", "2026-01-28"],
  "groups": {
    "us-east,checkout": {
      "n": 28, "center": 412.3,
      "lnpl": 318.9, "unpl": 505.7,
      "mr_bar": 35.1, "mr_ucl": 114.7
    }
  }
}
```

## Build / run / test

```bash
make help        # list all targets
make setup       # uv sync
make test        # pytest
make lint        # ruff + ty
make demo        # generate synthetic parquet + run baseline/check end-to-end
```

Python ≥3.12, managed with `uv`. Core deps: `duckdb`, `numpy` (verification
only — the math of record runs in SQL), `matplotlib` (charts), `click` (CLI).

## Roadmap

- **DuckLake source**: `--source 'ducklake:postgres:...'` so limits/checks
  run against a lakehouse catalog instead of raw globs — same API, real
  snapshots/time-travel underneath.
- **Ingestion hot path**: a Postgres log front-end (à la
  [kafka-to-pg](https://github.com/brojonat/short-circuit)) whose sweeper
  archives into the lake duck-spc watches — live telemetry in, SPC verdicts
  out.
- **Nonparametric limits**: empirical-quantile limits from the frozen
  baseline for heavy-tailed/multimodal streams where 3-sigma machinery
  doesn't fit.
- **X̄ subgroup charts** for data with rational subgroups.
- **Weekday-residual derivation** (`value − frozen weekday median`) for
  day-of-week seasonal streams.
