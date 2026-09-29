import numpy as np
import pandas as pd
import pytest

from app.data.schema import MACRO_COLUMNS
from app.services.diagnostics import (
    MacroCorrelator,
    RegimeSettings,
    SeasonalityRegimeClusterer,
    TooFewCompaniesError,
)
from tests.conftest import PanelFactory

QUARTERS = 40


def _diagnostics(strengths: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": list(strengths),
        "variable": "revenue_usd_m",
        "status": "ok",
        "seasonal_strength": list(strengths.values()),
        "trend_strength": 0.9,
    })


def _clusterer(n_regimes: int = 3) -> SeasonalityRegimeClusterer:
    return SeasonalityRegimeClusterer(settings=RegimeSettings(n_regimes=n_regimes))


def test_regimes_are_ordered_by_seasonal_strength() -> None:
    strengths = {"A": 0.02, "B": 0.05, "C": 0.5, "D": 0.55, "E": 0.95, "F": 0.9}

    regimes = _clusterer().assign(_diagnostics(strengths), variable="revenue_usd_m")

    assert regimes.to_dict() == {"A": 0, "B": 0, "C": 1, "D": 1, "E": 2, "F": 2}


def test_regimes_are_deterministic_for_a_seed() -> None:
    strengths = {"A": 0.02, "B": 0.5, "C": 0.95, "D": 0.1, "E": 0.6, "F": 0.9}
    diagnostics = _diagnostics(strengths)

    first = _clusterer().assign(diagnostics, variable="revenue_usd_m")
    second = _clusterer().assign(diagnostics, variable="revenue_usd_m")

    pd.testing.assert_series_equal(first, second)


def test_companies_without_a_full_diagnosis_get_no_regime() -> None:
    diagnostics = _diagnostics({"A": 0.1, "B": 0.5, "C": 0.9})
    diagnostics.loc[0, "status"] = "insufficient_data"

    regimes = _clusterer(n_regimes=2).assign(diagnostics, variable="revenue_usd_m")

    assert "A" not in regimes.index


def test_fewer_companies_than_regimes_is_a_named_error() -> None:
    diagnostics = _diagnostics({"A": 0.1, "B": 0.9})

    with pytest.raises(TooFewCompaniesError) as caught:
        _clusterer(n_regimes=3).assign(diagnostics, variable="revenue_usd_m")

    assert (caught.value.companies, caught.value.regimes) == (2, 3)


def test_growth_that_tracks_a_macro_series_correlates_perfectly(
    make_panel: PanelFactory,
) -> None:
    panel = make_panel(ticker="AAA", quarters=QUARTERS)
    panel["revenue_usd_m"] = 100 * np.exp(
        np.cumsum(np.sin(np.arange(QUARTERS) / 3)) * 0.05
    )
    # Built from the growth itself so the correlation is exactly 1 with no draw.
    panel["vix"] = pd.Series(np.log(panel["revenue_usd_m"])).diff(4)

    table = MacroCorrelator(macro_columns=MACRO_COLUMNS).correlate(
        {"AAA": panel}, variable="revenue_usd_m"
    )

    assert table.loc["AAA", "vix"] == pytest.approx(1.0)
    assert table.loc["AAA", "sector"] == "Technology"
    assert set(MACRO_COLUMNS) <= set(table.columns)


def test_only_the_injected_macro_columns_are_correlated(
    make_panel: PanelFactory,
) -> None:
    table = MacroCorrelator(macro_columns=("vix",)).correlate(
        {"AAA": make_panel(ticker="AAA", quarters=QUARTERS)}, variable="revenue_usd_m"
    )

    assert list(table.columns) == ["vix", "sector"]
