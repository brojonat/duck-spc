# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo",
#     "numpy>=2.0",
#     "matplotlib>=3.9",
# ]
# ///

"""How I Learned to Stop Worrying and Trust Statistics.

The story of 2.66: why XmR process-behaviour limits are trustworthy even
when you know nothing about the distribution generating your metric.
Companion notebook to duck-spc (and the slide deck in docs/deck/).
"""

import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np

    return mo, np, plt


@app.cell
def _(mo):
    mo.md(r"""
    # How I Learned to Stop Worrying and Trust Statistics

    Every metric wiggles. The question that matters is never *"did the number
    change?"* — it always changed — but **"did the process that generates the
    number change?"**

    Getting that question wrong is expensive in both directions:

    | Mistake | What it costs |
    |---|---|
    | Chasing routine noise | wasted investigations, and *tampering* — adjusting a stable process provably makes it worse |
    | Dismissing a real shift | the regression ships, the pump fails, the fraud continues |

    The tool is the **XmR chart**: natural process limits at
    $\bar{X} \pm 2.66\,\overline{mR}$, where $\overline{mR}$ is the mean of
    consecutive absolute differences. This notebook is about why you can
    trust that one constant — **even if the underlying distribution is the
    most pathological thing you can cook up**.
    """)
    return


@app.cell
def _(np):
    def xmr_limits(baseline: np.ndarray) -> dict:
        """Natural process limits from a frozen baseline window."""
        x = np.asarray(baseline, dtype=float)
        center = x.mean()
        mr_bar = np.abs(np.diff(x)).mean()
        return {
            "center": center,
            "lnpl": center - 2.66 * mr_bar,  # 2.66 = 3/1.128; do not tune
            "unpl": center + 2.66 * mr_bar,
            "mr_bar": mr_bar,
        }

    return (xmr_limits,)


@app.cell
def _(mo):
    mo.md(r"""
    ## 1. A stable process, in the flesh

    Here is a perfectly stable process — nothing happens, all week, every
    week. Every point is different. No point has an explanation. Drag the
    seed: the wiggles change, the *story* doesn't. This is what "nothing is
    wrong" looks like, and it never looks like a flat line.
    """)
    return


@app.cell
def _(mo):
    seed_slider = mo.ui.slider(0, 50, 1, value=7, label="random seed (a different, equally boring week)")
    seed_slider
    return (seed_slider,)


@app.cell
def _(np, plt, seed_slider, xmr_limits):
    rng_stable = np.random.default_rng(seed_slider.value)
    stable = rng_stable.normal(100, 6, size=60)
    lim_stable = xmr_limits(stable[:28])

    fig_stable, ax_stable = plt.subplots(figsize=(9, 3.2))
    ax_stable.plot(stable, marker="o", ms=3.5, lw=1, color="#4c9be8")
    ax_stable.axhline(lim_stable["center"], color="#888", lw=1)
    ax_stable.axhline(lim_stable["unpl"], color="#888", lw=1, ls="--")
    ax_stable.axhline(lim_stable["lnpl"], color="#888", lw=1, ls="--")
    ax_stable.axvspan(0, 27, color="#4c9be8", alpha=0.08, label="baseline (limits frozen here)")
    ax_stable.set_title("A stable process: routine variation, zero explanations required")
    ax_stable.legend(loc="upper right", fontsize=8)
    ax_stable.set_xlabel("observation")
    fig_stable
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 2. Where 2.66 comes from (it's not arbitrary, and it's not normality)

    Two ingredients:

    1. For consecutive observations from a stable process, the expected
       absolute difference is $E|X_i - X_{i-1}| = d_2 \, \sigma$ with
       $d_2 = 1.128$. So $\hat{\sigma} = \overline{mR} / 1.128$ — a sigma
       estimate built from *point-to-point* variation only, which signals
       (shifts, outliers) barely contaminate.
    2. Limits go at $\pm 3 \hat{\sigma}$ — Shewhart's *economic* choice,
       balancing the cost of false alarms against missed signals across a
       century of practice.

    Multiply: $3 / 1.128 = 2.66$. The simulation below checks ingredient 1.
    """)
    return


@app.cell
def _(mo, np):
    d2_rng = np.random.default_rng(0)
    d2_draws = d2_rng.normal(0, 1, size=(200_000, 2))
    d2_hat = np.abs(d2_draws[:, 0] - d2_draws[:, 1]).mean()
    mo.md(
        f"Simulated $E|X-Y|$ for two standard normals: **{d2_hat:.4f}** "
        f"(theory: $2/\\sqrt{{\\pi}} = {2 / np.sqrt(np.pi):.4f}$). "
        f"Hence $3/{d2_hat:.3f} \\approx 2.66$."
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 3. "But my data isn't normal!" — the pathological gauntlet

    Good news: **nothing above assumed your data is normal.** The $\pm 3\sigma$
    choice is protected by distribution-free bounds:

    | Assumption about your distribution | P(point beyond $3\sigma$) | Guarantee |
    |---|---|---|
    | **Nothing at all** (finite variance) — Chebyshev | $\le 1/9 \approx 11.1\%$ | even the adversarial worst case rarely alarms |
    | **Unimodal only** — Vysochanskij–Petunin | $\le 4/81 \approx 4.9\%$ | one weak, checkable assumption halves the haystack twice |
    | Normal | $0.27\%$ | the familiar best case |

    But bounds are bounds. Below we run the **actual XmR procedure** —
    finite baseline, $\overline{mR}$-estimated sigma, frozen limits — against
    genuinely nasty distributions and measure how often a *stable* process
    falsely alarms. This is the honest number: the whole procedure,
    estimation error included.
    """)
    return


