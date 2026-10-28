from pathlib import Path

import pytest
from click.testing import CliRunner

from app.data.add_company import add_company
from app.data.companies import CompanyRegistry, KnownCik
from app.data.exceptions import DataSourceUnavailableError
from app.data.sources import SecTicker

pytestmark = pytest.mark.usefixtures("stub_sec_lookup")

REGISTRY = """companies:
  - tickers:
      - AMZN
    panel:
      company: Amazon
      sector: Consumer Cyclical
      is_public: true
    sec:
      type: known_cik
      cik: "0001018724"
    market:
      type: from_ticker
"""


@pytest.fixture
def registry(tmp_path: Path) -> Path:
    path = tmp_path / "companies.yaml"
    path.write_text(REGISTRY, encoding="utf-8")
    return path


@pytest.fixture
def stub_sec_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.data.add_company.fetch_sec_tickers",
        lambda **_: {"INTC": SecTicker(cik="0000050863", title="INTEL CORP")},
    )


def test_appends_the_company_and_keeps_existing_entries(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        ["--ticker", "INTC", "--sector", "Technology", "--registry", str(registry)],
    )
    reloaded = CompanyRegistry.from_path(registry)

    assert result.exit_code == 0, result.output
    assert [company.tickers for company in reloaded.companies] == [("AMZN",), ("INTC",)]
    assert reloaded.scraped_company("INTC").sec == KnownCik(cik="0000050863")
    assert reloaded.company_metadata("INTC").company == "Intel Corp"


def test_a_name_with_yaml_syntax_is_written_as_text(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        [
            "--ticker",
            "INTC",
            "--sector",
            "Technology",
            "--company",
            "Intel: #1 chips",
            "--registry",
            str(registry),
        ],
    )

    assert result.exit_code == 0, result.output
    reloaded = CompanyRegistry.from_path(registry)
    assert reloaded.company_metadata("INTC").company == "Intel: #1 chips"


def test_an_entry_the_registry_rejects_is_rolled_back(
    registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.data.add_company.fetch_sec_tickers",
        lambda **_: {"INTC": SecTicker(cik="50863", title="INTEL CORP")},
    )

    result = CliRunner().invoke(
        add_company,
        ["--ticker", "INTC", "--sector", "Technology", "--registry", str(registry)],
    )

    assert result.exit_code == 1
    assert "not added" in result.output
    assert registry.read_text(encoding="utf-8") == REGISTRY


def test_rejects_a_ticker_sec_does_not_know(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        ["--ticker", "IBME", "--sector", "Technology", "--registry", str(registry)],
    )

    assert result.exit_code != 0
    assert "IBME" in result.output
    assert registry.read_text(encoding="utf-8") == REGISTRY


def test_reports_an_unavailable_sec_without_a_traceback(
    registry: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(**_: object) -> dict[str, SecTicker]:
        msg = "SEC ticker file not found"
        raise DataSourceUnavailableError(msg)

    monkeypatch.setattr("app.data.add_company.fetch_sec_tickers", unavailable)

    result = CliRunner().invoke(
        add_company,
        ["--ticker", "INTC", "--sector", "Technology", "--registry", str(registry)],
    )

    assert result.exit_code == 1
    assert "SEC ticker file not found" in result.output
    assert registry.read_text(encoding="utf-8") == REGISTRY


def test_rejects_a_ticker_already_registered(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        [
            "--ticker",
            "AMZN",
            "--sector",
            "Consumer Cyclical",
            "--registry",
            str(registry),
        ],
    )

    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_reminds_the_user_to_update_the_pinned_test(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        ["--ticker", "INTC", "--sector", "Technology", "--registry", str(registry)],
    )

    assert "test_companies.py" in result.output
