"""The us-gaap tag chains this project reads from SEC EDGAR.

Each panel field maps to an ordered list of tags: filers do not all use the same
tag for the same concept, and a single filer changes tags over time, so the
chain is tried in order and the first tag with data wins.
"""

from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

USD_UNIT: Final = "USD"
PER_SHARE_UNIT: Final = "USD/shares"
SHARES_UNIT: Final = "shares"


class ConceptSpec(BaseModel):
    """An ordered set of us-gaap tags reported under a single XBRL unit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tags: tuple[str, ...]
    unit: str = USD_UNIT

    @field_validator("tags")
    @classmethod
    def reject_empty_tags(cls, tags: tuple[str, ...]) -> tuple[str, ...]:
        """Guard against a tag chain that could never resolve a value.

        Returns:
            The validated tag tuple.

        Raises:
            ValueError: If the chain is empty or contains a blank tag.
        """
        if not tags or any(not tag for tag in tags):
            msg = "tags must contain at least one non-empty us-gaap tag"
            raise ValueError(msg)
        return tags


TAG_CHAINS: Final[dict[str, ConceptSpec]] = {
    "revenue": ConceptSpec(
        tags=(
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
            "Revenues",
        ),
    ),
    "cogs": ConceptSpec(tags=("CostOfGoodsAndServicesSold", "CostOfRevenue")),
    "costs_and_expenses": ConceptSpec(tags=("CostsAndExpenses",)),
    "operating_income": ConceptSpec(tags=("OperatingIncomeLoss",)),
    "net_income": ConceptSpec(tags=("NetIncomeLoss",)),
    "dep_amort": ConceptSpec(
        tags=(
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "Depreciation",
        ),
    ),
    "operating_cash_flow": ConceptSpec(
        tags=(
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        ),
    ),
    "capex": ConceptSpec(
        tags=(
            "PaymentsToAcquireProductiveAssets",
            "PaymentsToAcquirePropertyPlantAndEquipment",
        ),
    ),
    "eps": ConceptSpec(
        tags=("EarningsPerShareDiluted", "EarningsPerShareBasic"),
        unit=PER_SHARE_UNIT,
    ),
    "shares_outstanding": ConceptSpec(
        tags=("CommonStockSharesOutstanding",),
        unit=SHARES_UNIT,
    ),
}

DILUTED_SHARES_FALLBACK: Final = ConceptSpec(
    tags=("WeightedAverageNumberOfDilutedSharesOutstanding",),
    unit=SHARES_UNIT,
)
