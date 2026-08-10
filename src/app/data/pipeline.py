from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from app.data.dates import quarter_end_dates
from app.data.schema import (
    METADATA_COLUMNS,
    PANEL_COLUMNS,
    resolve_company_metadata,
)
from app.data.sources_bundle import IngestionSources

DEFAULT_HISTORY_YEARS = 20
XBRL_HISTORY_START = date(2008, 4, 1)
MILLIONS_DIVISOR = 1_000_000
Q1_END_MONTH = 3
Q2_END_MONTH = 6
Q3_END_MONTH = 9


def most_recent_completed_quarter(as_of: date) -> date:
    if as_of.month <= Q1_END_MONTH:
        return date(as_of.year - 1, 12, 31)
    if as_of.month <= Q2_END_MONTH:
        return date(as_of.year, 3, 31)
    if as_of.month <= Q3_END_MONTH:
        return date(as_of.year, 6, 30)
    return date(as_of.year, 9, 30)


def resolve_date_range(
    start: date | None,
    end: date | None,
    *,
    as_of: date | None = None,
) -> tuple[date, date]:
    reference_date = as_of or datetime.now(tz=UTC).date()
    resolved_end = end or most_recent_completed_quarter(reference_date)
    requested_start = start or date(
        resolved_end.year - DEFAULT_HISTORY_YEARS,
        resolved_end.month,
        resolved_end.day,
    )
    resolved_start = max(requested_start, XBRL_HISTORY_START)
    return resolved_start, resolved_end


def build_panel_skeleton(ticker: str, start: date, end: date) -> pd.DataFrame:
    metadata = resolve_company_metadata(ticker)
    normalized_ticker = ticker.upper()
    rows: list[dict[str, object]] = []

    for quarter_end in quarter_end_dates(start, end):
        row: dict[str, object] = dict.fromkeys(PANEL_COLUMNS)
        row["date"] = quarter_end
        row["company"] = metadata.company
        row["ticker"] = normalized_ticker
        row["sector"] = metadata.sector
        row["is_public"] = metadata.is_public
        rows.append(row)

    return pd.DataFrame(rows, columns=list(PANEL_COLUMNS))


def merge_panel(
    ticker: str,
    start: date,
    end: date,
    sources: IngestionSources,
) -> pd.DataFrame:
    panel = build_panel_skeleton(ticker, start, end).loc[:, list(METADATA_COLUMNS)]
    splits = sources.yfinance.fetch_splits(ticker)
    financials = sources.sec_edgar.fetch_financials_panel(
        ticker,
        start,
        end,
        splits,
    )
    market = sources.yfinance.fetch_market_panel(ticker, start, end)
    macro = sources.fred.fetch_macro_panel(start, end)

    for source_panel in (financials, market, macro):
        panel = panel.merge(source_panel, on="date", how="left")

    panel["market_cap_usd_m"] = (
        panel["stock_price_usd"] * panel["shares_outstanding"] / MILLIONS_DIVISOR
    )
    panel["pe_ratio"] = price_earnings_ratio(
        panel["stock_price_usd"],
        panel["eps"],
    )
    return panel.loc[:, list(PANEL_COLUMNS)]


def price_earnings_ratio(stock_price: pd.Series, eps: pd.Series) -> pd.Series:
    """Divide price by earnings per share, leaving non-positive earnings undefined.

    Returns:
        A series of P/E ratios aligned to the inputs.
    """
    positive_eps = eps.where(eps > 0)
    return stock_price / positive_eps


def write_panel(panel: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(output_path, index=False)
    return output_path
