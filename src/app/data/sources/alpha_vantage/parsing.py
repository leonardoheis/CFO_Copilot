"""Translate Alpha Vantage JSON payloads into panel values.

Everything here is a pure function of its arguments: no HTTP, no cache, no
credentials. The vendor's field names (``fiscalDateEnding``, ``totalRevenue``,
``quarterlyReports``) are confined to this module so they cannot leak into the
rest of the data layer.
"""

import logging
from collections.abc import Iterator
from datetime import date
from typing import cast

from app.data.dates import (
    QUARTER_END_TOLERANCE_DAYS,
    nearest_quarter_end,
)
from app.data.exceptions import MalformedPayloadError
from app.data.schema import MILLIONS_DIVISOR, FinancialQuarterValues, FinancialsRow

logger = logging.getLogger(__name__)

JsonObject = dict[str, object]


def merge_income(
    values_by_date: dict[date, FinancialQuarterValues],
    payload: JsonObject,
) -> None:
    for report, values in _quarterly_reports(values_by_date, payload):
        values.revenue_usd_m = millions(report, "totalRevenue")
        values.gross_profit_usd_m = millions(report, "grossProfit")
        values.opex_usd_m = millions(report, "operatingExpenses")
        values.operating_income_usd_m = millions(report, "operatingIncome")
        values.ebitda_usd_m = millions(report, "ebitda")
        values.net_income_usd_m = millions(report, "netIncome")
        diluted = number(report, "dilutedEPS")
        values.eps = diluted if diluted is not None else number(report, "basicEPS")


def merge_cash_flow(
    values_by_date: dict[date, FinancialQuarterValues],
    payload: JsonObject,
) -> None:
    for report, values in _quarterly_reports(values_by_date, payload):
        operating_cash_flow = number(report, "operatingCashflow")
        capital_expenditures = number(report, "capitalExpenditures")
        if operating_cash_flow is not None and capital_expenditures is not None:
            values.free_cash_flow_usd_m = (
                operating_cash_flow - abs(capital_expenditures)
            ) / MILLIONS_DIVISOR


def merge_balance_sheet(
    values_by_date: dict[date, FinancialQuarterValues],
    payload: JsonObject,
) -> None:
    for report, values in _quarterly_reports(values_by_date, payload):
        shares = number(report, "commonStockSharesOutstanding")
        if shares is not None:
            values.shares_outstanding = shares


def merge_earnings(
    values_by_date: dict[date, FinancialQuarterValues],
    payload: JsonObject,
) -> None:
    for report, values in _quarterly_reports(
        values_by_date,
        payload,
        key="quarterlyEarnings",
    ):
        earnings_per_share = number(report, "reportedEPS")
        if earnings_per_share is not None and values.eps is None:
            values.eps = earnings_per_share


def _quarterly_reports(
    values_by_date: dict[date, FinancialQuarterValues],
    payload: JsonObject,
    key: str = "quarterlyReports",
) -> Iterator[tuple[JsonObject, FinancialQuarterValues]]:
    for report in reports(payload, key):
        quarter_date = report_date(report)
        values = values_by_date.setdefault(quarter_date, FinancialQuarterValues())
        yield report, values


def reports(payload: JsonObject, key: str) -> list[JsonObject]:
    """Extract the report list stored under ``key``.

    Returns:
        Every dictionary entry under the key, or an empty list if absent.

    Raises:
        MalformedPayloadError: If the report container is not a list.
    """
    raw_reports = payload.get(key, [])
    if not isinstance(raw_reports, list):
        msg = f"Alpha Vantage {key} must be a list, got {type(raw_reports).__name__}"
        raise MalformedPayloadError(
            msg,
        )
    parsed_reports: list[JsonObject] = []
    for report in raw_reports:
        if not isinstance(report, dict):
            logger.warning(
                "Skipping non-object Alpha Vantage report in %s: %r",
                key,
                report,
            )
        else:
            parsed_reports.append(cast("JsonObject", report))
    return parsed_reports


