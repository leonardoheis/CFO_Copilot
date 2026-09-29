import numpy as np
import pandas as pd
import pytest

from app.data.schema import MACRO_COLUMNS
from app.services.features import (
    SEASONAL_LAG,
    FeatureBuilder,
    FeatureGroup,
    FeatureSpec,
    MissingFlagsError,
    MissingRegimeError,
    MixedTickerPanelError,
)
from tests.conftest import PanelFactory

KEYS = ["ticker", "origin_date", "target_date"]
LONGEST_LAG = 8
THIRD_QUARTER = 3


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
def test_each_group_adds_its_columns(
    make_panel: PanelFactory, group: FeatureGroup, columns: list[str]
) -> None:
    features = FeatureBuilder(spec=_spec(group)).build(
        _with_flags(make_panel()), horizon=1
    )

    assert list(features.columns) == KEYS + columns


def test_every_row_is_kept_and_indexed_like_the_panel(make_panel: PanelFactory) -> None:
    panel = make_panel()

    features = FeatureBuilder(spec=_spec(FeatureGroup.L)).build(panel, horizon=2)

    assert features.index.equals(panel.index)


def test_lag_one_is_the_origin_quarters_own_growth(make_panel: PanelFactory) -> None:
    panel = make_panel()
    features = FeatureBuilder(spec=_spec(FeatureGroup.L)).build(panel, horizon=1)

    expected = np.log(panel["revenue_usd_m"].iloc[9] / panel["revenue_usd_m"].iloc[5])
    assert features["growth_yoy_lag1"].iloc[9] == pytest.approx(expected)
    assert features["growth_yoy_lag2"].iloc[9] == features["growth_yoy_lag1"].iloc[8]


def test_short_history_is_nan_never_filled(make_panel: PanelFactory) -> None:
    features = FeatureBuilder(spec=_spec(FeatureGroup.L)).build(make_panel(), horizon=1)

    assert features["growth_yoy_lag1"].isna().sum() == SEASONAL_LAG
    assert (
        features[f"growth_yoy_lag{LONGEST_LAG}"].isna().sum()
        == SEASONAL_LAG + LONGEST_LAG - 1
    )


def test_an_interior_gap_leaves_nan_where_it_touches_the_growth(
    make_panel: PanelFactory,
) -> None:
    panel = make_panel()
    panel.loc[10, "revenue_usd_m"] = np.nan

    features = FeatureBuilder(spec=_spec(FeatureGroup.L)).build(panel, horizon=1)

    missing = set(features.index[features["growth_yoy_lag1"].isna()])
    assert missing == {0, 1, 2, 3, 10, 14}


def test_target_quarter_is_the_calendar_quarter_of_origin_plus_horizon(
    make_panel: PanelFactory,
) -> None:
    features = FeatureBuilder(spec=_spec(FeatureGroup.C)).build(make_panel(), horizon=2)

    assert features["origin_date"].iloc[0] == pd.Timestamp("2015-03-31")
    assert features["target_date"].iloc[0] == pd.Timestamp("2015-09-30")
    assert features["target_quarter"].iloc[0] == THIRD_QUARTER


def test_real_rate_is_fed_funds_minus_cpi(make_panel: PanelFactory) -> None:
    panel = make_panel()

    features = FeatureBuilder(spec=_spec(FeatureGroup.XD)).build(panel, horizon=1)

    pd.testing.assert_series_equal(
        features["real_rate"], panel["fed_funds"] - panel["cpi_yoy"], check_names=False
    )


def test_static_group_needs_a_regime_for_the_company(make_panel: PanelFactory) -> None:
    panel = make_panel(ticker="AAA")

    with pytest.raises(MissingRegimeError):
        FeatureBuilder(spec=_spec(FeatureGroup.S)).build(panel, horizon=1)
    with pytest.raises(MissingRegimeError, match="AAA"):
        FeatureBuilder(spec=_spec(FeatureGroup.S)).build(
            panel, horizon=1, regimes=pd.Series({"BBB": 1})
        )


def test_static_group_carries_sector_and_regime(make_panel: PanelFactory) -> None:
    features = FeatureBuilder(spec=_spec(FeatureGroup.S)).build(
        make_panel(ticker="AAA"),
        horizon=1,
        regimes=pd.Series({"AAA": 2}),
    )

    assert features["seasonality_regime"].eq(2).all()
    assert features["sector"].eq("Technology").all()


def test_flags_are_copied_from_the_origin_row(make_panel: PanelFactory) -> None:
    panel = _with_flags(make_panel())
    panel.loc[6, "covid"] = True

    features = FeatureBuilder(spec=_spec(FeatureGroup.F)).build(panel, horizon=1)

    assert features["covid"].tolist() == panel["covid"].tolist()


def test_group_f_without_flag_columns_is_refused(make_panel: PanelFactory) -> None:
    with pytest.raises(MissingFlagsError, match="covid"):
        FeatureBuilder(spec=_spec(FeatureGroup.F)).build(make_panel(), horizon=1)


def test_a_panel_of_two_companies_is_refused(make_panel: PanelFactory) -> None:
    mixed = pd.concat(
        [make_panel(ticker="AAA"), make_panel(ticker="BBB")], ignore_index=True
    )

    with pytest.raises(MixedTickerPanelError):
        FeatureBuilder(spec=_spec(FeatureGroup.L)).build(mixed, horizon=1)


def test_default_spec_builds_every_group() -> None:
    assert FeatureSpec().groups == frozenset(FeatureGroup)
