"""Options and steps the ingestion command-line tools share."""

from datetime import date, datetime

import click
import pandas as pd

from app.data.pipeline import merge_panel, resolve_date_range
from app.data.progress import Progress
from app.injections import Container

_ISO_DATE = click.DateTime(formats=["%Y-%m-%d"])

start_option = click.option(
    "--start",
    "start_date",
    type=_ISO_DATE,
    default=None,
    help="Inclusive start date (YYYY-MM-DD). Defaults to ~20 years before --end.",
)
end_option = click.option(
    "--end",
    "end_date",
    type=_ISO_DATE,
    default=None,
    help="Inclusive end date (YYYY-MM-DD). Defaults to the latest completed quarter.",
)


def resolved_dates(
    start_date: datetime | None, end_date: datetime | None
) -> tuple[date, date]:
    """Turn the parsed ``--start`` and ``--end`` into the ingestion window.

    Returns:
        Inclusive start and end dates, defaults filled in.
    """
    return resolve_date_range(
        start_date.date() if start_date else None,
        end_date.date() if end_date else None,
    )


def fetch_panel(
    ticker: str, window: tuple[date, date], container: Container, progress: Progress
) -> pd.DataFrame:
    """Merge every source's quarters for one company, reported as one stage.

    Returns:
        The merged panel.
    """
    start, end = window
    with progress.stage("fetching sources") as stage:
        panel = merge_panel(
            ticker=ticker,
            start=start,
            end=end,
            sources=container.ingestion_sources(),
        )
        stage.detail(f"{len(panel)} quarters")
    return panel
