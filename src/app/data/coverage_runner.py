import json
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import click

from app.data.cli import end_option, resolved_dates, start_option
from app.data.coverage import (
    OVERLAP_END,
    CoverageReport,
    evaluate_coverage,
)
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceError
from app.data.sources import (
    XBRL_HISTORY_START,
    AlphaVantageSource,
    SecEdgarSource,
    YfinanceSource,
)
from app.injections import configure_container
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProbeContext:
    start: date
    end: date
    client: AlphaVantageSource
    sec_source: SecEdgarSource
    market_source: YfinanceSource


def _write_coverage_report(
    destination: Path,
    resolved_start: date,
    resolved_end: date,
    reports: list[dict[str, object]],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "start": resolved_start.isoformat(),
                "end": resolved_end.isoformat(),
                "reports": reports,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    click.echo(f"Wrote coverage report to {destination}")


def _build_probe_context(start: date, end: date, *, refresh: bool) -> ProbeContext:
    container = configure_container()
    return ProbeContext(
        start=start,
        end=end,
        client=container.alpha_vantage_source(refresh=refresh),
        sec_source=container.sec_edgar_source(),
        market_source=container.yfinance_source(),
    )


def _collect_reports(
    tickers: tuple[str, ...],
    context: ProbeContext,
) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for ticker in tickers:
        normalized_ticker = ticker.upper()
        entry = _probe_ticker(normalized_ticker, context)
        reports.append(entry)
        status = "PASS" if entry["passed"] else "FAIL"
        error = entry.get("error")
        detail = "" if error is None else f" ({error})"
        click.echo(f"{normalized_ticker}: {status}{detail}")
    return reports


def _probe_ticker(ticker: str, context: ProbeContext) -> dict[str, object]:
    """Probe one ticker, recording a source failure rather than raising.

    Returns:
        The ticker's report entry; a failed source gives ``passed: False`` and
        its ``error``.
    """
    try:
        report = _coverage_report(ticker, context)
    except DataSourceError as error:
        logger.warning("Could not probe %s: %s", ticker, error)
        return {"ticker": ticker, "passed": False, "error": str(error)}
    return report.model_dump(mode="json")


def _coverage_report(ticker: str, context: ProbeContext) -> CoverageReport:
    alpha_panel = context.client.fetch_financials_panel(
        ticker,
        context.start,
        context.end,
    )
    overlap_end = min(context.end, OVERLAP_END)
    sec_panel = context.sec_source.fetch_financials_panel(
        ticker,
        XBRL_HISTORY_START,
        overlap_end,
        context.market_source.fetch_splits(ticker),
    )
    return evaluate_coverage(
        ticker,
        alpha_panel,
        sec_panel,
        quarter_end_dates(context.start, context.end),
    )


@click.command()
@click.option(
    "--ticker",
    "tickers",
    multiple=True,
    required=True,
    help="Ticker to probe. Repeat the option for multiple tickers.",
)
@start_option
@end_option
@click.option(
    "--refresh",
    is_flag=True,
    help="Ignore cached Alpha Vantage responses and request fresh data.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="JSON report path.",
)
def probe_alpha_vantage(
    tickers: tuple[str, ...],
    start_date: datetime | None,
    end_date: datetime | None,
    *,
    refresh: bool,
    output: Path | None,
) -> None:
    resolved_start, resolved_end = resolved_dates(start_date, end_date)
    context = _build_probe_context(resolved_start, resolved_end, refresh=refresh)
    reports = _collect_reports(tickers, context)

    destination = output or (
        Settings.DATA_DIRECTORY / "coverage" / "alpha_vantage_report.json"
    )
    _write_coverage_report(destination, resolved_start, resolved_end, reports)


def run_probe() -> None:
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "--":
        arguments = arguments[1:]
    probe_alpha_vantage.main(
        args=arguments,
        prog_name="probe-alpha-vantage",
        standalone_mode=True,
    )


if __name__ == "__main__":
    run_probe()
