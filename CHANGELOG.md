# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] - 2026-06-06

### Added

- v1 core: `Source`/`Stream`/`Limits`/`Report` library API with all XmR math
  (derivations, per-group limits, Rule 1 + Rule 2 detection) pushed down into
  DuckDB SQL over `read_parquet()`. Limits artifact (schema v1) with full
  provenance; group keys are explicit column/value maps.
- Explicit optional `exposure` column (default 1): `<period>:rate` derivation
  computes `sum(value)/sum(exposure)` inside the engine, since per-period
  rates cannot be precomputed row-wise upstream.
- Synthetic data generator (`duck_spc.synth`) emitting hive-partitioned
  Parquet plus a ground-truth manifest of injected signals (spike / shift /
  variance), magnitudes expressed in daily-stream sigmas.
- Test suite cross-checking the SQL against the SPC skill's numpy reference
  implementation point-for-point, and asserting injected signals are
  recovered exactly (clean group stays silent).
- `make demo`: generate → baseline → check end-to-end; report JSON on
  stdout, narrative on stderr.

- CLI (`duck-spc baseline|check|chart`, Click): JSON on stdout, narrative on
  stderr, exit 0 = stable / 1 = signals / 2 = error. Source overrides reuse
  the artifact's column contract.
- `duck-spc look`: one-shot exploration — freeze a baseline (defaults to the
  first 25% of the data), check the rest, render ASCII XmR charts and
  per-group verdicts straight to the terminal; `--json` for scripting.
- `duck-spc visualize`: Unix pipe sink — renders ASCII charts from a limits
  artifact or a check report on stdin/FILE. Check reports now embed their
  limits artifact (provenance + pipeability); hand-rolled zero-dependency
  renderer with ANSI color on TTYs (NO_COLOR respected). CLI errors are
  uniformly exit 2 so exit 1 strictly means "signals detected".
- XmR chart pair rendering (`Limits.chart` / `chart` verb): X + mR panels,
  frozen-limit provenance in the title, baseline shaded, signals red; mR
  breaches amber (advisory) unless `--mr-rule` opted in. Wired into
  `make demo`.
- Opt-in mR rule (`check --mr-rule`): moving range above mR_UCL flags spread
  changes the X chart misses; off by default per minimal-rules doctrine. The
  injected variance x3 fixture is now detected and asserted in tests.
- Presentation layer: marimo story notebook (`trust_the_limits.py`) with the
  2.66 derivation, Chebyshev/Vysochanskij–Petunin bounds, and an empirical
  gauntlet (full XmR procedure vs pathological distributions: lognormal
  4.5%, pareto α=2.5 4.8% false alarms — all under the 4.9% unimodal bound);
  self-contained d3 slide deck (`docs/deck/`) with live visuals and stubbed
  animation hooks. `make run-deck` / `make edit-notebook` /
  `make check-notebook`.
- marimo-pair skill pinned for live notebook pairing sessions.

### Changed

- README artifact format: `groups` is a list with explicit `key` maps
  (comma-joined keys would corrupt on categorical values containing commas);
  baseline windows documented as half-open `[start, end)`.

## [0.0.1] - 2026-06-06

### Added

- Project bootstrap: README designing both the library API (`Source` /
  `Stream` / `Limits` / `Report`) and the CLI surface (`baseline` / `check` /
  `chart`) before any code.
- Lean `install-skills.sh` (8 skills matched to README capabilities) and
  regenerated `skills-lock.json`, replacing a blanket whole-catalog install.
- Bookkeeping files: TODO.md, CHANGELOG.md, LEARNINGS.md.

### Removed

- Blanket `.agents/skills` install (90+ skills) and its lockfile.
