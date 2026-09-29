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
