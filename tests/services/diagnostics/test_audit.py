import math

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.diagnostics import DataDictionary, OutlierRegister, OutlierSettings

QUARTERS = 32
NEGATIVE_REVENUE = -50.0
FOURTH_QUARTER = 3
REGISTER_COLUMNS = "ticker date column value change robust_z hampel_z direction"


def _panel(ticker: str, revenue: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ticker,
        "date": pd.date_range("2015-03-31", periods=len(revenue), freq="QE"),
        "revenue_usd_m": revenue,
        "ebitda_usd_m": [value * 0.2 for value in revenue],
        "eps": np.linspace(1.0, 2.0, len(revenue)).round(3),
    })


def _growing_revenue() -> list[float]:
    rng = np.random.default_rng(0)
    steps = np.arange(QUARTERS)
    return list(100.0 * np.exp(0.02 * steps + 0.01 * rng.normal(size=QUARTERS)))


@pytest.fixture
def register() -> OutlierRegister:
    return OutlierRegister(settings=OutlierSettings())


def test_a_growing_series_registers_nothing(register: OutlierRegister) -> None:
    table = register.register(
        {"AAA": _panel("AAA", _growing_revenue())}, ["revenue_usd_m"]
    )

    assert table.empty
    assert " ".join(table.columns) == REGISTER_COLUMNS


def test_regular_seasonality_is_not_an_outlier(register: OutlierRegister) -> None:
    steps = np.arange(QUARTERS)
    # A retailer's Q4 surge repeats every year, so it is the company's normal.
    seasonal = 100.0 * np.exp(0.01 * steps + 0.3 * (steps % 4 == FOURTH_QUARTER))

    table = register.register({"AAA": _panel("AAA", list(seasonal))}, ["revenue_usd_m"])

    assert table.empty


def test_a_jump_is_registered_with_both_scores(register: OutlierRegister) -> None:
    revenue = _growing_revenue()
    jump_quarter = 16
    revenue[jump_quarter:] = [value * 4 for value in revenue[jump_quarter:]]

    table = register.register({"AAA": _panel("AAA", revenue)}, ["revenue_usd_m"])

    entry = table.iloc[0]
    assert entry["date"] == pd.Timestamp("2019-03-31")
    assert entry["direction"] == "up"
    assert entry["robust_z"] > OutlierSettings().z_threshold
    assert entry["change"] == pytest.approx(revenue[jump_quarter] / revenue[15] - 1)
    assert math.isfinite(entry["hampel_z"])


def test_the_most_extreme_entry_comes_first(register: OutlierRegister) -> None:
    revenue = _growing_revenue()
    revenue[10:] = [value * 3 for value in revenue[10:]]
    revenue[20:] = [value * 10 for value in revenue[20:]]

    table = register.register({"AAA": _panel("AAA", revenue)}, ["revenue_usd_m"])

    assert table["date"].iloc[0] == pd.Timestamp("2020-03-31")
    assert table["robust_z"].abs().is_monotonic_decreasing


def test_signed_lines_are_judged_against_trailing_revenue(
    register: OutlierRegister,
) -> None:
    panel = _panel("AAA", _growing_revenue())
    panel.loc[16, "ebitda_usd_m"] = -500.0

    table = register.register({"AAA": panel}, ["ebitda_usd_m"])

    assert pd.Timestamp("2019-03-31") in set(table["date"])
    assert "non_positive" not in set(table["direction"])


def test_a_non_positive_revenue_is_registered(register: OutlierRegister) -> None:
    revenue = _growing_revenue()
    revenue[5] = NEGATIVE_REVENUE

    table = register.register({"AAA": _panel("AAA", revenue)}, ["revenue_usd_m"])

    invalid = table[table["direction"] == "non_positive"]
    assert invalid["date"].tolist() == [pd.Timestamp("2016-06-30")]


def test_a_flat_window_gives_a_finite_hampel_score(register: OutlierRegister) -> None:
    revenue = [100.0] * 12 + _growing_revenue()[12:]
    revenue[8] = 400.0

    table = register.register({"AAA": _panel("AAA", revenue)}, ["revenue_usd_m"])

    assert not table.empty
    assert np.isfinite(table["hampel_z"]).all()


def test_a_short_history_is_not_judged(register: OutlierRegister) -> None:
    short = [100.0, 100.0, 900.0, 100.0]

    table = register.register({"AAA": _panel("AAA", short)}, ["revenue_usd_m"])

    assert table.empty


