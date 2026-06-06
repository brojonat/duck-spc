# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] - 2026-06-06

### Added

- Project bootstrap: README designing both the library API (`Source` /
  `Stream` / `Limits` / `Report`) and the CLI surface (`baseline` / `check` /
  `chart`) before any code.
- Lean `install-skills.sh` (8 skills matched to README capabilities) and
  regenerated `skills-lock.json`, replacing a blanket whole-catalog install.
- Bookkeeping files: TODO.md, CHANGELOG.md, LEARNINGS.md.

### Removed

- Blanket `.agents/skills` install (90+ skills) and its lockfile.
