# EDA and feature engineering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **No commit steps.** This repo forbids `git commit`/`push`/PR without explicit permission for that action (CLAUDE.md). Each task ends at green tests and stages nothing; the last task proposes a commit and waits.

**Goal:** Build the tested helpers behind `playground/01_eda_feature_engineering.ipynb` (consolidated-panel loading, series diagnostics, target transforms, feature builder, leakage check) on top of the NB00 outputs, so the notebook only orchestrates.

**Architecture:** The panel store, tracker and settings already exist from the NB00 plan; this plan adds `PanelStore.load_consolidated` and pure functions under `services/`, imported directly, because a class with no state fails `PLR6301`. Diagnostics and features never import W&B; the notebook passes their results to the tracker.

**Tech Stack:** pandas, statsmodels (ADF/KPSS/STL/Ljung-Box), scipy (Box-Cox), scikit-learn (KMeans), pydantic v2, pytest. wandb and the tracker arrive with the NB00 plan.

**Spec:** [`docs/specs/eda-feature-engineering.md`](../specs/eda-feature-engineering.md). Parent: [`docs/CFO_COPILOT_MASTER_PLAN.md`](../CFO_COPILOT_MASTER_PLAN.md).

**Prerequisite:** [`docs/plans/nb00-ingest-and-consolidate.md`](nb00-ingest-and-consolidate.md) executed, and its notebook run by the user so `data/processed/panel_long.parquet` and `macro_q.parquet` exist. Do not start before that.

## Global Constraints

- mypy strict; `uv run poe check` (lint + typecheck + test) green before finishing; coverage gate 80%.
- No `# noqa`, `# ruff: ignore`, `# type: ignore`, `@staticmethod`, and no `except … : continue` in loops.
- Result and config types: Pydantic `ConfigDict(frozen=True, extra="forbid")`, keyword-only.
- Docstrings: one line plus the `Returns:` block pydoclint requires; explain *why* in comments, never *what*; expressive names.
- Ruff runs `extend-select = ["ALL"]`: `ANN401` forbids `Any` in signatures; type helpers with pandas types or small Protocols.
- Paths and credentials come from `Settings`; no module-level state.
- Only `__init__.py` defines a package's public names; names crossing a module boundary drop the leading underscore.
- Do not run ingestion, hit W&B online, or write into `data/processed/`. Executing the notebook is the user's decision (memory: ask-before-acting).
- No new scripts; anything batch-like is a loop in the notebook.

## File Structure

| File | Responsibility |
|---|---|
| `src/app/settings.py` | `features_output_path` |
| `src/app/data/panel_store.py` | `PanelStore.load_consolidated`: NB00 outputs joined into one panel per ticker |
| `src/app/services/features/` | `exceptions.py`, `transforms.py`, `builder.py`, `leakage.py`, `dataset.py` |
| `src/app/services/diagnostics/` | `models.py`, `series.py`, `panel.py` |
| `tests/data/test_panel_store.py`, `tests/services/{features,diagnostics}/` | tests, each new directory with `__init__.py` |
| `src/app/playground/01_eda_feature_engineering.ipynb` | orchestration cells only |

Task order follows dependencies: 0 → 1 → 2 (transforms) → 3 → 4 → 5 → 6 → 7 → 8.

---

### Task 0: Precondition and features output path

**Files:**
- Modify: `src/app/settings.py`

**Interfaces:**
- Produces: `Settings.features_output_path(horizon: int) -> Path`.

- [x] **Step 1: Check the NB00 outputs exist.**

Run: `ls data/processed/panel_long.parquet data/processed/macro_q.parquet`
Expected: both listed. If not, stop and ask the user to run the NB00 notebook; this plan reads its outputs.

- [x] **Step 2: Add the path helper** beside `panel_output_path` in `_Settings`:

```python
    def features_output_path(self, horizon: int) -> Path:
        features_directory = self.DATA_DIRECTORY / "features"
        features_directory.mkdir(parents=True, exist_ok=True)
        return features_directory / f"features_h{horizon}.parquet"
```

Settings is outside the coverage gate, so it has no test of its own; the notebook exercises it.

---

### Task 1: Load the consolidated panels (R1)

**Files:**
- Modify: `src/app/data/panel_store.py`
- Test: `tests/data/test_panel_store.py` (extend the file from the NB00 plan)

**Interfaces:**
- Consumes: `consolidate_panels`, `add_flags`, `PanelStore`, `PanelNotFoundError`, `MalformedPanelError` (NB00 plan); `Settings.PANEL_LONG_PATH`, `Settings.MACRO_Q_PATH`.
- Produces: `PanelStore.panel_long_path` and `PanelStore.macro_q_path` (properties returning `Path`); `PanelStore.load_consolidated() -> dict[str, pd.DataFrame]`, one frame per ticker with the macro columns and the four flags, `is_projected` rows dropped, index reset.

- [ ] **Step 1: Write the failing tests** (append to `tests/data/test_panel_store.py`; add `from datetime import date`, `from app.data.consolidation import consolidate_panels`, `from app.data.flags import add_flags`, `from app.data.schema import MACRO_COLUMNS`)

```python
@pytest.fixture
def nb00_outputs(tmp_path, make_panel):
    consolidated = consolidate_panels({
        "AAA": make_panel(ticker="AAA"),
        "BBB": make_panel(ticker="BBB"),
    })
    panel_long = add_flags(
        consolidated.panel_long, {}, last_reported_quarter=date(2100, 1, 1)
    )
    store = PanelStore(tmp_path)
    panel_long.to_parquet(store.panel_long_path, index=False)
    consolidated.macro_q.to_parquet(store.macro_q_path, index=False)
    return store, panel_long, consolidated.macro_q


def test_load_consolidated_returns_one_frame_per_ticker(nb00_outputs) -> None:
    store, _, _ = nb00_outputs

    panels = store.load_consolidated()

    assert set(panels) == {"AAA", "BBB"}
    frame = panels["AAA"]
    flags = {"covid", "structural_break", "outlier_flag", "is_projected"}
    assert {*MACRO_COLUMNS, *flags} <= set(frame.columns)
    assert pd.api.types.is_datetime64_any_dtype(frame["date"])
    assert frame.index.tolist() == list(range(24))


def test_projected_rows_are_left_out(nb00_outputs) -> None:
    store, panel_long, _ = nb00_outputs
    panel_long.loc[panel_long.index[-1], "is_projected"] = True
    panel_long.to_parquet(store.panel_long_path, index=False)

    assert len(store.load_consolidated()["BBB"]) == 23


def test_missing_nb00_output_is_named(tmp_path) -> None:
    with pytest.raises(PanelNotFoundError, match="panel_long"):
        PanelStore(tmp_path).load_consolidated()


def test_macro_table_must_cover_every_panel_date(nb00_outputs) -> None:
    store, _, macro_q = nb00_outputs
    macro_q.iloc[:-1].to_parquet(store.macro_q_path, index=False)

    with pytest.raises(MalformedPanelError, match="macro"):
        store.load_consolidated()


def test_paths_match_the_settings_used_by_nb00() -> None:
    store = PanelStore(Settings.PANEL_LONG_PATH.parent)

    assert store.panel_long_path == Settings.PANEL_LONG_PATH
    assert store.macro_q_path == Settings.MACRO_Q_PATH
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/data/test_panel_store.py -v`
Expected: the five new tests FAIL, `AttributeError: 'PanelStore' object has no attribute 'load_consolidated'`.

