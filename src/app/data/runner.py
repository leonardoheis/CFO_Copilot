from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import cast

import click
from pydantic import BaseModel, ConfigDict

from app.data.pipeline import (
    XBRL_HISTORY_START,
    build_panel_skeleton,
    merge_panel,
    resolve_date_range,
    write_panel,
)
from app.data.progress import Progress
from app.injections import configure_container
from app.settings import Settings


class IngestRequest(BaseModel):
    """One ingestion run, as the CLI options describe it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    start: date | None = None
    end: date | None = None
    skeleton: bool = False
    output_path: Path | None = None
    quiet: bool = False

    @classmethod
    def from_options(cls, options: Mapping[str, object]) -> "IngestRequest":
        """Build a request from click's parsed options.

        Returns:
            The validated request.
        """
        return cls(
            ticker=str(options["ticker"]).upper(),
            start=_as_date(options.get("start_date")),
            end=_as_date(options.get("end_date")),
            skeleton=bool(options.get("skeleton")),
            output_path=cast("Path | None", options.get("output_path")),
            quiet=bool(options.get("quiet")),
        )


def _as_date(value: object) -> date | None:
    return value.date() if isinstance(value, datetime) else None


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
@click.option(
    "--quiet",
    is_flag=True,
    help="Print only the final line instead of one line per stage.",
)
def ingest_data(**options: object) -> None:
    _run(IngestRequest.from_options(options))


def _run(request: IngestRequest) -> None:
    ticker = request.ticker
    resolved_start, resolved_end = resolve_date_range(request.start, request.end)
    if resolved_start < XBRL_HISTORY_START:
        click.echo(
            "SEC XBRL facts are typically empty before "
            f"{XBRL_HISTORY_START.isoformat()}; Alpha Vantage fills that window "
            "when ALPHA_VANTAGE_API_KEY is set.",
        )

    progress = Progress(ticker, enabled=not request.quiet)
    with progress.stage("wiring sources"):
        container = configure_container()

    if request.skeleton:
        with progress.stage("building skeleton"):
            panel = build_panel_skeleton(
                ticker,
                resolved_start,
                resolved_end,
                container.company_registry(),
            )
    else:
        with progress.stage("fetching sources") as stage:
            panel = merge_panel(
                ticker=ticker,
                start=resolved_start,
                end=resolved_end,
                sources=container.ingestion_sources(),
            )
            stage.detail(f"{len(panel)} quarters")

    destination = request.output_path or Settings.panel_output_path(ticker)
    written_path = write_panel(panel, destination)
    click.echo(f"Wrote {len(panel)} quarterly rows to {written_path}")


def run_ingest() -> None:
    ingest_data.main(prog_name="ingest-data", standalone_mode=True)
