from collections.abc import Iterator

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from syrupy.assertion import SnapshotAssertion

from app.services.diagnostics import (
    EdaFigures,
    FigureSettings,
    OutlierRegister,
    OutlierSettings,
)

QUARTERS = 32


def _panel(ticker: str, jump: float) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    revenue = 100.0 * np.exp(
        0.02 * np.arange(QUARTERS) + 0.01 * rng.normal(size=QUARTERS)
    )
    revenue[16:] *= jump
    return pd.DataFrame({
        "ticker": ticker,
        "date": pd.date_range("2015-03-31", periods=QUARTERS, freq="QE"),
        "revenue_usd_m": revenue,
    })


@pytest.fixture
def figures() -> Iterator[EdaFigures]:
    yield EdaFigures(
        settings=FigureSettings(),
        outlier_register=OutlierRegister(settings=OutlierSettings()),
    )
    plt.close("all")


@pytest.fixture
def panels() -> dict[str, pd.DataFrame]:
    return {"AAA": _panel("AAA", 4.0), "BBB": _panel("BBB", 6.0)}


def _titles(figure: Figure) -> list[str]:
    return [axes.get_title() for axes in figure.axes if axes.get_title()]


def test_register_counts_draws_one_bar_chart(
    figures: EdaFigures, panels: dict[str, pd.DataFrame]
) -> None:
    register = OutlierRegister(settings=OutlierSettings()).register(
        panels, ["revenue_usd_m"]
    )

    figure = figures.register_counts(register)

    assert _titles(figure) == ["Outlier register: entries per column and direction"]


def test_top_series_draws_a_level_and_a_score_panel_per_series(
    figures: EdaFigures, panels: dict[str, pd.DataFrame]
) -> None:
    register = OutlierRegister(settings=OutlierSettings()).register(
        panels, ["revenue_usd_m"]
    )

    figure = figures.top_series_scores(register, panels)

    # BBB's jump is larger, so the register ranks it first.
    assert _titles(figure) == [
        "BBB revenue_usd_m: level",
        "BBB revenue_usd_m: distance from normal",
        "AAA revenue_usd_m: level",
        "AAA revenue_usd_m: distance from normal",
    ]


def test_target_distribution_draws_one_panel_per_arm_and_horizon(
    figures: EdaFigures,
) -> None:
    rng = np.random.default_rng(1)
    target_frame = pd.DataFrame({
        "arm": np.repeat(["log_diff1", "log_diff4"], 40),
        "horizon": np.tile(np.repeat([1, 2], 20), 2),
        "y": rng.normal(size=80),
    })

    figure = figures.target_distribution(target_frame, title="revenue_usd_m")

    arms_times_horizons = target_frame[["arm", "horizon"]].drop_duplicates()
    assert len([axes for axes in figure.axes if axes.has_data()]) == len(
        arms_times_horizons
    )


def test_change_figures_draw_every_column(figures: EdaFigures) -> None:
    rng = np.random.default_rng(2)
    changes = pd.DataFrame({
        "revenue_usd_m": rng.normal(size=60),
        "ebitda_usd_m": rng.normal(size=60),
    })

    distributions = figures.change_distributions(changes)
    boxes = figures.change_boxplots(changes)

    drawn = [axes for axes in distributions.axes if axes.has_data()]
    assert len(drawn) == len(changes.columns)
    assert _titles(boxes) == ["Spread and outliers of each column's change"]


def test_categories_draw_sectors_and_regimes(figures: EdaFigures) -> None:
    sectors = pd.Series(["Energy", "Energy", "Technology"], index=["A", "B", "C"])
    regimes = pd.Series([0, 1, 1], index=["A", "B", "C"])

    figure = figures.categories(sectors, regimes)

    assert _titles(figure) == [
        "Companies per sector",
        "Companies per seasonality regime (0 = least seasonal)",
    ]


def test_heatmaps_title_what_they_correlate(figures: EdaFigures) -> None:
    matrix = pd.DataFrame(
        [[1.0, 0.9], [0.9, 1.0]], index=["a", "b"], columns=["a", "b"]
    )

    correlation = figures.correlation_heatmap(matrix)
    sensitivity = figures.sector_sensitivity(matrix)

    assert "Spearman correlation of year-over-year changes" in _titles(correlation)
    assert "YoY growth vs macro: mean correlation by sector" in _titles(sensitivity)


def test_seasonal_strength_histogram_is_titled(figures: EdaFigures) -> None:
    diagnostics = pd.DataFrame({"seasonal_strength": [0.1, 0.5, 0.9]})

    figure = figures.seasonal_strength(diagnostics)

    assert _titles(figure) == ["Seasonal strength (STL, period 4)"]