- [ ] **Step 3: Implement.** In `panel_store.py` add constants `_PANEL_LONG_FILE: Final = "panel_long.parquet"` and `_MACRO_Q_FILE: Final = "macro_q.parquet"`, then in `PanelStore`:

```python
@property
def panel_long_path(self) -> Path:
    return self._directory / _PANEL_LONG_FILE


@property
def macro_q_path(self) -> Path:
    return self._directory / _MACRO_Q_FILE


def load_consolidated(self) -> dict[str, pd.DataFrame]:
    """Load the NB00 outputs as one panel per ticker, macro joined on.

    Returns:
        Per-ticker frames with macro columns and flags; projected rows are dropped.
    """
    absent = [
        path.name
        for path in (self.panel_long_path, self.macro_q_path)
        if not path.exists()
    ]
    if absent:
        message = f"NB00 outputs missing in {self._directory}: {', '.join(absent)}"
        raise PanelNotFoundError(message)
    merged = pd.read_parquet(self.panel_long_path).merge(
        pd.read_parquet(self.macro_q_path),
        on="date",
        how="left",
        validate="many_to_one",
    )
    if merged[list(MACRO_COLUMNS)].isna().any().any():
        message = "macro_q does not cover every panel date"
        raise MalformedPanelError(message)
    reported = merged.loc[~merged["is_projected"]]
    return {
        str(ticker): frame.reset_index(drop=True)
        for ticker, frame in reported.groupby("ticker", sort=True)
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/data/test_panel_store.py -v`
Expected: all pass (the NB00 tests in the same file still pass).

---

### Task 2: Target transforms (R5)

**Files:**
- Create: `src/app/services/features/{__init__,exceptions,transforms}.py`, `tests/services/features/{__init__,test_transforms}.py`

**Interfaces:**
- Produces:
  - `TargetArm` (`StrEnum`: `LOG_DIFF1`, `LOG_DIFF4`, `SEASNAIVE_RESIDUAL`)
  - `SEASONAL_LAG = 4`
  - `log_level(values: pd.Series) -> pd.Series`
  - `yoy_log_growth(values: pd.Series) -> pd.Series`
  - `make_target(values: pd.Series, arm: TargetArm, horizon: int) -> pd.Series`, indexed by origin row
  - `reconstruct_level(values: pd.Series, prediction: pd.Series, arm: TargetArm, horizon: int, *, shrinkage: float = 1.0) -> pd.Series`, indexed by origin row
  - `NonPositiveValueError`, `InvalidHorizonError`

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from app.services.features import (
    InvalidHorizonError,
    NonPositiveValueError,
    TargetArm,
    log_level,
    make_target,
    reconstruct_level,
    yoy_log_growth,
)


@pytest.fixture
def revenue() -> pd.Series:
    steps = np.arange(30)
    return pd.Series(100 * np.exp(0.02 * steps + 0.1 * np.sin(steps * np.pi / 2)))


@pytest.mark.parametrize("arm", list(TargetArm))
@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_round_trip_recovers_the_actual_level(revenue, arm, horizon) -> None:
    target = make_target(revenue, arm, horizon)

    rebuilt = reconstruct_level(revenue, target, arm, horizon)

    actual = revenue.shift(-horizon)
    known = rebuilt.notna() & actual.notna()
    assert known.sum() > 0
    np.testing.assert_allclose(rebuilt[known], actual[known], rtol=1e-9)


@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_zero_prediction_on_residual_arm_is_seasonal_naive_growth(
    revenue, horizon
) -> None:
    zero = pd.Series(0.0, index=revenue.index)

    rebuilt = reconstruct_level(revenue, zero, TargetArm.SEASNAIVE_RESIDUAL, horizon)

    log_values = np.log(revenue)
    expected = np.exp(log_values.shift(4 - horizon) + log_values.diff(4))
    pd.testing.assert_series_equal(rebuilt, expected, check_names=False)


def test_shrinkage_scales_only_the_residual_arm(revenue) -> None:
    ones = pd.Series(1.0, index=revenue.index)
    full = reconstruct_level(
        revenue, ones, TargetArm.SEASNAIVE_RESIDUAL, 1, shrinkage=1.0
    )
    half = reconstruct_level(
        revenue, ones, TargetArm.SEASNAIVE_RESIDUAL, 1, shrinkage=0.5
    )
    plain_full = reconstruct_level(revenue, ones, TargetArm.LOG_DIFF4, 1, shrinkage=1.0)
    plain_half = reconstruct_level(revenue, ones, TargetArm.LOG_DIFF4, 1, shrinkage=0.5)

    assert not np.allclose(full.dropna(), half.dropna())
    pd.testing.assert_series_equal(plain_full, plain_half)


def test_missing_values_stay_missing(revenue) -> None:
    revenue.iloc[10] = np.nan

    target = make_target(revenue, TargetArm.LOG_DIFF1, 1)

    assert np.isnan(target.iloc[10]) and np.isnan(target.iloc[9])
    assert target.iloc[8] == pytest.approx(np.log(revenue.iloc[9] / revenue.iloc[8]))


@pytest.mark.parametrize("bad_value", [0.0, -5.0])
def test_non_positive_values_are_refused_with_a_count(revenue, bad_value) -> None:
    revenue.iloc[[3, 7]] = bad_value

    with pytest.raises(NonPositiveValueError, match="2"):
        log_level(revenue)


@pytest.mark.parametrize("horizon", [0, 5])
def test_horizon_outside_one_to_four_is_refused(revenue, horizon) -> None:
    with pytest.raises(InvalidHorizonError):
        make_target(revenue, TargetArm.LOG_DIFF4, horizon)


def test_yoy_growth_is_the_four_quarter_log_difference(revenue) -> None:
    growth = yoy_log_growth(revenue)

    assert growth.iloc[:4].isna().all()
    assert growth.iloc[4] == pytest.approx(np.log(revenue.iloc[4] / revenue.iloc[0]))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/features/test_transforms.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement.** `exceptions.py`:

```python
class FeatureError(Exception):
    """Base error for feature engineering."""


class NonPositiveValueError(FeatureError):
    """Raised when a log transform meets zero or negative values."""


class InvalidHorizonError(FeatureError):
    """Raised for a horizon outside 1 to 4."""


class MissingFlagsError(FeatureError):
    """Raised when group F is requested without the NB00 flag columns."""


class MissingRegimeError(FeatureError):
    """Raised when group S is requested without a seasonality regime."""


class MixedTickerPanelError(FeatureError):
    """Raised when a panel holds more than one company."""


class LeakageError(FeatureError):
    """Raised when a feature changes after only later quarters changed."""
```

`transforms.py`:

