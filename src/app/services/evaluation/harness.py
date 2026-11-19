from collections.abc import Callable, Mapping, Sequence
from typing import Final, NamedTuple

import numpy as np
import pandas as pd

from app.domain import EvaluationProtocol, Forecaster, TargetVariable
from app.services.evaluation.baselines import Baseline, baseline_levels
from app.services.evaluation.conformal import jackknife_half_widths, rolling_half_widths
from app.services.evaluation.leakage import (
    LABEL_COLUMNS,
    check_held_out,
    check_no_look_ahead,
)
from app.services.evaluation.metrics import (
    IntervalMetricTables,
    PointMetricTables,
    diebold_mariano,
    in_sample_scale,
    interval_metric_tables,
    point_metric_tables,
)
from app.services.evaluation.models import (
    DieboldMarianoTest,
    EvaluationRecord,
    EvaluationSettings,
    ForecastTask,
    RunProvenance,
)
from app.services.evaluation.scale import (
    credibility_weighted_scale,
    on_error_scale,
    reconstruct_on_error_scale,
    sector_peer_scales,
)
from app.services.evaluation.splits import (
    HeldOutCompany,
    Split,
    protocol_a_splits,
    protocol_b_splits,
    truncate_history,
)
from app.services.features.transforms import SEASONAL_LAG, TargetFamily, target_family

KEYS: Final = ["ticker", "origin_date"]
# Computed in NB01 from each company's full history, which a new company does
# not have, so Protocol B models never see it (spec R3).
FULL_HISTORY_COLUMNS: Final = ["seasonality_regime"]
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
    """A forecaster scored on one target, arm and horizon, under one protocol."""

    task: ForecastTask
    baseline_to_beat: Baseline
    # One row per test row, missing predictions included as NaN.
    scored: pd.DataFrame
    # One row per test row and interval level: lower_scaled, upper_scaled.
    intervals: pd.DataFrame
    metrics: PointMetricTables
    interval_metrics: IntervalMetricTables
    significance: DieboldMarianoTest
    protocol: EvaluationProtocol = "A"
    # Protocol B only: quarters of the held-out company's history, None for all.
    history: int | None = None

    def records(self, *, model: str, provenance: RunProvenance) -> pd.DataFrame:
        """Validate every scored row at every level as an ``EvaluationRecord``.

        Returns:
            One record per test row and interval level, as a frame.
        """
        shared: dict[str, object] = {
            "model": model,
            "variable": self.task.variable,
            "arm": self.task.arm,
            "protocol": self.protocol,
            "history": self.history,
            "horizon": self.task.horizon,
            **provenance.model_dump(),
        }
        rows = self.scored.drop(columns=["baseline_scaled", "mase_scale"]).merge(
            self.intervals, on=KEYS, how="inner", validate="one_to_many"
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
    panel: pd.DataFrame,
    predictions: pd.DataFrame,
    task: ForecastTask,
    history: int | None = None,
) -> pd.DataFrame:
    own = predictions[predictions["ticker"].eq(panel["ticker"].iloc[0])]
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
                    history=history,
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


def _normalized_errors(forecasts: pd.DataFrame) -> pd.DataFrame:
    # Errors over each company's own scale, so one quantile fits a stable and a
    # volatile company alike (spec R8, Lei et al. 2018). A zero scale (an
    # error-free history) gives no ratio, so that error does not calibrate.
    scale = forecasts["mase_scale"].where(forecasts["mase_scale"].gt(0))
    return forecasts.assign(
        error=(forecasts["y_hat_scaled"] - forecasts["y_scaled"]) / scale
    )


def _bounds(reported: pd.DataFrame, level: float, ratio: pd.Series) -> pd.DataFrame:
    half_width = ratio * reported["mase_scale"]
    return reported[KEYS].assign(
        level=level,
        lower_scaled=reported["y_hat_scaled"] - half_width,
        upper_scaled=reported["y_hat_scaled"] + half_width,
    )


def _intervals(
    forecasts: pd.DataFrame,
    reported_origins: list[pd.Timestamp],
    settings: EvaluationSettings,
) -> pd.DataFrame:
    normalized = _normalized_errors(forecasts)
    reported = forecasts[forecasts["origin_date"].isin(reported_origins)]
    by_level: list[pd.DataFrame] = []
    for level in settings.interval_levels:
        ratio = rolling_half_widths(
            normalized,
            reported_origins,
            level=level,
            window=settings.calibration_window,
            step=settings.aci_step,
        )
        by_level.append(_bounds(reported, level, reported["origin_date"].map(ratio)))
    return pd.concat(by_level, ignore_index=True)