@app.cell
def _(mo):
    baseline_slider = mo.ui.slider(10, 50, 1, value=28, label="baseline points (limits frozen from these)")
    trials_slider = mo.ui.slider(100, 1000, 100, value=400, label="simulated stable processes per distribution")
    mo.vstack([baseline_slider, trials_slider])
    return baseline_slider, trials_slider


@app.cell
def _(np):
    def make_distributions():
        """Stable processes with increasingly hostile shapes. Each returns
        i.i.d. draws — stable by construction, so every alarm is false."""
        sqrt3 = np.sqrt(3.0)
        return {
            "normal": lambda rng, n: rng.normal(0, 1, n),
            "uniform": lambda rng, n: rng.uniform(-sqrt3, sqrt3, n),
            "exponential (skewed)": lambda rng, n: rng.exponential(1, n),
            "lognormal (heavy tail)": lambda rng, n: rng.lognormal(0, 1, n),
            "pareto a=2.5 (very heavy tail)": lambda rng, n: rng.pareto(2.5, n),
            "bimodal mixture": lambda rng, n: np.where(
                rng.random(n) < 0.5, rng.normal(-2, 0.5, n), rng.normal(2, 0.5, n)
            ),
        }

    return (make_distributions,)


@app.cell
def _(baseline_slider, make_distributions, np, trials_slider, xmr_limits):
    def false_alarm_rate(draw, n_baseline, n_check, trials, seed):
        """Rule 1 false alarms per point for a stable (i.i.d.) process,
        running the full XmR procedure per trial."""
        rng = np.random.default_rng(seed)
        alarms = 0
        for _ in range(trials):
            x = draw(rng, n_baseline + n_check)
            lim = xmr_limits(x[:n_baseline])
            check = x[n_baseline:]
            alarms += int(((check > lim["unpl"]) | (check < lim["lnpl"])).sum())
        return alarms / (trials * n_check)

    gauntlet = {
        name: false_alarm_rate(
            draw,
            n_baseline=baseline_slider.value,
            n_check=500,
            trials=trials_slider.value,
            seed=42,
        )
        for name, draw in make_distributions().items()
    }
    return (gauntlet,)


@app.cell
def _(gauntlet, np, plt):
    names = list(gauntlet)
    rates = [100 * gauntlet[n] for n in names]

    fig_g, ax_g = plt.subplots(figsize=(9, 4))
    bars = ax_g.barh(np.arange(len(names)), rates, color="#4c9be8")
    ax_g.set_yticks(np.arange(len(names)), names)
    ax_g.invert_yaxis()
    ax_g.axvline(100 / 9, color="#e85d5d", ls="--", lw=1.2)
    ax_g.text(100 / 9, -0.6, "Chebyshev worst case 11.1%", color="#e85d5d", fontsize=8, ha="center")
    ax_g.axvline(400 / 81, color="#e8a33d", ls="--", lw=1.2)
    ax_g.text(400 / 81, len(names) - 0.2, "unimodal bound 4.9%", color="#e8a33d", fontsize=8, ha="center")
    ax_g.axvline(0.27, color="#5dc78a", ls="--", lw=1.2)
    ax_g.text(0.27, len(names) - 0.2, "normal 0.27%", color="#5dc78a", fontsize=8, ha="left")
    ax_g.bar_label(bars, fmt="%.2f%%", fontsize=8, padding=3)
    ax_g.set_xlabel("false alarms per stable point (Rule 1), full XmR procedure")
    ax_g.set_title("The gauntlet: even pathological distributions rarely false-alarm at 2.66")
    fig_g.tight_layout()
    fig_g
    return


