import pytest
from pydantic import ValidationError

from app.data.schema import (
    FINANCIAL_COLUMNS,
    FinancialQuarterValues,
    FinancialsRow,
)


def test_financials_row_field_order_matches_panel_columns() -> None:
    """`model_dump()` is fed straight to pandas, so field order is the contract."""
    assert list(FinancialsRow.model_fields) == [
        "date",
        *FINANCIAL_COLUMNS,
        "shares_outstanding",
    ]


def test_accumulator_fields_are_all_optional_and_default_to_none() -> None:
    values = FinancialQuarterValues()

    assert all(value is None for value in values.model_dump().values())


def test_accumulator_rejects_an_unknown_field() -> None:
    """`extra="forbid"` turns a mistyped field name into an error, not a lost write."""
    with pytest.raises(ValidationError):
        FinancialQuarterValues(revenu_usd_m=1.0)  # type: ignore[call-arg]