```python
from enum import StrEnum
from typing import Final

import numpy as np
import pandas as pd

from app.services.features.exceptions import InvalidHorizonError, NonPositiveValueError

SEASONAL_LAG: Final = 4
_MAX_HORIZON: Final = SEASONAL_LAG


class TargetArm(StrEnum):
    LOG_DIFF1 = "log_diff1"
    LOG_DIFF4 = "log_diff4"
    SEASNAIVE_RESIDUAL = "seasnaive_residual"


def log_level(values: pd.Series) -> pd.Series:
    """Take the natural log, refusing zero and negative values.

    Returns:
        The log series, NaN where the input is NaN.
    """
    non_positive = int((values <= 0).sum())
    if non_positive:
        message = f"log is undefined for {non_positive} non-positive values"
        raise NonPositiveValueError(message)
    return pd.Series(np.log(values), index=values.index)


def yoy_log_growth(values: pd.Series) -> pd.Series:
    return log_level(values).diff(SEASONAL_LAG)


def _require_supported_horizon(horizon: int) -> None:
    if not 1 <= horizon <= _MAX_HORIZON:
        message = f"horizon must be 1 to {_MAX_HORIZON}, got {horizon}"
        raise InvalidHorizonError(message)


def make_target(values: pd.Series, arm: TargetArm, horizon: int) -> pd.Series:
    """Build the arm's target for the origin held in each row.

    Returns:
        The transformed target indexed like ``values``; NaN where unknown.
    """
    _require_supported_horizon(horizon)
    log_values = log_level(values)
    future = log_values.shift(-horizon)
    year_earlier = log_values.shift(SEASONAL_LAG - horizon)
    if arm is TargetArm.LOG_DIFF1:
        return future - log_values
    if arm is TargetArm.LOG_DIFF4:
        return future - year_earlier
    return future - year_earlier - log_values.diff(SEASONAL_LAG)


def reconstruct_level(
    values: pd.Series,
    prediction: pd.Series,
    arm: TargetArm,
    horizon: int,
    *,
    shrinkage: float = 1.0,
) -> pd.Series:
    """Turn a target-space prediction into a level at origin + horizon.

    Returns:
        The predicted level indexed by origin row. ``shrinkage`` scales the
        prediction on the residual arm only.
    """
    _require_supported_horizon(horizon)
    log_values = log_level(values)
    year_earlier = log_values.shift(SEASONAL_LAG - horizon)
    if arm is TargetArm.LOG_DIFF1:
        predicted_log = log_values + prediction
    elif arm is TargetArm.LOG_DIFF4:
        predicted_log = year_earlier + prediction
    else:
        predicted_log = (
            year_earlier + log_values.diff(SEASONAL_LAG) + shrinkage * prediction
        )
    return np.exp(predicted_log)
```

`__init__.py` re-exports every name in the Interfaces list plus the other exceptions from `exceptions.py`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/services/features/test_transforms.py -v`
Expected: all pass. If `assert_series_equal` complains about dtype or name only, fix the code path, not the assertion tolerance.

---

### Task 3: Series diagnostics (R2, R3)

**Files:**
- Create: `src/app/services/diagnostics/{__init__,models,series}.py`, `tests/services/diagnostics/{__init__,test_series}.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure statistics).
- Produces:
  - `SeriesDiagnostics` (frozen Pydantic): `ticker: str`, `variable: str`, `n_obs: int`, `status: Literal["ok","insufficient_data"]`, `log_defined: bool`, `d_levels`, `d_log: int | None`, `seasonal_strength`, `trend_strength`, `ljung_box_p`, `box_cox_lambda`, `coefficient_of_variation: float | None`
  - `observed_since_last_gap(series: pd.Series) -> pd.Series`
  - `differencing_order(series: pd.Series) -> int`
  - `seasonal_and_trend_strength(series: pd.Series, *, period: int = 4) -> tuple[float, float]`
  - `diagnose_series(ticker: str, variable: str, series: pd.Series) -> SeriesDiagnostics`
  - `diagnose_panel(panels: Mapping[str, pd.DataFrame], variables: Sequence[str]) -> pd.DataFrame`
  - `MIN_OBSERVATIONS = 16`

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from app.services.diagnostics import (
    MIN_OBSERVATIONS,
    SeriesDiagnostics,
    diagnose_panel,
    diagnose_series,
    differencing_order,
    observed_since_last_gap,
    seasonal_and_trend_strength,
)

RNG = np.random.default_rng(0)


def test_series_after_the_last_gap_is_kept_without_splicing() -> None:
    series = pd.Series([np.nan, 1.0, 2.0, np.nan, 4.0, 5.0, 6.0])

    assert observed_since_last_gap(series).tolist() == [4.0, 5.0, 6.0]


def test_series_without_gaps_is_unchanged() -> None:
    series = pd.Series([1.0, 2.0, 3.0])

    assert observed_since_last_gap(series).tolist() == [1.0, 2.0, 3.0]


def test_all_missing_series_is_empty() -> None:
    assert observed_since_last_gap(pd.Series([np.nan, np.nan])).empty


@pytest.mark.parametrize(("times_integrated", "expected"), [(0, 0), (1, 1), (2, 2)])
def test_differencing_order_matches_integration_order(
    times_integrated, expected
) -> None:
    series = pd.Series(RNG.normal(size=300))
    for _ in range(times_integrated):
        series = series.cumsum()

    assert differencing_order(series) == expected


def test_seasonal_series_scores_high_and_noise_scores_low() -> None:
    steps = np.arange(80)
    seasonal = pd.Series(np.sin(steps * np.pi / 2) + 0.05 * RNG.normal(size=80))
    noise = pd.Series(RNG.normal(size=80))

    assert seasonal_and_trend_strength(seasonal)[0] > 0.9
    assert seasonal_and_trend_strength(noise)[0] < 0.4


def test_trending_series_has_high_trend_strength() -> None:
    trend = pd.Series(np.arange(80) + 0.1 * RNG.normal(size=80))

    assert seasonal_and_trend_strength(trend)[1] > 0.9


def test_short_series_is_reported_not_raised() -> None:
    result = diagnose_series(
        "AAA", "revenue_usd_m", pd.Series(np.arange(1.0, MIN_OBSERVATIONS))
    )

    assert result.status == "insufficient_data"
    assert result.n_obs == MIN_OBSERVATIONS - 1
    assert result.d_levels is None


def test_non_positive_values_switch_off_log_fields_only() -> None:
    values = pd.Series(np.linspace(-5, 50, 60) + RNG.normal(size=60))

    result = diagnose_series("AAA", "free_cash_flow_usd_m", values)

    assert result.status == "ok"
    assert result.log_defined is False
    assert result.d_levels is not None
    assert result.d_log is None and result.box_cox_lambda is None


def test_positive_series_fills_every_field() -> None:
    steps = np.arange(80)
    values = pd.Series(100 * np.exp(0.02 * steps + 0.1 * np.sin(steps * np.pi / 2)))

    result = diagnose_series("AAA", "revenue_usd_m", values)

    assert result.log_defined is True
    assert None not in result.model_dump().values()


def test_gapped_series_counts_only_the_run_after_the_gap() -> None:
    values = pd.Series(np.linspace(10, 100, 40))
    values.iloc[[0, 1, 8]] = np.nan

    assert diagnose_series("TSLA", "revenue_usd_m", values).n_obs == 31


def test_panel_diagnostics_yield_one_row_per_company_and_variable(make_panel) -> None:
    panels = {
        "AAA": make_panel(ticker="AAA", quarters=40),
        "BBB": make_panel(ticker="BBB", quarters=40),
    }

    table = diagnose_panel(panels, ["revenue_usd_m", "eps"])

    assert len(table) == 4
    assert set(table.columns) == set(SeriesDiagnostics.model_fields)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/diagnostics/test_series.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement.** `models.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SeriesDiagnostics(BaseModel):
    """Everything NB01 records about one company's variable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    variable: str
    n_obs: int
    status: Literal["ok", "insufficient_data"]
    log_defined: bool
    d_levels: int | None = None
    d_log: int | None = None
    seasonal_strength: float | None = None
    trend_strength: float | None = None
    ljung_box_p: float | None = None
    box_cox_lambda: float | None = None
    coefficient_of_variation: float | None = None
```

`series.py`:

