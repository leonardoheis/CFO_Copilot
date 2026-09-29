import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.features import (
    FeatureBuilder,
    FeatureGroup,
    FeatureSpec,
    LeakageError,
    LeakageSettings,
    LookaheadGuard,
)
from tests.conftest import PanelFactory

REGIMES = pd.Series({"AAA": 1})


@pytest.fixture
def guard() -> LookaheadGuard:
    return LookaheadGuard(settings=LeakageSettings())


@pytest.mark.parametrize("horizon", [1, 2, 3, 4])
def test_real_builder_passes_at_every_horizon(
    make_panel: PanelFactory, guard: LookaheadGuard, horizon: int
) -> None:
    builder = FeatureBuilder(spec=FeatureSpec())

    guard.check(
        lambda panel: builder.build(panel, horizon=horizon, regimes=REGIMES),
        make_panel(ticker="AAA").assign(covid=False, structural_break=False),
        origins=[3, 8, 15, 20],
    )


def test_a_builder_that_peeks_one_quarter_ahead_is_caught(
    make_panel: PanelFactory, guard: LookaheadGuard
) -> None:
    builder = FeatureBuilder(spec=FeatureSpec(groups=frozenset({FeatureGroup.L})))

    def leaky(panel: pd.DataFrame) -> pd.DataFrame:
        features = builder.build(panel, horizon=1)
        return features.assign(peek=panel["revenue_usd_m"].shift(-1))

    with pytest.raises(LeakageError, match="peek") as caught:
        guard.check(leaky, make_panel(), origins=[8])
    assert caught.value.columns == ("peek",)


def test_settings_that_scramble_nothing_are_refused() -> None:
    with pytest.raises(ValidationError, match="scramble"):
        LeakageSettings(scramble_scale=1.0, scramble_shift=0.0)
