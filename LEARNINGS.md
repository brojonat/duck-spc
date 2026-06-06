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

## `make target | tail` masks failures

**What happened:** `make lint 2>&1 | tail -3 && git commit ...` committed
even though lint had failed with 12 errors — a shell pipeline's exit status
is the *last* command's (tail's success), not make's failure.

**Why it was surprising:** the `&&` chain looked like it gated the commit on
lint passing; the pipe silently broke the gate.

**How to avoid it:** never pipe a command whose exit code you're about to
act on. Run the gate bare (`make lint && git commit ...`) and only pipe in
separate, decorative invocations. (`set -o pipefail` also works but isn't on
in `make`/`sh` by default.)

## marimo notebooks need their own lint posture

**What happened:** ruff flagged B018 ("useless expression") and E501 on the
story notebook; ty failed on `import marimo`.

**Why it was surprising:** all three are *idioms*, not bugs — a bare
trailing expression IS how a marimo cell renders output; markdown prose runs
long; PEP 723 sandbox deps (marimo, matplotlib) are intentionally not
project deps.

**How to avoid it:** per-file ruff ignores (`"notebooks/*.py" = ["B018",
"E501"]`) and `[tool.ty.src] exclude = ["notebooks"]` in pyproject. Notebook
correctness is `uvx marimo check` + a script-mode run — that's what
`make check-notebook` does. Also: `marimo check --fix` auto-dedents markdown
cells and will rewrite the file under you.

## Deck engine: hash-only navigation doesn't reload

**What happened:** driving the deck to `#8` via CDP changed the URL but not
the slide — same-document hash changes don't re-run the boot script, and the
engine only read the hash at load.

**How to avoid it:** any hash-routed page needs a `hashchange` listener,
which also makes browser back/forward work. (Fixed in docs/deck/index.html.)

## Design doctrine for this project (from the SPC skill — do not relitigate)

Not a bug story, but worth pinning so future sessions don't "helpfully"
deviate:

- Limits come from the mean moving range (`2.66 · mR̄`), never
  `mean ± 3·std(data)` — the global SD is inflated by the signals.
- `2.66` and `3.268` are not tunable parameters.
- Limits are frozen from an explicit baseline window; never rolling.
- Detection is Rule 1 + Rule 2 only by default.
- Seasonal/trending data gets a *derived stream*, not a data transform.