def _jackknife_intervals(
    forecasts: pd.DataFrame,
    reported_origins: list[pd.Timestamp],
    settings: EvaluationSettings,
) -> pd.DataFrame:
    normalized = _normalized_errors(forecasts)
    reported = forecasts[forecasts["origin_date"].isin(reported_origins)]
    reported_keys = pd.MultiIndex.from_frame(reported[KEYS])
    by_level: list[pd.DataFrame] = []
    for level in settings.interval_levels:
        ratio = jackknife_half_widths(
            normalized,
            reported_origins,
            level=level,
            window=settings.calibration_window,
            step=settings.aci_step,
        )
        row_ratio = pd.Series(
            ratio.reindex(reported_keys).to_numpy(), index=reported.index
        )
        by_level.append(_bounds(reported, level, row_ratio))
    return pd.concat(by_level, ignore_index=True)


def _evaluation(
    forecasts: pd.DataFrame,
    intervals: pd.DataFrame,
    reported_origins: list[pd.Timestamp],
    task: ForecastTask,
) -> Evaluation:
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
    return Evaluation(
        task=task,
        baseline_to_beat=baseline_to_beat,
        scored=scored,
        intervals=intervals,
        metrics=point_metric_tables(scored, variable=task.variable),
        interval_metrics=interval_metric_tables(
            intervals.merge(
                scored[[*KEYS, "sector", "y_scaled"]],
                on=KEYS,
                how="inner",
                validate="many_to_one",
            )
        ),
        significance=diebold_mariano(scored, horizon=task.horizon),
    )


def _held_out_predictions(
    forecaster_factory: Callable[[], Forecaster],
    features: pd.DataFrame,
    held_out_companies: tuple[HeldOutCompany, ...],
    histories: Sequence[int | None],
) -> list[pd.DataFrame]:
    """Each held-out row's prediction at each history, one per entry of ``histories``.

    A model's training rows do not depend on the held-out company's history, so
    one fit per company and origin serves every history.

    Returns:
        ``ticker, origin_date, y_hat`` per history, in the order of ``histories``.
    """
    by_history: list[list[pd.DataFrame]] = [[] for _ in histories]
    for company in held_out_companies:
        for split in company.splits:
            if not split.test.any():
                continue
            train = features[split.train]
            test = features[split.test].drop(columns=list(LABEL_COLUMNS))
            check_no_look_ahead(train, test, split.origin)
            check_held_out(train, test, split.origin)
            model = forecaster_factory().fit(train)
            for predictions, history in zip(by_history, histories, strict=True):
                shown = test if history is None else truncate_history(test, history)
                y_hat = model.predict(shown, history=history)["y_hat"]
                predictions.append(test[KEYS].assign(y_hat=y_hat.reindex(test.index)))
    return [pd.concat(predictions, ignore_index=True) for predictions in by_history]


def _own_scales(
    rows: pd.DataFrame, positions: np.ndarray, task: ForecastTask, history: int | None
) -> tuple[np.ndarray, np.ndarray]:
    """Seasonal-naive MAE at each origin position, from errors inside the history.

    An error counts once its target is known by the origin and every quarter
    it reads lies in the last ``history`` quarters: last year's quarter for
    the forecast and, for a signed target, the four quarters of revenue that
    scale it (spec R5).

    Returns:
        The scale and the number of errors it averages, per position.
    """
    absolute_errors = (
        (rows[f"{Baseline.SEASONAL_NAIVE}_scaled"] - rows["y_scaled"]).abs().to_numpy()
    )
    defined = ~np.isnan(absolute_errors)
    error_sums = np.concatenate([
        [0.0],
        np.cumsum(np.where(defined, absolute_errors, 0.0)),
    ])
    error_counts = np.concatenate([[0], np.cumsum(defined)])
    lookback = SEASONAL_LAG - task.horizon
    if target_family(task.variable) is TargetFamily.SIGNED:
        lookback = max(lookback, SEASONAL_LAG - 1)
    # Errors from positions first to end - 1: targets known, inputs kept.
    end = np.maximum(positions - task.horizon + 1, 0)
    first = (
        np.zeros_like(positions)
        if history is None
        else np.minimum(np.maximum(positions - history + 1 + lookback, 0), end)
    )
    counts = error_counts[end] - error_counts[first]
    sums = error_sums[end] - error_sums[first]
    return np.where(counts > 0, sums / np.maximum(counts, 1), np.nan), counts


