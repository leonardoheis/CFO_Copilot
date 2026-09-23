from pathlib import Path

import pytest
from click.testing import CliRunner

from app.data.add_company import add_company

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
        "app.data.add_company.lookup_ticker",
        lambda ticker: {"INTC": ("0000050863", "INTEL CORP")}.get(ticker.upper()),
    )


def test_appends_the_company_and_keeps_existing_entries(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        ["--ticker", "INTC", "--sector", "Technology", "--registry", str(registry)],
    )
    written = registry.read_text(encoding="utf-8")

    assert result.exit_code == 0, result.output
    assert 'cik: "0000050863"' in written
    assert "- INTC" in written
    assert "Amazon" in written


def test_rejects_a_ticker_sec_does_not_know(registry: Path) -> None:
    result = CliRunner().invoke(
        add_company,
        ["--ticker", "IBME", "--sector", "Technology", "--registry", str(registry)],
    )

    assert result.exit_code != 0
    assert "IBME" in result.output
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
