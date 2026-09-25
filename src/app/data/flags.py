from collections.abc import Mapping, Sequence
from datetime import date
from typing import Final

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.data.exceptions import ConsolidationError

BREAK_WINDOW_QUARTERS: Final = 4
MIN_OUTLIER_ROWS: Final = 16
_COVID_QUARTERS: Final = tuple(
    pd.to_datetime(["2020-06-30", "2020-09-30", "2020-12-31"])
)
_MARGIN_INPUTS: Final = ["gross_margin", "operating_margin", "net_margin"]
_YOY_LAG: Final = 4


def covid_flag(dates: pd.Series) -> pd.Series:
    return dates.isin(_COVID_QUARTERS)


def is_projected(dates: pd.Series, *, last_reported_quarter: date) -> pd.Series:
    return dates > pd.Timestamp(last_reported_quarter)


def structural_break_flag(
    dates: pd.Series, break_quarters: Sequence[date]
) -> pd.Series:
    """Flag each break quarter and the next three, where YoY spans the break.

    Returns:
        A boolean series aligned to ``dates``.
    """
    flagged = pd.Series(data=False, index=dates.index)
    for quarter in break_quarters:
        window_start = pd.Timestamp(quarter)
        window_end = window_start + pd.offsets.QuarterEnd(BREAK_WINDOW_QUARTERS - 1)
        flagged |= dates.between(window_start, window_end)
    return flagged


def outlier_flag(
    panel: pd.DataFrame, *, contamination: float = 0.03, seed: int = 42
) -> pd.Series:
    """Flag unusual quarters with an Isolation Forest; the flag removes nothing.

    Fitted on the whole history, so it depends on later quarters and must not
    be used as a model feature.

    Returns:
        A boolean series aligned to ``panel``; rows missing an input are False.
    """
    revenue = panel["revenue_usd_m"]
    revenue_yoy_growth = np.log(revenue.where(revenue > 0)).diff(_YOY_LAG)
    inputs = (
        panel[_MARGIN_INPUTS].assign(revenue_yoy_growth=revenue_yoy_growth).dropna()
    )
    flagged = pd.Series(data=False, index=panel.index)
    if len(inputs) < MIN_OUTLIER_ROWS:
        return flagged
    standardized = (inputs - inputs.mean()) / inputs.std()
    labels = IsolationForest(
        contamination=contamination, random_state=seed
    ).fit_predict(standardized)
    flagged.loc[inputs.index[labels == -1]] = True
    return flagged


def _flag_company(
    company: pd.DataFrame,
    break_quarters: Sequence[date],
    *,
    last_reported_quarter: date,
    contamination: float,
    seed: int,
) -> pd.DataFrame:
    return company.assign(
        covid=covid_flag(company["date"]),
        structural_break=structural_break_flag(company["date"], break_quarters),
        outlier_flag=outlier_flag(company, contamination=contamination, seed=seed),
        is_projected=is_projected(
            company["date"], last_reported_quarter=last_reported_quarter
        ),
    )


def add_flags(
    panel_long: pd.DataFrame,
    breaks: Mapping[str, Sequence[date]],
    *,
    last_reported_quarter: date,
    contamination: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Add the four NB00 flag columns company by company.

    Returns:
        ``panel_long`` with ``covid``, ``structural_break``, ``outlier_flag``
        and ``is_projected``, in the original row order.

    Raises:
        ConsolidationError: A break names a ticker that is not in the panel.
    """
    unknown = sorted(set(breaks) - set(panel_long["ticker"]))
    if unknown:
        unknown_list = ", ".join(unknown)
        message = f"structural breaks for tickers not in the panel: {unknown_list}"
        raise ConsolidationError(message)
    return pd.concat([
        _flag_company(
            company,
            breaks.get(str(ticker), ()),
            last_reported_quarter=last_reported_quarter,
            contamination=contamination,
            seed=seed,
        )
        for ticker, company in panel_long.groupby("ticker", sort=False)
    ]).loc[panel_long.index]
