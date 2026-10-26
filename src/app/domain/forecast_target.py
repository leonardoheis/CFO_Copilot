from enum import StrEnum
from typing import Final


class TargetVariable(StrEnum):
    """The variables NB01 can forecast; values are the panel's column names."""

    REVENUE = "revenue_usd_m"
    GROSS_PROFIT = "gross_profit_usd_m"
    OPEX = "opex_usd_m"
    OPERATING_INCOME = "operating_income_usd_m"
    EBITDA = "ebitda_usd_m"
    FREE_CASH_FLOW = "free_cash_flow_usd_m"


# The forecast targets of master plan § 3.3; NB01 and NB01b run once for each.
TARGET_VARIABLES: Final = (
    TargetVariable.REVENUE,
    TargetVariable.OPERATING_INCOME,
    TargetVariable.EBITDA,
    TargetVariable.FREE_CASH_FLOW,
)