def report_date(report: JsonObject) -> date:
    """Read ``fiscalDateEnding`` and snap it to the calendar quarter it belongs to.

    Total by design: every report either yields a quarter or is rejected. At the
    46-day tolerance no valid date can fall outside a quarter, since the longest
    quarter is 92 days, so there is no "valid but unplaceable" outcome to model.

    Returns:
        The calendar quarter end the report belongs to.

    Raises:
        MalformedPayloadError: If ``fiscalDateEnding`` is absent, is not an ISO
            date, or cannot be placed on a calendar quarter. A report that cannot
            be placed in time is unusable, and treating it as merely missing
            would hide an API format change behind gaps in the panel.
    """
    raw_date = report.get("fiscalDateEnding")
    if not isinstance(raw_date, str):
        msg = (
            "Alpha Vantage report has no usable fiscalDateEnding "
            f"(got {type(raw_date).__name__})"
        )
        raise MalformedPayloadError(msg)
    try:
        parsed_date = date.fromisoformat(raw_date)
    except ValueError as error:
        msg = f"Alpha Vantage fiscalDateEnding is not an ISO date: {raw_date!r}"
        raise MalformedPayloadError(msg) from error

    try:
        return nearest_quarter_end(parsed_date, QUARTER_END_TOLERANCE_DAYS)
    except ValueError as error:
        msg = (
            f"Alpha Vantage fiscalDateEnding {raw_date!r} cannot be placed "
            "on a calendar quarter"
        )
        raise MalformedPayloadError(msg) from error


def number(report: JsonObject, key: str) -> float | None:
    """Coerce a reported field to a float.

    Returns:
        The parsed value, or ``None`` for absent, blank, or unparsable entries.
    """
    value = report.get(key)
    if value is None or str(value) in {"", "None", "null"}:
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        logger.warning(
            "Alpha Vantage %s is present but not a number: %r",
            key,
            value,
        )
        return None


def millions(report: JsonObject, key: str) -> float | None:
    """Coerce a reported field to a float scaled to millions.

    Returns:
        The parsed value in millions, or ``None`` if the field is unusable.
    """
    value = number(report, key)
    return value / MILLIONS_DIVISOR if value is not None else None


def row_for_date(
    values: FinancialQuarterValues | None,
    quarter_date: date,
) -> FinancialsRow:
    """Build one panel row, deriving margins from the accumulated values.

    ``values`` is ``None`` when no payload reported anything for this quarter,
    which yields a row of ``None`` values rather than dropping the quarter.

    Returns:
        The panel row for this quarter.
    """
    if values is None:
        values = FinancialQuarterValues()
    revenue = values.revenue_usd_m
    gross_profit = values.gross_profit_usd_m
    operating_income = values.operating_income_usd_m
    net_income = values.net_income_usd_m
    return FinancialsRow(
        date=quarter_date,
        revenue_usd_m=revenue,
        gross_profit_usd_m=gross_profit,
        opex_usd_m=values.opex_usd_m,
        operating_income_usd_m=operating_income,
        ebitda_usd_m=values.ebitda_usd_m,
        net_income_usd_m=net_income,
        free_cash_flow_usd_m=values.free_cash_flow_usd_m,
        gross_margin=_margin(gross_profit, revenue),
        operating_margin=_margin(operating_income, revenue),
        net_margin=_margin(net_income, revenue),
        eps=values.eps,
        shares_outstanding=values.shares_outstanding,
    )


def _margin(numerator: float | None, revenue: float | None) -> float | None:
    """Divide by revenue, guarding the unreported and zero-revenue cases.

    A falsy ``revenue`` is exactly the set this cannot divide by: ``None`` when
    the quarter reported no revenue at all, and ``0.0`` when it reported zero.

    Returns:
        The ratio, or ``None`` if either side is absent or revenue is zero.
    """
    if numerator is None or not revenue:
        return None
    return numerator / revenue
