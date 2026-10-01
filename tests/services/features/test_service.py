import pandas as pd
import pytest

from app.services.features import (
    FeatureBuilder,
    FeatureGroup,
    FeatureService,
    FeatureSpec,
    LeakageSettings,
    LookaheadGuard,
    TargetArm,
    TargetTransformer,
    TargetVariable,
    UnsupportedArmError,
    arms_for,
)
from tests.conftest import PanelFactory

SPEC = FeatureSpec(groups=frozenset({FeatureGroup.LAGS, FeatureGroup.STATIC}))
REGIMES = pd.Series({"AAA": 0, "BBB": 1})
QUARTERS = 24


def _service(spec: FeatureSpec = SPEC) -> FeatureService:
    return FeatureService(
        builder=FeatureBuilder(spec=spec),
        guard=LookaheadGuard(settings=LeakageSettings()),
    )


@pytest.fixture
def panels(make_panel: PanelFactory) -> dict[str, pd.DataFrame]:
    return {
        "AAA": make_panel(ticker="AAA", quarters=QUARTERS),
        "BBB": make_panel(ticker="BBB", quarters=QUARTERS, sector="Energy"),
    }


def test_every_origin_row_of_every_company_is_kept(
    panels: dict[str, pd.DataFrame],
) -> None:
    dataset = _service().assemble(
        panels, horizon=2, arm=TargetArm.LOG_DIFF4, regimes=REGIMES
    )

    assert len(dataset) == len(panels) * QUARTERS
    assert dataset["ticker"].value_counts().to_dict() == {
        "AAA": QUARTERS,
        "BBB": QUARTERS,
    }


def test_target_columns_match_the_transform(panels: dict[str, pd.DataFrame]) -> None:
    horizon = 2
    dataset = _service().assemble(
        panels, horizon=horizon, arm=TargetArm.LOG_DIFF4, regimes=REGIMES
    )
    company = dataset[dataset["ticker"] == "AAA"].reset_index(drop=True)
    revenue = panels["AAA"]["revenue_usd_m"]

    transformer = TargetTransformer(arm=TargetArm.LOG_DIFF4, horizon=horizon)
    pd.testing.assert_series_equal(
        company["y"], transformer.make(revenue), check_names=False
    )
    assert company["target_level"].iloc[0] == revenue.iloc[horizon]


def test_the_last_horizon_origins_have_no_target_yet(
    panels: dict[str, pd.DataFrame],
) -> None:
    horizon = 3
    dataset = _service().assemble(
        panels, horizon=horizon, arm=TargetArm.LOG_DIFF1, regimes=REGIMES
    )

    unlabelled = dataset[dataset["y"].isna()]
    assert unlabelled.groupby("ticker").size().eq(horizon).all()


def test_sector_is_categorical_across_companies(
    panels: dict[str, pd.DataFrame],
) -> None:
    dataset = _service().assemble(
        panels, horizon=1, arm=TargetArm.LOG_DIFF1, regimes=REGIMES
    )

    assert isinstance(dataset["sector"].dtype, pd.CategoricalDtype)


def test_without_the_static_group_no_sector_column_appears(
    panels: dict[str, pd.DataFrame],
) -> None:
    service = _service(FeatureSpec(groups=frozenset({FeatureGroup.LAGS})))

    dataset = service.assemble(panels, horizon=1, arm=TargetArm.LOG_DIFF1)

    assert "sector" not in dataset.columns


@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_own_builder_passes_the_lookahead_check(
    make_panel: PanelFactory, horizon: int
) -> None:
    service = _service(FeatureSpec())
    panel = make_panel(ticker="AAA").assign(covid=False, structural_break=False)

    service.check_lookahead(
        panel, horizon=horizon, origins=[3, 8, 15, 20], regimes=REGIMES
    )


def test_a_signed_target_gets_the_revenue_scaled_target(
    panels: dict[str, pd.DataFrame],
) -> None:
    spec = FeatureSpec(
        target_variable=TargetVariable.EBITDA,
        groups=frozenset({FeatureGroup.LAGS}),
    )
    horizon = 2

    dataset = _service(spec).assemble(
        panels, horizon=horizon, arm=TargetArm.REVENUE_SCALED_YOY
    )

    company = dataset[dataset["ticker"] == "AAA"].reset_index(drop=True)
    panel = panels["AAA"]
    expected = TargetTransformer(
        arm=TargetArm.REVENUE_SCALED_YOY, horizon=horizon
    ).make(panel["ebitda_usd_m"], revenue=panel["revenue_usd_m"])
    pd.testing.assert_series_equal(company["y"], expected, check_names=False)


def test_an_arm_foreign_to_the_target_is_refused(
    panels: dict[str, pd.DataFrame],
) -> None:
    spec = FeatureSpec(target_variable=TargetVariable.EBITDA)

    with pytest.raises(UnsupportedArmError, match="ebitda_usd_m") as caught:
        _service(spec).assemble(panels, horizon=1, arm=TargetArm.LOG_DIFF4)

    assert caught.value.arm == TargetArm.LOG_DIFF4


def test_target_frame_has_one_row_per_quarter_arm_and_horizon(
    panels: dict[str, pd.DataFrame],
) -> None:
    horizons = (1, 2)

    frame = _service(FeatureSpec()).target_frame(panels, horizons=horizons)

    assert list(frame.columns) == ["ticker", "date", "arm", "horizon", "y"]
    assert len(frame) == len(panels) * QUARTERS * len(horizons) * 3
    assert set(frame["arm"]) == {arm.value for arm in arms_for(TargetVariable.REVENUE)}


def test_target_frame_values_are_the_transformers(
    panels: dict[str, pd.DataFrame],
) -> None:
    frame = _service(FeatureSpec()).target_frame(panels, horizons=(2,))

    sample = frame[
        (frame["ticker"] == "AAA") & (frame["arm"] == TargetArm.LOG_DIFF4.value)
    ].reset_index(drop=True)
    revenue = panels["AAA"]["revenue_usd_m"]
    expected = TargetTransformer(arm=TargetArm.LOG_DIFF4, horizon=2).make(revenue)
    pd.testing.assert_series_equal(sample["y"], expected, check_names=False)


def test_a_signed_target_frame_uses_only_the_scaled_arm(
    panels: dict[str, pd.DataFrame],
) -> None:
    spec = FeatureSpec(target_variable=TargetVariable.EBITDA)

    frame = _service(spec).target_frame(panels, horizons=(1,))

    assert set(frame["arm"]) == {TargetArm.REVENUE_SCALED_YOY.value}
