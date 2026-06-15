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
  Western Electric rule zoo. One opt-in extra: `--mr-rule` flags moving
  ranges above mR_UCL (catches spread changes the X chart misses) — opt-in
  because every added rule buys sensitivity with false alarms.
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

## Quickstart: the happy path

duck-spc speaks Parquet with one column contract:
`(ts, <categorical group-by columns…>, value[, exposure])`. Get your data
into that shape (joins, unit conversion, normalization inputs are your job),
and everything below follows.

### 0. Kick the tires — sixty seconds, no data required

```bash
make setup        # uv sync
make demo         # writes synthetic telemetry (with planted signals) to demo_data/

uv run duck-spc look --source demo_data \
  --value value --group-by region,service --derive day:mean
```

BOOM — one ASCII XmR chart per group, planted signals caught red-handed:

```
── region=us-east, service=checkout ────────────────────────────
                          ●
 335.2 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  UNPL
            ·    ·    ·          ·      ·     ··   ·  ·
 331.1 ──·──··─·───··──·──··──·───··─·───··──·───·──··──── X̄
       · ·    ·   ·   ·  ·   ··  ·   · ·    ·   ·    ·
 326.9 ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  LNPL
       2026-01-01 ── dim = baseline, checked from 2026-01-29 ──
 ✗ 1 signal point(s) — first 2026-02-10 (rule1)

2/4 group(s) show special-cause variation — go find the cause(s).
```

The exit code *is* the verdict: `0` all stable, `1` signals, `2` error.
Baseline points render dim, checked points blue, signals red.

### 1. Point it at your bucket

```bash
duck-spc look --source 's3://my-bucket/events/' \
  --value latency_ms --group-by region,service --derive day:p95
```

`look` freezes a baseline from the **first 25% of the data** (it tells you
the window on stderr — pass `--window START:END` to choose deliberately),
checks everything after it, and puts the charts in your face. When you want
the data instead of the picture: `--json` for the report, `-o limits.json`
to keep the limits artifact it computed.

### 2. Graduate: freeze limits on purpose

Exploration done, baseline understood — now freeze it from a known-good
window and keep the artifact. This is the moment the limits stop being
exploratory and start being *the voice of the process*:

```bash
duck-spc baseline \
  --source 's3://my-bucket/events/' \
  --ts ts --value latency_ms \
  --group-by region,service \
  --derive day:p95 \
  --window 2026-01-01:2026-01-29 \
  > limits.json        # commit this — it carries its own provenance
```

### 3. Check on a schedule

```bash
# cron / CI / alert hook — quiet by default, the exit code does the talking
duck-spc check --limits limits.json

# a human investigating? pipe the same report into charts
duck-spc check --limits limits.json | duck-spc visualize
```

Reports embed the limits they were checked against, so the pipe Just Works —
and any saved report remains visualizable later, source intact.

### 4. When it fires

```bash
duck-spc chart --limits limits.json --group us-east,checkout -o incident.png
```

Rule 1 (point outside the limits) or Rule 2 (run of 9 one side of center):
the process changed — go find the assignable cause. And when you've fixed
it (or made a deliberate improvement the chart confirms), **re-baseline by
re-running `baseline` over a new window**. Never automatically; frozen
limits that quietly re-fit themselves are how charts go blind.

## Command reference

| Verb | Does | stdout | Exit code |
|---|---|---|---|
| `look` | one-shot: baseline + check + ASCII charts | charts (or `--json` report) | 0 stable / 1 signals / 2 error |
| `baseline` | freeze per-group limits from a window | limits artifact JSON | 0 / 2 |
| `check` | score data against frozen limits | report JSON (embeds limits) | 0 stable / 1 signals / 2 error |
| `visualize` | ASCII charts from artifact/report (stdin or FILE) | charts | 0 stable / 1 signals / 2 error |
| `chart` | render the X + mR pair for one group | — (writes image) | 0 / 2 |

All verbs put human narrative on **stderr** and machine-readable output on
**stdout**, so every command pipes. `--mr-rule` (on `look`/`check`/
`visualize`/`chart`) opts into the spread-change rule.

