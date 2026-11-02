import numpy as np
import pandas as pd
import pytest

from app.services.diagnostics import (
    DiagnosticsSettings,
    LevelTransform,
    TransformComparer,
    baseline_transform,
    box_cox,
    candidates_for,
    preferred_transform,
    summarize_transforms,
)
from tests.conftest import PanelFactory

QUARTERS = 80
SHORT_QUARTERS = 12
REVENUE = "revenue_usd_m"
OPERATING_INCOME = "operating_income_usd_m"


@pytest.fixture
def comparer() -> TransformComparer:
    return TransformComparer(settings=DiagnosticsSettings())


def _growing_panel(make_panel: PanelFactory, ticker: str, seed: int) -> pd.DataFrame:
    """Log-normal revenue, and an operating income that crosses zero.

    Both swing more as the company grows, the way real lines do.

    Returns:
        A panel whose revenue and operating income grow with a season.
    """
    rng = np.random.default_rng(seed)
    steps = np.arange(QUARTERS)
    panel = make_panel(ticker=ticker, quarters=QUARTERS)
    log_revenue = (
        0.03 * steps + 0.1 * np.sin(steps * np.pi / 2) + rng.normal(0, 0.05, QUARTERS)
    )
    panel[REVENUE] = 100 * np.exp(log_revenue)
    margin = 0.02 + rng.normal(0, 0.05, QUARTERS)
    panel[OPERATING_INCOME] = margin * panel[REVENUE]
    return panel


def _panels(make_panel: PanelFactory, tickers: list[str]) -> dict[str, pd.DataFrame]:
    return {
        ticker: _growing_panel(make_panel, ticker, seed)
        for seed, ticker in enumerate(tickers)
    }


def test_log_is_box_cox_with_lambda_zero() -> None:
    series = pd.Series([1.0, 2.5, 10.0, 40.0])

    np.testing.assert_allclose(
        box_cox(series, 0.0).to_numpy(), np.log(series.to_numpy())
    )


def test_each_target_is_compared_against_the_transform_it_uses_today() -> None:
    assert baseline_transform(REVENUE) is LevelTransform.LOG
    assert baseline_transform(OPERATING_INCOME) is LevelTransform.REVENUE_SCALED
    assert LevelTransform.LOG not in candidates_for(OPERATING_INCOME)


def test_log_removes_the_level_dependence_of_multiplicative_swings(
    make_panel: PanelFactory, comparer: TransformComparer
) -> None:
    table = comparer.compare(_panels(make_panel, ["AAA"]), variable=REVENUE)

    dependence = table.set_index("transform")["level_dependence"].to_dict()
    assert dependence[LevelTransform.LOG] < dependence[LevelTransform.NONE]


def test_scaling_by_revenue_removes_the_size_dependence_of_a_signed_line(
    make_panel: PanelFactory, comparer: TransformComparer
) -> None:
    table = comparer.compare(_panels(make_panel, ["AAA"]), variable=OPERATING_INCOME)

    dependence = table.set_index("transform")["level_dependence"].to_dict()
    assert dependence[LevelTransform.REVENUE_SCALED] < dependence[LevelTransform.NONE]


@pytest.mark.parametrize("variable", [REVENUE, OPERATING_INCOME])
def test_every_company_gets_one_row_per_candidate(
    make_panel: PanelFactory, comparer: TransformComparer, variable: str
) -> None:
    panels = _panels(make_panel, ["AAA", "BBB"])

    table = comparer.compare(panels, variable=variable)

    assert len(table) == len(panels) * len(candidates_for(variable))
    scores = ["level_dependence", "jarque_bera", "anderson_darling"]
    assert table[scores].notna().all().all()


@pytest.mark.parametrize(
    ("variable", "own", "sector"),
    [
        (REVENUE, "box_cox", "box_cox_sector"),
        (OPERATING_INCOME, "yeo_johnson", "yeo_johnson_sector"),
    ],
)
def test_the_sector_lambda_is_the_median_of_its_companies(
    make_panel: PanelFactory,
    comparer: TransformComparer,
    variable: str,
    own: str,
    sector: str,
) -> None:
    panels = _panels(make_panel, ["AAA", "BBB", "CCC"])

    table = comparer.compare(panels, variable=variable)

    own_lambdas = table.loc[table["transform"] == own, "lambda"]
    sector_lambdas = table.loc[table["transform"] == sector, "lambda"]
    assert sector_lambdas.tolist() == pytest.approx(
        [own_lambdas.median()] * len(panels)
    )


def test_a_series_too_short_to_diagnose_is_left_out(
    make_panel: PanelFactory, comparer: TransformComparer
) -> None:
    panels = {
        **_panels(make_panel, ["AAA"]),
        "BBB": make_panel(ticker="BBB", quarters=SHORT_QUARTERS),
    }

    table = comparer.compare(panels, variable=REVENUE)

    assert set(table["ticker"]) == {"AAA"}


def _scores(sqrt_beats_log: list[bool]) -> pd.DataFrame:
    rows = []
    for index, beats in enumerate(sqrt_beats_log):
        better = 0.1 if beats else 0.9
        rows.extend([
            {"ticker": f"T{index}", "transform": "log", "level_dependence": 0.5},
            {"ticker": f"T{index}", "transform": "sqrt", "level_dependence": better},
        ])
    table = pd.DataFrame(rows)
    normality = np.where(
        table["transform"] == "log", 5.0, table["level_dependence"] * 10
    )
    return table.assign(
        jarque_bera=normality,
        anderson_darling=normality,
        jarque_bera_p=0.5,
        skewness=0.0,
        excess_kurtosis=0.0,
    )


def test_a_transform_that_beats_the_baseline_in_most_companies_is_preferred() -> None:
    scores = _scores([True, True, True, False])

    assert (
        preferred_transform(scores, baseline=LevelTransform.LOG) is LevelTransform.SQRT
    )


def test_the_baseline_is_kept_when_nothing_beats_it_in_more_than_half() -> None:
    scores = _scores([True, True, False, False])

    assert (
        preferred_transform(scores, baseline=LevelTransform.LOG) is LevelTransform.LOG
    )


def test_winning_on_one_criterion_only_does_not_beat_the_baseline() -> None:
    scores = _scores([True, True, True, True])
    scores.loc[scores["transform"] == "sqrt", "jarque_bera"] = 50.0

    summary = summarize_transforms(scores, baseline=LevelTransform.LOG)

    beats = summary["beats_baseline_share"].to_dict()
    assert beats[LevelTransform.SQRT] == pytest.approx(0.0)
    assert (
        preferred_transform(scores, baseline=LevelTransform.LOG) is LevelTransform.LOG
    )


def test_the_second_opinion_can_disagree_with_jarque_bera() -> None:
    scores = _scores([True, True, True, True])
    scores.loc[scores["transform"] == "sqrt", "jarque_bera"] = 50.0

    decision = preferred_transform(
        scores, baseline=LevelTransform.LOG, normality="anderson_darling"
    )

    assert decision is LevelTransform.SQRT