def test_segment_figures_are_titled(figures: EdaFigures) -> None:
    rng = np.random.default_rng(4)
    frame = pd.DataFrame({
        "y": rng.normal(size=40),
        "sector": ["Energy", "Technology"] * 20,
        "regime": [0, 1, 2, 2] * 10,
        "period": ["before_covid", "covid", "after_covid", "after_covid"] * 10,
    })
    profile = pd.DataFrame({
        "regime": [0] * 4 + [1] * 4,
        "target_quarter": [1, 2, 3, 4] * 2,
        "mean_y": rng.normal(size=8),
    })
    timeline = pd.DataFrame({
        "date": pd.date_range("2019-03-31", periods=8, freq="QE"),
        "median_y": rng.normal(size=8),
        "covid": [False, False, False, False, True, True, False, False],
        "breaks": [0, 0, 1, 0, 0, 0, 0, 0],
    })

    boxes = figures.segment_boxplots(frame, ["sector", "regime", "period"])
    seasonal = figures.seasonal_profile(profile)
    trend = figures.median_timeline(timeline)

    assert _titles(boxes) == [
        "Target by sector",
        "Target by regime",
        "Target by period",
    ]
    assert _titles(seasonal) == ["Mean target by forecast quarter, per regime"]
    assert _titles(trend) == ["Panel-median target (covid shaded, breaks marked)"]


def test_feature_ranking_draws_one_bar_per_scored_feature(figures: EdaFigures) -> None:
    features = pd.DataFrame({
        "feature": ["growth_yoy_lag1", "vix", "real_rate"],
        "group": ["L", "X", "XD"],
        "mutual_information": [0.4, 0.05, np.nan],
    })

    figure = figures.feature_ranking(features)

    axes = figure.axes[0]
    assert axes.get_title() == "Mutual information with the target, per feature"
    assert [label.get_text() for label in axes.get_yticklabels()] == [
        "growth_yoy_lag1",
        "vix",
    ]


def test_transform_comparison_draws_both_criteria(figures: EdaFigures) -> None:
    table = pd.DataFrame({
        "transform": ["none", "log", "none", "log"],
        "level_dependence": [0.8, 0.2, 0.7, 0.1],
        "jarque_bera": [40.0, 5.0, 30.0, 4.0],
    })

    figure = figures.transform_comparison(table)

    assert _titles(figure) == [
        "Level dependence (|Spearman|; lower is better)",
        "Jarque-Bera of the STL remainder (lower is better)",
    ]


def test_a_title_added_by_the_caller_clears_the_panel_titles(
    figures: EdaFigures,
) -> None:
    table = pd.DataFrame({
        "transform": ["none", "log"],
        "level_dependence": [0.8, 0.2],
        "jarque_bera": [40.0, 5.0],
    })
    figure = figures.transform_comparison(table)

    title = figure.suptitle("revenue_usd_m", x=0.01, ha="left")
    figure.canvas.draw()

    title_bottom = title.get_window_extent().y0
    assert all(
        title_bottom >= axes.title.get_window_extent().y1 for axes in figure.axes
    )


def _boxes(figure: Figure) -> list[dict[str, list[object]]]:
    return [
        {
            "labels": [label.get_text() for label in axes.get_yticklabels()],
            "colours": [to_hex(patch.get_facecolor()) for patch in axes.patches],
            "heights": [
                round(float(patch.get_path().get_extents().height), 6)
                for patch in axes.patches
            ],
        }
        for axes in figure.axes
    ]


def test_every_boxplot_keeps_its_boxes(
    figures: EdaFigures, snapshot: SnapshotAssertion
) -> None:
    rng = np.random.default_rng(5)
    changes = pd.DataFrame({
        "revenue_usd_m": rng.normal(size=60),
        "ebitda_usd_m": rng.normal(size=60),
    })
    segments = pd.DataFrame({
        "y": rng.normal(size=40),
        "sector": ["Energy", "Technology"] * 20,
        "regime": [0, 1, 2, 2] * 10,
    })
    comparison = pd.DataFrame({
        "transform": ["none", "log", "none", "log"],
        "level_dependence": [0.8, 0.2, 0.7, 0.1],
        "jarque_bera": [40.0, 5.0, 30.0, 4.0],
    })

    assert {
        "change": _boxes(figures.change_boxplots(changes)),
        "segment": _boxes(figures.segment_boxplots(segments, ["sector", "regime"])),
        "transform": _boxes(figures.transform_comparison(comparison)),
    } == snapshot