`--source` accepts anything DuckDB can read: local globs,
`s3://bucket/prefix/` (hive-partitioned by date), `gs://`, `az://`.

`--derive` shapes the stream before charting:

| Value | Meaning |
|---|---|
| `none` | chart raw individual values (default) |
| `<period>:<stat>` | per-period statistic, e.g. `day:mean`, `day:p95`, `hour:median`, `day:sd`, `day:count`, `day:rate` |
| `diff` | first differences (de-trending) |

Periods: `hour`, `day`, `week`, `month`. Stats: `mean`, `median`, `p90`,
`p95`, `p99`, `sd`, `count`, `sum`, `rate`. Windows are half-open
(`[start, end)`).

**Exposure.** Pass `--exposure <col>` (or `Source(..., exposure=...)`) when
rows carry unequal weight — units in operation, requests served. Then
`day:rate` charts `sum(value) / sum(exposure)` per period, which cannot be
precomputed upstream as a row-wise ratio (sum-of-ratios ≠ ratio-of-sums).
Without an exposure column every row counts as 1 and `rate` degenerates to
the per-period mean. Everything upstream of the
`(ts, categories…, value[, exposure])` contract — joins, unit conversions,
normalization inputs — is the caller's job.

## Bring your own schema (custom SQL)

Your Parquet rarely lands in the exact `(ts, category…, value[, exposure])`
shape. Instead of reshaping it on disk, hand `look`/`baseline` a `--query`
that projects your columns into the contract. It's a self-contained DuckDB
`SELECT` — read your files with `read_parquet(...)` inside it, rename and
compute as needed; `--ts` / `--value` / `--group-by` / `--exposure` then name
the columns *it outputs*:

```bash
duck-spc baseline \
  --query "SELECT event_time AS ts,
                  site            AS region,
                  status_code,
                  latency_ms      AS value
           FROM read_parquet('s3://bucket/raw/**/*.parquet')
           WHERE status_code < 500" \
  --value value --group-by region --window 2026-01-01:2026-01-29 \
  > limits.json
```

`--source` and `--query` are alternatives (give exactly one). The query is
saved into the limits artifact, so `check`/`visualize` reuse it with no extra
flags. In the library it's `Source.from_query(sql, ts=, value=, group_by=,
exposure=)`. Custom-SQL sources are materialized into a temp table before the
XmR math runs, so the query executes once per operation regardless of how
many streams it feeds.

## ⚠️ Seasonality and trend: derive a stationary stream first

**This is the easiest way to misuse SPC.** XmR limits assume successive points
are *exchangeable* — no day-of-week cycle, no time-of-day rhythm, no growth
trend. Point a control chart at raw seasonal/trending telemetry and you get
one of two failures: limits so wide they never fire, or a chart that alarms
every Monday morning forever. The chart isn't broken; it's faithfully
reporting that Mondays differ from Sundays — which you already knew.

The fix is never a fancier chart. It's **charting a derived stream that no
longer has the temporal structure.** duck-spc gives you, in increasing power:

- **`--derive diff`** — first differences. Kills a slow trend.
- **`--derive <period>:<stat>`** — chart a per-period statistic (`day:p95`,
  `hour:median`, …) instead of raw points; collapses within-period noise.
- **`--query` with a window function** — subtract the seasonal profile
  yourself. This deseasonalizes day-of-week effects in one line:

  ```sql
  SELECT ts, region, service,
         value - avg(value) OVER (PARTITION BY region, service, dayofweek(ts))
           AS value
  FROM read_parquet('s3://bucket/events/**/*.parquet')
  ```

  Then chart *that* residual — it's stationary, so the limits mean something.

If your process has genuine seasonality you haven't removed, **do not trust
the chart yet.** Richer automatic detrending (e.g. Prophet-style
seasonal/trend decomposition, frozen per-weekday baselines) is on the roadmap;
until then, derive the stream and sanity-check that it looks stationary before
reading signals into it.

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

# ...or shape a non-matching schema with a query:
# src = Source.from_query(
#     "SELECT event_time AS ts, site AS region, latency_ms AS value "
#     "FROM read_parquet('s3://bucket/raw/**/*.parquet')",
#     ts="ts", value="value", group_by=["region"],
# )

# Derive the stationary stream, then freeze limits from a baseline window
stream = src.derive("day:p95")
limits = stream.baseline("2026-01-01", "2026-01-29")   # half-open [start, end)
limits.save("limits.json")

# Later (different process, different month): check against frozen limits
limits = Limits.load("limits.json")
report = limits.check(src, since="2026-06-01")         # mr_rule=True to opt in

report.ok            # True → trust the statistics, go back to sleep
report.signals       # [{group, rules, ts, value, ...}] when not ok
report.to_json()

# Charts (matplotlib): X chart + mR chart, baseline window shaded
limits.chart(("us-east", "checkout"), "chart.png", source=src)
```

