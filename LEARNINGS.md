# Learnings

Hard-won knowledge. Each entry: *what happened, why it was surprising, how
to avoid it.*

## `npx skills add` only sees what's pushed to GitHub

**What happened:** `npx skills add brojonat/llmsrules -s
statistical-process-control` failed with "No matching skills found" even
though the skill existed at `~/projects/llmsrules/skills/`. The skill
directory was untracked — never committed or pushed — so the fresh clone
npx makes didn't contain it.

**Why it was surprising:** the skill was visibly present on disk and other
skills from the same repo installed fine, so the error read like a name
typo rather than a sync problem.

**How to avoid it:** when an install of a freshly authored skill fails,
check `git status` in the source repo before debugging the skill name or
the tool. New skills must be committed *and pushed* before they're
installable. The "Available skills" list npx prints on failure is the
ground truth of what's on the remote — diff it against expectations.

## Design doctrine for this project (from the SPC skill — do not relitigate)

Not a bug story, but worth pinning so future sessions don't "helpfully"
deviate:

- Limits come from the mean moving range (`2.66 · mR̄`), never
  `mean ± 3·std(data)` — the global SD is inflated by the signals.
- `2.66` and `3.268` are not tunable parameters.
- Limits are frozen from an explicit baseline window; never rolling.
- Detection is Rule 1 + Rule 2 only by default.
- Seasonal/trending data gets a *derived stream*, not a data transform.
