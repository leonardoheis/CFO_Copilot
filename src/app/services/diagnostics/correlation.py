from collections.abc import Mapping, Sequence
from typing import Final

import numpy as np
import pandas as pd

from app.data.schema import MACRO_COLUMNS, POSITIVE_COLUMNS, RATIO_COLUMNS
from app.services.diagnostics.models import CorrelationSettings
from app.services.features.transforms import (
    SEASONAL_LAG,
    TargetVariable,
    trailing_revenue,
)

_PAIR_COLUMNS: Final = ["left", "right", "rho"]


def _yoy_change(panel: pd.DataFrame, column: str) -> pd.Series:
    values = panel[column]
    if column in POSITIVE_COLUMNS:
        # A defective non-positive value has no log; it becomes missing here.
        return pd.Series(np.log(values.where(values > 0)), index=panel.index).diff(
            SEASONAL_LAG
        )
    if column in RATIO_COLUMNS or column in MACRO_COLUMNS:
        return values.diff(SEASONAL_LAG)
    return values.diff(SEASONAL_LAG) / trailing_revenue(panel[TargetVariable.REVENUE])


def yoy_changes(panel: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Change against the same quarter a year earlier, relative to size.

    Returns:
        Per column: the log change if it must be positive, the plain change for
        ratios and macro series, the change over trailing revenue otherwise.
    """
    return pd.DataFrame({column: _yoy_change(panel, column) for column in columns})


def pooled_yoy_changes(
    panels: Mapping[str, pd.DataFrame], columns: Sequence[str]
) -> pd.DataFrame:
    """Stack every company's year-over-year changes.

    Returns:
        ``ticker, date`` and one column per requested column.
    """
    return pd.concat(
        [
            pd.concat([panel[["ticker", "date"]], yoy_changes(panel, columns)], axis=1)
            for panel in panels.values()
        ],
        ignore_index=True,
    )


class CorrelationAnalyzer:
    """Correlate year-over-year changes and list redundant pairs.

    Levels trend together over 20 years, so they correlate spuriously; changes
    do not.

    Usage::

        analyzer = container.correlation_analyzer()
        changes = pooled_yoy_changes(panels, columns)
        matrix = analyzer.matrix(changes[columns])
        redundant = analyzer.redundant_pairs(matrix)
    """

    def __init__(self, settings: CorrelationSettings) -> None:
        self._settings = settings

    @property
    def redundancy_threshold(self) -> float:
        return self._settings.redundancy_threshold

    def matrix(self, changes: pd.DataFrame) -> pd.DataFrame:
        """Correlate every pair of numeric columns.

        Returns:
            The square correlation matrix.
        """
        return changes.select_dtypes("number").corr(method=self._settings.method)

    def redundant_pairs(self, matrix: pd.DataFrame) -> pd.DataFrame:
        """List pairs whose correlation exceeds the redundancy threshold.

        Returns:
            ``left, right, rho``, strongest first; each pair once.
        """
        rows, columns = np.triu_indices(len(matrix), k=1)
        pairs = pd.DataFrame({
            "left": matrix.index[rows],
            "right": matrix.columns[columns],
            "rho": matrix.to_numpy()[rows, columns],
        })
        strong = pairs["rho"].abs() > self._settings.redundancy_threshold
        return (
            pairs
            .loc[strong, _PAIR_COLUMNS]
            .sort_values("rho", key=abs, ascending=False)
            .reset_index(drop=True)
        )
