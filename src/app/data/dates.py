from datetime import date, timedelta

import pandas as pd


def quarter_end_dates(start: date, end: date) -> list[date]:
    periods = pd.date_range(start=start, end=end, freq="QE")
    return [period.date() for period in periods]


def nearest_quarter_end(value: date, tolerance_days: int = 15) -> date:
    """Return the nearest calendar quarter end within the allowed tolerance.

    Returns:
        The nearest calendar quarter-end date.

    Raises:
        ValueError: If no quarter end is within ``tolerance_days``.
    """
    timestamp = pd.Timestamp(value)
    quarter_end = timestamp.to_period("Q").end_time.normalize()
    candidates = (
        quarter_end - pd.offsets.QuarterEnd(1),
        quarter_end,
        quarter_end + pd.offsets.QuarterEnd(1),
    )
    nearest = min(candidates, key=lambda candidate: abs(candidate - timestamp))
    if abs(nearest - timestamp).days > tolerance_days:
        msg = f"{value} is not near a calendar quarter end"
        raise ValueError(msg)
    return nearest.date()


def normalize_datetime_index(index: pd.Index) -> pd.DatetimeIndex:
    datetime_index = pd.to_datetime(index)
    if datetime_index.tz is not None:
        return datetime_index.tz_convert(None)
    return datetime_index


def align_series_to_quarters(
    series: pd.Series,
    quarter_dates: list[date],
) -> pd.Series:
    if series.empty:
        return pd.Series([float("nan")] * len(quarter_dates), index=quarter_dates)

    normalized = series.sort_index()
    normalized.index = normalize_datetime_index(normalized.index)
    quarterly = normalized.resample("QE").last()
    quarter_index = pd.DatetimeIndex(quarter_dates)
    aligned = quarterly.reindex(quarter_index)
    aligned.index = pd.Index(quarter_dates, name="date")
    return aligned


def inclusive_history_end(end: date) -> date:
    return end + timedelta(days=1)
