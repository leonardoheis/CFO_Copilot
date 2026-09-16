"""Register a new ticker in config/companies.yaml after verifying it with SEC."""

import json
import urllib.request
from pathlib import Path
from typing import Final

import click

from app.data.companies import CompanyRegistry
from app.settings import Settings

SEC_TICKERS_URL: Final = "https://www.sec.gov/files/company_tickers.json"
CIK_DIGITS: Final = 10
PINNED_TEST: Final = "tests/data/test_companies.py"

ENTRY_TEMPLATE: Final = """
  - tickers:
      - {ticker}
    panel:
      company: {company}
      sector: {sector}
      is_public: true
    sec:
      type: known_cik
      cik: "{cik}"
    market:
      type: from_ticker
"""


def lookup_ticker(ticker: str) -> tuple[str, str] | None:
    """Find a ticker in SEC's published ticker file.

    Returns:
        Its zero-padded CIK and registered title, or None when SEC has no
        such ticker.
    """
    request = urllib.request.Request(  # https, fixed SEC URL
        SEC_TICKERS_URL,
        headers={"User-Agent": Settings.SEC_USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=Settings.REQUEST_TIMEOUT) as response:  # ruff: ignore[suspicious-url-open-usage]
        payload = json.load(response)

    wanted = ticker.upper()
    for entry in payload.values():
        if entry["ticker"].upper() == wanted:
            return str(entry["cik_str"]).zfill(CIK_DIGITS), entry["title"]
    return None


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

    found = lookup_ticker(normalized)
    if found is None:
        message = (
            f"SEC does not list {normalized}. Check the symbol — a ticker that "
            "is not in company_tickers.json cannot be resolved to a CIK."
        )
        raise click.ClickException(message)

    cik, title = found
    entry = ENTRY_TEMPLATE.format(
        ticker=normalized,
        company=company or title.title(),
        sector=sector,
        cik=cik,
    )
    with path.open("a", encoding="utf-8") as registry:
        registry.write(entry)

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
