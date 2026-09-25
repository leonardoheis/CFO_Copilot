from typing import Final

import pandas as pd

from app.data.schema import FINANCIAL_COLUMNS

CHECKED_COLUMNS: Final = (
    *FINANCIAL_COLUMNS,
    "stock_price_usd",
    "dividend_yield",
    "market_cap_usd_m",
    "pe_ratio",
)
_PRE_LISTING_COLUMNS: Final = (
    "stock_price_usd",
    "dividend_yield",
    "market_cap_usd_m",
    "pe_ratio",
    "eps",
)
_FILING_COLUMNS: Final = (*FINANCIAL_COLUMNS, "market_cap_usd_m")


def _reasons(
    column: str, company: pd.DataFrame, first_price_date: pd.Timestamp
) -> pd.Series:
    eps = company["eps"]
    rules = (
        ("pe_undefined_by_rule", column == "pe_ratio", eps.isna() | (eps <= 0)),
        (
            "pre_listing",
            column in _PRE_LISTING_COLUMNS,
            company["date"] < first_price_date,
        ),
        ("no_filing_data", column in _FILING_COLUMNS, company["revenue_usd_m"].isna()),
    )
    reason = pd.Series("unexplained", index=company.index)
    for name, applies, mask in reversed(rules):
        reason = reason.mask(mask & applies, name)
    return reason


def _company_ledger(company: pd.DataFrame) -> pd.DataFrame:
    first_price_date = company.loc[company["stock_price_usd"].notna(), "date"].min()
    frames = []
    for column in CHECKED_COLUMNS:
        missing = company[column].isna()
        reasons = _reasons(column, company, first_price_date)
        frames.append(
            company.loc[missing, ["ticker", "date"]].assign(
                column=column, reason=reasons[missing]
            )
        )
    return pd.concat(frames)


def missing_value_ledger(panel_long: pd.DataFrame) -> pd.DataFrame:
    """List every NaN cell with the reason it is missing.

    Rules are ordered and the first that applies wins, so the loop in
    ``_reasons`` runs over them reversed and earlier rules overwrite later ones.

    Returns:
        One row per NaN cell; ``unexplained`` rows need review or a waiver.
    """
    return pd.concat(
        [
            _company_ledger(company)
            for _, company in panel_long.groupby("ticker", sort=True)
        ],
        ignore_index=True,
    )
