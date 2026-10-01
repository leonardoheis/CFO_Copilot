import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.diagnostics import (
    CorrelationAnalyzer,
    CorrelationSettings,
    pooled_yoy_changes,
    yoy_changes,
)

QUARTERS = 24
LAG = 4


def _panel() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    steps = np.arange(QUARTERS)
    revenue = 100.0 * np.exp(0.02 * steps + 0.05 * rng.normal(size=QUARTERS))
    return pd.DataFrame({
        "ticker": "AAA",
        "date": pd.date_range("2015-03-31", periods=QUARTERS, freq="QE"),
        "revenue_usd_m": revenue,
        "ebitda_usd_m": 20.0 * np.sin(steps) - 5.0,
        "gross_margin": 0.4 + 0.01 * rng.normal(size=QUARTERS),
    })


def test_a_positive_column_changes_by_its_log() -> None:
    panel = _panel()

    changes = yoy_changes(panel, ["revenue_usd_m"])

    expected = np.log(panel["revenue_usd_m"]).diff(LAG)
    pd.testing.assert_series_equal(
        changes["revenue_usd_m"], expected, check_names=False
    )


def test_a_signed_line_changes_by_trailing_revenue() -> None:
    panel = _panel()

    changes = yoy_changes(panel, ["ebitda_usd_m"])

    expected = (
        panel["ebitda_usd_m"].diff(LAG) / panel["revenue_usd_m"].rolling(LAG).sum()
    )
    pd.testing.assert_series_equal(changes["ebitda_usd_m"], expected, check_names=False)


def test_a_ratio_changes_by_its_plain_difference() -> None:
    panel = _panel()

    changes = yoy_changes(panel, ["gross_margin"])

    pd.testing.assert_series_equal(
        changes["gross_margin"], panel["gross_margin"].diff(LAG), check_names=False
    )


def test_pooled_changes_stack_every_company() -> None:
    panels = {"AAA": _panel(), "BBB": _panel().assign(ticker="BBB")}

    pooled = pooled_yoy_changes(panels, ["revenue_usd_m", "gross_margin"])

    assert len(pooled) == len(panels) * QUARTERS
    assert list(pooled.columns) == ["ticker", "date", "revenue_usd_m", "gross_margin"]


def test_only_pairs_above_the_threshold_are_redundant() -> None:
    rng = np.random.default_rng(3)
    base = rng.normal(size=200)
    changes = pd.DataFrame({
        "twin_a": base,
        "twin_b": base + 0.05 * rng.normal(size=200),
        "cousin": base + 1.0 * rng.normal(size=200),
    })
    analyzer = CorrelationAnalyzer(settings=CorrelationSettings())

    matrix = analyzer.matrix(changes)
    pairs = analyzer.redundant_pairs(matrix)

    assert list(pairs.columns) == ["left", "right", "rho"]
    assert pairs[["left", "right"]].to_numpy().tolist() == [["twin_a", "twin_b"]]
    assert matrix.loc["twin_a", "twin_b"] == pytest.approx(
        changes["twin_a"].corr(changes["twin_b"], method="spearman")
    )


def test_settings_refuse_a_threshold_outside_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        CorrelationSettings(redundancy_threshold=1.5)
