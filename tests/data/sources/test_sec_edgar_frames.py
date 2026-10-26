from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from syrupy.assertion import SnapshotAssertion

from app.data.sources.sec_edgar import SecEdgarSource

CASSETTES = Path(__file__).parent / "cassettes" / "test_sec_edgar"
# Early XBRL (legacy CIKs, recovered opex and shares) and recent Q4 derivation.
WINDOWS = (
    (date(2008, 1, 1), date(2011, 12, 31)),
    (date(2019, 1, 1), date(2021, 12, 31)),
)


@pytest.mark.parametrize(
    ("ticker", "splits"),
    [
        pytest.param(
            "AMZN",
            pd.Series([20.0], index=pd.DatetimeIndex(["2022-06-06"])),
            marks=pytest.mark.vcr(
                str(CASSETTES / "test_fetch_financials_panel_has_financial_columns.yaml")
            ),
            id="AMZN",
        ),
        pytest.param(
            "GOOGL",
            pd.Series(
                [2.002_430_1, 20.0],
                index=pd.DatetimeIndex(["2014-03-27", "2022-07-18"]),
            ),
            marks=pytest.mark.vcr(
                str(
                    CASSETTES
                    / "test_fetch_financials_panel_has_financial_columns_for_googl.yaml"
                )
            ),
            id="GOOGL",
        ),
    ],
)
def test_each_cassette_keeps_its_quarterly_frames(
    sec_source: SecEdgarSource,
    snapshot: SnapshotAssertion,
    ticker: str,
    splits: pd.Series,
) -> None:
    frames = {
        f"{start.year}-{end.year}": sec_source.fetch_quarterly_financials(
            ticker, start, end, splits
        ).to_dict(orient="list")
        for start, end in WINDOWS
    }

    assert frames == snapshot
