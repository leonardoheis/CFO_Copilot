"""Derive panel columns from raw SEC EDGAR concept series.

Pure functions: no HTTP and no knowledge of how the raw frame was fetched.
"""

import logging
from typing import Final, cast

import pandas as pd

from app.data.exceptions import MalformedPayloadError
from app.data.schema import FINANCIAL_COLUMNS, MILLIONS_DIVISOR, PROVENANCE_COLUMNS
from app.data.splits import cumulative_split_factors
from app.data.xbrl import XbrlFact

MIN_SHARE_COUNT_FRACTION_OF_MEDIAN: Final = 0.01
logger = logging.getLogger(__name__)

type JsonObject = dict[str, object]


def concept_facts(company_facts: JsonObject, tag: str, unit: str) -> list[XbrlFact]:
    """Read one us-gaap tag's facts in one unit from a companyfacts payload.

    Returns:
        The facts, or an empty list when the company never filed the tag or unit.

    Raises:
        MalformedPayloadError: The unit is present but is not a list of facts.
    """
    facts = cast("JsonObject", company_facts.get("facts", {}))
    us_gaap = cast("JsonObject", facts.get("us-gaap", {}))
    concept = cast("JsonObject", us_gaap.get(tag, {}))
    units = cast("JsonObject", concept.get("units", {}))
    unit_facts = units.get(unit, [])
    if not isinstance(unit_facts, list):
        msg = f"SEC companyfacts {tag} [{unit}] is not a list of facts"
        raise MalformedPayloadError(msg)
    return cast("list[XbrlFact]", unit_facts)


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


def implied_shares_from_earnings(
    net_income: pd.Series,
    eps: pd.Series,
) -> pd.Series:
    """Recover a diluted share count from net income and diluted EPS.

    A last-resort fallback for quarters where a filer reports no share-count
    fact at all. Because ``eps`` is already split-adjusted, the quotient
    ``net income / EPS`` lands on the current split-adjusted share basis,
    matching the primary shares chain. Zero EPS yields no estimate.

    Returns:
        Implied shares outstanding, NaN where EPS is zero or missing.
    """
    safe_eps = eps.where(eps != 0)
    return net_income / safe_eps


def without_implausible_counts(values: pd.Series, cik: str) -> pd.Series:
    """Drop share counts that are non-positive or far below the company's median.

    Returns:
        The series with implausible counts replaced by NaN.
    """
    # Filers occasionally tag a count in thousands or millions (TXN 2009-Q3:
    # 1,268 for 1,268 million) and the API does not rescale it.
    positive_median = values[values > 0].median()
    implausible = values.notna() & (
        (values <= 0) | (values < MIN_SHARE_COUNT_FRACTION_OF_MEDIAN * positive_median)
    )
    if implausible.any():
        logger.warning(
            "Discarding %d non-positive or mis-scaled share counts for CIK %s",
            int(implausible.sum()),
            cik,
        )
    return values.where(~implausible)


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
            **{column: raw[column] for column in PROVENANCE_COLUMNS},
        },
    )
    return panel.loc[
        :,
        ["date", *FINANCIAL_COLUMNS, "shares_outstanding", *PROVENANCE_COLUMNS],
    ]
