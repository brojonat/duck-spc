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
- [ ] CLI: `baseline` / `check` / `chart` verbs; JSON stdout, status stderr,
      exit 0/1/2; `duck-spc` entry point in pyproject
- [ ] Charts: X + mR pair, baseline window shaded, signals in red
      (`Limits.chart`, add matplotlib dep); wire a chart into `make demo`
- [ ] mR-chart rule (moving range above mR_UCL) so the injected variance
      signal in the test fixture is detectable, then assert on it

## Roadmap (post-v1)
- [ ] DuckLake source (`ducklake:postgres:...`) [blocked: v1]
- [ ] Nonparametric quantile limits for heavy-tailed streams
- [ ] Weekday-residual derivation (frozen per-weekday medians)
- [ ] X̄ subgroup charts
- [ ] Ingestion hot path (pg-messaging style log → sweeper → lake)
      [blocked: ducklake source]
