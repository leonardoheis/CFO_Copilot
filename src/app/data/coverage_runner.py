import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import click

from app.data.coverage import (
    OVERLAP_END,
    OVERLAP_START,
    CoverageReport,
    evaluate_coverage,
    report_as_dict,
)
from app.data.dates import quarter_end_dates
from app.data.exceptions import DataSourceError
from app.data.pipeline import most_recent_completed_quarter
from app.data.sources.alpha_vantage import AlphaVantageSource
from app.data.sources.sec_edgar import SecEdgarSource
from app.data.sources.yfinance_source import YfinanceSource
from app.settings import Settings

DEFAULT_PROBE_YEARS = 20


def _parse_date(value: datetime | None) -> date | None:
    return value.date() if value is not None else None


def _default_start(end: date) -> date:
    return date(end.year - DEFAULT_PROBE_YEARS, end.month, end.day)


def _probe_ticker(  # ruff: ignore[too-many-arguments,too-many-positional-arguments]
    ticker: str,
    start: date,
    end: date,
    client: AlphaVantageSource,
    sec_source: SecEdgarSource,
    market_source: YfinanceSource,
) -> CoverageReport:
    alpha_panel = client.fetch_financials_panel(ticker, start, end)
    overlap_end = min(end, OVERLAP_END)
    sec_panel = sec_source.fetch_financials_panel(
        ticker,
        OVERLAP_START,
        overlap_end,
        market_source.fetch_splits(ticker),
    )
    return evaluate_coverage(
        ticker,
        alpha_panel,
        sec_panel,
        quarter_end_dates(start, end),
    )


@click.command()
@click.option(
    "--ticker",
    "tickers",
    multiple=True,
    required=True,
    help="Ticker to probe. Repeat the option for multiple tickers.",
)
@click.option(
    "--start",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Inclusive history start date. Defaults to 20 years before --end.",
)
@click.option(
    "--end",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Inclusive history end date. Defaults to the latest completed quarter.",
)
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
    start: datetime | None,
    end: datetime | None,
    *,
    refresh: bool,
    output: Path | None,
) -> None:
    resolved_end = _parse_date(end) or most_recent_completed_quarter(
        datetime.now(tz=UTC).date(),
    )
    resolved_start = _parse_date(start) or _default_start(resolved_end)
    client = AlphaVantageSource(
        api_key=Settings.ALPHA_VANTAGE_API_KEY,
        cache_directory=Settings.DATA_DIRECTORY / "raw" / "alpha_vantage",
        refresh=refresh,
    )
    sec_source = SecEdgarSource(user_agent=Settings.SEC_USER_AGENT)
    market_source = YfinanceSource()
    reports: list[dict[str, object]] = []

    for ticker in tickers:
        normalized_ticker = ticker.upper()
        try:
            report = _probe_ticker(
                normalized_ticker,
                resolved_start,
                resolved_end,
                client,
                sec_source,
                market_source,
            )
            reports.append(report_as_dict(report))
            status = "PASS" if report.passed else "FAIL"
            click.echo(f"{normalized_ticker}: {status}")
        except DataSourceError as error:
            reports.append(
                {
                    "ticker": normalized_ticker,
                    "passed": False,
                    "error": str(error),
                },
            )
            click.echo(f"{normalized_ticker}: FAIL ({error})")

    destination = output or (
        Settings.DATA_DIRECTORY / "coverage" / "alpha_vantage_report.json"
    )
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
