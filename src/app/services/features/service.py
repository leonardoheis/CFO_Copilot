from collections.abc import Mapping, Sequence

import pandas as pd

from app.services.features.builder import (
    FeatureBuilder,
    FeatureGroup,
    feature_groups_by_column,
)
from app.services.features.exceptions import UnsupportedArmError
from app.services.features.leakage import LookaheadGuard
from app.services.features.transforms import (
    TargetArm,
    TargetTransformer,
    TargetVariable,
    arms_for,
)


def training_rows(dataset: pd.DataFrame) -> pd.DataFrame:
    """Keep the rows a model can learn from: a known target and every feature.

    Returns:
        ``dataset`` without warm-up rows and without rows whose target is unknown.
    """
    features = [c for c in feature_groups_by_column() if c in dataset.columns]
    return dataset.dropna(subset=[*features, "y"])


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
        rows = features.assign(
            target_level=target.shift(-transformer.horizon),
            y=transformer.make(target, revenue=panel[TargetVariable.REVENUE]),
        )
        # Dropped only after the builder ran on the full history, so the first
        # listed quarter's lags still read the pre-listing financials.
        if "pre_listing" in panel.columns:
            rows = rows.loc[~panel["pre_listing"].astype(bool).to_numpy()]
        return rows

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

        Raises:
            UnsupportedArmError: The arm is not one of the target variable's.
        """
        supported = arms_for(self._builder.target_variable)
        if arm not in supported:
            raise UnsupportedArmError(
                variable=self._builder.target_variable.value,
                arm=arm.value,
                supported=tuple(member.value for member in supported),
            )
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

    def target_frame(
        self, panels: Mapping[str, pd.DataFrame], *, horizons: Sequence[int]
    ) -> pd.DataFrame:
        """Build the target of every arm the variable uses, at every horizon.

        Returns:
            One row per company-quarter, arm and horizon: ``ticker, date, arm,
            horizon, y``; ``y`` is NaN where it is not yet known.
        """
        variable = self._builder.target_variable
        return pd.concat(
            [
                pd.DataFrame({
                    "ticker": ticker,
                    "date": panel["date"],
                    "arm": arm.value,
                    "horizon": horizon,
                    "y": TargetTransformer(arm=arm, horizon=horizon).make(
                        panel[variable], revenue=panel[TargetVariable.REVENUE]
                    ),
                })
                for ticker, panel in panels.items()
                for arm in arms_for(variable)
                for horizon in horizons
            ],
            ignore_index=True,
        )

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