```python
import warnings
from collections.abc import Mapping, Sequence
from typing import Final

import numpy as np
import pandas as pd
from scipy.stats import boxcox_normmax
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import InterpolationWarning, adfuller, kpss

from app.services.diagnostics.models import SeriesDiagnostics

MIN_OBSERVATIONS: Final = 16
_MAX_DIFFERENCING_ORDER: Final = 2
_SIGNIFICANCE: Final = 0.05
_QUARTERLY_PERIOD: Final = 4
_LJUNG_BOX_LAG: Final = 8


def observed_since_last_gap(series: pd.Series) -> pd.Series:
    """Keep the run after the last missing value so no gap is spliced shut.

    Returns:
        The trailing run of observed values, possibly empty.
    """
    gap_positions = np.flatnonzero(series.isna().to_numpy())
    start = 0 if gap_positions.size == 0 else int(gap_positions[-1]) + 1
    return series.iloc[start:]


def _looks_stationary(series: pd.Series) -> bool:
    # kpss clips its p-value at the table bounds and warns; the direction of the
    # decision is still valid, so the warning carries no information here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", InterpolationWarning)
        kpss_p = kpss(series, regression="c", nlags="auto")[1]
    return bool(adfuller(series)[1] < _SIGNIFICANCE and kpss_p > _SIGNIFICANCE)


def differencing_order(series: pd.Series) -> int:
    """Find the smallest d where ADF rejects a unit root and KPSS does not reject stationarity.

    Returns:
        The order, capped at 2.
    """
    current = series.dropna()
    for order in range(_MAX_DIFFERENCING_ORDER + 1):
        if _looks_stationary(current):
            return order
        current = current.diff().dropna()
    return _MAX_DIFFERENCING_ORDER


def _strength(component: np.ndarray, remainder: np.ndarray) -> float:
    return float(max(0.0, 1.0 - np.var(remainder) / np.var(component + remainder)))


def seasonal_and_trend_strength(
    series: pd.Series, *, period: int = _QUARTERLY_PERIOD
) -> tuple[float, float]:
    """Measure STL seasonal and trend strength, each between 0 and 1.

    Returns:
        ``(seasonal_strength, trend_strength)``.
    """
    fit = STL(series.to_numpy(), period=period, robust=True).fit()
    return (
        _strength(fit.seasonal, fit.resid),
        _strength(fit.trend, fit.resid),
    )


def _ljung_box_p(series: pd.Series, order: int) -> float:
    differenced = series.diff(order).dropna() if order else series
    result = acorr_ljungbox(differenced, lags=[_LJUNG_BOX_LAG], return_df=True)
    return float(result["lb_pvalue"].iloc[0])


def diagnose_series(ticker: str, variable: str, series: pd.Series) -> SeriesDiagnostics:
    """Diagnose one series; a short or gapped one yields a record, not an error.

    Returns:
        The record for this company and variable.
    """
    observed = observed_since_last_gap(series)
    log_defined = bool(len(observed) and (observed > 0).all())
    if len(observed) < MIN_OBSERVATIONS:
        return SeriesDiagnostics(
            ticker=ticker,
            variable=variable,
            n_obs=len(observed),
            status="insufficient_data",
            log_defined=log_defined,
        )
    d_levels = differencing_order(observed)
    seasonal_strength, trend_strength = seasonal_and_trend_strength(observed)
    return SeriesDiagnostics(
        ticker=ticker,
        variable=variable,
        n_obs=len(observed),
        status="ok",
        log_defined=log_defined,
        d_levels=d_levels,
        d_log=differencing_order(np.log(observed)) if log_defined else None,
        seasonal_strength=seasonal_strength,
        trend_strength=trend_strength,
        ljung_box_p=_ljung_box_p(observed, d_levels),
        box_cox_lambda=float(boxcox_normmax(observed, method="mle"))
        if log_defined
        else None,
        coefficient_of_variation=float(observed.std() / abs(observed.mean())),
    )


def diagnose_panel(
    panels: Mapping[str, pd.DataFrame], variables: Sequence[str]
) -> pd.DataFrame:
    """Diagnose every company and variable.

    Returns:
        One row per (ticker, variable), columns from ``SeriesDiagnostics``.
    """
    records = [
        diagnose_series(ticker, variable, panel[variable]).model_dump()
        for ticker, panel in panels.items()
        for variable in variables
    ]
    return pd.DataFrame(records)
```

`np.log(observed)` returns a Series for a Series input, which is what `differencing_order` takes. `__init__.py` re-exports `MIN_OBSERVATIONS`, `SeriesDiagnostics`, `diagnose_panel`, `diagnose_series`, `differencing_order`, `observed_since_last_gap`, `seasonal_and_trend_strength` (Task 4 adds two more).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/services/diagnostics/test_series.py -v`
Expected: all pass. The stationarity tests use 300 draws so the seed does not decide the result. If one still fails, print the ADF and KPSS p-values before touching a threshold.

---

### Task 4: Panel-level EDA outputs (R4)

**Files:**
- Create: `src/app/services/diagnostics/panel.py`, `tests/services/diagnostics/test_panel.py`
- Modify: `src/app/services/diagnostics/__init__.py`

**Interfaces:**
- Consumes: `diagnose_panel` output columns (Task 3), `yoy_log_growth` (Task 2), `MACRO_COLUMNS`.
- Produces:
  - `seasonality_regimes(diagnostics: pd.DataFrame, *, variable: str, n_regimes: int = 3, seed: int = 42) -> pd.Series` (index ticker, name `seasonality_regime`, regime 0 least seasonal)
  - `growth_macro_correlations(panels: Mapping[str, pd.DataFrame], *, variable: str) -> pd.DataFrame` (index ticker, macro columns plus `sector`)

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from app.data.schema import MACRO_COLUMNS
from app.services.diagnostics import growth_macro_correlations, seasonality_regimes


def _diagnostics(strengths: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": list(strengths),
        "variable": "revenue_usd_m",
        "status": "ok",
        "seasonal_strength": list(strengths.values()),
        "trend_strength": 0.9,
    })


def test_regimes_are_ordered_by_seasonal_strength() -> None:
    strengths = {"A": 0.02, "B": 0.05, "C": 0.5, "D": 0.55, "E": 0.95, "F": 0.9}

    regimes = seasonality_regimes(_diagnostics(strengths), variable="revenue_usd_m")

    assert regimes.to_dict() == {"A": 0, "B": 0, "C": 1, "D": 1, "E": 2, "F": 2}


def test_regimes_are_deterministic_for_a_seed() -> None:
    strengths = {"A": 0.02, "B": 0.5, "C": 0.95, "D": 0.1, "E": 0.6, "F": 0.9}
    diagnostics = _diagnostics(strengths)

    first = seasonality_regimes(diagnostics, variable="revenue_usd_m")
    second = seasonality_regimes(diagnostics, variable="revenue_usd_m")

    pd.testing.assert_series_equal(first, second)


def test_companies_without_a_full_diagnosis_get_no_regime() -> None:
    diagnostics = _diagnostics({"A": 0.1, "B": 0.5, "C": 0.9})
    diagnostics.loc[0, "status"] = "insufficient_data"

    regimes = seasonality_regimes(diagnostics, variable="revenue_usd_m", n_regimes=2)

    assert "A" not in regimes.index


def test_growth_that_tracks_a_macro_series_correlates_perfectly(make_panel) -> None:
    panel = make_panel(ticker="AAA", quarters=40)
    panel["revenue_usd_m"] = 100 * np.exp(np.cumsum(np.sin(np.arange(40) / 3)) * 0.05)
    panel["vix"] = np.log(panel["revenue_usd_m"]).diff(4)

    table = growth_macro_correlations({"AAA": panel}, variable="revenue_usd_m")

    assert table.loc["AAA", "vix"] == pytest.approx(1.0)
    assert table.loc["AAA", "sector"] == "Technology"
    assert set(MACRO_COLUMNS) <= set(table.columns)
```