## The limits artifact

`limits.json` is the contract between `baseline` and `check`. It records
its own provenance so a chart's limits are always traceable:

```json
{
  "version": 2,
  "computed_at": "2026-06-06T00:00:00+00:00",
  "source": "s3://my-bucket/events/",
  "source_sql": null,
  "ts": "ts", "value": "latency_ms", "exposure": null,
  "group_by": ["region", "service"],
  "derive": "day:p95",
  "baseline_window": ["2026-01-01", "2026-01-29"],
  "groups": [
    {
      "key": {"region": "us-east", "service": "checkout"},
      "n": 28, "center": 412.3,
      "mr_bar": 35.1, "lnpl": 318.9, "unpl": 505.7, "mr_ucl": 114.7
    }
  ]
}
```

Exactly one of `source` (a Parquet path) or `source_sql` (a custom query) is
set; the other is `null`. Group keys are explicit column/value maps (not
joined strings), so categorical values containing commas can't corrupt the
contract. (v1 artifacts without `source_sql` still load.)

## Presentation

The sales pitch — *why you can trust 2.66 even against pathological
distributions* — lives in two artifacts:

- **`notebooks/trust_the_limits.py`** — marimo notebook
  (`make edit-notebook`). Interactive: the d₂ derivation, the
  distribution-free bounds (Chebyshev 11.1% / unimodal 4.9% / normal 0.27%),
  and the empirical gauntlet running the full XmR procedure against
  heavy-tailed monsters. Every number in the deck is computed here.
- **`docs/deck/index.html`** — a self-contained HTML slide deck
  (`make run-deck`, then http://localhost:8042). Dark-themed, mobile-responsive,
  with keyboard / swipe / on-screen-button navigation and live d3 visuals: a
  streaming stable process, the XmR anatomy, the false-alarm gauntlet, an
  SD-vs-mR̄ comparison, a distribution-morph (shapes go pathological while the
  ±3σ tail mass stays tiny), and a frozen-vs-rolling-limits demo. One file, d3
  from a CDN, no build step.

### Where the deck is published (vendoring)

`docs/deck/index.html` is the **canonical source**. The blog
([brojonat.com](https://brojonat.com)) hosts a copy at
[`/spc/`](https://brojonat.com/spc/), linked from the companion post. That
copy is **vendored**, not submoduled: the `brojonat-hugo` repo pulls the deck
from this repo's remote and commits it into its own `static/`.

To refresh the published deck after editing it here:

1. Commit and push the deck change in this repo.
2. In the `brojonat-hugo` repo, run `make vendor-deck` — it shallow-clones this
   repo into a temp dir and copies the deck into `static/spc/`. Review the
   diff, commit, then `make deploy`.

The hugo build uses its committed copy, so deploying never needs this repo
checked out as a sibling or any network access. (Vendored rather than a git
submodule on purpose: nothing to `submodule init`, the site stays
self-contained and builds offline, and diffs show real content instead of a
commit-pointer bump.)

## Build / run / test

```bash
make help        # list all targets
make setup       # uv sync
make test        # pytest
make lint        # ruff + ty
make demo        # synthetic parquet -> baseline -> check -> chart, end to end
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
