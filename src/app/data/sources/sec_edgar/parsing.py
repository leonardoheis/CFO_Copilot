"""Derive panel columns from raw SEC EDGAR concept series.

Pure functions: no HTTP and no knowledge of how the raw frame was fetched.
"""

import pandas as pd

from app.data.schema import FINANCIAL_COLUMNS, MILLIONS_DIVISOR
from app.data.splits import cumulative_split_factors


def merge_raw_financial_frames(
    preferred: pd.DataFrame,
    fallback: pd.DataFrame,
) -> pd.DataFrame:
    """Overlay two raw concept frames, preferring non-null values from the first.

    Returns:
        A frame with the same columns, gaps in ``preferred`` filled from ``fallback``.
    """
    merged = preferred.copy()
    for column in preferred.columns:
        if column == "date":
            continue
        merged[column] = preferred[column].combine_first(fallback[column])
    return merged


def split_factors_for_filing_dates(
    filed_dates: pd.Series,
    splits: pd.Series | None,
) -> pd.Series:
    """Scale reported per-share values onto the current share basis.

    Returns:
        A series of cumulative split factors aligned to the filing dates.
    """
    if splits is None:
        return pd.Series(1.0, index=filed_dates.index)
    parsed_dates = pd.to_datetime(filed_dates.replace("", None))
    valid = parsed_dates.notna()
    factors = pd.Series(1.0, index=filed_dates.index)
    if valid.any():
        factors.loc[valid] = cumulative_split_factors(
            splits,
            pd.DatetimeIndex(parsed_dates.loc[valid]),
        ).to_numpy()
    return factors


def financial_panel_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Convert raw us-gaap concept series into the financial panel columns.

    Returns:
        A frame of the panel's financial columns plus ``shares_outstanding``.
    """
    revenue = raw["revenue"]
    cogs = raw["cogs"]
    gross_profit = revenue - cogs
    operating_income = raw["operating_income"]
    net_income = raw["net_income"]
    safe_revenue = revenue.where(revenue != 0)
    reported_opex = raw["costs_and_expenses"] - cogs
    derived_opex = revenue - operating_income - cogs
    opex = reported_opex.where(reported_opex.notna(), derived_opex)

    panel = pd.DataFrame(
        {
            "date": raw["date"],
            "revenue_usd_m": revenue / MILLIONS_DIVISOR,
            "gross_profit_usd_m": gross_profit / MILLIONS_DIVISOR,
            "opex_usd_m": opex / MILLIONS_DIVISOR,
            "operating_income_usd_m": operating_income / MILLIONS_DIVISOR,
            "ebitda_usd_m": (operating_income + raw["dep_amort"]) / MILLIONS_DIVISOR,
            "net_income_usd_m": net_income / MILLIONS_DIVISOR,
            "free_cash_flow_usd_m": (raw["operating_cash_flow"] - raw["capex"])
            / MILLIONS_DIVISOR,
            "gross_margin": gross_profit / safe_revenue,
            "operating_margin": operating_income / safe_revenue,
            "net_margin": net_income / safe_revenue,
            "eps": raw["eps"],
            "shares_outstanding": raw["shares_outstanding"],
        },
    )
    return panel.loc[:, ["date", *FINANCIAL_COLUMNS, "shares_outstanding"]]