The last test builds the macro column from the growth itself, so the expected correlation is exactly 1 without a random draw.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/diagnostics/test_panel.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement** `panel.py`:

```python
from collections.abc import Mapping

import pandas as pd
from sklearn.cluster import KMeans

from app.data.schema import MACRO_COLUMNS
from app.services.features.transforms import yoy_log_growth

_CLUSTERING_COLUMNS = ["seasonal_strength", "trend_strength"]


def seasonality_regimes(
    diagnostics: pd.DataFrame, *, variable: str, n_regimes: int = 3, seed: int = 42
) -> pd.Series:
    """Cluster companies by seasonal and trend strength into ordered regimes.

    Returns:
        Regime id per ticker; 0 is the least seasonal cluster.
    """
    fully_diagnosed = diagnostics.query(
        "variable == @variable and status == 'ok'"
    ).set_index("ticker")
    labels = KMeans(n_clusters=n_regimes, random_state=seed, n_init=10).fit_predict(
        fully_diagnosed[_CLUSTERING_COLUMNS]
    )
    raw = pd.Series(labels, index=fully_diagnosed.index)
    rank_by_seasonality = (
        fully_diagnosed["seasonal_strength"]
        .groupby(raw)
        .mean()
        .rank()
        .sub(1)
        .astype(int)
    )
    return raw.map(rank_by_seasonality).rename("seasonality_regime")


def growth_macro_correlations(
    panels: Mapping[str, pd.DataFrame], *, variable: str
) -> pd.DataFrame:
    """Correlate each company's YoY log growth with every macro column.

    Returns:
        One row per ticker: a correlation per macro column plus ``sector``.
    """
    rows = {
        ticker: {
            **{
                column: yoy_log_growth(panel[variable]).corr(panel[column])
                for column in MACRO_COLUMNS
            },
            "sector": panel["sector"].iloc[0],
        }
        for ticker, panel in panels.items()
    }
    return pd.DataFrame.from_dict(rows, orient="index")
```

Re-export both from `diagnostics/__init__.py`. Diagnostics imports `features.transforms`; features never imports diagnostics, so the dependency stays one-way. The sector table is `table.groupby("sector").mean(numeric_only=True)` in the notebook, one line, so it gets no helper.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/services/diagnostics -v`
Expected: all pass.

---

### Task 5: Feature builder (R6)

**Files:**
- Create: `src/app/services/features/builder.py`, `tests/services/features/test_builder.py`
- Modify: `src/app/services/features/__init__.py`

**Interfaces:**
- Consumes: `yoy_log_growth`, `MissingRegimeError`, `MixedTickerPanelError`, `MACRO_COLUMNS`.
- Produces:
  - `FeatureGroup` (`StrEnum`: `L R M X XD C S F`)
  - `FeatureSpec(target_variable: str = "revenue_usd_m", groups: frozenset[FeatureGroup])` (frozen)
  - `build_features(panel: pd.DataFrame, spec: FeatureSpec, *, horizon: int, regimes: pd.Series | None = None) -> pd.DataFrame`. Same rows and index as `panel`; columns `ticker`, `origin_date`, `target_date`, then group columns in the order L, R, M, X, XD, C, S.

Column names: L `growth_yoy_lag{1,2,3,4,5,8}`; R `growth_yoy_mean_{4,8}q`, `growth_yoy_std_{4,8}q`, `growth_yoy_momentum`; M `gross_margin`, `operating_margin`, `net_margin`; X the ten `MACRO_COLUMNS`; XD `real_rate`; C `target_quarter`; S `sector`, `seasonality_regime`; F `covid`, `structural_break`.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from app.data.schema import MACRO_COLUMNS
from app.services.features import (
    FeatureGroup,
    FeatureSpec,
    MissingFlagsError,
    MissingRegimeError,
    MixedTickerPanelError,
    build_features,
)

KEYS = ["ticker", "origin_date", "target_date"]


def _spec(*groups: FeatureGroup) -> FeatureSpec:
    return FeatureSpec(groups=frozenset(groups))


def _with_flags(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.assign(
        covid=False, structural_break=False, outlier_flag=False, is_projected=False
    )


@pytest.mark.parametrize(
    ("group", "columns"),
    [
        (FeatureGroup.L, [f"growth_yoy_lag{k}" for k in (1, 2, 3, 4, 5, 8)]),
        (
            FeatureGroup.R,
            [
                "growth_yoy_mean_4q",
                "growth_yoy_mean_8q",
                "growth_yoy_std_4q",
                "growth_yoy_std_8q",
                "growth_yoy_momentum",
            ],
        ),
        (FeatureGroup.M, ["gross_margin", "operating_margin", "net_margin"]),
        (FeatureGroup.X, list(MACRO_COLUMNS)),
        (FeatureGroup.XD, ["real_rate"]),
        (FeatureGroup.C, ["target_quarter"]),
        (FeatureGroup.F, ["covid", "structural_break"]),
    ],
)
def test_each_group_adds_its_columns(make_panel, group, columns) -> None:
    features = build_features(_with_flags(make_panel()), _spec(group), horizon=1)

    assert list(features.columns) == KEYS + columns


def test_every_row_is_kept_and_indexed_like_the_panel(make_panel) -> None:
    panel = make_panel()

    features = build_features(panel, _spec(FeatureGroup.L), horizon=2)

    assert features.index.equals(panel.index)


def test_lag_one_is_the_origin_quarters_own_growth(make_panel) -> None:
    panel = make_panel()
    features = build_features(panel, _spec(FeatureGroup.L), horizon=1)

    expected = np.log(panel["revenue_usd_m"].iloc[9] / panel["revenue_usd_m"].iloc[5])
    assert features["growth_yoy_lag1"].iloc[9] == pytest.approx(expected)
    assert features["growth_yoy_lag2"].iloc[9] == features["growth_yoy_lag1"].iloc[8]


def test_short_history_is_nan_never_filled(make_panel) -> None:
    features = build_features(make_panel(), _spec(FeatureGroup.L), horizon=1)

    assert features["growth_yoy_lag1"].isna().sum() == 4
    assert features["growth_yoy_lag8"].isna().sum() == 11


def test_an_interior_gap_leaves_nan_where_it_touches_the_growth(make_panel) -> None:
    panel = make_panel()
    panel.loc[10, "revenue_usd_m"] = np.nan

    features = build_features(panel, _spec(FeatureGroup.L), horizon=1)

    missing = set(features.index[features["growth_yoy_lag1"].isna()])
    assert missing == {0, 1, 2, 3, 10, 14}


def test_target_quarter_is_the_calendar_quarter_of_origin_plus_horizon(
    make_panel,
) -> None:
    features = build_features(make_panel(), _spec(FeatureGroup.C), horizon=2)

    assert features["origin_date"].iloc[0] == pd.Timestamp("2015-03-31")
    assert features["target_date"].iloc[0] == pd.Timestamp("2015-09-30")
    assert features["target_quarter"].iloc[0] == 3


def test_real_rate_is_fed_funds_minus_cpi(make_panel) -> None:
    panel = make_panel()

    features = build_features(panel, _spec(FeatureGroup.XD), horizon=1)

    pd.testing.assert_series_equal(
        features["real_rate"], panel["fed_funds"] - panel["cpi_yoy"], check_names=False
    )


def test_static_group_needs_a_regime_for_the_company(make_panel) -> None:
    panel = make_panel(ticker="AAA")

    with pytest.raises(MissingRegimeError):
        build_features(panel, _spec(FeatureGroup.S), horizon=1)
    with pytest.raises(MissingRegimeError, match="AAA"):
        build_features(
            panel, _spec(FeatureGroup.S), horizon=1, regimes=pd.Series({"BBB": 1})
        )


def test_static_group_carries_sector_and_regime(make_panel) -> None:
    features = build_features(
        make_panel(ticker="AAA"),
        _spec(FeatureGroup.S),
        horizon=1,
        regimes=pd.Series({"AAA": 2}),
    )

    assert features["seasonality_regime"].eq(2).all()
    assert features["sector"].eq("Technology").all()


def test_flags_are_copied_from_the_origin_row(make_panel) -> None:
    panel = _with_flags(make_panel())
    panel.loc[6, "covid"] = True

    features = build_features(panel, _spec(FeatureGroup.F), horizon=1)

    assert features["covid"].tolist() == panel["covid"].tolist()


def test_group_f_without_flag_columns_is_refused(make_panel) -> None:
    with pytest.raises(MissingFlagsError, match="covid"):
        build_features(make_panel(), _spec(FeatureGroup.F), horizon=1)


def test_a_panel_of_two_companies_is_refused(make_panel) -> None:
    mixed = pd.concat(
        [make_panel(ticker="AAA"), make_panel(ticker="BBB")], ignore_index=True
    )

    with pytest.raises(MixedTickerPanelError):
        build_features(mixed, _spec(FeatureGroup.L), horizon=1)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/features/test_builder.py -v`
