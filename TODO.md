# TODO

## Bootstrap
- [x] README with library API + CLI design
- [x] Lean install-skills.sh + skills-lock.json (replaced blanket install)
- [ ] pyproject.toml scaffold (uv, ruff, ty, pytest; `duck-spc` entry point)

## v1 — XmR over Parquet
- [ ] Synthetic data generator: date-partitioned parquet with known injected
      signals (spike, sustained shift, variance increase) for demo + tests
- [ ] SQL: stream derivation (`none`, `<period>:<stat>`, `diff`) as a
      composable CTE over `read_parquet()`
- [ ] SQL: per-group XmR limits from a baseline window (center, mR̄, NPLs)
- [ ] SQL: detection — Rule 1 (outside limits), Rule 2 (run of 9, via
      gaps-and-islands)
- [ ] Limits artifact: schema v1, save/load with provenance validation
- [ ] Library API: `Source`, `Stream` (`.derive`, `.baseline`), `Limits`
      (`.check`, `.chart`, `.save/.load`), `Report`
- [ ] CLI: `baseline` / `check` / `chart` verbs; JSON stdout, status stderr,
      exit 0/1/2
- [ ] Charts: X + mR pair, baseline window shaded, signals in red
- [ ] Tests: SQL results vs numpy reference impl (from the SPC skill) on the
      synthetic data; rule hits match injected signals exactly
- [ ] `make demo`: generate → baseline → check → chart end-to-end

## Roadmap (post-v1)
- [ ] DuckLake source (`ducklake:postgres:...`) [blocked: v1]
- [ ] Nonparametric quantile limits for heavy-tailed streams
- [ ] Weekday-residual derivation (frozen per-weekday medians)
- [ ] X̄ subgroup charts
- [ ] Ingestion hot path (pg-messaging style log → sweeper → lake)
      [blocked: ducklake source]
