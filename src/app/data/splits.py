import pandas as pd

from app.data.dates import normalize_datetime_index


def cumulative_split_factors(
    splits: pd.Series,
    index: pd.DatetimeIndex,
) -> pd.Series:
    """Return the future split factor for each date in ``index``.

    The factor converts historical per-share values and share counts to the
    current split-adjusted basis. Splits effective on the date itself are
    considered already effective and therefore are not included.

    Returns:
        A series of future split factors aligned to ``index``.
    """
    if splits.empty:
        return pd.Series(1.0, index=index)

    ordered = splits.sort_index().astype(float)
    ordered.index = normalize_datetime_index(ordered.index)
    ordered = ordered[~ordered.index.duplicated(keep="last")]
    cumulative = ordered.cumprod()
    applied_to_date = cumulative.reindex(index, method="ffill").fillna(1.0)
    return float(cumulative.iloc[-1]) / applied_to_date