Expected: FAIL, `cannot import name 'build_features'`.

- [ ] **Step 3: Implement** `builder.py`:

```python
from enum import StrEnum
from typing import Final

import pandas as pd
from pydantic import BaseModel, ConfigDict

from app.data.schema import MACRO_COLUMNS
from app.services.features.exceptions import (
    MissingFlagsError,
    MissingRegimeError,
    MixedTickerPanelError,
)
from app.services.features.transforms import yoy_log_growth

GROWTH_LAGS: Final = (1, 2, 3, 4, 5, 8)
ROLLING_WINDOWS: Final = (4, 8)
MARGIN_COLUMNS: Final = ("gross_margin", "operating_margin", "net_margin")
FLAG_COLUMNS: Final = ("covid", "structural_break")


class FeatureGroup(StrEnum):
    L = "L"
    R = "R"
    M = "M"
    X = "X"
    XD = "XD"
    C = "C"
    S = "S"
    F = "F"


class FeatureSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_variable: str = "revenue_usd_m"
    groups: frozenset[FeatureGroup]


def _lag_features(growth: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        f"growth_yoy_lag{k}": growth.shift(k - 1) for k in GROWTH_LAGS
    })


def _rolling_features(growth: pd.Series) -> pd.DataFrame:
    means = {f"growth_yoy_mean_{w}q": growth.rolling(w).mean() for w in ROLLING_WINDOWS}
    stds = {f"growth_yoy_std_{w}q": growth.rolling(w).std() for w in ROLLING_WINDOWS}
    return pd.DataFrame({
        **means,
        **stds,
        "growth_yoy_momentum": growth - growth.shift(1),
    })


def _static_features(panel: pd.DataFrame, regimes: pd.Series | None) -> pd.DataFrame:
    ticker = panel["ticker"].iloc[0]
    if regimes is None or ticker not in regimes.index:
        message = f"no seasonality regime for {ticker}; run the EDA regimes first"
        raise MissingRegimeError(message)
    return pd.DataFrame({
        "sector": panel["sector"],
        "seasonality_regime": regimes[ticker],
    })


def _flag_features(panel: pd.DataFrame) -> pd.DataFrame:
    absent = [column for column in FLAG_COLUMNS if column not in panel.columns]
    if absent:
        message = f"group F needs the NB00 flag columns: {', '.join(absent)}"
        raise MissingFlagsError(message)
    return panel[list(FLAG_COLUMNS)]


def build_features(
    panel: pd.DataFrame,
    spec: FeatureSpec,
    *,
    horizon: int,
    regimes: pd.Series | None = None,
) -> pd.DataFrame:
    """Build features that use only quarters up to each row's origin.

    Returns:
        One row per origin quarter, indexed like ``panel``.
    """
    if panel["ticker"].nunique() != 1:
        message = "build_features takes one company's panel at a time"
        raise MixedTickerPanelError(message)
    growth = yoy_log_growth(panel[spec.target_variable])
    target_dates = panel["date"] + pd.offsets.QuarterEnd(horizon)
    groups = spec.groups
    parts = [
        pd.DataFrame({
            "ticker": panel["ticker"],
            "origin_date": panel["date"],
            "target_date": target_dates,
        })
    ]
    if FeatureGroup.L in groups:
        parts.append(_lag_features(growth))
    if FeatureGroup.R in groups:
        parts.append(_rolling_features(growth))
    if FeatureGroup.M in groups:
        parts.append(panel[list(MARGIN_COLUMNS)])
    if FeatureGroup.X in groups:
        parts.append(panel[list(MACRO_COLUMNS)])
    if FeatureGroup.XD in groups:
        parts.append(pd.DataFrame({"real_rate": panel["fed_funds"] - panel["cpi_yoy"]}))
    if FeatureGroup.C in groups:
        parts.append(pd.DataFrame({"target_quarter": target_dates.dt.quarter}))
    if FeatureGroup.S in groups:
        parts.append(_static_features(panel, regimes))
    if FeatureGroup.F in groups:
        parts.append(_flag_features(panel))
    return pd.concat(parts, axis=1)
```

Re-export `FeatureGroup`, `FeatureSpec`, `build_features` from `features/__init__.py`. `outlier_flag` is deliberately not a group: NB00 fits it on each company's whole history, so it would leak later quarters.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/services/features/test_builder.py -v && uv run poe lint`
Expected: all pass. If ruff flags branch count (`PLR0912`) or complexity (`C901`) on `build_features`, split by moving the guard and the key frame into private helpers. Do not suppress.

---

### Task 6: Leakage check (R7)

**Files:**
- Create: `src/app/services/features/leakage.py`, `tests/services/features/test_leakage.py`
- Modify: `src/app/services/features/__init__.py`

**Interfaces:**
- Consumes: `build_features`, `FeatureSpec`, `FeatureGroup`, `LeakageError`.
- Produces: `assert_no_lookahead(build: Callable[[pd.DataFrame], pd.DataFrame], panel: pd.DataFrame, *, origins: Sequence[int]) -> None`. Passing a builder callable lets the test pass a deliberately leaky one.

- [ ] **Step 1: Write the failing tests**

