import pytest
from pydantic import ValidationError
from syrupy.assertion import SnapshotAssertion

from app.data.schema import (
    COMPANY_VALUE_COLUMNS,
    COST_OF_REVENUE_COLUMNS,
    DERIVED_COLUMNS,
    FINANCIAL_COLUMNS,
    MACRO_COLUMNS,
    MARKET_COLUMNS,
    METADATA_COLUMNS,
    PANEL_COLUMNS,
    PROVENANCE_COLUMNS,
    FinancialQuarterValues,
    FinancialsRow,
)


def test_accumulator_fields_are_all_financials_row_fields() -> None:
    assert set(FinancialQuarterValues.model_fields) <= set(FinancialsRow.model_fields)


def test_every_column_declaration_keeps_its_names_in_order(
    snapshot: SnapshotAssertion,
) -> None:
    assert {
        "METADATA_COLUMNS": METADATA_COLUMNS,
        "FINANCIAL_COLUMNS": FINANCIAL_COLUMNS,
        "COST_OF_REVENUE_COLUMNS": COST_OF_REVENUE_COLUMNS,
        "PROVENANCE_COLUMNS": PROVENANCE_COLUMNS,
        "MARKET_COLUMNS": MARKET_COLUMNS,
        "DERIVED_COLUMNS": DERIVED_COLUMNS,
        "MACRO_COLUMNS": MACRO_COLUMNS,
        "COMPANY_VALUE_COLUMNS": COMPANY_VALUE_COLUMNS,
        "PANEL_COLUMNS": PANEL_COLUMNS,
        "FinancialsRow": tuple(FinancialsRow.model_fields),
        "FinancialQuarterValues": tuple(FinancialQuarterValues.model_fields),
    } == snapshot


def test_accumulator_fields_are_all_optional_and_default_to_none() -> None:
    values = FinancialQuarterValues()

    assert all(value is None for value in values.model_dump().values())


def test_accumulator_rejects_an_unknown_field() -> None:
    """`extra="forbid"` turns a mistyped field name into an error, not a lost write."""
    with pytest.raises(ValidationError):
        FinancialQuarterValues(revenu_usd_m=1.0)  # type: ignore[call-arg]
