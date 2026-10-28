"""The us-gaap tag chains this project reads from SEC EDGAR.

Each panel field maps to an ordered list of tags: filers do not all use the same
tag for the same concept, and a single filer changes tags over time, so the
chain is tried in order and the first tag with data wins.
"""

from datetime import date
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

USD_UNIT: Final = "USD"
PER_SHARE_UNIT: Final = "USD/shares"
SHARES_UNIT: Final = "shares"
# Filers' XBRL facts are typically empty before this date.
XBRL_HISTORY_START: Final = date(2008, 4, 1)


class ConceptSpec(BaseModel):
    """An ordered set of us-gaap tags reported under a single XBRL unit.

    ``prefer_largest`` suits a total whose narrower tags report components of
    it; leave it off where a later tag may legitimately be larger, as basic EPS
    is over diluted. ``never_negative`` marks a cost that a filer can only get
    wrong in sign (CAT 2008-Q2, BA 2009-Q4), so its magnitude is used.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tags: tuple[str, ...]
    unit: str = USD_UNIT
    prefer_largest: bool = False
    never_negative: bool = False

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
            "SalesRevenueGoodsNet",
            "Revenues",
            # Utilities' total; never RevenueFromContractWithCustomerIncluding-
            # AssessedTax, whose restated vintages outgrow Revenues at SO and GE.
            "RegulatedAndUnregulatedOperatingRevenue",
        ),
        prefer_largest=True,
    ),
    "cogs": ConceptSpec(
        tags=(
            "CostOfGoodsAndServicesSold",
            "CostOfGoodsSold",
            "CostOfRevenue",
        ),
        prefer_largest=True,
        never_negative=True,
    ),
    "costs_and_expenses": ConceptSpec(tags=("CostsAndExpenses",)),
    "operating_income": ConceptSpec(tags=("OperatingIncomeLoss",)),
    "net_income": ConceptSpec(tags=("NetIncomeLoss",)),
    "dep_amort": ConceptSpec(
        tags=(
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
            "DepreciationAmortizationAndOther",
            "OtherDepreciationAndAmortization",
        ),
        prefer_largest=True,
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
        prefer_largest=True,
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


class CostOfRevenueParts(BaseModel):
    """The chains parsing sums into a cost of revenue where no total is filed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total: ConceptSpec
    products: ConceptSpec
    services: ConceptSpec


class DepreciationAndAmortizationParts(BaseModel):
    """The chains parsing sums into D&A where no total is filed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    depreciation: ConceptSpec
    amortization: ConceptSpec


# SLB, VZ and GE file products and services apart with no combined total.
COST_OF_REVENUE_PARTS: Final = CostOfRevenueParts(
    total=ConceptSpec(
        tags=("CostOfGoodsAndServicesSold", "CostOfRevenue"),
        prefer_largest=True,
        never_negative=True,
    ),
    products=ConceptSpec(tags=("CostOfGoodsSold",), never_negative=True),
    services=ConceptSpec(tags=("CostOfServices",), never_negative=True),
)
# ABT, IBM, ORCL and others file these two apart with no total.
D_AND_A_PARTS: Final = DepreciationAndAmortizationParts(
    depreciation=ConceptSpec(tags=("Depreciation",)),
    amortization=ConceptSpec(tags=("AmortizationOfIntangibleAssets",)),
)
