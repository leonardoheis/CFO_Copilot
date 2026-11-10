from collections.abc import Mapping
from typing import Final, NamedTuple

import pandas as pd

from app.domain import Forecaster, TargetVariable
from app.services.evaluation.baselines import Baseline, baseline_levels
from app.services.evaluation.conformal import rolling_half_widths
from app.services.evaluation.leakage import LABEL_COLUMNS, check_no_look_ahead
from app.services.evaluation.metrics import (
    IntervalMetricTables,
    PointMetricTables,
    in_sample_scale,
    interval_metric_tables,
    point_metric_tables,
)
from app.services.evaluation.models import (
    EvaluationRecord,
    EvaluationSettings,
    ForecastTask,
    RunProvenance,
)
from app.services.evaluation.scale import on_error_scale, reconstruct_on_error_scale
from app.services.evaluation.splits import Split, protocol_a_splits

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

    task: ForecastTask
    baseline_to_beat: Baseline
    # One row per test row, missing predictions included as NaN.
    scored: pd.DataFrame
    # One row per test row and interval level: lower_scaled, upper_scaled.
    intervals: pd.DataFrame
    metrics: PointMetricTables
    interval_metrics: IntervalMetricTables

    def records(self, *, model: str, provenance: RunProvenance) -> pd.DataFrame:
        """Validate every scored row at every level as an ``EvaluationRecord``.

        Returns:
            One record per test row and interval level, as a frame.
        """
        shared = {
            "model": model,
            "variable": self.task.variable,
            "arm": self.task.arm,
            "protocol": "A",
            "horizon": self.task.horizon,
            **provenance.model_dump(),
        }
        rows = self.scored.drop(columns=["baseline_scaled", "mase_scale"]).merge(
            self.intervals, on=KEYS
        )
        return pd.DataFrame([
            EvaluationRecord.model_validate(row | shared).model_dump()
            for row in rows.to_dict("records")
        ])


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
            for baseline in Baseline
        },
    )


def _mase_scales(
    dataset: pd.DataFrame, rows: pd.DataFrame, splits: tuple[Split, ...]
) -> pd.Series:
    trained = dataset[KEYS].merge(rows, on=KEYS)
    seasonal_naive_errors = trained.assign(
        error=trained[f"{Baseline.SEASONAL_NAIVE}_scaled"] - trained["y_scaled"]
    )
    scales: pd.Series = pd.concat(
        {
            split.origin: in_sample_scale(seasonal_naive_errors, split.origin)
            for split in splits
        },
        names=["origin_date", "ticker"],
    )
    return scales


def _intervals(
    forecasts: pd.DataFrame,
    reported_origins: list[pd.Timestamp],
    settings: EvaluationSettings,
) -> pd.DataFrame:
    # Errors over each company's own scale, so one quantile fits a stable and a
    # volatile company alike (spec R8, Lei et al. 2018).
    normalized = forecasts.assign(
        error=(forecasts["y_hat_scaled"] - forecasts["y_scaled"])
        / forecasts["mase_scale"]
    )
    reported = forecasts[forecasts["origin_date"].isin(reported_origins)]
    by_level = []
    for level in settings.interval_levels:
        ratio = rolling_half_widths(
            normalized,
            reported_origins,
            level=level,
            window=settings.calibration_window,
            step=settings.aci_step,
        )
        half_width = reported["origin_date"].map(ratio) * reported["mase_scale"]
        by_level.append(
            reported[KEYS].assign(
                level=level,
                lower_scaled=reported["y_hat_scaled"] - half_width,
                upper_scaled=reported["y_hat_scaled"] + half_width,
            )
        )
    return pd.concat(by_level, ignore_index=True)


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
        forecaster is refit at every origin and never sees a test label. It is
        also refit at the earlier origins whose errors calibrate the first
        reported interval; those are never scored.

        Returns:
            The baseline to beat, the scored test rows, their intervals and
            their metric tables.
        """
        settings = self._settings
        splits = protocol_a_splits(
            dataset,
            settings.n_origins + settings.calibration_window + task.horizon - 1,
        )
        reported_origins = [split.origin for split in splits[-settings.n_origins :]]
        predictions = pd.concat([
            _predictions_at(forecaster, dataset, split) for split in splits
        ])
        rows = pd.concat(
            [_company_rows(panel, predictions, task) for panel in panels.values()],
            ignore_index=True,
        )
        forecasts = predictions[KEYS].merge(rows, on=KEYS, how="left")
        forecasts["mase_scale"] = (
            _mase_scales(dataset, rows, splits)
            .reindex(pd.MultiIndex.from_frame(forecasts[["origin_date", "ticker"]]))
            .to_numpy()
        )
        scored = forecasts[forecasts["origin_date"].isin(reported_origins)].reset_index(
            drop=True
        )
        # Every baseline competes (spec R6): naive beats both seasonal ones on
        # the margin-like targets at h = 1. Baseline(...) because mypy 1.15
        # (the nbqa hook) types a StrEnum's members as str.
        baseline_to_beat = Baseline(
            min(
                Baseline,
                key=lambda baseline: float(
                    (scored[f"{baseline}_scaled"] - scored["y_scaled"]).abs().mean()
                ),
            )
        )
        scored["baseline_scaled"] = scored[f"{baseline_to_beat}_scaled"]
        scored = scored[SCORED_COLUMNS]
        intervals = _intervals(forecasts, reported_origins, settings)
        return Evaluation(
            task=task,
            baseline_to_beat=baseline_to_beat,
            scored=scored,
            intervals=intervals,
            metrics=point_metric_tables(scored, variable=task.variable),
            interval_metrics=interval_metric_tables(
                intervals.merge(scored[[*KEYS, "sector", "y_scaled"]], on=KEYS)
            ),
        )