def _held_out_rows(
    panel: pd.DataFrame,
    predictions: pd.DataFrame,
    task: ForecastTask,
    history: int | None,
) -> pd.DataFrame:
    """One held-out company's rows at its origins, as if it had ``history`` quarters.

    A value at an origin reads at most its last five quarters, so the panel is
    scored once. Only drift, which runs from the first quarter kept, and the
    MASE scale follow the history, as for a company with that much of it.

    Returns:
        One row per predicted origin, with its ``mase_scale`` and the number
        of seasonal-naive errors it averages, ``scale_errors``.
    """
    rows = _company_rows(panel, predictions, task, history)
    positions = np.flatnonzero(rows["origin_date"].isin(predictions["origin_date"]))
    scales, counts = _own_scales(rows, positions, task, history)
    return (
        rows
        .iloc[positions]
        .assign(mase_scale=scales, scale_errors=counts)
        .reset_index(drop=True)
    )


def _held_out_forecasts(
    predictions_by_history: list[pd.DataFrame],
    histories: Sequence[int | None],
    panels: Mapping[str, pd.DataFrame],
    task: ForecastTask,
) -> list[pd.DataFrame]:
    """Each history's held-out rows, with their sector peers' scale beside them.

    Returns:
        One frame per entry of ``histories``, which must end with all of it.
    """
    by_history: list[pd.DataFrame] = []
    for history, predictions in zip(histories, predictions_by_history, strict=True):
        companies = [
            _held_out_rows(panels[str(ticker)], company, task, history)
            for ticker, company in predictions.groupby("ticker")
        ]
        by_history.append(pd.concat(companies, ignore_index=True))
    # Peers are known companies, so their scales use their full histories.
    peer_scale = sector_peer_scales(by_history[-1])
    return [
        forecasts.assign(
            peer_scale=peer_scale.reindex(
                pd.MultiIndex.from_frame(forecasts[KEYS])
            ).to_numpy()
        )
        for forecasts in by_history
    ]


def _new_company_evaluation(
    forecasts: pd.DataFrame,
    reported_origins: list[pd.Timestamp],
    task: ForecastTask,
    settings: EvaluationSettings,
    history: int | None,
) -> Evaluation:
    # A new company's own scale can rest on one error, even one of zero, so
    # MASE and the interval both use the blend with its peers (spec R7, R8).
    blended_scale = credibility_weighted_scale(
        forecasts["mase_scale"],
        forecasts["scale_errors"],
        forecasts["peer_scale"],
        prior_errors=settings.scale_prior_errors,
    )
    scaled = forecasts.assign(mase_scale=blended_scale)
    intervals = _jackknife_intervals(scaled, reported_origins, settings)
    evaluation = _evaluation(scaled, intervals, reported_origins, task)
    return evaluation._replace(protocol="B", history=history)


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
            The baseline to beat, the scored test rows, their intervals, their
            metric tables and the Diebold-Mariano test against the baseline.
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
        return _evaluation(
            forecasts,
            _intervals(forecasts, reported_origins, settings),
            reported_origins,
            task,
        )

    def evaluate_new_companies(
        self,
        forecaster_factory: Callable[[], Forecaster],
        dataset: pd.DataFrame,
        *,
        panels: Mapping[str, pd.DataFrame],
        task: ForecastTask,
    ) -> tuple[Evaluation, ...]:
        """Score each company as new using an unfitted forecaster per fold.

        The factory must create a fresh model for each company and origin.
        Each model is fit without its held-out company. At prediction time it
        receives features cut to that company's own history, once per
        configured length and once for its full history. The interval uses
        the jackknife over the other companies' errors at the same history,
        scaled by its own error size blended with its sector peers' (spec R3, R8).
        ``seasonality_regime`` is dropped: it is computed from full histories.

        Returns:
            One evaluation per history, shortest first, the full history last.
        """
        settings = self._settings
        histories: tuple[int | None, ...] = (*settings.histories, None)
        features = dataset.drop(columns=FULL_HISTORY_COLUMNS, errors="ignore")
        held_out_companies = protocol_b_splits(
            features,
            settings.n_origins + settings.calibration_window + task.horizon - 1,
        )
        reported_origins = [
            split.origin
            for split in held_out_companies[0].splits[-settings.n_origins :]
        ]
        predictions_by_history = _held_out_predictions(
            forecaster_factory, features, held_out_companies, histories
        )
        forecasts_by_history = _held_out_forecasts(
            predictions_by_history, histories, panels, task
        )
        return tuple(
            _new_company_evaluation(
                forecasts, reported_origins, task, settings, history
            )
            for history, forecasts in zip(histories, forecasts_by_history, strict=True)
        )
