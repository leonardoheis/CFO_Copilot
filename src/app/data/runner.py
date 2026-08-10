from datetime import date, datetime
from pathlib import Path

import click

from app.data.pipeline import (
    build_panel_skeleton,
    merge_panel,
    resolve_date_range,
    write_panel,
)
from app.data.sources import FredSource, SecEdgarSource, YfinanceSource
from app.data.sources_bundle import IngestionSources
from app.settings import Settings


def _parse_optional_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


@click.command()
@click.option("--ticker", required=True, help="Ticker symbol, e.g. AMZN.")
@click.option(
    "--start",
    "start_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Inclusive start date (YYYY-MM-DD). Defaults to ~20 years before --end.",
)
@click.option(
    "--end",
    "end_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Inclusive end date (YYYY-MM-DD). Defaults to the latest completed quarter.",
)
@click.option(
    "--skeleton",
    is_flag=True,
    help="Write a structured empty panel without calling external data sources.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output Parquet path. Defaults to data/processed/<ticker>_panel.parquet.",
)
def ingest_data(
    ticker: str,
    start_date: datetime | None,
    end_date: datetime | None,
    *,
    skeleton: bool,
    output_path: Path | None,
) -> None:
    start = _parse_optional_date(
        start_date.strftime("%Y-%m-%d") if start_date is not None else None,
    )
    end = _parse_optional_date(
        end_date.strftime("%Y-%m-%d") if end_date is not None else None,
    )
    resolved_start, resolved_end = resolve_date_range(start, end)
    if start is not None and resolved_start != start:
        click.echo(
            f"Adjusted start date from {start.isoformat()} to "
            f"{resolved_start.isoformat()} because SEC XBRL coverage begins "
            f"on {resolved_start.isoformat()}.",
        )

    if skeleton:
        panel = build_panel_skeleton(ticker, resolved_start, resolved_end)
    else:
        panel = merge_panel(
            ticker=ticker,
            start=resolved_start,
            end=resolved_end,
            sources=IngestionSources(
                fred=FredSource(api_key=Settings.FRED_API_KEY),
                yfinance=YfinanceSource(),
                sec_edgar=SecEdgarSource(user_agent=Settings.SEC_USER_AGENT),
            ),
        )

    destination = output_path or Settings.panel_output_path(ticker)
    written_path = write_panel(panel, destination)
    click.echo(f"Wrote {len(panel)} quarterly rows to {written_path}")


def run_ingest() -> None:
    ingest_data.main(prog_name="ingest-data", standalone_mode=True)