@app.cell
def _(gauntlet, mo):
    worst = max(gauntlet.items(), key=lambda kv: kv[1])
    mo.md(
        f"""
    **Read it off:** the worst distribution we could throw at the chart —
    *{worst[0]}* — falsely alarms on **{100 * worst[1]:.1f}%** of stable
    points, comfortably under Chebyshev's adversarial ceiling of 11.1%, and
    most realistic shapes land in low single digits. At one point per day,
    even the heavy-tailed cases page you a couple of times a quarter *if
    your process is truly that ugly* — and the fix for that is the
    nonparametric quantile-limits mode on the duck-spc roadmap, not a
    different constant.

    **This is the sales pitch in one sentence:** you don't have to know your
    distribution for the chart to be useful — the limits are conservative by
    construction, and every assumption you *can* defend (unimodality) only
    tightens them.
    """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## 4. Why $\overline{mR}$ and not the standard deviation of the data

    The classic objection: "isn't this just mean ± 3 SD?" **No — and the
    difference is the whole trick.** The global SD measures the spread of
    everything, *including the signals you're hunting*. Inject a shift and
    the SD swells, the limits swell with it, and the chart goes blind to its
    own signal. The moving range only sees point-to-point variation, so the
    shift contaminates exactly one of its terms.
    """)
    return


@app.cell
def _(np, plt, xmr_limits):
    rng_shift = np.random.default_rng(3)
    shifted = np.concatenate(
        [rng_shift.normal(100, 5, 30), rng_shift.normal(115, 5, 30)]  # 3-sigma shift at t=30
    )
    lim_mr = xmr_limits(shifted)  # naive: limits from ALL data, mR-based
    naive_sd = shifted.std(ddof=1)
    naive_hi = shifted.mean() + 3 * naive_sd
    naive_lo = shifted.mean() - 3 * naive_sd

    fig_sd, axes_sd = plt.subplots(1, 2, figsize=(10, 3.4), sharey=True)
    for ax_i, (title, hi, lo, mid) in zip(
        axes_sd,
        [
            ("mean ± 3·std(data): the shift inflates its own limits", naive_hi, naive_lo, shifted.mean()),
            ("± 2.66·mR̄: the shift stands out", lim_mr["unpl"], lim_mr["lnpl"], lim_mr["center"]),
        ],
        strict=True,
    ):
        out = (shifted > hi) | (shifted < lo)
        ax_i.plot(shifted, marker="o", ms=3, lw=0.9, color="#4c9be8")
        ax_i.plot(np.where(out)[0], shifted[out], "o", ms=5, color="#e85d5d")
        ax_i.axhline(mid, color="#888", lw=1)
        ax_i.axhline(hi, color="#888", lw=1, ls="--")
        ax_i.axhline(lo, color="#888", lw=1, ls="--")
        ax_i.axvline(29.5, color="#e8a33d", lw=1, ls=":")
        ax_i.set_title(title, fontsize=9)
    fig_sd.suptitle("Same data, same shift — only one chart sees it", y=1.04)
    fig_sd.tight_layout()
    fig_sd
    return


@app.cell
def _(mo):
    mo.md(r"""
    *(Note the deck is even harsher than this demo: doctrine says compute
    limits from a frozen clean baseline, in which case the contrast is
    starker still. Here both panels got the contaminated data — the mR̄
    limits survive contamination, the SD limits don't.)*

    ## 5. Takeaways

    1. **Chart the process, not your anxiety.** Within natural limits →
       routine variation → no explanations exist; go back to sleep.
    2. **2.66 is not a knob.** It's $3/d_2$, the 3 is a century-old economic
       optimum, and distribution-free bounds make it conservative for *any*
       finite-variance process. Tuning it just re-invents arbitrary
       thresholds.
    3. **The moving range is the trick** — sigma from point-to-point
       variation stays honest even when the data contains the very signals
       you're looking for.
    4. **Freeze the limits.** A stable process is one where next month looks
       like the baseline; rolling limits absorb anomalies and go silent.

    duck-spc pushes exactly this math into DuckDB SQL over your Parquet —
    thousands of streams per scan, frozen-limit artifacts with provenance,
    and an exit code that tells your pager whether anything *actually*
    happened. See `README.md` and the slide deck under `docs/deck/`.
    """)
    return


if __name__ == "__main__":
    app.run()
