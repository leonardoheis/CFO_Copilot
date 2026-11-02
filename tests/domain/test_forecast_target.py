from app.domain import TARGET_VARIABLES, TargetVariable


def test_the_forecast_targets_are_the_notebooks_four() -> None:
    assert TARGET_VARIABLES == (
        TargetVariable.REVENUE,
        TargetVariable.OPERATING_INCOME,
        TargetVariable.EBITDA,
        TargetVariable.FREE_CASH_FLOW,
    )
