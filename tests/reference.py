"""Numpy reference implementation, copied from the statistical-process-control
skill. This is the test oracle: the SQL pushdown in duck_spc.sql must agree
with it exactly."""

import numpy as np


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
        "mr_ucl": 3.268 * mr_bar,
    }


def xmr_signals(values: np.ndarray, lim: dict) -> dict:
    """Rule 1 (outside limits) and Rule 2 (run of 9 on one side)."""
    x = np.asarray(values, dtype=float)
    outside = (x > lim["unpl"]) | (x < lim["lnpl"])
    side = np.sign(x - lim["center"])
    run = np.zeros(len(x), dtype=bool)
    streak = 0
    for i in range(len(x)):
        streak = streak + 1 if i > 0 and side[i] == side[i - 1] and side[i] != 0 else 1
        if streak >= 9:
            run[i - 8 : i + 1] = True
    return {"outside_limits": outside, "run_of_nine": run}
