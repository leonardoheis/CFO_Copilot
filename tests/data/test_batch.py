from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from app.data import batch
from app.data.batch import (
    IngestOutcome,
    load_completed,
    pending_tickers,
    record_completed,
    reingest_batch,
)

type ScriptedRun = Callable[[list[IngestOutcome]], tuple[list[str], Path]]


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


@pytest.fixture
def scripted_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ScriptedRun:
    ledger = tmp_path / "reingest_ledger.json"
    monkeypatch.setattr(batch, "ledger_path", lambda: ledger)

    def run(outcomes: list[IngestOutcome]) -> tuple[list[str], Path]:
        attempted: list[str] = []
        remaining = iter(outcomes)

        def fake_ingest_one(
            ticker: str, _start: date, _end: date, *, quiet: bool
        ) -> IngestOutcome:
            assert quiet
            attempted.append(ticker)
            return next(remaining)

        monkeypatch.setattr(batch, "_ingest_one", fake_ingest_one)
        result = CliRunner().invoke(
            reingest_batch, ["--limit", str(len(outcomes)), "--quiet"]
        )
        assert result.exit_code == 0, result.output
        return attempted, ledger

    return run


def test_batch_continues_past_a_broken_company(scripted_run: ScriptedRun) -> None:
    script = [IngestOutcome.FAILED, IngestOutcome.WRITTEN]

    attempted, ledger = scripted_run(script)

    assert len(attempted) == len(script)
    assert set(load_completed(ledger)) == {attempted[1]}


def test_batch_stops_on_a_spent_quota_keeping_what_it_wrote(
    scripted_run: ScriptedRun,
) -> None:
    script = [
        IngestOutcome.WRITTEN,
        IngestOutcome.QUOTA_EXHAUSTED,
        IngestOutcome.WRITTEN,
    ]

    attempted, ledger = scripted_run(script)

    assert len(attempted) == script.index(IngestOutcome.QUOTA_EXHAUSTED) + 1
    assert set(load_completed(ledger)) == {attempted[0]}
