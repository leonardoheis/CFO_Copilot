from pathlib import Path

from app.data.batch import (
    IngestOutcome,
    load_completed,
    pending_tickers,
    record_completed,
)


def test_pending_skips_tickers_already_in_the_ledger() -> None:
    all_tickers = ("AAPL", "MSFT", "AMZN")

    pending = pending_tickers(all_tickers, {"MSFT": "2026-09-27T00:00:00+00:00"})

    assert pending == ["AAPL", "AMZN"]


def test_pending_is_empty_once_every_company_is_done() -> None:
    all_tickers = ("AAPL", "MSFT")
    completed = dict.fromkeys(all_tickers, "2026-09-27T00:00:00+00:00")

    assert pending_tickers(all_tickers, completed) == []


def test_ledger_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "reingest_ledger.json"
    completed = {"AAPL": "2026-09-27T00:00:00+00:00"}

    record_completed(path, completed)

    assert load_completed(path) == completed


def test_missing_ledger_reads_as_nothing_completed(tmp_path: Path) -> None:
    assert load_completed(tmp_path / "absent.json") == {}


def test_malformed_ledger_reads_as_nothing_completed(tmp_path: Path) -> None:
    path = tmp_path / "reingest_ledger.json"
    path.write_text('["AAPL"]')

    assert load_completed(path) == {}


def test_quota_exhaustion_is_distinct_from_failure() -> None:
    """The batch stops on a spent quota but continues past a broken company."""
    assert IngestOutcome.QUOTA_EXHAUSTED is not IngestOutcome.FAILED
