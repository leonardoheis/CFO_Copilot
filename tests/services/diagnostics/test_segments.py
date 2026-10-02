import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.services.diagnostics import (
    SegmentProfiler,
    SegmentSettings,
    median_timeline,
    seasonal_profile,
    segment_frame,
)

QUARTERS = 20
COVID_QUARTERS = (8, 9)


def _panel(ticker: str, sector: str) -> pd.DataFrame:
    covid = np.zeros(QUARTERS, dtype=bool)
    covid[list(COVID_QUARTERS)] = True
    return pd.DataFrame({
        "ticker": ticker,
        "date": pd.date_range("2015-03-31", periods=QUARTERS, freq="QE"),
        "sector": sector,
        "covid": covid,
        "structural_break": False,
    })


@pytest.fixture
def panels() -> dict[str, pd.DataFrame]:
    return {"AAA": _panel("AAA", "Energy"), "BBB": _panel("BBB", "Technology")}


@pytest.fixture
def target_frame(panels: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.concat(
        [
            pd.DataFrame({
                "ticker": ticker,
                "date": panel["date"],
                "arm": "log_diff4",
                "horizon": 1,
                "y": rng.normal(size=QUARTERS),
            })
            for ticker, panel in panels.items()
        ],
        ignore_index=True,
    )


@pytest.fixture
def profiler() -> SegmentProfiler:
    return SegmentProfiler(settings=SegmentSettings())


def test_segment_frame_labels_sector_regime_and_period(
    panels: dict[str, pd.DataFrame],
    target_frame: pd.DataFrame,
) -> None:
    regimes = pd.Series({"AAA": 0, "BBB": 2})

    frame = segment_frame(target_frame, panels, regimes)

    aaa = frame[frame["ticker"] == "AAA"].reset_index(drop=True)
    assert set(aaa["sector"]) == {"Energy"}
    assert set(aaa["regime"]) == {0}
    assert aaa["period"].tolist() == (
        ["before_covid"] * 8 + ["covid"] * 2 + ["after_covid"] * 10
    )


def test_by_segment_has_one_row_per_segment_value(
    profiler: SegmentProfiler,
    panels: dict[str, pd.DataFrame],
    target_frame: pd.DataFrame,
) -> None:
    frame = segment_frame(target_frame, panels, pd.Series({"AAA": 0, "BBB": 2}))

    table = profiler.by_segment(frame, ["sector", "regime", "period"])

    assert " ".join(table.columns) == (
        "segment value companies observations median lower_quartile upper_quartile"
    )
    assert len(table) == 2 + 2 + 3
    energy = table[(table["segment"] == "sector") & (table["value"] == "Energy")]
    assert energy["median"].iloc[0] == pytest.approx(
        target_frame.loc[target_frame["ticker"] == "AAA", "y"].median()
    )


def test_seasonal_profile_has_four_quarters_per_regime(
    panels: dict[str, pd.DataFrame],
    target_frame: pd.DataFrame,
) -> None:
    frame = segment_frame(target_frame, panels, pd.Series({"AAA": 0, "BBB": 2}))

    profile = seasonal_profile(frame)

    assert list(profile.columns) == ["regime", "target_quarter", "mean_y"]
    assert profile.groupby("regime").size().to_dict() == {0: 4, 2: 4}


def test_timeline_marks_covid_and_break_quarters(
    panels: dict[str, pd.DataFrame],
    target_frame: pd.DataFrame,
) -> None:
    panels["AAA"].loc[12, "structural_break"] = True
    frame = segment_frame(target_frame, panels, pd.Series({"AAA": 0, "BBB": 2}))

    timeline = median_timeline(frame)

    assert list(timeline.columns) == ["date", "median_y", "covid", "breaks"]
    assert len(timeline) == QUARTERS
    assert timeline["covid"].sum() == len(COVID_QUARTERS)
    assert timeline.loc[12, "breaks"] == 1


def test_settings_refuse_an_inverted_spread() -> None:
    with pytest.raises(ValidationError):
        SegmentSettings(spread_quantiles=(0.75, 0.25))


def test_segment_values_are_labels_of_one_type(
    profiler: SegmentProfiler,
    panels: dict[str, pd.DataFrame],
    target_frame: pd.DataFrame,
) -> None:
    frame = segment_frame(target_frame, panels, pd.Series({"AAA": 0, "BBB": 2}))

    table = profiler.by_segment(frame, ["sector", "regime"])

    # W&B tables refuse a column mixing strings and numbers.
    assert {type(value) for value in table["value"]} == {str}
