from datetime import date

import pandas as pd

from app.data.schema import PROVENANCE_COLUMNS
from app.data.sources.sec_edgar.parsing import financial_panel_from_raw


def test_zero_revenue_quarter_yields_no_margins_instead_of_dividing() -> None:
    raw = pd.DataFrame(
        {
            "date": [date(2020, 3, 31)],
            "revenue": [0.0],
            "cogs": [5.0e6],
            "operating_income": [-5.0e6],
            "net_income": [-4.0e6],
            "costs_and_expenses": [5.0e6],
            "dep_amort": [1.0e6],
            "operating_cash_flow": [1.0e6],
            "capex": [0.5e6],
            "eps": [-0.1],
            "shares_outstanding": [40.0e6],
            **{column: [None] for column in PROVENANCE_COLUMNS},
        },
    )

    panel = financial_panel_from_raw(raw)

    assert panel[["gross_margin", "operating_margin", "net_margin"]].isna().all().all()
