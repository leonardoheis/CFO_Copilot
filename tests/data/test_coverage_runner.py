import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from app.data import coverage_runner
from app.data.coverage import CoverageReport
from app.data.coverage_runner import ProbeContext, probe_alpha_vantage, run_probe
from app.data.exceptions import DataSourceUnavailableError

START = date(2020, 3, 31)
END = date(2024, 3, 31)


def _report(ticker: str, *, passed: bool) -> CoverageReport:
    return CoverageReport(
        ticker=ticker,
        oldest_alpha_quarter=None,
        newest_alpha_quarter=None,
        pre_xbrl={},
        handoff_missing_dates=(),
        overlap_max_relative_error={},
        gates={},
        passed=passed,
    )


@pytest.fixture
def probed_tickers(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    probed: list[str] = []
    monkeypatch.setattr(
        coverage_runner,
        "_build_probe_context",
        lambda start, end, *, refresh: SimpleNamespace(
            start=start, end=end, refresh=refresh
        ),
    )

    def fake_probe(ticker: str, _: object) -> CoverageReport:
        probed.append(ticker)
        if ticker == "DOWN":
            message = "quota exceeded"
            raise DataSourceUnavailableError(message)
        return _report(ticker, passed=ticker != "BAD")

    monkeypatch.setattr(coverage_runner, "_probe_ticker", fake_probe)
    return probed


def test_default_start_is_twenty_years_before_end() -> None:
    assert coverage_runner._default_start(END) == date(2004, 3, 31)  # ruff: ignore[private-member-access]


def test_probe_writes_a_report_per_ticker(
    tmp_path: Path,
    probed_tickers: list[str],
) -> None:
    output = tmp_path / "nested" / "report.json"

    result = CliRunner().invoke(
        probe_alpha_vantage,
        [
            "--ticker", "amzn",
            "--ticker", "BAD",
            "--start", "2020-03-31",
            "--end", "2024-03-31",
            "--output", str(output),
        ],
    )  # fmt: skip

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result.exit_code == 0, result.output
    assert probed_tickers == ["AMZN", "BAD"]
    assert "AMZN: PASS" in result.output
    assert "BAD: FAIL" in result.output
    assert written["start"] == START.isoformat()
    assert written["end"] == END.isoformat()
    assert [report["passed"] for report in written["reports"]] == [True, False]


def test_probe_records_a_data_source_error_and_continues(
    tmp_path: Path,
    probed_tickers: list[str],
) -> None:
    output = tmp_path / "report.json"

    result = CliRunner().invoke(
        probe_alpha_vantage,
        ["--ticker", "DOWN", "--ticker", "AMZN", "--output", str(output)],
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result.exit_code == 0, result.output
    assert probed_tickers == ["DOWN", "AMZN"]
    assert "DOWN: FAIL (quota exceeded)" in result.output
    assert written["reports"][0] == {
        "ticker": "DOWN",
        "passed": False,
        "error": "quota exceeded",
    }
    assert written["reports"][1]["ticker"] == "AMZN"


def test_probe_defaults_the_range_to_twenty_years_ending_last_quarter(
    tmp_path: Path,
    probed_tickers: list[str],  # ruff: ignore[unused-function-argument]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(coverage_runner, "most_recent_completed_quarter", lambda _: END)
    output = tmp_path / "report.json"

    CliRunner().invoke(
        probe_alpha_vantage,
        ["--ticker", "AMZN", "--output", str(output)],
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["end"] == END.isoformat()
    assert written["start"] == "2004-03-31"


def test_build_probe_context_wires_sources_from_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = MagicMock()
    alpha_vantage = MagicMock()
    monkeypatch.setattr(coverage_runner, "configure_container", lambda: container)
    monkeypatch.setattr(coverage_runner, "AlphaVantageSource", alpha_vantage)

    context = coverage_runner._build_probe_context(  # ruff: ignore[private-member-access]
        START, END, refresh=True
    )

    assert context.sec_source is container.sec_edgar_source.return_value
    assert context.market_source is container.yfinance_source.return_value
    assert context.client is alpha_vantage.return_value
    assert alpha_vantage.call_args.kwargs["refresh"] is True


def test_probe_ticker_evaluates_alpha_against_sec_over_the_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = ProbeContext(
        start=START,
        end=END,
        client=MagicMock(),
        sec_source=MagicMock(),
        market_source=MagicMock(),
    )
    evaluate = MagicMock(return_value=_report("AMZN", passed=True))
    monkeypatch.setattr(coverage_runner, "evaluate_coverage", evaluate)

    report = coverage_runner._probe_ticker("AMZN", context)  # ruff: ignore[private-member-access]

    assert report.passed is True
    context.client.fetch_financials_panel.assert_called_once_with("AMZN", START, END)
    sec_args = context.sec_source.fetch_financials_panel.call_args.args
    assert sec_args[3] is context.market_source.fetch_splits.return_value
    assert evaluate.call_args.args[0] == "AMZN"


def test_run_probe_drops_a_leading_double_dash(
    tmp_path: Path,
    probed_tickers: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        ["probe", "--", "--ticker", "AMZN", "--output", str(output)],
    )

    with pytest.raises(SystemExit) as exit_info:
        run_probe()

    assert exit_info.value.code == 0
    assert probed_tickers == ["AMZN"]
    assert output.exists()
