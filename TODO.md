# TODO

## Bootstrap
- [x] README with library API + CLI design
- [x] Lean install-skills.sh + skills-lock.json (replaced blanket install)
- [x] pyproject.toml scaffold (uv, ruff, ty, pytest)

## v1 — XmR over Parquet
- [x] Synthetic data generator: date-partitioned parquet with known injected
      signals (spike, sustained shift, variance increase) for demo + tests
- [x] SQL: stream derivation (`none`, `<period>:<stat>`, `diff`) over
      `read_parquet()`; explicit optional exposure column (`rate` = sum/sum)
- [x] SQL: per-group XmR limits from a baseline window (center, mR̄, NPLs)
- [x] SQL: detection — Rule 1 (outside limits), Rule 2 (run of 9, via
      gaps-and-islands)
- [x] Limits artifact: schema v1, save/load with provenance validation
- [x] Library API: `Source`, `Stream` (`.derive`, `.baseline`), `Limits`
      (`.check`, `.evaluate`, `.save/.load`), `Report`
- [x] Tests: SQL results vs numpy reference impl (from the SPC skill) on the
      synthetic data; rule hits match injected signals exactly
- [x] `make demo`: generate → baseline → check end-to-end
- [x] CLI: `baseline` / `check` / `chart` verbs; JSON stdout, status stderr,
      exit 0/1/2; `duck-spc` entry point in pyproject
- [x] Charts: X + mR pair, baseline window shaded, signals in red
      (`Limits.chart`); wired into `make demo` (demo_data/spike.png)
- [x] mR-chart rule (moving range above mR_UCL), opt-in via
      `check(mr_rule=True)` / `--mr-rule`; variance x3 fixture asserted
- [x] `duck-spc look`: one-shot explore verb (default baseline = first 25%),
      ASCII XmR charts + verdicts on stdout, `--json` for scripting
- [x] `duck-spc visualize`: pipe sink rendering ASCII charts from a limits
      artifact or check report on stdin (reports embed their limits)
- [ ] ASCII mR strip under the X chart in visualize/look (currently the mR
      story is signal markers + verdict text only)

## Presentation
- [x] marimo story notebook (`notebooks/trust_the_limits.py`): d2 derivation,
      distribution-free bounds, empirical false-alarm gauntlet, SD-trap demo
- [x] HTML slide deck (`docs/deck/index.html`): custom engine, d3 visuals
      (live stable process, XmR anatomy, gauntlet bars, SD-vs-mR̄ panels)
- [ ] Decide on / build the stubbed animations (`TODO(anim)` markers):
      distribution-morph with stable 3σ tail mass (centerpiece), limits
      drawn left-to-right, SD-limits inflating live, rolling-limits
      absorbing an anomaly, pager vignette
- [ ] Second notebook: drive the real duck-spc pipeline (synth → baseline →
      check) once the local-package story for sandboxed notebooks is settled
- [ ] Deck: regenerate gauntlet numbers from the notebook when defaults
      change (numbers are pasted into `hooks["gauntlet"]`, provenance noted)

## Entry points & detrending
- [x] Custom SQL entry point: `Source.from_query` / `--query` projects any
      Parquet into the contract; query saved in the artifact; materialized to
      a temp table so it runs once and nested window functions work
- [x] Seasonality footgun: prominent README callout + the simple escape
      hatches (`diff`, `<period>:<stat>`, deseasonalize-in-`--query`)
- [ ] Automatic detrending exploration — evaluate **Facebook Prophet**
      (seasonal/trend decomposition) as an optional preprocessing step, vs a
      lighter built-in. Open questions: extra dep weight, where it runs
      (Python vs SQL), and how the removed seasonal profile gets frozen into
      the artifact so `check` stays reproducible
- [ ] Weekday-residual derivation as a first-class `--derive` (frozen
      per-weekday medians in the artifact) — the no-new-dep version of the above
- [ ] Stationarity sanity check: warn when a chosen stream still looks
      seasonal/autocorrelated (so the footgun gets caught, not just documented)

## Roadmap (post-v1)
- [ ] DuckLake source (`ducklake:postgres:...`) [blocked: v1]
- [ ] Nonparametric quantile limits for heavy-tailed streams
- [ ] X̄ subgroup charts
- [ ] Ingestion hot path (pg-messaging style log → sweeper → lake)
      [blocked: ducklake source]