```python
import pandas as pd
import pytest

from app.services.features import (
    FeatureGroup,
    FeatureSpec,
    LeakageError,
    assert_no_lookahead,
    build_features,
)

ALL_GROUPS = frozenset(FeatureGroup)
REGIMES = pd.Series({"AAA": 1})


@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_real_builder_passes_at_every_horizon(make_panel, horizon) -> None:
    spec = FeatureSpec(groups=ALL_GROUPS)

    assert_no_lookahead(
        lambda panel: build_features(panel, spec, horizon=horizon, regimes=REGIMES),
        make_panel(ticker="AAA").assign(covid=False, structural_break=False),
        origins=[3, 8, 15, 20],
    )


def test_a_builder_that_peeks_one_quarter_ahead_is_caught(make_panel) -> None:
    def leaky(panel: pd.DataFrame) -> pd.DataFrame:
        features = build_features(
            panel, FeatureSpec(groups=frozenset({FeatureGroup.L})), horizon=1
        )
        return features.assign(peek=panel["revenue_usd_m"].shift(-1))

    with pytest.raises(LeakageError, match="peek"):
        assert_no_lookahead(leaky, make_panel(), origins=[8])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/features/test_leakage.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement** `leakage.py`:

```python
from collections.abc import Callable, Sequence

import pandas as pd

from app.services.features.exceptions import LeakageError

_SCRAMBLE_SCALE = 3.0
_SCRAMBLE_SHIFT = 1.0


def _with_later_quarters_scrambled(panel: pd.DataFrame, origin: int) -> pd.DataFrame:
    scrambled = panel.copy()
    numeric_columns = scrambled.select_dtypes("number").columns
    later_rows = scrambled.index[origin + 1 :]
    scrambled.loc[later_rows, numeric_columns] = (
        scrambled.loc[later_rows, numeric_columns] * _SCRAMBLE_SCALE + _SCRAMBLE_SHIFT
    )
    return scrambled


def assert_no_lookahead(
    build: Callable[[pd.DataFrame], pd.DataFrame],
    panel: pd.DataFrame,
    *,
    origins: Sequence[int],
) -> None:
    """Fail when a row's features change after only later quarters change.

    Raises:
        LeakageError: naming the columns that moved and the origin row.
    """
    baseline = build(panel)
    for origin in origins:
        scrambled = build(_with_later_quarters_scrambled(panel, origin))
        before, after = baseline.iloc[origin], scrambled.iloc[origin]
        unchanged = (before == after) | (before.isna() & after.isna())
        if not unchanged.all():
            moved = ", ".join(unchanged.index[~unchanged])
            message = (
                f"features at origin row {origin} changed with later quarters: {moved}"
            )
            raise LeakageError(message)
```

Re-export from `features/__init__.py`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/services/features/test_leakage.py -v`
Expected: 5 passed. If a real-builder case fails, the builder has a genuine look-ahead: fix `builder.py`, not the check.

---

### Task 7: Dataset assembly and export (R8)

**Files:**
- Create: `src/app/services/features/dataset.py`, `tests/services/features/test_dataset.py`
- Modify: `src/app/services/features/__init__.py`

**Interfaces:**
- Consumes: `build_features`, `make_target`, `FeatureSpec`, `TargetArm`; `app.data.write_panel`; `Settings.features_output_path`.
- Produces: `assemble_dataset(panels: Mapping[str, pd.DataFrame], spec: FeatureSpec, *, horizon: int, arm: TargetArm, regimes: pd.Series | None = None) -> pd.DataFrame`. Every origin row of every company; keys `ticker`, `origin_date`, `target_date`, the group columns, then `target_level_usd_m` (actual value at origin + h) and `y` (the arm's target). `sector` is a category dtype when group S is present. Export reuses `write_panel(dataset, Settings.features_output_path(h))`; the name is panel-specific but the function is a plain parquet writer.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from app.services.features import (
    FeatureGroup,
    FeatureSpec,
    TargetArm,
    assemble_dataset,
    make_target,
)

SPEC = FeatureSpec(groups=frozenset({FeatureGroup.L, FeatureGroup.S}))
REGIMES = pd.Series({"AAA": 0, "BBB": 1})


@pytest.fixture
def panels(make_panel) -> dict[str, pd.DataFrame]:
    return {
        "AAA": make_panel(ticker="AAA"),
        "BBB": make_panel(ticker="BBB", sector="Energy"),
    }


def test_every_origin_row_of_every_company_is_kept(panels) -> None:
    dataset = assemble_dataset(
        panels, SPEC, horizon=2, arm=TargetArm.LOG_DIFF4, regimes=REGIMES
    )

    assert len(dataset) == 48
    assert dataset["ticker"].value_counts().to_dict() == {"AAA": 24, "BBB": 24}


def test_target_columns_match_the_transform(panels) -> None:
    dataset = assemble_dataset(
        panels, SPEC, horizon=2, arm=TargetArm.LOG_DIFF4, regimes=REGIMES
    )
    company = dataset[dataset["ticker"] == "AAA"].reset_index(drop=True)

    expected = make_target(panels["AAA"]["revenue_usd_m"], TargetArm.LOG_DIFF4, 2)
    pd.testing.assert_series_equal(company["y"], expected, check_names=False)
    assert (
        company["target_level_usd_m"].iloc[0] == panels["AAA"]["revenue_usd_m"].iloc[2]
    )


def test_the_last_horizon_origins_have_no_target_yet(panels) -> None:
    dataset = assemble_dataset(
        panels, SPEC, horizon=3, arm=TargetArm.LOG_DIFF1, regimes=REGIMES
    )

    unlabelled = dataset[dataset["y"].isna()]
    assert unlabelled.groupby("ticker").size().eq(3).all()


def test_sector_is_categorical_across_companies(panels) -> None:
    dataset = assemble_dataset(
        panels, SPEC, horizon=1, arm=TargetArm.LOG_DIFF1, regimes=REGIMES
    )

    assert isinstance(dataset["sector"].dtype, pd.CategoricalDtype)


def test_without_group_s_no_sector_column_appears(panels) -> None:
    spec = FeatureSpec(groups=frozenset({FeatureGroup.L}))

    dataset = assemble_dataset(panels, spec, horizon=1, arm=TargetArm.LOG_DIFF1)

    assert "sector" not in dataset.columns
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/features/test_dataset.py -v`
Expected: FAIL, import error.

- [ ] **Step 3: Implement** `dataset.py`:

```python
from collections.abc import Mapping

import pandas as pd

from app.services.features.builder import FeatureGroup, FeatureSpec, build_features
from app.services.features.transforms import TargetArm, make_target


def _company_rows(
    panel: pd.DataFrame,
    spec: FeatureSpec,
    *,
    horizon: int,
    arm: TargetArm,
    regimes: pd.Series | None,
) -> pd.DataFrame:
    target = panel[spec.target_variable]
    return build_features(panel, spec, horizon=horizon, regimes=regimes).assign(
        target_level_usd_m=target.shift(-horizon),
        y=make_target(target, arm, horizon),
    )


def assemble_dataset(
    panels: Mapping[str, pd.DataFrame],
    spec: FeatureSpec,
    *,
    horizon: int,
    arm: TargetArm,
    regimes: pd.Series | None = None,
) -> pd.DataFrame:
    """Pool every company's origin rows with the arm's target for one horizon.

    Returns:
        All origin rows; ``y`` is NaN where the target is not yet known.
    """
    dataset = pd.concat(
        [
            _company_rows(panel, spec, horizon=horizon, arm=arm, regimes=regimes)
            for panel in panels.values()
        ],
        ignore_index=True,
    )
    if FeatureGroup.S in spec.groups:
        dataset["sector"] = dataset["sector"].astype("category")
    return dataset
