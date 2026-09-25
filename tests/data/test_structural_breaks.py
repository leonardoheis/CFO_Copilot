from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.data.companies import CompanyRegistry
from app.data.structural_breaks import load_structural_breaks
from app.settings import Settings


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "breaks.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_sorted_quarters_by_ticker(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "breaks:\n  ABT: [2013-03-31]\n  GE: [2024-06-30, 2023-03-31]\n"
    )

    assert load_structural_breaks(path) == {
        "ABT": (date(2013, 3, 31),),
        "GE": (date(2023, 3, 31), date(2024, 6, 30)),
    }


def test_a_date_that_is_not_a_quarter_end_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="quarter"):
        load_structural_breaks(_write(tmp_path, "breaks:\n  ABT: [2013-03-15]\n"))


def test_unknown_keys_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_structural_breaks(_write(tmp_path, "breaks: {}\nsurprise: 1\n"))


def test_the_shipped_file_names_only_registry_tickers(
    company_registry: CompanyRegistry,
) -> None:
    breaks = load_structural_breaks(Settings.STRUCTURAL_BREAKS_PATH)
    registry_tickers = {
        ticker for company in company_registry.companies for ticker in company.tickers
    }

    assert set(breaks) <= registry_tickers
