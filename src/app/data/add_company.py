"""Register a new ticker in config/companies.yaml after verifying it with SEC."""

import textwrap
from pathlib import Path
from typing import Final

import click
import yaml

from app.data.companies import CompanyRegistry
from app.data.exceptions import ConfigError, DataSourceError
from app.data.sources import fetch_sec_tickers
from app.settings import Settings

PINNED_TEST: Final = "tests/data/test_companies.py"


@click.command()
@click.option("--ticker", required=True, help="Ticker symbol, e.g. INTC.")
@click.option("--sector", required=True, help="Sector for the panel metadata.")
@click.option("--company", default=None, help="Display name. Defaults to SEC's title.")
@click.option(
    "--registry",
    "registry_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Registry file. Defaults to config/companies.yaml.",
)
def add_company(
    ticker: str,
    sector: str,
    company: str | None,
    registry_path: Path | None,
) -> None:
    normalized = ticker.upper()
    path = registry_path or Settings.COMPANY_REGISTRY_PATH

    if _is_registered(path, normalized):
        message = f"{normalized} is already in {path}"
        raise click.ClickException(message)

    try:
        sec_tickers = fetch_sec_tickers(
            user_agent=Settings.SEC_USER_AGENT,
            timeout=Settings.REQUEST_TIMEOUT,
        )
    except DataSourceError as error:
        raise click.ClickException(str(error)) from error
    found = sec_tickers.get(normalized)
    if found is None:
        message = (
            f"SEC does not list {normalized}. Check the symbol — a ticker that "
            "is not in company_tickers.json cannot be resolved to a CIK."
        )
        raise click.ClickException(message)

    cik, title = found.cik, found.title
    entry = {
        "tickers": [normalized],
        "panel": {
            "company": company or title.title(),
            "sector": sector,
            "is_public": True,
        },
        "sec": {"type": "known_cik", "cik": cik},
        "market": {"type": "from_ticker"},
    }
    original = path.read_text(encoding="utf-8")
    # Appended rather than re-dumped, so the registry's comments survive.
    path.write_text(
        original
        + "\n"
        + textwrap.indent(yaml.safe_dump([entry], sort_keys=False), "  "),
        encoding="utf-8",
    )
    try:
        CompanyRegistry.from_path(path)
    except ConfigError as error:
        path.write_text(original, encoding="utf-8")
        message = (
            f"The new entry would make {path} invalid, so it was not added: {error}"
        )
        raise click.ClickException(message) from error

    click.echo(f"Added {normalized} ({title}) with CIK {cik} to {path}")
    click.echo(
        f'Now add "{company or title.title()}" to the pinned set in {PINNED_TEST}, '
        "then run: uv run python -m app.data --ticker " + normalized,
    )


def _is_registered(path: Path, ticker: str) -> bool:
    if not path.exists():
        return False
    return any(
        ticker in company.tickers
        for company in CompanyRegistry.from_path(path).companies
    )


def run_add_company() -> None:
    add_company.main(prog_name="add-company", standalone_mode=True)


if __name__ == "__main__":
    run_add_company()