```

Re-export `assemble_dataset`.

- [ ] **Step 4: Run to verify pass, then the whole suite**

Run: `uv run pytest tests/services/features tests/services/diagnostics tests/services/tracking tests/data/test_panel_store.py -v`
Expected: all pass.

---

### Task 8: Notebook orchestration and acceptance run

**Files:**
- Modify: `src/app/playground/01_eda_feature_engineering.ipynb` (edit with `NotebookEdit`; keep the four existing section headings)

No unit tests for the notebook. The helpers it calls are already tested, and its cells hold no logic. The acceptance criteria A1–A9 are checked by cells and by two shell checks. **Do not execute the notebook yourself**: it reads real panels and, once `WANDB_MODE=online`, publishes runs. Hand it over and let the user run it (memory: ask-before-acting).

- [ ] **Step 1: Cell 1, "1. Load panels"** (code cell under the heading)

```python
from app.injections import configure_container
from app.data.schema import MACRO_COLUMNS
from app.services.diagnostics import (
    diagnose_panel,
    growth_macro_correlations,
    seasonality_regimes,
)
from app.services.features import (
    FeatureGroup,
    FeatureSpec,
    TargetArm,
    assemble_dataset,
    assert_no_lookahead,
    build_features,
)
from app.services.tracking import RunConfig, run_name
from app.settings import Settings
from app.data import write_panel

container = configure_container()
tracker = container.experiment_tracker()
panels = container.panel_store().load_consolidated()

n_rows = sum(len(panel) for panel in panels.values())
assert len(panels) == 60 and all(len(p) == 81 for p in panels.values())  # A1
assert all({"covid", "structural_break"} <= set(p.columns) for p in panels.values())
TARGETS = [
    "revenue_usd_m",
    "operating_income_usd_m",
    "ebitda_usd_m",
    "free_cash_flow_usd_m",
]
```

- [ ] **Step 2: Cell 2, "2. Diagnostics"**

```python
diagnostics = diagnose_panel(panels, TARGETS)
assert len(diagnostics) == 240  # A2
revenue_obs = diagnostics.query("variable == 'revenue_usd_m'").set_index("ticker")[
    "n_obs"
]
assert revenue_obs[["TSLA", "BBY", "ADBE", "ORCL"]].tolist() == [72, 78, 80, 80]
assert revenue_obs.drop(["TSLA", "BBY", "ADBE", "ORCL"]).eq(81).all()

regimes = seasonality_regimes(diagnostics, variable="revenue_usd_m")
sector_sensitivity = (
    growth_macro_correlations(panels, variable="revenue_usd_m")
    .groupby("sector")
    .mean(numeric_only=True)
)

for variable in TARGETS:
    config = RunConfig(panel_size=len(panels), n_rows=n_rows, target_variable=variable)
    with tracker.start_run(
        run_name(notebook="nb01", model="eda", variable=variable),
        config,
        job_type="eda",
    ) as run:
        run.log_table("diagnostics", diagnostics.query("variable == @variable"))
        if variable == "revenue_usd_m":
            run.log_table("seasonality_regimes", regimes.reset_index())
            run.log_table(
                "macro_sensitivity_by_sector", sector_sensitivity.reset_index()
            )
```

Add cells that plot the seasonal-strength histogram, the `d_levels` versus `d_log` cross-tab, and `sector_sensitivity` as a heatmap with matplotlib, and call `run.log_figure(...)` inside the same `with` block. Compare the six Appendix C companies to the `diagnostics` rows (A3) in a markdown cell that states any disagreement and its cause.

- [ ] **Step 3: Cell 3, "3. Feature engineering"**

```python
spec = FeatureSpec(groups=frozenset(FeatureGroup))
for horizon in (1, 2, 3, 4):
    for panel in panels.values():
        assert_no_lookahead(
            lambda p: build_features(p, spec, horizon=horizon, regimes=regimes),
            panel,
            origins=[8, 20, 40, 60],
        )  # A4
```

Add a cell for A5: for each arm and horizon, `reconstruct_level(revenue, make_target(revenue, arm, h), arm, h)` against `revenue.shift(-h)` with `np.testing.assert_allclose(..., rtol=1e-9)` on one company.

- [ ] **Step 4: Cell 4, "4. Export features"**

```python
config = RunConfig(
    panel_size=len(panels),
    n_rows=n_rows,
    target_variable="revenue_usd_m",
    target_transform=TargetArm.SEASNAIVE_RESIDUAL.value,
    feature_groups=tuple(sorted(group.value for group in spec.groups)),
)
with tracker.start_run(
    run_name(notebook="nb02", model="features", variable="revenue_usd_m"),
    config,
    job_type="features",
) as run:
    for horizon in (1, 2, 3, 4):
        dataset = assemble_dataset(
            panels,
            spec,
            horizon=horizon,
            arm=TargetArm.SEASNAIVE_RESIDUAL,
            regimes=regimes,
        )
        assert (
            len(dataset) == n_rows
            and dataset["y"].notna().sum() <= n_rows - 60 * horizon
        )  # A6
        path = write_panel(dataset, Settings.features_output_path(horizon))
        run.log_dataset(f"features_h{horizon}", path)
```

The run logs `n_features` in a follow-up `run.log_metrics({"n_features": dataset.shape[1] - 5})` (the five non-feature columns are `ticker`, `origin_date`, `target_date`, `target_level_usd_m`, `y`). `RunConfig.n_features` is frozen at construction, so compute it from a `build_features(...)` call on one panel *before* building `config`.

- [ ] **Step 5: Static checks on the notebook (A9, A8)**

Run:

```bash
uv run python -c "import json,sys; nb=json.load(open('src/app/playground/01_eda_feature_engineering.ipynb')); bad=[c for c in nb['cells'] if c['cell_type']=='code' and any(l.lstrip('').startswith(('def ','class ')) for l in c['source'])]; sys.exit(len(bad))"
uv run poe check
```

Expected: exit 0 for the first (no `def`/`class` at the start of a line in any code cell), then lint, typecheck and tests green with coverage ≥ 80%.

- [ ] **Step 6: Hand over.** Summarize the files added and modified, the `poe check` result, and which acceptance criteria are verified by tests (A5 shape, A8, A9) versus by the notebook run the user has not yet done (A1–A4, A6, A7). Stage nothing. Propose a commit message and wait for explicit approval.

---

## Self-review

**Spec coverage.** R1 → Task 1. R2, R3 → Task 3. R4 → Task 4. R5 → Task 2. R6 → Task 5 (groups L to F). R7 → Task 6. R8 → Task 7 and Task 8 step 4. R9 → Task 8 cells (tracker from the NB00 plan). R10 → Task 8 step 5. R11 → Global Constraints, enforced by `poe check`. A1–A7 → Task 8 cells; A8 → Task 8 step 5; A9 → Task 8 step 5.

**Known soft spots to watch during execution.**
- Task 3's `diagnose_series` may trip `PLR0913`/`C901`; split into helpers rather than suppressing.
- `kpss`, `boxcox_normmax` and `STL` results depend on library versions; if A3 disagrees with Appendix C, record the cause in the notebook as the spec requires.
- Task 8's regime lookup needs every ticker in `regimes`. A company with `insufficient_data` revenue would raise `MissingRegimeError`, which is the intended loud failure (spec R6).
- `build_features` now has eight group branches plus the ticker guard; if ruff reports `C901` or `PLR0912`, move the key frame and the guard into private helpers. Do not suppress.

**Type consistency.** `make_target` and `reconstruct_level` take `(values, arm, horizon)` in that order everywhere; `build_features` and `assemble_dataset` take keyword-only `horizon`; `PanelStore.load_consolidated` returns the per-ticker frames the notebook and `assemble_dataset` consume.