def test_only_the_requested_columns_are_checked(register: OutlierRegister) -> None:
    revenue = _growing_revenue()
    revenue[16:] = [value * 4 for value in revenue[16:]]

    table = register.register({"AAA": _panel("AAA", revenue)}, ["eps"])

    assert "revenue_usd_m" not in set(table["column"])


def test_settings_refuse_a_non_positive_threshold() -> None:
    with pytest.raises(ValidationError):
        OutlierSettings(z_threshold=0.0)


def test_dictionary_describes_every_requested_column() -> None:
    revenue = _growing_revenue()
    revenue[5] = NEGATIVE_REVENUE
    revenue[6] = math.nan
    pooled = _panel("AAA", revenue)
    register = OutlierRegister(settings=OutlierSettings()).register(
        {"AAA": pooled}, ["revenue_usd_m", "eps"]
    )

    table = DataDictionary(settings=OutlierSettings()).describe(
        pooled, ["revenue_usd_m", "eps"], register=register
    )

    assert list(table.columns) == [
        "column",
        "dtype",
        "missing_share",
        "unique",
        "min",
        "max",
        "invalid_sign",
        "register_count",
    ]
    revenue_row = table.set_index("column").loc["revenue_usd_m"]
    assert revenue_row["missing_share"] == pytest.approx(1 / QUARTERS)
    assert revenue_row["invalid_sign"] == 1
    assert revenue_row["min"] == pytest.approx(NEGATIVE_REVENUE)
    assert (
        revenue_row["register_count"] == (register["column"] == "revenue_usd_m").sum()
    )
    assert table.set_index("column").loc["eps", "invalid_sign"] == 0


def test_mostly_identical_changes_still_give_finite_scores(
    register: OutlierRegister,
) -> None:
    steps = np.arange(QUARTERS)
    # Over half the changes are equal, so the MAD collapses to ~0.
    revenue = list(100.0 * np.exp(0.01 * steps + 0.3 * (steps % 4 == FOURTH_QUARTER)))
    revenue[20:] = [value * 20 for value in revenue[20:]]

    table = register.register({"AAA": _panel("AAA", revenue)}, ["revenue_usd_m"])

    assert table["date"].tolist() == [pd.Timestamp("2020-03-31")]
    assert np.isfinite(table["robust_z"]).all()


def test_a_derived_column_is_left_to_its_inputs(register: OutlierRegister) -> None:
    panel = _panel("AAA", _growing_revenue()).assign(pe_ratio=30.0)
    panel.loc[16, "pe_ratio"] = 16_505.0

    table = register.register({"AAA": panel}, ["pe_ratio"])

    assert table.empty


def _target_frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": "AAA",
        "date": pd.date_range("2015-03-31", periods=len(values), freq="QE"),
        "arm": "log_diff4",
        "horizon": 1,
        "y": values,
    })


def test_an_extreme_target_value_is_registered(register: OutlierRegister) -> None:
    rng = np.random.default_rng(1)
    values = list(0.05 + 0.01 * rng.normal(size=QUARTERS))
    values[10] = 2.0

    extremes = register.register_target(_target_frame(values))

    assert " ".join(extremes.columns) == "ticker date arm horizon y robust_z direction"
    assert extremes["date"].tolist() == [pd.Timestamp("2017-09-30")]
    assert extremes["direction"].iloc[0] == "up"


def test_an_ordinary_target_registers_nothing(register: OutlierRegister) -> None:
    rng = np.random.default_rng(1)

    extremes = register.register_target(
        _target_frame(list(0.05 + 0.01 * rng.normal(size=QUARTERS)))
    )

    assert extremes.empty


def test_scores_cover_every_quarter_of_a_series(register: OutlierRegister) -> None:
    revenue = _growing_revenue()
    revenue[16:] = [value * 4 for value in revenue[16:]]

    scores = register.scores_for(_panel("AAA", revenue), "revenue_usd_m")

    assert list(scores.columns) == [
        "date",
        "value",
        "change",
        "robust_z",
        "hampel_z",
    ]
    assert len(scores) == QUARTERS
    flagged = scores.loc[scores["robust_z"].abs() > register.z_threshold, "date"]
    assert flagged.tolist() == [pd.Timestamp("2019-03-31")]


def test_a_series_too_short_to_score_gives_no_scores(
    register: OutlierRegister,
) -> None:
    scores = register.scores_for(
        _panel("AAA", [100.0, 100.0, 900.0, 100.0]), "revenue_usd_m"
    )

    assert scores.empty
