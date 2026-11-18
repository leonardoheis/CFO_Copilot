from collections.abc import Iterator
from itertools import product

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure

from app.services.evaluation import (
    coverage_reliability_figure,
    error_by_history_figure,
    mae_by_sector_figure,
)

BASELINES = ("seasonal_naive", "naive")
HORIZONS = (1, 4)
HISTORIES = ("8", "12", "all")
pytestmark = pytest.mark.usefixtures("close_figures")


@pytest.fixture
def close_figures() -> Iterator[None]:
    yield
    plt.close("all")


def _titles(figure: Figure) -> list[str]:
    return [axes.get_title() for axes in figure.axes if axes.get_title()]


def test_mae_by_sector_draws_one_heatmap_per_baseline() -> None:
    by_sector = pd.DataFrame([
        {"baseline": baseline, "sector": sector, "horizon": horizon, "mae": 0.1}
        for baseline, sector, horizon in product(
            BASELINES, ("Energy", "Utilities"), HORIZONS
        )
    ])

    figure = mae_by_sector_figure(by_sector, title="revenue, Protocol A")

    assert _titles(figure) == list(BASELINES)
    assert figure.get_suptitle() == "revenue, Protocol A"


def test_coverage_reliability_marks_each_nominal_level() -> None:
    pooled = pd.DataFrame([
        {"baseline": baseline, "level": level, "coverage": level + 0.01}
        for baseline, level in product(BASELINES, (0.8, 0.9, 0.95))
    ])

    figure = coverage_reliability_figure(pooled, title="revenue, Protocol B")

    (axes,) = figure.axes
    assert axes.get_title() == "revenue, Protocol B"
    nominal = [
        lines.get_segments()[0][0][1]
        for lines in axes.collections
        if isinstance(lines, LineCollection)
    ]
    assert nominal == pytest.approx([0.8, 0.9, 0.95])


def test_error_by_history_draws_one_panel_per_horizon_in_history_order() -> None:
    pooled = pd.DataFrame([
        {"baseline": baseline, "horizon": horizon, "history": history, "mae": 0.1}
        for baseline, horizon, history in product(BASELINES, HORIZONS, HISTORIES)
    ])

    figure = error_by_history_figure(pooled, title="revenue, Protocol B")

    assert _titles(figure) == [f"h = {horizon}" for horizon in HORIZONS]
    labels = [tick.get_text() for tick in figure.axes[0].get_xticklabels()]
    assert labels == list(HISTORIES)
