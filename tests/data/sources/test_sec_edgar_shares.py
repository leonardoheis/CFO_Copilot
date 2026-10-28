"""Share-count paths of `SecEdgarSource`, which have their own failure modes.

See `docs/specs/shares-outstanding-defects.md`.
"""

from datetime import date
from typing import cast

import pytest

from app.data.sources.sec_edgar import SecEdgarSource
from app.data.sources.sec_edgar.xbrl import XbrlFact
from tests.data.conftest import ConceptServer


def test_diluted_shares_fallback_weights_a_fiscal_q4_average(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """Subtracting two weighted averages raw gave PG a negative share count."""
    quarter = date(2026, 6, 30)

    serve_concepts({
        "WeightedAverageNumberOfDilutedSharesOutstanding": [
            XbrlFact(
                start="2025-07-01", end="2026-03-31", val=2_425.8e6, filed="2026-04-20"
            ),
            XbrlFact(
                start="2025-07-01", end="2026-06-30", val=2_422.5e6, filed="2026-08-04"
            ),
        ]
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel.loc[0, "shares_outstanding"] == pytest.approx(2_412.6e6, rel=1e-6)


def test_non_positive_share_count_is_discarded(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    quarter = date(2026, 6, 30)

    # fetch_concept types every payload as a duration fact; the instant tags
    # are narrowed by their caller, exactly as the source itself does.
    serve_concepts({
        "CommonStockSharesOutstanding": cast(
            "list[XbrlFact]",
            [{"end": "2026-06-30", "val": -3.3e6, "filed": "2026-08-04"}],
        )
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel["shares_outstanding"].isna().all()


def test_share_count_tagged_at_the_wrong_scale_is_discarded(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """TXN tagged its 2009-Q3 diluted count as 1,268 rather than 1,268 million."""

    serve_concepts({
        "WeightedAverageNumberOfDilutedSharesOutstanding": [
            XbrlFact(
                start="2009-04-01", end="2009-06-30", val=1_272e6, filed="2009-07-29"
            ),
            XbrlFact(
                start="2009-07-01", end="2009-09-30", val=1_268, filed="2010-11-04"
            ),
            XbrlFact(
                start="2009-10-01", end="2009-12-31", val=1_265e6, filed="2010-02-20"
            ),
        ]
    })

    panel = sec_source.fetch_financials_panel(
        "AMZN", date(2009, 6, 30), date(2009, 12, 31)
    )

    assert panel["shares_outstanding"].isna().tolist() == [False, True, False]


def test_implied_shares_from_inconsistent_eps_are_discarded(
    sec_source: SecEdgarSource,
    serve_concepts: ConceptServer,
) -> None:
    """A split-restated EPS can disagree in sign with net income, as GIS 2009 did."""
    quarter = date(2009, 6, 30)

    serve_concepts({
        "NetIncomeLoss": [
            XbrlFact(
                start="2009-04-01",
                end="2009-06-30",
                val=358.8e6,
                filed="2009-08-01",
            ),
        ],
        "EarningsPerShareDiluted": [
            XbrlFact(
                start="2009-04-01", end="2009-06-30", val=-0.83, filed="2009-08-01"
            ),
        ],
    })

    panel = sec_source.fetch_financials_panel("AMZN", quarter, quarter)

    assert panel["shares_outstanding"].isna().all()
