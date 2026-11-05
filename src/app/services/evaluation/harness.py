from collections.abc import Mapping
from typing import Final, NamedTuple

import pandas as pd

from app.domain import Forecaster, TargetVariable
from app.services.evaluation.baselines import Baseline, baseline_levels
from app.services.evaluation.leakage import LABEL_COLUMNS, check_no_look_ahead
from app.services.evaluation.metrics import (
    PointMetricTables,
    in_sample_scale,
    point_metric_tables,
)
from app.services.evaluation.models import EvaluationSettings, ForecastTask
from app.services.evaluation.scale import on_error_scale, reconstruct_on_error_scale
from app.services.evaluation.splits import Split, protocol_a_splits

# The candidates for the baseline to beat (spec R6).
SEASONAL_BASELINES: Final = (Baseline.SEASONAL_NAIVE, Baseline.SEASONAL_NAIVE_GROWTH)
KEYS: Final = ["ticker", "origin_date"]
SCORED_COLUMNS: Final = [
    "ticker",
    "sector",
    "origin_date",
    "target_date",
    "y_level",
    "y_hat_level",
    "y_scaled",
    "y_hat_scaled",
    "baseline_scaled",
    "mase_scale",
]


class Evaluation(NamedTuple):
    """A forecaster scored on one target, arm and horizon."""

    baseline_to_beat: Baseline
    # One row per test row, missing predictions included as NaN.
    scored: pd.DataFrame
    metrics: PointMetricTables


def _predictions_at(
    forecaster: Forecaster, dataset: pd.DataFrame, split: Split
) -> pd.DataFrame:
    train = dataset[split.train]
    test = dataset[split.test].drop(columns=list(LABEL_COLUMNS))
    check_no_look_ahead(train, test, split.origin)
    y_hat = forecaster.fit(train).predict(test)["y_hat"]
    return test[KEYS].assign(y_hat=y_hat.reindex(test.index))


def _company_rows(
    panel: pd.DataFrame, predictions: pd.DataFrame, task: ForecastTask
) -> pd.DataFrame:
    own = predictions[predictions["ticker"] == panel["ticker"].iloc[0]]
    rows = reconstruct_on_error_scale(
        panel,
        variable=task.variable,
        arm=task.arm,
        horizon=task.horizon,
        prediction=pd.Series(own["y_hat"].to_numpy(), index=own["origin_date"]),
    )
    return rows.assign(
        sector=panel["sector"],
        target_date=panel["date"] + pd.offsets.QuarterEnd(task.horizon),
        **{
            f"{baseline}_scaled": on_error_scale(
                task.variable,
                baseline_levels(
                    panel,
                    variable=task.variable,
                    horizon=task.horizon,
                    baseline=baseline,
                ),
                panel[TargetVariable.REVENUE],
            )
            for baseline in SEASONAL_BASELINES
        },
    )


class EvaluationHarness:
    """Score every forecaster on the same rows, scale, baselines and metrics.

    Usage::

        harness = container.evaluation_harness()
        task = ForecastTask(variable=variable, arm=TargetArm.LOG_DIFF4, horizon=1)
        evaluation = harness.evaluate(forecaster, dataset, panels=panels, task=task)
    """

    def __init__(self, settings: EvaluationSettings) -> None:
        self._settings = settings

    def evaluate(
        self,
        forecaster: Forecaster,
        dataset: pd.DataFrame,
        *,
        panels: Mapping[str, pd.DataFrame],
        task: ForecastTask,
    ) -> Evaluation:
        """Score ``forecaster`` under Protocol A at its last labelled origins.

        ``dataset`` is the feature dataset of the task's arm and horizon;
        ``panels`` are the companies' quarterly panels, keyed by ticker. The
        forecaster is refit at every origin and never sees a test label.

        Returns:
            The baseline to beat, the scored test rows and their metric tables.
        """
        splits = protocol_a_splits(dataset, self._settings.n_origins)
        predictions = pd.concat([
            _predictions_at(forecaster, dataset, split) for split in splits
        ])
        rows = pd.concat(
            [_company_rows(panel, predictions, task) for panel in panels.values()],
            ignore_index=True,
        )
        trained = dataset[KEYS].merge(rows, on=KEYS)
        seasonal_naive_errors = trained.assign(
            error=trained[f"{Baseline.SEASONAL_NAIVE}_scaled"] - trained["y_scaled"]
        )
        scales = pd.concat(
            {
                split.origin: in_sample_scale(seasonal_naive_errors, split.origin)
                for split in splits
            },
            names=["origin_date", "ticker"],
        )
        scored = predictions[KEYS].merge(rows, on=KEYS, how="left")
        scored["mase_scale"] = scales.reindex(
            pd.MultiIndex.from_frame(scored[["origin_date", "ticker"]])
        ).to_numpy()
        baseline_to_beat = min(
            SEASONAL_BASELINES,
            key=lambda baseline: float(
                (scored[f"{baseline}_scaled"] - scored["y_scaled"]).abs().mean()
            ),
        )
        scored["baseline_scaled"] = scored[f"{baseline_to_beat}_scaled"]
        scored = scored[SCORED_COLUMNS]
        return Evaluation(
            baseline_to_beat=baseline_to_beat,
            scored=scored,
            metrics=point_metric_tables(scored, variable=task.variable),
        )
