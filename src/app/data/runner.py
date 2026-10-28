from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

import click
from pydantic import BaseModel, ConfigDict

from app.data.cli import end_option, fetch_panel, resolved_dates, start_option
from app.data.pipeline import build_panel_skeleton, write_panel
from app.data.progress import Progress
from app.data.sources import XBRL_HISTORY_START
from app.injections import configure_container


class IngestRequest(BaseModel):
    """One ingestion run, as the CLI options describe it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: str
    start_date: datetime | None = None
    end_date: datetime | None = None
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
            start_date=cast("datetime | None", options.get("start_date")),
            end_date=cast("datetime | None", options.get("end_date")),
            skeleton=bool(options.get("skeleton")),
            output_path=cast("Path | None", options.get("output_path")),
            quiet=bool(options.get("quiet")),
        )


@click.command()
@click.option("--ticker", required=True, help="Ticker symbol, e.g. AMZN.")
@start_option
@end_option
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
    resolved_start, resolved_end = resolved_dates(request.start_date, request.end_date)
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
        panel = fetch_panel(ticker, (resolved_start, resolved_end), container, progress)

    destination = request.output_path or container.panel_store().path_for(ticker)
    written_path = write_panel(panel, destination)
    click.echo(f"Wrote {len(panel)} quarterly rows to {written_path}")


def run_ingest() -> None:
    ingest_data.main(prog_name="ingest-data", standalone_mode=True)
