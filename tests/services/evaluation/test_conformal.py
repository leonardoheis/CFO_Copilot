import math

import numpy as np
import pandas as pd
import pytest

from app.services.evaluation import rolling_half_widths

ORIGINS = pd.date_range("1996-03-31", periods=120, freq="QE")
COMPANIES = 40
WINDOW = 20
TEST_ORIGINS = list(ORIGINS[-60:])


def _errors(scale: np.ndarray) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    origin_dates = np.repeat(ORIGINS, COMPANIES)
    return pd.DataFrame({
        "origin_date": origin_dates,
        "target_date": origin_dates + pd.offsets.QuarterEnd(1),
        "error": rng.normal(0.0, np.repeat(scale, COMPANIES)),
    })


def _coverage(errors: pd.DataFrame, half_widths: pd.Series) -> float:
    tested = errors[errors["origin_date"].isin(half_widths.index)]
    width = tested["origin_date"].map(half_widths)
    return float((tested["error"].abs() <= width).mean())


@pytest.mark.parametrize("level", [0.80, 0.90, 0.95])
def test_exchangeable_errors_reach_nominal_coverage(level: float) -> None:
    errors = _errors(np.ones(len(ORIGINS)))

    half_widths = rolling_half_widths(
        errors, TEST_ORIGINS, level=level, window=WINDOW, step=0.05
    )

    assert _coverage(errors, half_widths) == pytest.approx(level, abs=0.02)


def test_errors_whose_target_is_after_the_origin_never_calibrate() -> None:
    errors = _errors(np.ones(len(ORIGINS)))
    origin = TEST_ORIGINS[0]
    before = rolling_half_widths(errors, [origin], level=0.9, window=WINDOW, step=0.05)

    # The origin's own errors have their target a quarter after it.
    errors.loc[errors["origin_date"] == origin, "error"] = 1e6

    after = rolling_half_widths(errors, [origin], level=0.9, window=WINDOW, step=0.05)
    assert after[origin] == before[origin]


def test_adaptive_correction_recovers_coverage_after_errors_grow() -> None:
    jump = 90
    scale = np.where(np.arange(len(ORIGINS)) < jump, 1.0, 3.0)
    errors = _errors(scale)
    after_the_jump = list(ORIGINS[jump : jump + 10])

    static, adaptive = (
        _coverage(
            errors,
            rolling_half_widths(
                errors, after_the_jump, level=0.9, window=WINDOW, step=step
            ),
        )
        for step in (0.0, 0.05)
    )

    assert adaptive > static


def test_too_few_calibration_errors_give_an_unbounded_interval() -> None:
    errors = _errors(np.ones(len(ORIGINS))).groupby("origin_date").head(5)

    half_widths = rolling_half_widths(
        errors, [ORIGINS[1]], level=0.95, window=1, step=0.0
    )

    assert math.isinf(half_widths[ORIGINS[1]])
