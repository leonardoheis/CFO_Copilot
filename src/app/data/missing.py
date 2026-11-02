from typing import Final

import pandas as pd

from app.data.companies import CompanyPanelMetadata, CompanyRegistry
from app.data.flags import pre_listing_flag
from app.data.schema import COMPANY_VALUE_COLUMNS, FINANCIAL_COLUMNS

_PRE_LISTING_COLUMNS: Final = (
    "stock_price_usd",
    "dividend_yield",
    "market_cap_usd_m",
    "pe_ratio",
    "eps",
)
_FILING_COLUMNS: Final = (*FINANCIAL_COLUMNS, "market_cap_usd_m")


def _reasons(
    column: str,
    company: pd.DataFrame,
    pre_listing_rows: pd.Series,
    declared_reason: str | None,
    withheld_rows: pd.Series,
) -> pd.Series:
    eps = company["eps"]
    every_row = pd.Series(data=True, index=company.index)
    rules = (
        (str(declared_reason), declared_reason is not None, every_row),
        ("withheld_quarter", column in FINANCIAL_COLUMNS, withheld_rows),
        ("pe_undefined_by_rule", column == "pe_ratio", eps.isna() | (eps <= 0)),
        (
            "pre_listing",
            column in _PRE_LISTING_COLUMNS,
            pre_listing_rows,
        ),
        ("no_filing_data", column in _FILING_COLUMNS, company["revenue_usd_m"].isna()),
    )
    reason = pd.Series("unexplained", index=company.index)
    for name, applies, mask in reversed(rules):
        reason = reason.mask(mask & applies, name)
    return reason


def _company_ledger(
    company: pd.DataFrame, metadata: CompanyPanelMetadata
) -> pd.DataFrame:
    declared_reasons = metadata.declared_empty_columns()
    pre_listing_rows = pre_listing_flag(company)
    withheld_rows = pd.to_datetime(company["date"]).dt.date.isin(
        metadata.withheld_quarters
    )
    frames = []
    for column in COMPANY_VALUE_COLUMNS:
        missing = company[column].isna()
        reasons = _reasons(
            column,
            company,
            pre_listing_rows,
            declared_reasons.get(column),
            withheld_rows,
        )
        frames.append(
            company.loc[missing, ["ticker", "date"]].assign(
                column=column, reason=reasons[missing]
            )
        )
    return pd.concat(frames)


def missing_value_ledger(
    panel_long: pd.DataFrame, registry: CompanyRegistry
) -> pd.DataFrame:
    """List every NaN cell with the reason it is missing.

    Rules are ordered and the first that applies wins, so the loop in
    ``_reasons`` runs over them reversed and earlier rules overwrite later ones.
    A column the registry declares empty for a company wins over every rule.

    Returns:
        One row per NaN cell; ``unexplained`` rows need review or a waiver.
    """
    return pd.concat(
        [
            _company_ledger(company, registry.company_metadata(str(ticker)))
            for ticker, company in panel_long.groupby("ticker", sort=True)
        ],
        ignore_index=True,
    )
