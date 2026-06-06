"""Shared fixture: one synthetic dataset with known injected signals.

Day indexing: day 0 = 2026-01-01. Baseline window is days 0..27
([2026-01-01, 2026-01-29), 28 daily points); checks run on days 28..69.

Injected ground truth:
  (us-east, checkout)  spike, day 40 (2026-02-10), 6 daily-sigmas  -> Rule 1
  (us-east, search)    shift from day 35 (2026-02-05), 2 daily-sigmas -> Rule 2
  (eu-west, checkout)  variance x3 from day 45 (not asserted until mR rules land)
  (eu-west, search)    clean -> must stay silent
"""

from datetime import date

import pytest

from duck_spc import Source
from duck_spc.synth import Signal, generate

START = date(2026, 1, 1)
BASELINE = ("2026-01-01", "2026-01-29")
SPIKE_GROUP = {"region": "us-east", "service": "checkout"}
SHIFT_GROUP = {"region": "us-east", "service": "search"}
VARIANCE_GROUP = {"region": "eu-west", "service": "checkout"}
CLEAN_GROUP = {"region": "eu-west", "service": "search"}
SPIKE_DAY = "2026-02-10"
SHIFT_DAY = "2026-02-05"
VARIANCE_DAY = "2026-02-15"


@pytest.fixture(scope="session")
def dataset(tmp_path_factory):
    out = tmp_path_factory.mktemp("synth")
    manifest = generate(
        out,
        start=START,
        days=70,
        events_per_day=200,
        seed=7,
        signals=[
            Signal(SPIKE_GROUP, "spike", date(2026, 2, 10), 6.0),
            Signal(SHIFT_GROUP, "shift", date(2026, 2, 5), 2.0),
            Signal(VARIANCE_GROUP, "variance", date(2026, 2, 15), 3.0),
        ],
    )
    return out, manifest


@pytest.fixture(scope="session")
def source(dataset):
    out, _ = dataset
    return Source(str(out), ts="ts", value="value", group_by=("region", "service"))


@pytest.fixture(scope="session")
def limits(source):
    return source.derive("day:mean").baseline(*BASELINE)
