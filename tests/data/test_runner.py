from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner

from app.data.progress import Progress
from app.data.runner import ingest_data

EXPECTED_ROWS = 2


def _panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date(2024, 3, 31), date(2024, 6, 30)],
            "revenue_usd_m": [1.0, 2.0],
        },
    )


def test_progress_reports_each_stage(capsys: pytest.CaptureFixture[str]) -> None:
    progress = Progress("INTC", enabled=True)
    with progress.stage("SEC concepts"):
        pass
    captured = capsys.readouterr().out

    assert "INTC" in captured
    assert "SEC concepts" in captured


def test_progress_stays_silent_when_disabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    progress = Progress("INTC", enabled=False)
    with progress.stage("SEC concepts"):
        pass

    assert not capsys.readouterr().out


def test_progress_reports_a_stage_detail(capsys: pytest.CaptureFixture[str]) -> None:
    progress = Progress("INTC", enabled=True)
    with progress.stage("Alpha Vantage fallback") as stage:
        stage.detail("filling 43 gaps")
    captured = capsys.readouterr().out

    assert "filling 43 gaps" in captured


def test_ingest_writes_the_panel_and_reports_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "INTC_panel.parquet"
    monkeypatch.setattr("app.data.runner.merge_panel", lambda **_: _panel())

    result = CliRunner().invoke(
        ingest_data,
        ["--ticker", "INTC", "--output", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert f"Wrote {EXPECTED_ROWS} quarterly rows" in result.output
    assert output.exists()


def test_quiet_suppresses_stage_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "INTC_panel.parquet"
    monkeypatch.setattr("app.data.runner.merge_panel", lambda **_: _panel())

    result = CliRunner().invoke(
        ingest_data,
        ["--ticker", "INTC", "--output", str(output), "--quiet"],
    )

    assert result.exit_code == 0, result.output
    assert "Wrote" in result.output
    assert "resolving" not in result.output
