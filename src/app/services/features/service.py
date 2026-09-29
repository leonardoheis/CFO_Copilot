from collections.abc import Mapping, Sequence

import pandas as pd

from app.services.features.builder import FeatureBuilder, FeatureGroup
from app.services.features.leakage import LookaheadGuard
from app.services.features.transforms import TargetArm, TargetTransformer


class FeatureService:
    """Assemble pooled feature datasets and prove they do not look ahead.

    Usage::

        service = container.feature_service()
        dataset = service.assemble(panels, horizon=2, arm=TargetArm.LOG_DIFF4)
        service.check_lookahead(panel, horizon=2, origins=[3, 8, 15])
    """

    def __init__(self, builder: FeatureBuilder, guard: LookaheadGuard) -> None:
        self._builder = builder
        self._guard = guard

    def _company_rows(
        self,
        panel: pd.DataFrame,
        transformer: TargetTransformer,
        regimes: pd.Series | None,
    ) -> pd.DataFrame:
        target = panel[self._builder.target_variable]
        features = self._builder.build(
            panel, horizon=transformer.horizon, regimes=regimes
        )
        return features.assign(
            target_level=target.shift(-transformer.horizon),
            y=transformer.make(target),
        )

    def assemble(
        self,
        panels: Mapping[str, pd.DataFrame],
        *,
        horizon: int,
        arm: TargetArm,
        regimes: pd.Series | None = None,
    ) -> pd.DataFrame:
        """Pool every company's origin rows with the arm's target for one horizon.

        Returns:
            All origin rows; ``y`` is NaN where the target is not yet known.
        """
        transformer = TargetTransformer(arm=arm, horizon=horizon)
        dataset = pd.concat(
            [
                self._company_rows(panel, transformer, regimes)
                for panel in panels.values()
            ],
            ignore_index=True,
        )
        if self._builder.includes(FeatureGroup.STATIC):
            dataset["sector"] = dataset["sector"].astype("category")
        return dataset

    def check_lookahead(
        self,
        panel: pd.DataFrame,
        *,
        horizon: int,
        origins: Sequence[int],
        regimes: pd.Series | None = None,
    ) -> None:
        """Fail when this service's builder reads quarters after an origin."""
        self._guard.check(
            lambda scrambled: self._builder.build(
                scrambled, horizon=horizon, regimes=regimes
            ),
            panel,
            origins=origins,
        )
