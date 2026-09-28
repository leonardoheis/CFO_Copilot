"""Re-ingest the panel a few companies at a time, within a daily API quota.

A full re-ingest needs four Alpha Vantage calls per company, and the free tier
allows roughly twenty-five a day. This works through the registry across several
days: each run takes the companies not yet done, stops the moment the provider
says the quota is spent, and records what succeeded so the next run resumes
where this one stopped.
"""

import json
import logging
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

import click

from app.data.exceptions import DataSourceError, RateLimitedError
from app.data.pipeline import merge_panel, resolve_date_range, write_panel
from app.data.progress import Progress
from app.injections import configure_container
from app.settings import Settings

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_CALLS_PER_COMPANY = 4
DEFAULT_DAILY_COMPANIES = 6
LEDGER_FILENAME = "reingest_ledger.json"


class IngestOutcome(StrEnum):
    """Why one company's run ended, so the caller need not read an exception."""

    WRITTEN = "written"
    QUOTA_EXHAUSTED = "quota_exhausted"
    FAILED = "failed"


def ledger_path() -> Path:
    return Settings.DATA_DIRECTORY / "processed" / LEDGER_FILENAME


def load_completed(path: Path) -> dict[str, str]:
    """Read the tickers already re-ingested, keyed to when they finished.

    Returns:
        A mapping of ticker to ISO timestamp, empty when no ledger exists yet.
    """
    if not path.exists():
        return {}
    content = json.loads(path.read_text())
    if not isinstance(content, dict):
        logger.warning("Ignoring malformed ledger at %s", path)
        return {}
    return {str(key): str(value) for key, value in content.items()}


def record_completed(path: Path, completed: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(completed, indent=2, sort_keys=True) + "\n")


def pending_tickers(all_tickers: tuple[str, ...], completed: dict[str, str]) -> list[str]:
    """List the companies still awaiting a re-ingest, in registry order.

    Returns:
        Tickers not present in the ledger.
    """
    return [ticker for ticker in all_tickers if ticker not in completed]


def _ingest_one(ticker: str, start: date, end: date, *, quiet: bool) -> IngestOutcome:
    """Re-ingest one company, reporting why it ended rather than raising.

    Returns:
        The outcome, so the caller can stop on a spent quota but continue past a
        company that is simply broken.
    """
    progress = Progress(ticker, enabled=not quiet)
    container = configure_container()
    try:
        with progress.stage("fetching sources") as stage:
            panel = merge_panel(
                ticker=ticker,
                start=start,
                end=end,
                sources=container.ingestion_sources(),
            )
            stage.detail(f"{len(panel)} quarters")
    except RateLimitedError as error:
        logger.warning("Quota spent before %s could finish: %s", ticker, error)
        return IngestOutcome.QUOTA_EXHAUSTED
    except DataSourceError:
        logger.exception("Could not re-ingest %s", ticker)
        return IngestOutcome.FAILED

    write_panel(panel, Settings.panel_output_path(ticker))
    return IngestOutcome.WRITTEN


@click.command()
@click.option(
    "--limit",
    default=DEFAULT_DAILY_COMPANIES,
    show_default=True,
    help="How many companies to attempt in this run.",
)
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
    "--quiet",
    is_flag=True,
    help="Print only the summary instead of one line per stage.",
)
def reingest_batch(
    limit: int,
    start_date: datetime | None,
    end_date: datetime | None,
    *,
    quiet: bool,
) -> None:
    """Re-ingest up to `--limit` companies that have not been done yet."""
    container = configure_container()
    # A company's first ticker is the one its panel is written under; the rest
    # are historical symbols the market sources fall back to.
    all_tickers = tuple(
        company.tickers[0] for company in container.company_registry().companies
    )
    path = ledger_path()
    completed = load_completed(path)
    pending = pending_tickers(all_tickers, completed)

    if not pending:
        click.echo(f"All {len(all_tickers)} companies already re-ingested.")
        return

    start, end = resolve_date_range(
        start_date.date() if start_date else None,
        end_date.date() if end_date else None,
    )
    click.echo(
        f"{len(pending)} of {len(all_tickers)} companies pending; "
        f"attempting {min(limit, len(pending))} "
        f"(~{min(limit, len(pending)) * ALPHA_VANTAGE_CALLS_PER_COMPANY} "
        "Alpha Vantage calls).",
    )

    written: list[str] = []
    failed: list[str] = []
    stopped_early = False
    for ticker in pending[:limit]:
        outcome = _ingest_one(ticker, start, end, quiet=quiet)
        if outcome is IngestOutcome.QUOTA_EXHAUSTED:
            stopped_early = True
            break
        if outcome is IngestOutcome.FAILED:
            failed.append(ticker)
            continue
        written.append(ticker)
        completed[ticker] = datetime.now(tz=UTC).isoformat()
        record_completed(path, completed)

    _report(written, failed, remaining=len(pending) - len(written), stopped=stopped_early)


def _report(
    written: list[str],
    failed: list[str],
    *,
    remaining: int,
    stopped: bool,
) -> None:
    click.echo(f"Wrote {len(written)}: {', '.join(written) if written else 'none'}")
    if failed:
        click.echo(f"Failed {len(failed)}: {', '.join(failed)}")
    if stopped:
        click.echo("Stopped early: Alpha Vantage quota is spent. Resume tomorrow.")
    click.echo(f"{remaining} companies still pending.")


def run_reingest_batch() -> None:
    reingest_batch.main(prog_name="reingest-batch", standalone_mode=True)


if __name__ == "__main__":
    run_reingest_batch()
